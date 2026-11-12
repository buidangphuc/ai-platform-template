from app.bootstrap.features.base import Feature
from app.bootstrap.services import open_runtime
from app.modules.platform.http.upstream import Upstream
from tests.factories import build_test_settings, local_upstreams
from tests.http_server import Reply


class _Service:
    pass


def _feature(*upstreams: Upstream) -> Feature:
    return Feature(
        name="geo",
        service=_Service,
        build=lambda resources, settings: _Service(),
        upstreams=upstreams,
    )


async def test_local_upstreams_points_the_named_upstream_at_the_local_server(
    monkeypatch, local_http_server
):
    local_http_server.script("/lookup", Reply(json={"ok": True}))
    local_upstreams(monkeypatch, {"geo": local_http_server.url})
    feature = _feature(
        Upstream("geo", base_url=lambda settings: "http://geo.invalid"),
    )

    async with open_runtime(
        build_test_settings(), init_resources=False, addons=(), features=(feature,)
    ) as resources:
        response = await resources.http("geo").get("/lookup")

    assert response.json() == {"ok": True}
    assert [r.path for r in local_http_server.requests] == ["/lookup"]


async def test_local_upstreams_leaves_other_upstreams_untouched(
    monkeypatch, local_http_server
):
    local_upstreams(monkeypatch, {"geo": local_http_server.url})
    feature = _feature(
        Upstream("geo", base_url=lambda settings: "http://geo.invalid"),
        Upstream("other", base_url=lambda settings: "http://other.invalid"),
    )

    async with open_runtime(
        build_test_settings(), init_resources=False, addons=(), features=(feature,)
    ) as resources:
        assert str(resources.http("geo")._client.base_url) == local_http_server.url
        assert str(resources.http("other")._client.base_url) == "http://other.invalid"
