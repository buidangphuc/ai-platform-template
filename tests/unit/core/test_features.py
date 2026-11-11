import sys
from dataclasses import replace

import pytest
from fastapi import APIRouter, Request

from app.bootstrap.application import create_app
from app.bootstrap.features.base import Feature, import_models
from app.bootstrap.features.completions import completions_feature
from app.bootstrap.features.registry import FEATURES
from app.bootstrap.resources import ApplicationResources
from app.bootstrap.state import get_app_resources
from app.bootstrap.worker import worker_context
from app.core.config import Settings
from app.core.database.model import Base
from app.core.errors import ServiceUnavailableError
from app.modules.business.completions.service import CompletionService
from app.modules.messaging.queue.worker import NonRetryableMessageError
from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.store import TaskRecord
from tests.factories import api_client_for, build_test_settings

URL = "/api/v1/completions"
HEADERS = {"Authorization": "Bearer test-token"}


class PingService:
    def __init__(self, word: str) -> None:
        self.word = word

    def say(self) -> str:
        return f"{self.word}-pong"


ping_router = APIRouter(prefix="/ping", tags=["ping"])
ping_task_router = APIRouter(prefix="/ping", tags=["ping"])


@ping_router.get("")
async def ping(request: Request) -> dict[str, str]:
    return {"say": get_app_resources(request.app).service(PingService).say()}


@ping_task_router.post("/tasks")
async def ping_task() -> dict[str, str]:
    return {}


async def _ping_task(resources: ApplicationResources, task: TaskRecord) -> dict:
    return {"say": resources.service(PingService).say(), "echo": task.payload["word"]}


def ping_feature(**overrides: object) -> Feature:
    feature = Feature(
        name="ping",
        service=PingService,
        build=lambda resources, settings: PingService("ping"),
        routers=(ping_router,),
        task_routers=(ping_task_router,),
        tasks={"ping": _ping_task},
    )
    return replace(feature, **overrides)


def _worker_settings() -> Settings:
    return build_test_settings(
        QUEUE_ENABLED=True,
        TASKS_ENABLED=True,
        QUEUE_BACKEND="memory",
        TASK_STORE_BACKEND="memory",
    )


def _paths(app) -> set[str]:
    return {getattr(route, "path", "") for route in app.routes}


def test_default_registry_holds_completions_and_conversations():
    assert [feature.name for feature in FEATURES] == ["completions", "conversations"]
    assert FEATURES[0].service is CompletionService


async def test_second_feature_route_service_and_task_need_no_shared_edits(
    test_settings: Settings,
):
    features = (completions_feature(), ping_feature())
    app = create_app(settings=test_settings, init_resources=False, features=features)

    async with api_client_for(app) as client:
        resources = get_app_resources(app)
        assert resources.service(PingService).word == "ping"
        assert isinstance(resources.service(CompletionService), CompletionService)
        response = await client.get("/api/v1/ping")
        assert response.json() == {"say": "ping-pong"}
        completion = await client.post(
            URL,
            headers=HEADERS,
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert completion.status_code == 200

    async with worker_context(_worker_settings(), features=features) as ctx:
        task = await ctx.tasks.service.submit(
            type="ping", payload={"word": "w"}, principal_id="alice"
        )
        [message] = await ctx.tasks.queue.receive(max_messages=1)
        await ctx.worker.handler(message)
        done = await ctx.tasks.service.require(task.id)

    assert done.status == TaskStatus.COMPLETED
    assert done.result == {"say": "ping-pong", "echo": "w"}


async def test_disabled_feature_is_not_built_mounted_or_resolvable(
    test_settings: Settings,
):
    built: list[str] = []

    def build(resources, settings):
        built.append("ping")
        return PingService("ping")

    feature = ping_feature(build=build, enabled=lambda settings: False)
    app = create_app(settings=test_settings, init_resources=False, features=(feature,))

    async with api_client_for(app) as client:
        assert (await client.get("/api/v1/ping")).status_code == 404
        with pytest.raises(ServiceUnavailableError):
            get_app_resources(app).service(PingService)

    assert built == []
    assert "/api/v1/ping" not in _paths(app)


def test_task_routers_follow_tasks_enabled(test_settings: Settings):
    features = (ping_feature(),)
    disabled = create_app(
        settings=test_settings, init_resources=False, features=features
    )
    enabled = create_app(
        settings=test_settings.model_copy(
            update={"QUEUE_ENABLED": True, "TASKS_ENABLED": True}
        ),
        init_resources=False,
        features=features,
    )

    assert "/api/v1/ping" in _paths(disabled)
    assert "/api/v1/ping/tasks" not in _paths(disabled)
    assert "/api/v1/ping/tasks" in _paths(enabled)


async def test_duplicate_task_type_fails_at_startup(test_settings: Settings):
    class _Other:
        pass

    first = ping_feature()
    second = ping_feature(name="pong", service=_Other, build=lambda r, s: _Other())
    app = create_app(
        settings=test_settings, init_resources=False, features=(first, second)
    )

    with pytest.raises(ValueError, match=r"'ping'.*'ping'.*'pong'"):
        async with app.router.lifespan_context(app):
            pass


async def test_duplicate_service_type_fails_at_startup(test_settings: Settings):
    first = ping_feature()
    second = ping_feature(name="pong", tasks={"pong": _ping_task})
    app = create_app(
        settings=test_settings, init_resources=False, features=(first, second)
    )

    with pytest.raises(ValueError, match=r"PingService.*'ping'.*'pong'"):
        async with app.router.lifespan_context(app):
            pass


async def test_duplicate_check_ignores_disabled_features(test_settings: Settings):
    first = ping_feature()
    second = ping_feature(name="pong", enabled=lambda settings: False)
    app = create_app(
        settings=test_settings, init_resources=False, features=(first, second)
    )

    async with app.router.lifespan_context(app):
        assert get_app_resources(app).service(PingService).word == "ping"


async def test_worker_fails_a_task_of_unknown_type_without_retry():
    async with worker_context(_worker_settings(), features=(ping_feature(),)) as ctx:
        task = await ctx.tasks.service.submit(
            type="nope", payload={}, principal_id="alice"
        )
        [message] = await ctx.tasks.queue.receive(max_messages=1)

        with pytest.raises(NonRetryableMessageError):
            await ctx.worker.handler(message)

        failed = await ctx.tasks.service.require(task.id)

    assert failed.status == TaskStatus.FAILED
    assert failed.error is not None and "nope" not in failed.error


def test_feature_models_appear_in_base_metadata(tmp_path, monkeypatch):
    module = tmp_path / "feature_models_probe.py"
    module.write_text(
        "from sqlalchemy import Column, Integer, Table\n"
        "from app.core.database.model import Base\n"
        "probe = Table('feature_models_probe', Base.metadata,"
        " Column('id', Integer, primary_key=True))\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    feature = ping_feature(models=("feature_models_probe",))

    try:
        import_models((feature,))
        assert "feature_models_probe" in Base.metadata.tables
    finally:
        probe = Base.metadata.tables.get("feature_models_probe")
        if probe is not None:
            Base.metadata.remove(probe)
        sys.modules.pop("feature_models_probe", None)
