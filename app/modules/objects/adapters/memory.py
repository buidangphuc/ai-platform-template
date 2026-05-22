from __future__ import annotations


class MemoryObjectGateway:
    def __init__(self, *, prefix: str = "app") -> None:
        self.prefix = prefix.strip("/")
        self._values: dict[str, bytes] = {}
        self._closed = False

    async def put(
        self,
        key: str,
        value: bytes,
        *,
        content_type: str | None = None,
    ) -> None:
        self._ensure_open()
        self._values[self._key(key)] = value

    async def get(self, key: str) -> bytes | None:
        self._ensure_open()
        return self._values.get(self._key(key))

    async def delete(self, key: str) -> None:
        self._ensure_open()
        self._values.pop(self._key(key), None)

    async def exists(self, key: str) -> bool:
        self._ensure_open()
        return self._key(key) in self._values

    async def presign_get(self, key: str, *, expires_seconds: int = 3600) -> str:
        self._ensure_open()
        return f"memory://{self._key(key)}"

    async def close(self) -> None:
        self._closed = True
        self._values.clear()

    def _key(self, key: str) -> str:
        normalized = key.strip("/")
        return f"{self.prefix}/{normalized}" if self.prefix else normalized

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("object gateway is closed")
