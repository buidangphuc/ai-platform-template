import re
from collections.abc import Mapping
from typing import Literal, cast

TraceContentMode = Literal["off", "redacted", "full"]

_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]+\b"),
    re.compile(r"\bBearer\s+\S+\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key id
)
# 13-19 digits, optionally grouped by single spaces/dashes; Luhn decides.
_CARD_CANDIDATE = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
# Vietnamese numbers (0xxxxxxxxx / +84xxxxxxxxx) and E.164-style international ones.
_PHONE = re.compile(
    r"(?<![\w+])(?:\+84|0)(?:[ .-]?\d){9}(?!\d)"
    r"|(?<![\w+])\+\d{1,3}(?:[ .-]?\d){7,12}(?!\d)"
)
_SECRET_KEY_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "token",
    "password",
    "secret",
    "pepper",
)


def _luhn_valid(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _mask_card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    if 13 <= len(digits) <= 19 and _luhn_valid(digits):
        return "[card]"
    return match.group(0)


class RedactionPolicy:
    def __init__(self, *, mode: TraceContentMode = "redacted") -> None:
        self.mode = mode

    @classmethod
    def from_trace_content(cls, trace_content: str) -> "RedactionPolicy":
        if trace_content in {"off", "redacted", "full"}:
            return cls(mode=cast(TraceContentMode, trace_content))
        return cls(mode="redacted")

    def redact_text(self, value: str) -> str:
        if self.mode == "full":
            return value
        if self.mode == "off":
            return "[redacted]"

        redacted = _EMAIL.sub("[email]", value)
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub("[secret]", redacted)
        redacted = _CARD_CANDIDATE.sub(_mask_card, redacted)
        return _PHONE.sub("[phone]", redacted)

    def redact_mapping(self, payload: Mapping[str, object]) -> dict[str, object]:
        if self.mode == "full":
            return dict(payload)
        if self.mode == "off":
            return dict.fromkeys(payload, "[redacted]")

        redacted: dict[str, object] = {}
        for key, value in payload.items():
            if self._is_secret_key(key):
                redacted[key] = "[secret]"
            else:
                redacted[key] = self._redact_value(value)
        return redacted

    def _redact_value(self, value: object) -> object:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, Mapping):
            return self.redact_mapping(value)
        if isinstance(value, list | tuple):
            return [self._redact_value(item) for item in value]
        return value

    def _is_secret_key(self, key: str) -> bool:
        normalized = key.lower().replace("-", "_")
        return any(marker in normalized for marker in _SECRET_KEY_MARKERS)
