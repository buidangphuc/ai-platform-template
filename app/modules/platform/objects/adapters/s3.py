from __future__ import annotations

from collections.abc import Callable
from inspect import isawaitable
from typing import Any

try:
    import aioboto3
except ImportError:  # pragma: no cover - exercised when optional extra is missing
    aioboto3 = None


def _require_aioboto3() -> None:
    if aioboto3 is None:
        raise RuntimeError(
            "S3 object adapter requires the [aws] extra: "
            "uv pip install 'fastapi-template[aws]'"
        )


class S3ObjectGateway:
    def __init__(
        self,
        *,
        bucket: str,
        region_name: str,
        prefix: str = "app",
        endpoint_url: str | None = None,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        if session_factory is None:
            _require_aioboto3()
        if not bucket:
            raise ValueError("bucket is required for S3 object gateway")
        self.bucket = bucket
        self.region_name = region_name
        self.prefix = prefix.strip("/")
        self.endpoint_url = endpoint_url
        self._session = (
            session_factory() if session_factory is not None else aioboto3.Session()
        )
        self._client_cm = None
        self._client = None

    async def _get_client(self):
        if self._client is None:
            kwargs: dict[str, Any] = {"region_name": self.region_name}
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
            self._client_cm = self._session.client("s3", **kwargs)
            self._client = await self._client_cm.__aenter__()
        return self._client

    async def put(
        self,
        key: str,
        value: bytes,
        *,
        content_type: str | None = None,
    ) -> None:
        client = await self._get_client()
        kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": self._key(key),
            "Body": value,
        }
        if content_type:
            kwargs["ContentType"] = content_type
        await client.put_object(**kwargs)

    async def get(self, key: str) -> bytes | None:
        client = await self._get_client()
        try:
            response = await client.get_object(Bucket=self.bucket, Key=self._key(key))
        except Exception as exc:
            if exc.__class__.__name__ in {"NoSuchKey", "ClientError"}:
                return None
            raise
        body = response["Body"]
        return await body.read()

    async def delete(self, key: str) -> None:
        client = await self._get_client()
        await client.delete_object(Bucket=self.bucket, Key=self._key(key))

    async def exists(self, key: str) -> bool:
        client = await self._get_client()
        try:
            await client.head_object(Bucket=self.bucket, Key=self._key(key))
        except Exception as exc:
            if exc.__class__.__name__ in {"NoSuchKey", "ClientError"}:
                return False
            raise
        return True

    async def list(self, prefix: str = "", *, limit: int = 100) -> list[str]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        client = await self._get_client()
        scoped = self._key(prefix) if prefix else self.prefix
        response = await client.list_objects_v2(
            Bucket=self.bucket,
            Prefix=scoped,
            MaxKeys=limit,
        )
        prefix_len = len(self.prefix) + 1 if self.prefix else 0
        return [obj["Key"][prefix_len:] for obj in response.get("Contents", [])]

    async def presign_get(self, key: str, *, expires_seconds: int = 3600) -> str:
        client = await self._get_client()
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": self._key(key)},
            ExpiresIn=expires_seconds,
        )
        if isawaitable(url):
            url = await url
        return str(url)

    async def presign_put(
        self,
        key: str,
        *,
        expires_seconds: int = 3600,
        content_type: str | None = None,
    ) -> str:
        client = await self._get_client()
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": self._key(key)}
        if content_type:
            params["ContentType"] = content_type
        url = client.generate_presigned_url(
            "put_object",
            Params=params,
            ExpiresIn=expires_seconds,
        )
        if isawaitable(url):
            url = await url
        return str(url)

    async def close(self) -> None:
        if self._client_cm is not None:
            await self._client_cm.__aexit__(None, None, None)
            self._client_cm = None
            self._client = None

    def _key(self, key: str) -> str:
        normalized = key.strip("/")
        return f"{self.prefix}/{normalized}" if self.prefix else normalized
