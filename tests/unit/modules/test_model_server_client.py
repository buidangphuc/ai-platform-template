"""ModelServerClient: the ML-template /predict contract + failure modes."""

from __future__ import annotations

import httpx
import pytest

from app.core.errors import ServiceUnavailableError
from app.modules.platform.http.upstream import UpstreamClient
from app.modules.platform.model_server.client import ModelServerClient
from tests.http_server import (
    LocalHttpServer,
    Reply,
)


@pytest.fixture()
async def model(local_http_server: LocalHttpServer):
    client = UpstreamClient(
        "model_server", httpx.AsyncClient(base_url=local_http_server.url, timeout=2.0)
    )
    yield ModelServerClient(client)
    await client.aclose()


async def test_predict_single_text_contract(local_http_server, model):
    local_http_server.script("/predict", Reply(json={"label": "Sports", "score": 0.97}))

    out = await model.predict({"text": "goal!"})

    assert out == {"label": "Sports", "score": 0.97}
    [request] = local_http_server.requests
    assert request.method == "POST"
    assert request.path == "/predict"
    assert request.json() == {"text": "goal!"}


async def test_predict_batch_contract(local_http_server, model):
    local_http_server.script("/predict", Reply(json=[{"label": "A", "score": 0.9}]))

    out = await model.predict({"texts": ["x"]})

    assert out == [{"label": "A", "score": 0.9}]


async def test_unreachable_server_is_service_unavailable(local_http_server, model):
    await local_http_server.stop()

    with pytest.raises(ServiceUnavailableError) as exc:
        await model.predict({"text": "x"})
    assert exc.value.code == "model_server_unavailable"


async def test_dropped_connection_is_service_unavailable(local_http_server, model):
    local_http_server.script("/predict", Reply(drop=True))

    with pytest.raises(ServiceUnavailableError) as exc:
        await model.predict({"text": "x"})
    assert exc.value.code == "model_server_unavailable"


async def test_non_200_is_backend_error_not_fabrication(local_http_server, model):
    local_http_server.script("/predict", Reply(500))

    with pytest.raises(ServiceUnavailableError) as exc:
        await model.predict({"text": "x"})
    assert exc.value.code == "model_server_error"


async def test_ping_reflects_reachability(local_http_server, model):
    local_http_server.script("/health", Reply(json={"status": "ok"}))
    assert await model.ping() is True

    await local_http_server.stop()
    assert await model.ping() is False


async def test_check_passes_when_healthy_and_raises_when_down(local_http_server, model):
    local_http_server.script("/health", Reply(json={"status": "ok"}))
    await model.check()

    local_http_server.script("/health", Reply(503))
    with pytest.raises(ServiceUnavailableError):
        await model.check()
