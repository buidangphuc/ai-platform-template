"""ModelServerClient: the ML-template /predict contract + failure modes."""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.errors import ServiceUnavailableError
from app.modules.platform.http.upstream import UpstreamClient
from app.modules.platform.model_server.client import ModelServerClient


def _model(handler) -> ModelServerClient:
    return ModelServerClient(
        UpstreamClient(
            "model_server",
            httpx.AsyncClient(
                base_url="http://model.test",
                transport=httpx.MockTransport(handler),
            ),
        )
    )


def _reply(status_code: int, body=None):
    return lambda request: httpx.Response(status_code, json=body)


def _down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down")


async def test_predict_single_text_contract():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"label": "Sports", "score": 0.97})

    out = await _model(handler).predict({"text": "goal!"})

    assert out == {"label": "Sports", "score": 0.97}
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/predict"
    assert json.loads(seen[0].content) == {"text": "goal!"}


async def test_predict_batch_contract():
    out = await _model(_reply(200, [{"label": "A", "score": 0.9}])).predict(
        {"texts": ["x"]}
    )
    assert out == [{"label": "A", "score": 0.9}]


async def test_unreachable_server_is_service_unavailable():
    with pytest.raises(ServiceUnavailableError) as exc:
        await _model(_down).predict({"text": "x"})
    assert exc.value.code == "model_server_unavailable"


async def test_non_200_is_backend_error_not_fabrication():
    with pytest.raises(ServiceUnavailableError) as exc:
        await _model(_reply(500)).predict({"text": "x"})
    assert exc.value.code == "model_server_error"


async def test_ping_reflects_reachability():
    up = _model(_reply(200, {"status": "ok"}))
    down = _model(_down)
    assert await up.ping() is True
    assert await down.ping() is False


async def test_check_passes_when_healthy_and_raises_when_down():
    up = _model(_reply(200, {"status": "ok"}))
    down = _model(_down)

    await up.check()
    with pytest.raises(ServiceUnavailableError):
        await down.check()
