BOOTSTRAP_HEADERS = {"X-Bootstrap-Token": "test-bootstrap-token"}


def configure_bootstrap_token(client):
    client._transport.app.state.settings.API_KEY_BOOTSTRAP_TOKEN = (
        "test-bootstrap-token"
    )


async def test_create_api_key_returns_secret_once(client):
    configure_bootstrap_token(client)

    response = await client.post(
        "/api/v1/auth/api-keys",
        headers=BOOTSTRAP_HEADERS,
        json={"name": "local-test"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "local-test"
    assert body["api_key"].startswith("ak_")
    assert body["api_key_id"]


async def test_create_api_key_requires_bootstrap_token(client):
    configure_bootstrap_token(client)

    response = await client.post(
        "/api/v1/auth/api-keys",
        json={"name": "local-test"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_authenticated_endpoint_accepts_api_key(client):
    configure_bootstrap_token(client)

    created = await client.post(
        "/api/v1/auth/api-keys",
        headers=BOOTSTRAP_HEADERS,
        json={"name": "local-test"},
    )
    api_key = created.json()["api_key"]

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert response.status_code == 200
    assert response.json()["auth_type"] == "api_key"
