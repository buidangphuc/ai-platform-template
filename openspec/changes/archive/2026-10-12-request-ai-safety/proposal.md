## Why

An audit of the completions path and its AI-adjacent surface found gaps that let
clients or retrieved content steer the model, and left the HTTP edge unreliable:

- Clients could send `role="system"`: direct prompt injection by design.
- No request bounds (message count, content length, metadata size); unknown
  fields were silently ignored.
- The result contract had no token usage or finish reason.
- No seam to plug in input/output guardrails.
- RAG returned retrieved text raw to the model, with an unbounded `top_k`.
- Redaction skipped strings inside lists and missed common secrets and PII.
- Unhandled exceptions produced a plain-text 500 without the error envelope or
  request id.
- The per-IP rate limit keyed on the client-controlled leftmost
  `X-Forwarded-For`, so it was trivially bypassed.
- The LLM judge prompt inlined the graded output, which could steer the judge.

## What Changes

- **BREAKING** `CompletionRole` is `user | assistant`; `system` is rejected with
  422. The server owns the system prompt (handler/factory).
- **BREAKING** `CompletionRequest`/`CompletionMessage` forbid extra fields.
  Bounds: at most 64 messages, 32,000 characters per message, 32 metadata keys
  and 4,096 serialized metadata bytes (constants in `business/completions/schemas.py`).
- `CompletionResult`/`CompletionResponse` gain `usage` (`input_tokens`,
  `output_tokens`, `total_tokens`) and `finish_reason`, both optional. The echo
  handler fills them. Streaming usage is out of scope.
- `CompletionService(handler, guards=())`: `CompletionGuard` protocol with
  `check_input` / `check_output`, `GuardrailViolation` (422, codes
  `guardrail_input_violation` / `guardrail_output_violation`), fail-closed.
  `compose_business_services` / `open_runtime` take a `completion_guards_factory`.
  Streaming runs input guards only.
- `knowledge_search` wraps each match in `<document id=... source="retrieved">`,
  neutralises an embedded closing tag, states in its description that content is
  untrusted data, and bounds `top_k` to 20.
- `RedactionPolicy` redacts strings inside lists, more secret keys
  (`authorization`, `cookie`/`set-cookie`, `apikey`, `x-api-key`), and masks
  phone numbers (Vietnamese and international), Luhn-valid card numbers and AWS
  access key ids.
- A catch-all `Exception` handler logs the stack trace and returns the
  `internal_server_error` envelope with `request_id` and `X-Request-ID`.
- New setting `TRUSTED_PROXY_COUNT` (default 0): `X-Forwarded-For` is ignored
  unless N > 0, then the address N hops from the right is used.
- The LLM judge wraps criteria and output in tags and tells the judge to ignore
  instructions inside them.

## Capabilities

### New Capabilities

- `api/completions-safety`: request contract, usage fields and guardrail seam of
  the completions API. (Added as a new capability because `api/completions` from
  `bootstrap-single-owner` is not archived yet.)
- `ai/rag`: how retrieved content is presented to the model.
- `core/http-safety`: unhandled-error envelope and client address for rate limiting.
- `core/redaction`: what the redaction policy masks.
- `ai/evals`: judge prompt shape.

### Modified Capabilities

None.

## Impact

- Code: `app/modules/business/completions/**`, `app/api/v1/completions/sync.py`,
  `app/bootstrap/{services,middleware}.py`, `app/core/{errors,redaction,middleware}.py`,
  `app/core/config/http.py`, `app/modules/ai/rag/tools.py`,
  `app/modules/ai/evals/evaluators.py`, `evals/completions_smoke.jsonl`, `.env.example`.
- Clients sending `system` messages or unknown fields get 422. Task payloads
  persisted with a `system` message fail validation in the worker and are marked failed.
- Behind a proxy, set `TRUSTED_PROXY_COUNT` to the number of proxies, or every
  client shares the proxy's address in the IP rate limit.
- `create_app` does not yet forward `completion_guards_factory`; products wire
  guards through `open_runtime`/`compose_business_services` until `application.py` is updated.
- Unverified: guard output on streams; real-proxy `X-Forwarded-For` behaviour.
