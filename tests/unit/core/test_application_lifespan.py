import sys
import types

import pytest

from app.bootstrap import application as application_module
from app.bootstrap.application import _build_lifespan
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
