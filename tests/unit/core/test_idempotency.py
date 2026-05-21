from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.core.idempotency import get_idempotency_key


def _request(headers: dict[str, str]):
    return SimpleNamespace(headers=headers, state=SimpleNamespace())


def test_idempotency_key_is_optional():
    request = _request({})

    assert get_idempotency_key(request) is None
    assert request.state.idempotency_key is None


def test_idempotency_key_is_trimmed_and_stored_on_request_state():
    request = _request({"Idempotency-Key": " job-123 "})

    assert get_idempotency_key(request) == "job-123"
    assert request.state.idempotency_key == "job-123"


def test_idempotency_key_rejects_blank_header():
    with pytest.raises(AppError) as exc_info:
        get_idempotency_key(_request({"Idempotency-Key": "   "}))

    assert exc_info.value.code == "invalid_idempotency_key"
    assert exc_info.value.status_code == 400


def test_idempotency_key_rejects_oversized_header():
    with pytest.raises(AppError) as exc_info:
        get_idempotency_key(_request({"Idempotency-Key": "x" * 256}))

    assert exc_info.value.code == "invalid_idempotency_key"
    assert exc_info.value.status_code == 400
