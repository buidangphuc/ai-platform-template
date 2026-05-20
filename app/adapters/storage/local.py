from pathlib import Path

import aiofiles

from app.contracts.storage import StoredObject


class LocalObjectStorage:
    def __init__(self, *, root: str | Path) -> None:
        self.root = Path(root)

    async def put_bytes(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        path = self._safe_path(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "wb") as file:
            await file.write(data)
        return StoredObject(
            bucket=bucket,
            key=key,
            content_type=content_type,
            metadata=metadata or {},
            size_bytes=len(data),
        )

    async def get_bytes(self, bucket: str, key: str) -> bytes:
        path = self._safe_path(bucket, key)
        async with aiofiles.open(path, "rb") as file:
            return await file.read()

    async def exists(self, bucket: str, key: str) -> bool:
        return self._safe_path(bucket, key).exists()

    async def delete(self, bucket: str, key: str) -> None:
        self._safe_path(bucket, key).unlink(missing_ok=True)

    def _safe_path(self, bucket: str, key: str) -> Path:
        if not bucket or bucket in {".", ".."} or "/" in bucket or "\\" in bucket:
            raise ValueError("unsafe storage bucket")
        bucket_path = (self.root / bucket).resolve()
        candidate = (bucket_path / key).resolve()
        try:
            candidate.relative_to(bucket_path)
        except ValueError as exc:
            raise ValueError("unsafe storage key") from exc
        return candidate
