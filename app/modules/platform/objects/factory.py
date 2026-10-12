from __future__ import annotations

from app.core.config import Settings
from app.modules.platform.objects.gateway import ObjectGateway


def build_object_gateway(settings: Settings) -> ObjectGateway:
    if settings.OBJECT_BACKEND == "memory":
        from app.modules.platform.objects.adapters.memory import MemoryObjectGateway

        return MemoryObjectGateway(prefix=settings.OBJECT_PREFIX)

    if settings.OBJECT_BACKEND == "s3":
        if not settings.OBJECT_S3_BUCKET:
            raise RuntimeError("OBJECT_S3_BUCKET is required for s3 object backend")
        from app.modules.platform.objects.adapters.s3 import S3ObjectGateway

        return S3ObjectGateway(
            bucket=settings.OBJECT_S3_BUCKET,
            region_name=settings.OBJECT_S3_REGION,
            prefix=settings.OBJECT_PREFIX,
            endpoint_url=settings.OBJECT_S3_ENDPOINT_URL or None,
        )

    raise ValueError(f"Unknown OBJECT_BACKEND={settings.OBJECT_BACKEND!r}")
