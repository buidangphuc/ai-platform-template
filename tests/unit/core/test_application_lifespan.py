from collections.abc import Callable

import pytest
from fastapi import FastAPI
from loguru import logger
from pymongo.errors import InvalidOperation
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.bootstrap import (
    application as application_module,
    resources as resources_module,
)
from app.bootstrap.addons.llm import LlmAddon
from app.bootstrap.application import _build_lifespan, create_app
from app.bootstrap.features.registry import FEATURES
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.health import HealthService
from app.modules.ai.llm import langfuse as langfuse_module
from app.modules.platform.mongo.gateway import MongoGateway
from tests.infra import SqsQueue, require


def _bare_app() -> FastAPI:
    app = FastAPI()
    app.state.resources = ApplicationResources()
    app.state.in_flight_tracker = None
    app.state.health_service = HealthService(check_external_dependencies=False)
    return app


class _FakeLangfuseClient:
    def __init__(self) -> None:
        self.flushes = 0

    def flush(self) -> None:
        self.flushes += 1


async def test_lifespan_flushes_langfuse_through_the_llm_addon(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    client = _FakeLangfuseClient()
    monkeypatch.setattr(langfuse_module, "_build_langfuse_client", lambda s: client)
    settings = test_settings.model_copy(
        update={
            "LLM_ENABLED": True,
            "LANGFUSE_ENABLED": True,
            "LANGFUSE_PUBLIC_KEY": "lf-public",
            "LANGFUSE_SECRET_KEY": "lf-private",  # pragma: allowlist secret
        }
    )

    lifespan = _build_lifespan(
        settings,
        init_resources=True,
        addons=(LlmAddon(),),
        features=FEATURES,
    )

    async with lifespan(_bare_app()):
        assert client.flushes == 0

    assert client.flushes == 1
    assert not hasattr(application_module, "_flush_langfuse_client")


def _capture_logs() -> tuple[list[str], int]:
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(message.record["message"]))
    return messages, sink_id


async def test_lifespan_logs_redacted_settings_once(test_settings: Settings):
    settings = test_settings.model_copy(
        update={"REDIS_PASSWORD": "redis-secret-value"}  # pragma: allowlist secret
    )
    messages, sink_id = _capture_logs()
    try:
        lifespan = _build_lifespan(
            settings, init_resources=True, addons=(), features=FEATURES
        )
        async with lifespan(_bare_app()):
            pass
    finally:
        logger.remove(sink_id)

    lines = [message for message in messages if message.startswith("settings ")]
    assert len(lines) == 1
    assert "redis-secret-value" not in lines[0]
    assert "REDIS_PASSWORD" in lines[0]


async def test_lifespan_without_resources_does_not_log_settings(
    test_settings: Settings,
):
    messages, sink_id = _capture_logs()
    try:
        lifespan = _build_lifespan(
            test_settings, init_resources=False, addons=(), features=FEATURES
        )
        async with lifespan(_bare_app()):
            pass
    finally:
        logger.remove(sink_id)

    assert [m for m in messages if m.startswith("settings ")] == []


@pytest.fixture()
def aws_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")


async def _backend_pids(engine: AsyncEngine, pids: set[int]) -> set[int]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT pid FROM pg_stat_activity WHERE pid = ANY(:pids)"),
            {"pids": list(pids)},
        )
        return {row[0] for row in rows}


