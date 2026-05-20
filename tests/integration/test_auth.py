async def test_create_api_key_returns_secret_once(client):
    response = await client.post(
        "/api/v1/auth/api-keys",
        json={"name": "local-test"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "local-test"
    assert body["api_key"].startswith("ak_")
    assert body["api_key_id"]


async def test_authenticated_endpoint_accepts_api_key(client):
    created = await client.post(
        "/api/v1/auth/api-keys",
        json={"name": "local-test"},
    )
    api_key = created.json()["api_key"]

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert response.status_code == 200
    assert response.json()["auth_type"] == "api_key"
