# core/http-safety Specification

## Purpose
Error envelope for unhandled failures and the client address used for per-IP rate limiting.

## Requirements

### Requirement: Unhandled exceptions use the error envelope

An unhandled exception SHALL be logged with its stack trace and answered with status 500, code
`internal_server_error`, the request id in the body and in the `X-Request-ID` header, and no
exception detail.

#### Scenario: Route raises
- **WHEN** a route raises an unexpected exception
- **THEN** the response is a 500 JSON envelope with the request id and without the exception message

### Requirement: Forwarded client address is trusted only through known proxies

The per-IP rate limit SHALL use the socket peer address unless `TRUSTED_PROXY_COUNT` is greater than
0. Then it SHALL use the `X-Forwarded-For` entry that many hops from the right, and the peer address
when the chain is shorter than that.

#### Scenario: Spoofed header ignored by default
- **WHEN** `TRUSTED_PROXY_COUNT` is 0 and a request carries `X-Forwarded-For: 6.6.6.6`
- **THEN** the rate limit key is the socket peer

#### Scenario: One trusted proxy
- **WHEN** `TRUSTED_PROXY_COUNT` is 1 and the header is `6.6.6.6, 1.2.3.4`
- **THEN** the rate limit key is `1.2.3.4`
