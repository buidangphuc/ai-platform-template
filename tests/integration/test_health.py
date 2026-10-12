import pytest


@pytest.mark.parametrize("path", ["/healthz", "/api/v1/healthz"])
async def test_liveness_always_returns_ok(client, path):
    response = await client.get(path)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/readyz", "/api/v1/readyz"])
async def test_readiness_returns_dependency_statuses(client, path):
    response = await client.get(path)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["dependencies"]["api"] == "ok"


async def test_readiness_returns_503_when_dependency_is_down(client):
    from app.core.health import HealthService

    async def down() -> None:
        raise RuntimeError("down")

    async def up() -> None:
        return None

    client._transport.app.state.health_service = HealthService(
        check_external_dependencies=True,
        checks=(("postgres", down), ("redis", up)),
    )

    response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    assert response.json()["dependencies"]["postgres"] == "error"


async def test_liveness_does_not_depend_on_health_service(client):
    # Liveness must stay 200 even if dependencies (and the service) are broken.
    client._transport.app.state.health_service = None

    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_is_503_while_draining_and_liveness_stays_ok():
    import asyncio

    from httpx import ASGITransport, AsyncClient

    from app.bootstrap.application import create_app
    from tests.factories import build_test_settings

    app = create_app(
        settings=build_test_settings(
            GRACEFUL_SHUTDOWN_ENABLED=True, GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS=5
        ),
        init_resources=False,
    )
    lifespan = app.router.lifespan_context(app)
    await lifespan.__aenter__()
    app.state.in_flight_tracker.acquire()  # a request that outlives shutdown start
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/readyz")).status_code == 200

        shutdown = asyncio.create_task(lifespan.__aexit__(None, None, None))
        await asyncio.sleep(0.1)  # shutdown is now waiting on the in-flight request

        readiness = await client.get("/readyz")
        liveness = await client.get("/healthz")
        app.state.in_flight_tracker.release()
        await shutdown

    assert readiness.status_code == 503
    assert readiness.json()["status"] == "draining"
    assert liveness.status_code == 200
