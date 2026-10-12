# platform/identity Specification

## Purpose
How requests authenticate: hashed API keys from AUTH_API_KEYS, validated at startup, resolved to a principal.

## Requirements

### Requirement: Requests authenticate with a configured API key

A request SHALL authenticate only when the SHA-256 digest of its bearer token
equals the digest of an `AUTH_API_KEYS` entry. The resulting principal SHALL have
`id` equal to the entry's subject and `scopes` equal to the entry's scopes; an
entry without scopes SHALL grant none. The comparison SHALL be constant-time and
SHALL examine every entry. Several entries MAY share a subject. With no keys
configured, protected routes SHALL answer `auth_not_configured`; a missing,
non-bearer or unknown token SHALL answer 401.

#### Scenario: Overlap rotation
- **WHEN** two entries share the subject `alice` and clients present either token
- **THEN** both authenticate as principal `alice`

#### Scenario: No implicit privilege
- **WHEN** an entry lists no scopes
- **THEN** its principal has no scopes and fails `require_scopes("admin")`

### Requirement: AUTH_API_KEYS is validated at startup

A malformed entry (missing field, empty subject, digest not 64 hex characters)
SHALL fail settings construction in every environment. Outside dev/local/test at
least one key SHALL be configured, and in production an entry whose digest is a
known placeholder token SHALL be rejected.

#### Scenario: Placeholder token in production
- **WHEN** `ENVIRONMENT=production` and a key hashes `change-me-local-bearer-token`
- **THEN** settings construction fails naming `AUTH_API_KEYS`
