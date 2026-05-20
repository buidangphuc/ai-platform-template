async def test_health_returns_api_status(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readiness_returns_dependency_statuses(client):
    response = await client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["dependencies"]["api"] == "ok"


async def test_api_prefix_health_returns_api_status(client):
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_api_prefix_readiness_returns_dependency_statuses(client):
    response = await client.get("/api/v1/ready")

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
        postgres_check=down,
        redis_check=up,
    )

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    assert response.json()["dependencies"]["postgres"] == "error"
