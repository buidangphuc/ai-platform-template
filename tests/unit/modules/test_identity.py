import hmac

import pytest

from app.core.errors import ForbiddenError, UnauthorizedError
from app.modules.platform.identity.auth import (
    authenticate_bearer_token,
    require_scopes,
)
from app.modules.platform.identity.schemas import Principal
from tests.factories import api_key_entry, build_test_settings


def _settings(*entries: str):
    return build_test_settings(AUTH_API_KEYS=",".join(entries))


async def test_authenticate_maps_the_matching_key_to_its_subject_and_scopes():
    settings = _settings(
        api_key_entry("alice", "alice-token", "read", "write"),
        api_key_entry("bob", "bob-token"),
    )

    alice = await authenticate_bearer_token("Bearer alice-token", settings=settings)
    bob = await authenticate_bearer_token("Bearer bob-token", settings=settings)

    assert (alice.id, alice.scopes) == ("alice", ("read", "write"))
    assert (bob.id, bob.scopes) == ("bob", ())  # no implicit admin


async def test_several_keys_may_share_a_subject_for_overlap_rotation():
    settings = _settings(
        api_key_entry("alice", "old-token", "read"),
        api_key_entry("alice", "new-token", "read"),
    )

    old = await authenticate_bearer_token("Bearer old-token", settings=settings)
    new = await authenticate_bearer_token("Bearer new-token", settings=settings)

    assert old.id == new.id == "alice"


@pytest.mark.parametrize("header", [None, "Basic abc", "Bearer wrong", "Bearer "])
async def test_authenticate_rejects_missing_or_unknown_credentials(header):
    settings = _settings(api_key_entry("alice", "alice-token"))

    with pytest.raises(UnauthorizedError):
        await authenticate_bearer_token(header, settings=settings)


async def test_authenticate_reports_not_configured_when_no_keys():
    with pytest.raises(ForbiddenError) as exc_info:
        await authenticate_bearer_token(
            "Bearer anything", settings=build_test_settings(AUTH_API_KEYS="")
        )

    assert exc_info.value.code == "auth_not_configured"


async def test_authenticate_compares_against_every_key_without_early_exit(
    monkeypatch,
):
    settings = _settings(
        api_key_entry("a", "token-a"),
        api_key_entry("b", "token-b"),
        api_key_entry("c", "token-c"),
    )
    calls = 0
    real = hmac.compare_digest

    def counting(left, right):
        nonlocal calls
        calls += 1
        return real(left, right)

    monkeypatch.setattr(hmac, "compare_digest", counting)

    principal = await authenticate_bearer_token("Bearer token-a", settings=settings)

    assert principal.id == "a"  # first key matched, yet all three were compared
    assert calls == 3


async def test_require_scopes_returns_principal_when_all_present():
    principal = Principal(id="svc", type="service", scopes=("admin", "billing"))
    dependency = require_scopes("admin")

    result = await dependency(principal=principal)

    assert result is principal


async def test_require_scopes_raises_when_any_scope_missing():
    principal = Principal(id="svc", type="service", scopes=("billing",))
    dependency = require_scopes("admin", "billing")

    with pytest.raises(ForbiddenError) as exc_info:
        await dependency(principal=principal)

    assert exc_info.value.code == "insufficient_scope"
    assert exc_info.value.status_code == 403
    assert exc_info.value.data == {
        "required": ["admin", "billing"],
        "missing": ["admin"],
    }


async def test_require_scopes_with_empty_required_always_allows():
    principal = Principal(id="svc", type="service", scopes=())
    dependency = require_scopes()

    result = await dependency(principal=principal)

    assert result is principal
