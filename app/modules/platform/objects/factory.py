from __future__ import annotations

from app.core.config import Settings
from app.modules.platform.objects.gateway import ObjectGateway


async def open_object_gateway(settings: Settings) -> ObjectGateway:
    match settings.OBJECT_BACKEND:
        case "memory":
            from app.modules.platform.objects.adapters.memory import (
                MemoryObjectGateway,
            )

            return MemoryObjectGateway(prefix=settings.OBJECT_PREFIX)
        case "s3":
            from app.modules.platform.objects.adapters.s3 import S3ObjectGateway

            return await S3ObjectGateway(
                bucket=settings.OBJECT_S3_BUCKET,
                region_name=settings.OBJECT_S3_REGION,
                prefix=settings.OBJECT_PREFIX,
                endpoint_url=settings.OBJECT_S3_ENDPOINT_URL or None,
            ).open()
