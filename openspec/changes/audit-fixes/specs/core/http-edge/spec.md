## ADDED Requirements

### Requirement: Database URL survives any password

`POSTGRES_URL` SHALL be built with SQLAlchemy's `URL.create` so that user, password and database containing `@`, `/`, `:`, `#`, `%` or spaces round-trip through `make_url`.

#### Scenario: Reserved characters
- **WHEN** the password contains `@`, `/`, `:` and `#`
- **THEN** `make_url(settings.POSTGRES_URL)` yields the configured host, port, user, password and database

### Requirement: Request ids are validated

An incoming `X-Request-ID` SHALL be used only when it matches `[A-Za-z0-9._-]{1,128}`; otherwise a generated id SHALL be used. The response header SHALL carry the id in use.

#### Scenario: Injection attempt
- **WHEN** the header contains spaces or `=`
- **THEN** a generated `req_...` id is used in the log and the response

#### Scenario: Valid id
- **WHEN** the header is `abc-123`
- **THEN** it is used unchanged

### Requirement: Oversize bodies always get 413

A request body larger than `MAX_REQUEST_BODY_BYTES` SHALL get 413 with the standard envelope whether or not it declares `Content-Length`.

#### Scenario: Chunked upload
- **WHEN** a body without `Content-Length` exceeds the limit
- **THEN** the response is 413, not 400

### Requirement: Exclude patterns match path segments

A request-timeout or rate-limit exclude pattern SHALL match a path only when the pattern's segments appear as consecutive whole segments of the path.

#### Scenario: Whole segment
- **WHEN** the pattern is `/stream`
- **THEN** `/api/v1/completions/stream` is excluded and `/api/v1/streamers/1` is not

### Requirement: Every response is logged and carries edge headers

Middleware order, outermost first, SHALL be: request id, access log, CORS, security headers, trusted host, IP rate limit, request timeout, gzip, in-flight tracker, body limit. The access log SHALL record the status the client received.

#### Scenario: Timeout
- **WHEN** a request exceeds the request timeout
- **THEN** the client gets 504 and the access log line says `status=504`

#### Scenario: Rate limited
- **WHEN** the IP limiter rejects a request from an allowed origin
- **THEN** the 429 is access-logged and carries CORS and security headers

#### Scenario: Preflight
- **WHEN** a CORS preflight arrives
- **THEN** it is answered by the CORS layer and does not consume rate-limit budget
