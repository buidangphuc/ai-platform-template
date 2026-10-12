"""IPRateLimitMiddleware client address: X-Forwarded-For only via trusted hops."""

from typing import Any

import pytest

from app.core.middleware import IPRateLimitMiddleware


async def _noop(scope: Any, receive: Any, send: Any) -> None:  # pragma: no cover
    return None


def _scope(xff: list[str], peer: str | None = "10.0.0.9") -> Any:
    return {
        "type": "http",
        "headers": [(b"x-forwarded-for", value.encode()) for value in xff],
        "client": (peer, 1234) if peer else None,
    }


def _ip(scope: Any, trusted: int) -> str:
    middleware = IPRateLimitMiddleware(_noop, trusted_proxy_count=trusted)
    return middleware._extract_client_ip(scope)


def test_default_ignores_spoofed_forwarded_for():
    assert _ip(_scope(["6.6.6.6"]), trusted=0) == "10.0.0.9"


def test_missing_peer_is_unknown():
    assert _ip(_scope([], peer=None), trusted=0) == "unknown"


def test_one_trusted_proxy_uses_rightmost_entry_not_spoofed_leftmost():
    # Client sent "6.6.6.6"; our proxy appended the real peer 1.2.3.4.
    assert _ip(_scope(["6.6.6.6, 1.2.3.4"]), trusted=1) == "1.2.3.4"


def test_two_trusted_proxies_take_second_from_right():
    assert _ip(_scope(["6.6.6.6, 1.2.3.4, 10.1.1.1"]), trusted=2) == "1.2.3.4"


def test_multiple_header_lines_are_joined_in_order():
    assert _ip(_scope(["6.6.6.6", "1.2.3.4"]), trusted=1) == "1.2.3.4"


def test_chain_shorter_than_trusted_count_falls_back_to_peer():
    assert _ip(_scope(["6.6.6.6"]), trusted=2) == "10.0.0.9"


def test_no_header_falls_back_to_peer():
    assert _ip(_scope([]), trusted=1) == "10.0.0.9"


def test_negative_count_is_rejected():
    with pytest.raises(ValueError):
        IPRateLimitMiddleware(_noop, trusted_proxy_count=-1)
