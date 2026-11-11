from app.bootstrap.addons.base import default_resource_addons
from app.bootstrap.addons.llm import LlmAddon
from app.bootstrap.resources import ApplicationResources
from app.core.telemetry import FanOutSink, LogLlmSink
from app.modules.ai.llm.runtime import LLMInstance
from tests.factories import build_test_settings, open_addon


def test_llm_addon_is_disabled_by_default():
    assert LlmAddon().is_enabled(build_test_settings()) is False
    assert LlmAddon().is_enabled(build_test_settings(LLM_ENABLED=True)) is True


def test_resources_have_no_llm_by_default():
    assert ApplicationResources().llm is None


def test_llm_addon_is_registered_after_telemetry():
    names = [addon.name for addon in default_resource_addons()]

    assert names.index("llm") == names.index("telemetry") + 1


async def test_llm_addon_open_and_close():
    resources = ApplicationResources()

    stack = await open_addon(
        LlmAddon(), resources, build_test_settings(LLM_ENABLED=True)
    )

    assert isinstance(resources.llm, LLMInstance)
    await stack.aclose()


async def test_llm_addon_sink_is_log_only_without_telemetry():
    resources = ApplicationResources()

    await open_addon(LlmAddon(), resources, build_test_settings(LLM_ENABLED=True))

    assert resources.llm is not None
    sink = resources.llm.sink
    assert isinstance(sink, FanOutSink)
    assert [type(s) for s in sink.sinks] == [LogLlmSink]


async def test_llm_addon_sink_fans_out_to_telemetry():
    resources = ApplicationResources()
    telemetry = object()
    resources.telemetry = telemetry  # type: ignore[assignment]

    await open_addon(LlmAddon(), resources, build_test_settings(LLM_ENABLED=True))

    assert resources.llm is not None
    sink = resources.llm.sink
    assert isinstance(sink, FanOutSink)
    assert sink.sinks[1] is telemetry
