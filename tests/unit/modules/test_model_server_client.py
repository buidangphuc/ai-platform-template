"""ModelServerClient: the ML-template /predict contract + failure modes."""

from __future__ import annotations

import pytest

from app.core.errors import ServiceUnavailableError
from app.modules.platform.model_server.client import ModelServerClient


class _FakeResponse:
    def __init__(self, status_code: int, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _FakeClient:
    def __init__(self, response):
        self._response = response
        self.last = None

    async def post(self, path, json):
        self.last = (path, json)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    async def get(self, path):
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


async def test_predict_single_text_contract():
    fake = _FakeClient(_FakeResponse(200, {"label": "Sports", "score": 0.97}))
    client = ModelServerClient(fake)

    out = await client.predict({"text": "goal!"})

    assert out == {"label": "Sports", "score": 0.97}
    assert fake.last == ("/predict", {"text": "goal!"})


async def test_predict_batch_contract():
    fake = _FakeClient(_FakeResponse(200, [{"label": "A", "score": 0.9}]))
    out = await ModelServerClient(fake).predict({"texts": ["x"]})
    assert out == [{"label": "A", "score": 0.9}]


async def test_unreachable_server_is_service_unavailable():
    client = ModelServerClient(_FakeClient(ConnectionError("down")))
    with pytest.raises(ServiceUnavailableError) as exc:
        await client.predict({"text": "x"})
    assert exc.value.code == "model_server_unavailable"


async def test_non_200_is_backend_error_not_fabrication():
    client = ModelServerClient(_FakeClient(_FakeResponse(500)))
    with pytest.raises(ServiceUnavailableError) as exc:
        await client.predict({"text": "x"})
    assert exc.value.code == "model_server_error"


async def test_ping_reflects_reachability():
    up = ModelServerClient(_FakeClient(_FakeResponse(200, {"status": "ok"})))
    down = ModelServerClient(_FakeClient(ConnectionError("down")))
    assert await up.ping() is True
    assert await down.ping() is False


async def test_check_passes_when_healthy_and_raises_when_down():
    up = ModelServerClient(_FakeClient(_FakeResponse(200, {"status": "ok"})))
    down = ModelServerClient(_FakeClient(ConnectionError("down")))

    await up.check()
    with pytest.raises(ServiceUnavailableError):
        await down.check()
