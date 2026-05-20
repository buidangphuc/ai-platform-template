from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class StoredObject(BaseModel):
    bucket: str
    key: str
    content_type: str
    metadata: dict[str, str] = Field(default_factory=dict)
    size_bytes: int


@runtime_checkable
class ObjectStorage(Protocol):
    async def put_bytes(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        raise NotImplementedError

    async def get_bytes(self, bucket: str, key: str) -> bytes:
        raise NotImplementedError

    async def exists(self, bucket: str, key: str) -> bool:
        raise NotImplementedError

    async def delete(self, bucket: str, key: str) -> None:
        raise NotImplementedError
