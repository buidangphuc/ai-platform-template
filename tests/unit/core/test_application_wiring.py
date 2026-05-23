from app.bootstrap import application as application_module
from app.bootstrap.application import create_app
from app.core.config import Settings


def test_completion_http_router_lives_in_api_layer():
    import importlib.util

    assert importlib.util.find_spec("app.api.v1.completions.router") is not None
    assert importlib.util.find_spec("app.modules.business.completions.router") is None


def test_auth_endpoint_is_not_registered(test_settings: Settings):
    app = create_app(settings=test_settings, init_resources=False)

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/v1/auth/me" not in paths


def test_app_wiring_bootstraps_basic_runtime_only(test_settings: Settings):
    app = create_app(settings=test_settings, init_resources=False)

    resources = app.state.resources
    assert resources.engine is None
    assert resources.sessionmaker is None
    assert resources.redis is None
    assert resources.queue_gateway is None
    assert resources.task_store is None
    assert resources.task_service is None
    assert resources.cache is None
    assert resources.objects is None
    assert resources.idempotency_store is None
    assert resources.outbox_store is None
    assert resources.principal_rate_limiter is None
    assert resources.ip_rate_limiter is None
    assert resources.webhook_signer is None
    assert app.state.health_service is not None


def test_app_accepts_completion_handler_as_business_boundary(
    test_settings: Settings,
):
    handler = object()

    app = create_app(
        completion_handler=handler,
        settings=test_settings,
        init_resources=False,
    )

    pipeline = app.state.resources.completion_pipeline
    assert pipeline is not None
    assert pipeline.handler is handler


def test_create_app_delegates_middleware_installation(
    monkeypatch,
    test_settings: Settings,
):
    calls = []

    def install_core_middlewares(app, settings):
        calls.append((app, settings))

    monkeypatch.setattr(
        application_module,
        "install_core_middlewares",
        install_core_middlewares,
    )

    app = create_app(settings=test_settings, init_resources=False)

    assert calls == [(app, test_settings)]
