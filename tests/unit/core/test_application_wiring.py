from app.bootstrap import application as application_module
from app.bootstrap.application import create_app
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.business.completions.handlers.echo import EchoCompletionHandler


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
    assert resources.tasks is None
    assert resources.cache is None
    assert resources.objects is None
    assert resources.idempotency_store is None
    assert resources.outbox_store is None
    assert resources.principal_rate_limiter is None
    assert resources.ip_rate_limiter is None
    assert resources.webhook_signer is None
    assert app.state.health_service is not None


async def test_lifespan_composes_completion_service_from_handler_factory(
    test_settings: Settings,
):
    handler = EchoCompletionHandler()
    seen: list[ApplicationResources] = []

    def factory(resources: ApplicationResources, settings: Settings):
        seen.append(resources)
        return handler

    app = create_app(
        completion_handler_factory=factory,
        settings=test_settings,
        init_resources=False,
    )

    async with app.router.lifespan_context(app):
        resources = app.state.resources
        assert seen == [resources]
        assert resources.completion_service.handler is handler


def test_task_routes_mount_only_when_tasks_enabled(test_settings: Settings):
    disabled = create_app(settings=test_settings, init_resources=False)
    enabled = create_app(
        settings=test_settings.model_copy(
            update={"QUEUE_ENABLED": True, "TASKS_ENABLED": True}
        ),
        init_resources=False,
    )

    def paths(app):
        return {getattr(route, "path", "") for route in app.routes}

    assert "/api/v1/completions/tasks" not in paths(disabled)
    assert "/api/v1/completions/tasks" in paths(enabled)


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
