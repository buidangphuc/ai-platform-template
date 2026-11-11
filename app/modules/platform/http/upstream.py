from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx
from loguru import logger

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.core.request_context import get_request_id
from app.core.resilience import (
    CircuitBreaker,
    CircuitBreakerPolicy,
    RetryPolicy,
    TimeoutPolicy,
    is_transient_error,
    retry_after_seconds,
)

REQUEST_ID_HEADER = "X-Request-ID"


def _no_headers(settings: Settings) -> Mapping[str, str]:
    return {}


@dataclass(frozen=True)
class Upstream:
    name: str
    base_url: Callable[[Settings], str]
    timeout: float = 10.0
    retries: int = 0
    headers: Callable[[Settings], Mapping[str, str]] = _no_headers
    follow_redirects: bool = False


class UpstreamClient:
    def __init__(
        self,
        name: str,
        client: httpx.AsyncClient,
        *,
        retries: int = 0,
        breaker: CircuitBreaker | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.name = name
        self._client = client
        self._retry = RetryPolicy(max_attempts=retries + 1)
        self._breaker = breaker or CircuitBreakerPolicy().build()
        self._sleep = sleep

    @classmethod
    def from_upstream(
        cls,
        upstream: Upstream,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> UpstreamClient:
        client = httpx.AsyncClient(
            base_url=upstream.base_url(settings),
            headers=dict(upstream.headers(settings)),
            timeout=TimeoutPolicy(upstream.timeout).timeout_seconds,
            follow_redirects=upstream.follow_redirects,
            transport=transport,
        )
        return cls(upstream.name, client, retries=upstream.retries)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", None) or {})
        request_id = get_request_id()
        if request_id != "-":
            headers.setdefault(REQUEST_ID_HEADER, request_id)
        started = perf_counter()
        outcome = "error"
        try:
            response = await self._send(method, url, headers, kwargs)
            outcome = str(response.status_code)
            return response
        except ServiceUnavailableError:
            outcome = "unavailable"
            raise
        finally:
            logger.info(
                "upstream call method={} upstream={} path={} status={} duration_ms={}",
                method,
                self.name,
                httpx.URL(url).path,
                outcome,
                round((perf_counter() - started) * 1000, 1),
            )

    async def _send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        kwargs: dict[str, Any],
    ) -> httpx.Response:
        attempt = 0
        while True:
            attempt += 1
            if not self._breaker.try_acquire():
                raise self._unavailable("circuit open")
            try:
                response = await self._client.request(
                    method, url, headers=headers, **kwargs
                )
            except asyncio.CancelledError:
                self._breaker.release_probe()
                raise
            except Exception as exc:
                self._breaker.record_failure(exc)
                decision = self._retry.decision(attempt=attempt, error=exc)
                if not decision.should_retry:
                    if is_transient_error(exc):
                        raise self._unavailable(type(exc).__name__) from exc
                    raise
                await self._sleep(decision.next_delay_seconds or 0.0)
                continue
            error = httpx.HTTPStatusError(
                "upstream status", request=response.request, response=response
            )
            if not is_transient_error(error):
                self._breaker.record_success()
                return response
            self._breaker.record_failure(error)
            decision = self._retry.decision(
                attempt=attempt,
                status_code=response.status_code,
                retry_after_seconds=retry_after_seconds(error),
            )
            if not decision.should_retry:
                return response
            await self._sleep(decision.next_delay_seconds or 0.0)

    def _unavailable(self, reason: str) -> ServiceUnavailableError:
        return ServiceUnavailableError(
            f"Upstream {self.name} is unavailable ({reason})",
            code="upstream_unavailable",
        )
