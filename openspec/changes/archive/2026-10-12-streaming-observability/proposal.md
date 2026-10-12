## Why

An audit of the completions stream and the shutdown path found that a client could
not rely on either:

- `CompletionHandler.stream` returned `CompletionStreamChunk | str`, so the API
  normalised with an `isinstance` check for a case no handler needs.
- An input-guard violation (or a handler startup error) is raised on the first
  iteration, after `StreamingResponse` already sent `200`; the client saw a broken
  stream instead of the 422 JSON error.
- No SSE hygiene: proxies buffered the stream, idle connections were closed, a
  mid-stream failure raised out of the response, and nothing bounded how long a
  stream could wait on the model.
- Streamed completions carried no token usage or finish reason.
- On shutdown `/readyz` kept returning `200` while in-flight requests drained, and
  the container did not pass a graceful-shutdown timeout to uvicorn.
- Langfuse flush used a `hasattr`/`None` dance on the global client.
- Worker logs showed `req=-` because task messages carried no request id.
- No per-completion log line (latency, tokens, model) existed.

## What Changes

- The `stream` port is `AsyncIterator[CompletionStreamChunk]`; `normalize_stream_chunk`
  is deleted. `CompletionStreamChunk` gains optional `model`, `usage`, `finish_reason`
  (the last chunk reports them). The echo handler fills them.
- The stream endpoint awaits the first chunk before it builds the response, so guard
  violations and handler startup errors return the normal JSON error.
- SSE: `Cache-Control: no-cache`, `X-Accel-Buffering: no`; `: ping` heartbeat every
  `SSE_HEARTBEAT_SECONDS` while waiting for a chunk; a mid-stream failure emits
  `event: error` with `{"type":"error","code":...}` (never exception text) and closes.
- Deadlines: `STREAM_FIRST_TOKEN_TIMEOUT_SECONDS` (before the first chunk: JSON 504,
  code `stream_timeout`) and `STREAM_IDLE_TIMEOUT_SECONDS` (after: `event: error`,
  code `stream_timeout`).
- The `done` event carries `usage`, `finish_reason` and `model` when the handler
  reported them. **Additive**: a handler that reports none still gets `{"type":"done"}`.
- Lifespan marks the `HealthService` draining before it drains in-flight requests;
  `/readyz` returns `503` (`status: "draining"`), `/healthz` is unaffected.
- **BREAKING (default)** `GRACEFUL_SHUTDOWN_ENABLED` defaults to `true` (was `false`):
  the in-flight tracker is cheap and rolling deploys need it. The Dockerfile `CMD`
  passes `--timeout-graceful-shutdown ${GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS:-30}`.
- Langfuse flush is one typed `get_client().flush()` guarded by `LANGFUSE_ENABLED`
  and the optional-extra import. The app has no owned tracker/client on
  `ApplicationResources` (the handler factory builds the `LLMInstance` privately), so
  the process-wide client is the only handle.
- `TaskMessage` gains an optional `request_id` (omitted from the body when `None`;
  `from_body` stays strict). `TaskService.submit(..., request_id=)` and
  `TaskDispatcher.submit(task, *, request_id=)` carry it; the API view passes
  `get_request_id()`. The worker sets the request-id ContextVar while it processes
  the message. Reclaimed tasks are re-announced without a request id.
- One structured log line per completion (sync and stream): `mode`, `outcome`,
  `model`, `duration_ms`, `ttft_ms` (stream), `finish_reason`, token counts. No
  prompt or output content.

## Capabilities

### New Capabilities

- `api/completions-streaming`: the SSE contract of `POST /completions/stream` and the
  per-completion log line. (New capability because earlier completions changes are
  not archived yet.)
- `core/health`: readiness while draining, graceful-shutdown wiring.
- `messaging/tasks-tracing`: request-id propagation from submit to worker.

### Modified Capabilities

None.

## Impact

- Code: `app/api/v1/completions/**` (new `streaming.py`, `observability.py`),
  `app/modules/business/completions/{ports,service,schemas,handlers/echo}.py`,
  `app/bootstrap/{application,worker}.py`, `app/core/{health}.py`,
  `app/core/config/{http,runtime}.py`, `app/modules/messaging/tasks/{message,service,outbox}.py`
  (`outbox.py`: pass `request_id` through the dispatcher protocol), `Dockerfile`, `.env.example`.
- Custom handlers must yield `CompletionStreamChunk` (a bare `str` no longer type-checks
  and is not accepted at runtime).
- Clients reading the stream should ignore SSE comment lines (`: ping`) and handle
  `event: error`.
- Keep the pod's `terminationGracePeriodSeconds` above twice
  `GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS`: uvicorn waits for connections first, then the
  lifespan drains.
- Unverified: with uvicorn, listeners close and connections drain before the lifespan
  shutdown runs, so `/readyz` returning `503` while draining is only observable on
  servers that keep serving during lifespan shutdown (and in tests); a k8s `preStop`
  delay remains the way to take a pod out of rotation before SIGTERM.
- Follow-up: OpenTelemetry tracing/metrics replaces the log line as the completion
  observability story; output guards on streamed chunks are still not applied.
