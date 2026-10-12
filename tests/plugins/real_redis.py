"""pytest plugin: run the fakeredis-based tests against a real Redis.

Usage: ``REAL_REDIS_URL=redis://localhost:6379/15 pytest -p tests.plugins.real_redis
tests/unit/modules/queues/test_redis_stream.py ...``. Every ``FakeRedis(...)`` becomes a
client on that database, flushed first. fakeredis differs from Redis in places
(e.g. approximate stream trimming), so CI runs the Redis-backed tests both ways.
"""

import os

import fakeredis.aioredis as fake_aioredis
import redis
import redis.asyncio as real_aioredis

_URL = os.environ["REAL_REDIS_URL"]


class _RealRedis(real_aioredis.Redis):
    def __init__(self, *args: object, decode_responses: bool = False, **kwargs: object):
        redis.Redis.from_url(_URL).flushdb()
        pool = real_aioredis.ConnectionPool.from_url(
            _URL, decode_responses=decode_responses
        )
        super().__init__(connection_pool=pool)


fake_aioredis.FakeRedis = _RealRedis  # type: ignore[misc]