@pytest.mark.usefixtures("redis_client")
async def test_app_lifespan_owns_database_and_redis_resources(
    infra_settings: Callable[..., Settings],
    pg_url: str,
    pg_engine: AsyncEngine,
    redis_prefix: str,
):
    settings = infra_settings(
        DATABASE_ENABLED=True,
        REDIS_ENABLED=True,
        QUEUE_ENABLED=True,
        QUEUE_BACKEND="redis",
        QUEUE_NAME=f"{redis_prefix}:queue",
        TASKS_ENABLED=True,
        TASK_STORE_BACKEND="postgres",
    )
    app = create_app(settings=settings, init_resources=True)
    resources_before = app.state.resources

    assert resources_before.engine is None
    assert resources_before.sessionmaker is None
    assert resources_before.redis is None
    assert resources_before.queue_gateway is None
    assert resources_before.tasks is None

    async with app.router.lifespan_context(app):
        resources_open = app.state.resources
        assert resources_open.engine is not None
        assert resources_open.sessionmaker is not None
        assert resources_open.redis is not None
        assert resources_open.queue_gateway is not None
        assert resources_open.tasks is not None
        assert resources_open.tasks.queue is resources_open.queue_gateway

        readiness = await app.state.health_service.readiness()
        assert readiness.dependencies == {"api": "ok", "postgres": "ok", "redis": "ok"}

        async with resources_open.sessionmaker() as session:
            pid = (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        redis = resources_open.redis
        redis_client_id = await redis.client_id()
        assert await redis.client_id() == redis_client_id
        assert await _backend_pids(pg_engine, {pid}) == {pid}

    assert await _backend_pids(pg_engine, {pid}) == set()
    assert await redis.client_id() != redis_client_id
    await redis.aclose()
    resources_closed = app.state.resources
    assert resources_closed.engine is None
    assert resources_closed.redis is None
    assert resources_closed.queue_gateway is None
    assert resources_closed.tasks is None
    assert app.state.health_service is not None


@pytest.mark.usefixtures("aws_credentials")
async def test_app_lifespan_opens_and_closes_the_sqs_queue(
    infra_settings: Callable[..., Settings],
    sqs_queue: SqsQueue,
):
    settings = infra_settings(
        QUEUE_ENABLED=True,
        QUEUE_BACKEND="sqs",
        SQS_QUEUE_URL=sqs_queue.url,
        SQS_ENDPOINT_URL=sqs_queue.endpoint_url,
        SQS_REGION=sqs_queue.region,
    )
    app = create_app(settings=settings, init_resources=True)

    async with app.router.lifespan_context(app):
        queue = app.state.resources.queue_gateway
        assert queue is not None
        await queue.send({"ping": 1})
        (message,) = await queue.receive(max_messages=1, wait_seconds=1)
        assert message.body == {"ping": 1}

    assert app.state.resources.queue_gateway is None


@pytest.mark.usefixtures("aws_credentials")
async def test_app_lifespan_fails_startup_when_the_sqs_queue_is_missing(
    infra_settings: Callable[..., Settings],
    sqs_queue: SqsQueue,
):
    settings = infra_settings(
        QUEUE_ENABLED=True,
        QUEUE_BACKEND="sqs",
        SQS_QUEUE_URL=f"{sqs_queue.url}-missing",
        SQS_ENDPOINT_URL=sqs_queue.endpoint_url,
        SQS_REGION=sqs_queue.region,
    )
    app = create_app(settings=settings, init_resources=True)

    with pytest.raises(RuntimeError, match="not reachable"):
        async with app.router.lifespan_context(app):
            pytest.fail("lifespan must not start")


async def test_app_lifespan_owns_mongo_addon_resource(
    infra_settings: Callable[..., Settings],
    mongo_gateway: MongoGateway,
):
    settings = infra_settings(
        MONGO_ENABLED=True,
        MONGODB_URI=require("mongo"),
        MONGODB_DATABASE=mongo_gateway.database.name,
    )
    app = create_app(settings=settings, init_resources=True)

    async with app.router.lifespan_context(app):
        gateway = app.state.resources.mongo
        assert gateway is not None
        readiness = await app.state.health_service.readiness()
        assert readiness.dependencies["mongo"] == "ok"
        assert (await gateway.ping())["ok"] == 1

    assert app.state.resources.mongo is None
    with pytest.raises(InvalidOperation):
        await gateway.ping()


@pytest.mark.usefixtures("redis_client")
async def test_readiness_reports_unreachable_and_misconfigured_dependencies(
    infra_settings: Callable[..., Settings],
    pg_url: str,
    mongo_gateway: MongoGateway,
):
    cases = {
        "postgres": {"POSTGRES_PORT": 1},
        "redis": {"REDIS_PORT": 1},
        "mongo": {"MONGODB_URI": "mongodb://127.0.0.1:1"},
    }
    for name, override in cases.items():
        settings = infra_settings(
            DATABASE_ENABLED=name == "postgres",
            REDIS_ENABLED=name == "redis",
            MONGO_ENABLED=name == "mongo",
            MONGODB_DATABASE=mongo_gateway.database.name,
            MONGODB_SERVER_SELECTION_TIMEOUT_MS=300,
            HEALTH_CHECK_TIMEOUT_SECONDS=3,
            **override,
        )
        app = create_app(settings=settings, init_resources=True)

        async with app.router.lifespan_context(app):
            readiness = await app.state.health_service.readiness()

        assert readiness.status == "error", name
        assert readiness.dependencies[name] == "error", name


async def test_readiness_reports_a_postgres_password_rejected_by_the_server(
    infra_settings: Callable[..., Settings],
    pg_url: str,
):
    settings = infra_settings(DATABASE_ENABLED=True, POSTGRES_PASSWORD="wrong")
    app = create_app(settings=settings, init_resources=True)

    async with app.router.lifespan_context(app):
        readiness = await app.state.health_service.readiness()

    assert readiness.dependencies["postgres"] == "error"


@pytest.mark.usefixtures("redis_client")
async def test_readiness_reports_a_redis_password_rejected_by_the_server(
    infra_settings: Callable[..., Settings],
):
    settings = infra_settings(REDIS_ENABLED=True, REDIS_PASSWORD="wrong")
    app = create_app(settings=settings, init_resources=True)

    async with app.router.lifespan_context(app):
        readiness = await app.state.health_service.readiness()

    assert readiness.dependencies["redis"] == "error"


async def test_app_lifespan_honors_resource_flags(test_settings: Settings):
    settings = test_settings.model_copy(
        update={
            "DATABASE_ENABLED": False,
            "REDIS_ENABLED": False,
            "QUEUE_ENABLED": False,
            "TASKS_ENABLED": False,
        }
    )
    app = create_app(settings=settings, init_resources=True)

    async with app.router.lifespan_context(app):
        resources_open = app.state.resources
        assert resources_open.engine is None
        assert resources_open.sessionmaker is None
        assert resources_open.redis is None
        assert resources_open.queue_gateway is None
        assert resources_open.tasks is None
        assert resources_open.health_checks.checks == ()
        assert app.state.health_service is not None


async def test_app_lifespan_init_resources_false_opens_no_runtime_resources(
    test_settings: Settings,
):
    settings = test_settings.model_copy(
        update={"DATABASE_ENABLED": True, "REDIS_ENABLED": True}
    )
    app = create_app(settings=settings, init_resources=False)

    async with app.router.lifespan_context(app):
        resources_open = app.state.resources
        assert resources_open.engine is None
        assert resources_open.redis is None


def test_resource_lifecycle_uses_named_open_steps():
    for name in (
        "_open_database",
        "_open_redis",
        "_open_queue",
        "_open_tasks",
        "build_health_service",
    ):
        assert callable(getattr(resources_module, name))


@pytest.mark.usefixtures("redis_client")
async def test_openers_register_readiness_checks_with_the_configured_timeout(
    infra_settings: Callable[..., Settings],
    pg_url: str,
):
    settings = infra_settings(
        DATABASE_ENABLED=True,
        REDIS_ENABLED=True,
        QUEUE_ENABLED=False,
        TASKS_ENABLED=False,
        HEALTH_CHECK_TIMEOUT_SECONDS=0.75,
    )

    async with resources_module.open_application_resources(
        settings, init_resources=True
    ) as resources:
        service = resources_module.build_health_service(resources, init_resources=True)

        assert [name for name, _ in service.checks] == ["postgres", "redis"]
        assert service.check_timeout_seconds == 0.75


async def test_no_readiness_checks_for_resources_that_are_not_opened(
    test_settings: Settings,
):
    settings = test_settings.model_copy(
        update={"DATABASE_ENABLED": False, "REDIS_ENABLED": False}
    )

    async with resources_module.open_application_resources(
        settings, init_resources=True
    ) as resources:
        assert resources.health_checks.checks == ()
