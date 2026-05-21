import sys
import types

import pytest

from app.bootstrap import application as application_module
from app.bootstrap.application import _build_lifespan, create_app
from app.core.config import Settings


class _FakeLangfuseClient:
    def __init__(self) -> None:
        self.flushed = False

    def flush(self) -> None:
        self.flushed = True


def _install_fake_langfuse(monkeypatch: pytest.MonkeyPatch) -> _FakeLangfuseClient:
    client = _FakeLangfuseClient()
    fake_module = types.ModuleType("langfuse")
    fake_module.get_client = lambda: client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", fake_module)
    return client


async def test_lifespan_flushes_langfuse_client_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    fake_client = _install_fake_langfuse(monkeypatch)
    settings = test_settings.model_copy(update={"LANGFUSE_ENABLED": True})

    lifespan = _build_lifespan(settings, init_resources=True)

    async with lifespan(None):  # type: ignore[arg-type]
        assert fake_client.flushed is False

    assert fake_client.flushed is True


async def test_lifespan_skips_flush_when_init_resources_is_false(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    flush_calls: list[str] = []

    def _should_not_be_called() -> None:
        flush_calls.append("called")

    monkeypatch.setattr(
        application_module,
        "_flush_langfuse_client",
        _should_not_be_called,
    )
    settings = test_settings.model_copy(update={"LANGFUSE_ENABLED": True})

    lifespan = _build_lifespan(settings, init_resources=False)

    async with lifespan(None):  # type: ignore[arg-type]
        pass

    assert flush_calls == []


async def test_lifespan_skips_flush_when_langfuse_disabled(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    flush_calls: list[str] = []

    monkeypatch.setattr(
        application_module,
        "_flush_langfuse_client",
        lambda: flush_calls.append("called"),
    )

    lifespan = _build_lifespan(test_settings, init_resources=True)

    async with lifespan(None):  # type: ignore[arg-type]
        pass

    assert flush_calls == []


async def test_lifespan_flush_tolerates_missing_langfuse_package(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    monkeypatch.setitem(sys.modules, "langfuse", None)
    settings = test_settings.model_copy(update={"LANGFUSE_ENABLED": True})

    lifespan = _build_lifespan(settings, init_resources=True)

    async with lifespan(None):  # type: ignore[arg-type]
        pass


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


class _FakeRedis:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


async def test_app_lifespan_owns_database_and_redis_resources(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
):
    engine = _FakeEngine()
    redis = _FakeRedis()
    sessionmaker = object()

    monkeypatch.setattr(
        application_module,
        "build_engine",
        lambda settings: engine,
        raising=False,
    )
    monkeypatch.setattr(
        application_module,
        "build_sessionmaker",
        lambda received_engine: sessionmaker,
        raising=False,
    )
    monkeypatch.setattr(
        application_module,
        "build_redis_client",
        lambda settings: redis,
        raising=False,
    )

    app = create_app(settings=test_settings, init_resources=True)

    assert app.state.engine is engine
    assert app.state.sessionmaker is sessionmaker
    assert app.state.redis is redis

    async with app.router.lifespan_context(app):
        assert engine.disposed is False
        assert redis.closed is False

    assert engine.disposed is True
    assert redis.closed is True
