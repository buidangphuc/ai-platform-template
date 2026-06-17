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
