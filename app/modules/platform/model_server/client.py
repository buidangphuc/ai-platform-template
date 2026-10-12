"""HTTP client for a self-hosted model server — the platform half of the
contract with the ML pipeline template's serving image.

The ML template (`datasience`) serves:

    POST /predict  {"text": "..."}            -> {"label": "...", "score": 0.97}
    POST /predict  {"texts": ["...", "..."]}  -> [{"label": ..., "score": ...}, ...]
    GET  /health                              -> {"status": "ok"}
    GET  /metrics                             -> Prometheus text

Any server speaking an HTTP predict contract fits — the client is duck-typed
(httpx-like, bound to a base_url) and injected, so tests use a fake. Products
build one in their domain runtime (own the URL setting + lifecycle), e.g.::

    client = build_httpx_model_server_client(settings.MY_MODEL_URL, timeout=10)
    model = ModelServerClient(client)
    runtime = MyRuntime(model=model, http_client=client)  # close() -> aclose()

Unreachable/erroring servers surface as ServiceUnavailableError — the caller
degrades cleanly instead of fabricating a result.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import ServiceUnavailableError


class ModelServerClient:
    def __init__(self, client: Any, *, predict_path: str = "/predict") -> None:
        self._client = client  # httpx-like AsyncClient bound to the server URL
        self._predict_path = predict_path

    async def predict(self, payload: dict[str, Any]) -> Any:
        """POST the payload to the predict endpoint and return the JSON reply."""
        try:
            response = await self._client.post(self._predict_path, json=payload)
        except Exception as exc:
            raise ServiceUnavailableError(
                message="Model server is unreachable",
                code="model_server_unavailable",
            ) from exc
        if response.status_code != 200:
            raise ServiceUnavailableError(
                message=f"Model server returned {response.status_code}",
                code="model_server_error",
            )
        return response.json()

    async def ping(self) -> bool:
        """Health probe — feeds a product's degraded-state reporting."""
        try:
            response = await self._client.get("/health")
        except Exception:
            return False
        return response.status_code == 200

    async def check(self) -> None:
        """Readiness check: raises when the server does not answer ``/health``.

        Shaped as a ``DependencyCheck`` so a product addon can register it with
        ``resources.health_checks.register("model_server", model.check)``.
        """
        if not await self.ping():
            raise ServiceUnavailableError(
                message="Model server is not healthy",
                code="model_server_unavailable",
            )


def build_httpx_model_server_client(base_url: str, *, timeout: float = 10.0) -> Any:
    """Shared httpx.AsyncClient bound to the server — own it in your domain
    runtime and close it in the runtime's close()."""
    import httpx

    return httpx.AsyncClient(base_url=base_url, timeout=timeout)
