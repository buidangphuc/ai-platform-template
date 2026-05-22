from __future__ import annotations

import hashlib
import hmac
import time


class WebhookSigner:
    def __init__(self, *, secret: str, tolerance_seconds: int = 300) -> None:
        if not secret:
            raise ValueError("secret is required")
        if tolerance_seconds <= 0:
            raise ValueError("tolerance_seconds must be positive")
        self.secret = secret.encode("utf-8")
        self.tolerance_seconds = tolerance_seconds

    def sign(self, payload: bytes, *, timestamp: int | None = None) -> str:
        timestamp = int(time.time()) if timestamp is None else timestamp
        signed_payload = self._signed_payload(payload, timestamp)
        digest = hmac.new(self.secret, signed_payload, hashlib.sha256).hexdigest()
        return f"v1={digest}"

    def verify(
        self,
        payload: bytes,
        *,
        signature: str,
        timestamp: int,
        now: int | None = None,
    ) -> bool:
        now = int(time.time()) if now is None else now
        if abs(now - timestamp) > self.tolerance_seconds:
            return False
        expected = self.sign(payload, timestamp=timestamp)
        return hmac.compare_digest(expected, signature)

    def _signed_payload(self, payload: bytes, timestamp: int) -> bytes:
        return f"{timestamp}.".encode() + payload
