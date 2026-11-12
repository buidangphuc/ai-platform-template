from redis.asyncio import Redis

from app.core.config import Settings


def build_redis_client(settings: Settings, *, decode_responses: bool = True) -> Redis:
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        username=settings.REDIS_USERNAME or None,
        password=settings.REDIS_PASSWORD or None,
        db=settings.REDIS_DATABASE,
        socket_timeout=settings.REDIS_TIMEOUT_SECONDS,
        decode_responses=decode_responses,
    )


async def check_redis_connection(redis: Redis) -> None:
    await redis.ping()
