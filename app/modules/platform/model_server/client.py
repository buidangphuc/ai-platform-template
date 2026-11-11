"""HTTP client for a self-hosted model server — the platform half of the
contract with the ML pipeline template's serving image.

The ML template (`datasience`) serves:

    POST /predict  {"text": "..."}            -> {"label": "...", "score": 0.97}
    POST /predict  {"texts": ["...", "..."]}  -> [{"label": ..., "score": ...}, ...]
    GET  /health                              -> {"status": "ok"}
    GET  /metrics                             -> Prometheus text

Any server speaking an HTTP predict contract fits. The client takes an
``UpstreamClient`` (timeout, retry, breaker and request-id tracing come from
it); a feature declares the ``Upstream`` and builds the client in ``build``::

    upstreams = (Upstream("model_server", lambda s: s.MY_MODEL_URL, retries=1),)
    build = lambda res, s: MyService(ModelServerClient(res.http("model_server")))

Unreachable/erroring servers surface as ServiceUnavailableError — the caller
degrades cleanly instead of fabricating a result.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import ServiceUnavailableError
from app.modules.platform.http.upstream import UpstreamClient


class ModelServerClient:
    def __init__(
        self, client: UpstreamClient, *, predict_path: str = "/predict"
    ) -> None:
        self._client = client
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
