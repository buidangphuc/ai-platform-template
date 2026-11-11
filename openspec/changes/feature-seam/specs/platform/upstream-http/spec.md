## ADDED Requirements

### Requirement: Named upstream clients

A feature SHALL declare `Upstream(name, base_url, timeout, retries, headers, follow_redirects)`. Bootstrap SHALL open one `httpx.AsyncClient` per upstream of every enabled feature, expose it as `resources.http(name)` (an `UpstreamClient`), and close it with the runtime. A duplicate name SHALL fail at startup; an unknown name SHALL raise `ServiceUnavailableError`.

#### Scenario: Two upstreams are isolated
- **WHEN** upstream `a` fails until its breaker opens
- **THEN** calls to `a` raise `ServiceUnavailableError` with code `upstream_unavailable` and calls to upstream `b` still succeed

### Requirement: Resilience and tracing on every call

`UpstreamClient` SHALL apply the upstream's timeout, retry only transient failures up to `retries` using `RetryPolicy`, trip a per-upstream `CircuitBreaker`, send `X-Request-ID` from `get_request_id()`, and log one line per call without bodies or auth headers.

#### Scenario: Transient failure is retried
- **WHEN** an upstream returns `503` once and then `200` with `retries=1`
- **THEN** the call returns the `200` response

#### Scenario: Deterministic error is not retried
- **WHEN** an upstream returns `404`
- **THEN** the response is returned at once and the breaker is not charged
