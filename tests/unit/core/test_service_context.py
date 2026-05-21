from types import SimpleNamespace

import pytest

from app.core.context import ServiceContext, build_service_context
from app.core.errors import AppError
from app.modules.identity.schemas import Principal


def test_service_context_does_not_parse_idempotency_key_when_disabled():
    db = object()
    request = SimpleNamespace(
        headers={"Idempotency-Key": "   "},
        state=SimpleNamespace(),
    )
    principal = Principal(id="svc-local", type="service", scopes=("admin",))

    context = build_service_context(
        request=request,
        request_id="req-1",
        principal=principal,
        db=db,
        idempotency_enabled=False,
    )

    assert context == ServiceContext(
        request_id="req-1",
        principal=principal,
        idempotency_key=None,
        db=db,
    )
    assert not hasattr(context, "redis")
    assert not hasattr(context, "feature_flags")


def test_service_context_parses_idempotency_key_when_enabled():
    db = object()
    request = SimpleNamespace(
        headers={"Idempotency-Key": " job-1 "},
        state=SimpleNamespace(),
    )
    principal = Principal(id="svc-local", type="service", scopes=("admin",))

    context = build_service_context(
        request=request,
        request_id="req-1",
        principal=principal,
        db=db,
        idempotency_enabled=True,
    )

    assert context.idempotency_key == "job-1"
    assert request.state.idempotency_key == "job-1"


def test_service_context_validates_idempotency_key_only_when_enabled():
    db = object()
    principal = Principal(id="svc-local", type="service", scopes=("admin",))

    with pytest.raises(AppError):
        build_service_context(
            request=SimpleNamespace(
                headers={"Idempotency-Key": "   "},
                state=SimpleNamespace(),
            ),
            request_id="req-1",
            principal=principal,
            db=db,
            idempotency_enabled=True,
        )
