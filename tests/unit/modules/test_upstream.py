from __future__ import annotations

from dataclasses import replace

import httpx
import pytest
from loguru import logger

from app.bootstrap.features.base import Feature
from app.bootstrap.resources import ApplicationResources
from app.bootstrap.services import open_runtime
from app.core.errors import ServiceUnavailableError
from app.core.request_context import reset_request_id, set_request_id
from app.core.resilience import BreakerState, CircuitBreakerPolicy
from app.modules.platform.http.upstream import Upstream, UpstreamClient
from tests.factories import build_test_settings, local_upstreams
from tests.http_server import (
    LocalHttpServer,
    Reply,
)


class _Service:
    pass


class _OtherService:
    pass


def _client(
    server: LocalHttpServer,
    *,
    name: str = "svc",
    retries: int = 0,
    threshold: int = 3,
    timeout: float = 2.0,
    sleeps: list[float] | None = None,
) -> UpstreamClient:
    async def sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    return UpstreamClient(
        name,
        httpx.AsyncClient(base_url=server.url, timeout=timeout),
        retries=retries,
        breaker=CircuitBreakerPolicy(failure_threshold=threshold).build(),
        sleep=sleep,
    )


@pytest.fixture()
async def open_client(local_http_server):
    clients: list[UpstreamClient] = []

    def build(**kwargs) -> UpstreamClient:
        client = _client(local_http_server, **kwargs)
        clients.append(client)
        return client

    yield build
    for client in clients:
        await client.aclose()


async def test_transient_503_is_retried_then_succeeds(local_http_server, open_client):
    local_http_server.script("/x", Reply(503), Reply(200))
    sleeps: list[float] = []

    response = await open_client(retries=1, sleeps=sleeps).get("/x")

    assert response.status_code == 200
    assert len(local_http_server.requests) == 2
    assert len(sleeps) == 1


async def test_dropped_connection_is_retried_then_succeeds(
    local_http_server, open_client
):
    local_http_server.script("/x", Reply(drop=True), Reply(200))

    response = await open_client(retries=1).get("/x")

    assert response.status_code == 200
    assert len(local_http_server.requests) == 2


async def test_retries_are_capped_and_then_unavailable(local_http_server, open_client):
    local_http_server.script("/x", Reply(drop=True))

    with pytest.raises(ServiceUnavailableError) as exc:
        await open_client(retries=2, threshold=10).get("/x")

    assert exc.value.code == "upstream_unavailable"
    assert len(local_http_server.requests) == 3


async def test_refused_connection_is_unavailable(local_http_server, open_client):
    client = open_client(retries=1, threshold=10)
    await local_http_server.stop()

    with pytest.raises(ServiceUnavailableError) as exc:
        await client.get("/x")

    assert exc.value.code == "upstream_unavailable"


async def test_slow_upstream_times_out_as_unavailable(local_http_server, open_client):
    local_http_server.script("/slow", Reply(delay=0.5))

    with pytest.raises(ServiceUnavailableError) as exc:
        await open_client(timeout=0.05, threshold=10).get("/slow")

    assert exc.value.code == "upstream_unavailable"


async def test_404_is_returned_at_once_and_does_not_charge_the_breaker(
    local_http_server, open_client
):
    local_http_server.script("/missing", Reply(404))
    client = open_client(retries=3)

    response = await client.get("/missing")

    assert response.status_code == 404
    assert len(local_http_server.requests) == 1
    assert client._breaker.failure_count == 0


async def test_exhausted_transient_status_is_returned_and_charges_the_breaker(
    local_http_server, open_client
):
    local_http_server.script("/x", Reply(500))
    client = open_client(retries=1, threshold=10)

    response = await client.get("/x")

    assert response.status_code == 500
    assert client._breaker.failure_count == 2


async def test_breaker_opens_then_rejects_without_calling_the_server(
    local_http_server, open_client
):
    local_http_server.script("/x", Reply(503))
    client = open_client(threshold=2)
    await client.get("/x")
    await client.get("/x")
    assert client._breaker.state is BreakerState.OPEN
    before = len(local_http_server.requests)

    with pytest.raises(ServiceUnavailableError) as exc:
        await client.get("/x")

    assert exc.value.code == "upstream_unavailable"
    assert len(local_http_server.requests) == before


async def test_breaker_opens_after_n_connection_failures(
    local_http_server, open_client
):
    local_http_server.script("/x", Reply(drop=True))
    client = open_client(threshold=2)
    for _ in range(2):
        with pytest.raises(ServiceUnavailableError):
            await client.get("/x")
    before = len(local_http_server.requests)

    with pytest.raises(ServiceUnavailableError) as exc:
        await client.get("/x")

    assert client._breaker.state is BreakerState.OPEN
    assert exc.value.code == "upstream_unavailable"
    assert len(local_http_server.requests) == before


