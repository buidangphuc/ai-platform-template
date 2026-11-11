import httpx

from app.bootstrap.features.base import Feature
from app.bootstrap.services import open_runtime
from app.modules.platform.http.upstream import Upstream
from tests.factories import build_test_settings, mock_upstreams


class _Service:
    pass


async def test_mock_upstreams_serves_the_named_upstream(monkeypatch):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"ok": True})

    mock_upstreams(monkeypatch, {"geo": handler})
    feature = Feature(
        name="geo",
        service=_Service,
        build=lambda resources, settings: _Service(),
        upstreams=(Upstream("geo", base_url=lambda settings: "http://geo.invalid"),),
    )

    async with open_runtime(
        build_test_settings(), init_resources=False, addons=(), features=(feature,)
    ) as resources:
        response = await resources.http("geo").get("/lookup")

    assert response.json() == {"ok": True}
    assert seen == ["/lookup"]
