from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int | None = None


class RedisRateLimiter:
    """Sliding-window-counter rate limiter (Redis).

    Uses two keys per ``(prefix, key)``: one for the current window, one for
    the previous. The previous key's TTL is set to ``2 * window_seconds`` so
    it survives long enough to influence weighting. The Lua script is
    atomic — no race between the check and increment.

    The window index and elapsed time come from the Redis server clock
    (``TIME``) inside the script, so every pod agrees on which window a
    request belongs to; a per-process clock would give each pod its own
    window boundaries. The script derives the window keys itself, which makes
    them undeclared KEYS: fine on a single node, not under Redis Cluster
    (wrap ``prefix:key`` in a ``{hash tag}`` if you ever shard).
    """

    _CHECK_SCRIPT = """
local base_key = KEYS[1]
local window_seconds = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])

local server_time = redis.call('TIME')
local now = tonumber(server_time[1]) + tonumber(server_time[2]) / 1000000
local window_index = math.floor(now / window_seconds)
local elapsed = now - window_index * window_seconds
local current_key = base_key .. ':' .. window_index
local previous_key = base_key .. ':' .. (window_index - 1)

local current = tonumber(redis.call('GET', current_key) or '0')
local previous = tonumber(redis.call('GET', previous_key) or '0')
local previous_weight = 1.0 - (elapsed / window_seconds)
if previous_weight < 0 then previous_weight = 0 end
local weighted = current + math.floor(previous * previous_weight)
local retry_after = math.ceil(window_seconds - elapsed)
if retry_after < 1 then retry_after = 1 end

if weighted >= limit then
    return {weighted, retry_after, 0}
end

local new_current = redis.call('INCR', current_key)
if new_current == 1 then
    redis.call('EXPIRE', current_key, window_seconds * 2)
end
local weighted_after = new_current + math.floor(previous * previous_weight)
return {weighted_after, retry_after, 1}
"""

    def __init__(
        self,
        *,
        redis,
        limit: int,
        window_seconds: int = 60,
        prefix: str = "rate-limit",
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.redis = redis
        self.limit = limit
        self.window_seconds = window_seconds
        self.prefix = prefix

    async def check(self, key: str) -> RateLimitResult:
        result = await self.redis.eval(
            self._CHECK_SCRIPT,
            1,
            f"{self.prefix}:{key}",
            self.window_seconds,
            self.limit,
        )
        weighted = int(result[0])
        retry_after = int(result[1])
        allowed = bool(int(result[2]))

        if not allowed:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after_seconds=max(retry_after, 1),
            )
        return RateLimitResult(
            allowed=True,
            remaining=max(self.limit - weighted, 0),
        )