async def test_two_upstreams_are_isolated(local_http_server, open_client):
    local_http_server.script("/down", Reply(503))
    local_http_server.script("/up", Reply(200))
    a = open_client(name="a", threshold=1)
    b = open_client(name="b", threshold=1)
    await a.get("/down")

    with pytest.raises(ServiceUnavailableError) as exc:
        await a.get("/down")

    assert exc.value.code == "upstream_unavailable"
    assert (await b.get("/up")).status_code == 200


async def test_request_id_header_reaches_the_server(local_http_server, open_client):
    local_http_server.script("/x", Reply(200))
    client = open_client()
    token = set_request_id("req_abc")
    try:
        await client.get("/x")
    finally:
        reset_request_id(token)
    await client.get("/x")

    assert [r.headers.get("x-request-id") for r in local_http_server.requests] == [
        "req_abc",
        None,
    ]


async def test_post_forwards_the_body(local_http_server, open_client):
    local_http_server.script("/p", Reply(200))

    await open_client().post("/p", json={"a": 1})

    [request] = local_http_server.requests
    assert request.method == "POST"
    assert request.json() == {"a": 1}


async def test_one_log_line_per_call_without_query_or_headers(
    local_http_server, open_client
):
    local_http_server.script("/v1/items", Reply(200))
    lines: list[str] = []
    sink = logger.add(lines.append, format="{message}")

    try:
        await open_client(name="geo").request(
            "GET",
            "/v1/items?token=secret-query",
            headers={"Authorization": "Bearer secret-header"},
        )
    finally:
        logger.remove(sink)

    assert len(lines) == 1
    line = lines[0]
    assert "GET" in line
    assert "geo" in line
    assert "/v1/items" in line
    assert "200" in line
    assert "duration_ms" in line
    assert "secret-query" not in line
    assert "secret-header" not in line


def _feature(name: str, service: type, *upstreams: Upstream) -> Feature:
    return Feature(
        name=name,
        service=service,
        build=lambda resources, settings: service(),
        upstreams=upstreams,
    )


def _upstream(name: str = "geo", **overrides: object) -> Upstream:
    return replace(
        Upstream(name=name, base_url=lambda settings: "http://geo.test"),
        **overrides,
    )


async def test_bootstrap_opens_and_closes_upstreams_of_enabled_features(
    monkeypatch, local_http_server
):
    local_http_server.script("/ping", Reply(200))
    local_upstreams(monkeypatch, {"geo": local_http_server.url})
    feature = _feature("a", _Service, _upstream("geo"))
    disabled = replace(
        _feature("b", _OtherService, _upstream("other")),
        enabled=lambda settings: False,
    )
    async with open_runtime(
        build_test_settings(),
        init_resources=False,
        addons=(),
        features=(feature, disabled),
    ) as resources:
        client = resources.http("geo")
        assert isinstance(client, UpstreamClient)
        with pytest.raises(ServiceUnavailableError) as exc:
            resources.http("other")
        assert exc.value.code == "upstream_not_configured"
        assert not client._client.is_closed
        assert (await client.get("/ping")).status_code == 200

    assert client._client.is_closed


async def test_build_can_use_the_upstream():
    seen: list[UpstreamClient] = []

    def build(resources: ApplicationResources, settings) -> _Service:
        seen.append(resources.http("geo"))
        return _Service()

    feature = replace(_feature("a", _Service, _upstream("geo")), build=build)
    async with open_runtime(
        build_test_settings(), init_resources=False, addons=(), features=(feature,)
    ) as resources:
        assert seen == [resources.http("geo")]


async def test_upstream_settings_are_applied_to_the_client():
    upstream = _upstream(
        "geo",
        base_url=lambda settings: f"http://{settings.POSTGRES_HOST}.test",
        headers=lambda settings: {"X-Key": "k"},
        timeout=3.0,
        follow_redirects=True,
    )
    async with open_runtime(
        build_test_settings(),
        init_resources=False,
        addons=(),
        features=(_feature("a", _Service, upstream),),
    ) as resources:
        inner = resources.http("geo")._client
        assert str(inner.base_url) == "http://localhost.test"
        assert inner.headers["x-key"] == "k"
        assert inner.timeout == httpx.Timeout(3.0)
        assert inner.follow_redirects is True


async def test_duplicate_upstream_name_fails_at_startup():
    features = (
        _feature("a", _Service, _upstream("geo")),
        _feature("b", _OtherService, _upstream("geo")),
    )
    with pytest.raises(ValueError, match="'geo'.*'a'.*'b'"):
        async with open_runtime(
            build_test_settings(), init_resources=False, addons=(), features=features
        ):
            pass


async def test_unknown_upstream_name_is_not_configured():
    async with open_runtime(
        build_test_settings(), init_resources=False, addons=(), features=()
    ) as resources:
        with pytest.raises(ServiceUnavailableError) as exc:
            resources.http("nope")
    assert exc.value.code == "upstream_not_configured"
