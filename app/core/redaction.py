import re
from collections.abc import Mapping
from typing import Literal, cast

TraceContentMode = Literal["off", "redacted", "full"]


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

        redacted = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", value)
        redacted = re.sub(r"\bsk-[A-Za-z0-9_-]+\b", "[secret]", redacted)
        redacted = re.sub(r"\bBearer\s+\S+\b", "[secret]", redacted)
        return redacted

    def redact_mapping(self, payload: Mapping[str, object]) -> dict[str, object]:
        if self.mode == "full":
            return dict(payload)
        if self.mode == "off":
            return dict.fromkeys(payload, "[redacted]")

        redacted: dict[str, object] = {}
        for key, value in payload.items():
            if self._is_secret_key(key):
                redacted[key] = "[secret]"
            elif isinstance(value, str):
                redacted[key] = self.redact_text(value)
            elif isinstance(value, Mapping):
                redacted[key] = self.redact_mapping(value)
            elif isinstance(value, list):
                redacted[key] = [
                    self.redact_mapping(item) if isinstance(item, Mapping) else item
                    for item in value
                ]
            else:
                redacted[key] = value
        return redacted

    def _is_secret_key(self, key: str) -> bool:
        normalized = key.lower()
        return any(
            marker in normalized
            for marker in ("api_key", "token", "password", "secret", "pepper")
        )
