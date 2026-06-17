from app.bootstrap.application import create_app
from tests.factories import api_client_for, build_test_settings


async def _get(app, path: str):
    async with api_client_for(app) as client:
        return await client.get(path)


async def test_docs_endpoints_exposed_when_enabled():
    app = create_app(
        settings=build_test_settings(DOCS_ENABLED=True),
        init_resources=False,
    )

    assert (await _get(app, "/docs")).status_code == 200
    assert (await _get(app, "/redoc")).status_code == 200
    assert (await _get(app, "/openapi.json")).status_code == 200


async def test_docs_endpoints_hidden_when_disabled():
    app = create_app(
        settings=build_test_settings(DOCS_ENABLED=False),
        init_resources=False,
    )

    assert (await _get(app, "/docs")).status_code == 404
    assert (await _get(app, "/redoc")).status_code == 404
    assert (await _get(app, "/openapi.json")).status_code == 404
