from app.bootstrap.application import create_app
from app.core.config import Settings


def test_app_wiring_bootstraps_basic_runtime_only(test_settings: Settings):
    app = create_app(settings=test_settings, init_resources=False)

    assert not hasattr(app.state, "adapters")
    assert not hasattr(app.state, "observability")
    assert not hasattr(app.state, "chat_model")
    assert not hasattr(app.state, "prompt_registry")
    assert not hasattr(app.state, "usage_tracker")
    assert not hasattr(app.state, "redaction_policy")
    assert not hasattr(app.state, "knowledge_service")
    assert not hasattr(app.state, "rag_eval_service")
    assert not hasattr(app.state, "agent_runner")
    assert not hasattr(app.state, "feedback_repository")
    assert not hasattr(app.state, "api_key_repository")
    assert app.state.health_service is not None
    assert app.state.rate_limiter is not None


def test_app_accepts_completion_handler_as_business_boundary(
    test_settings: Settings,
):
    handler = object()

    app = create_app(handler, settings=test_settings, init_resources=False)

    assert app.state.completion_handler is handler
