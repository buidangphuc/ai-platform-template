from redis.asyncio import Redis

from app.core.config import Settings


def build_redis_client(settings: Settings) -> Redis:
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None,
        db=settings.REDIS_DATABASE,
        socket_timeout=settings.REDIS_TIMEOUT_SECONDS,
        decode_responses=True,
    )


async def check_redis_connection(settings: Settings) -> None:
    client = build_redis_client(settings)
    try:
        await client.ping()
    finally:
        await client.aclose()
