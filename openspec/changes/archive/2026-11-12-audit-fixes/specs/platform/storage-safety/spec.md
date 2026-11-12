## ADDED Requirements

### Requirement: Cache values are bytes in and bytes out

The cache opened by the cache addon SHALL return exactly the bytes that were stored, for any byte string. The addon SHALL use its own Redis client with response decoding off and close it on the stack; other capabilities keep the shared decoding client.

#### Scenario: Non-UTF-8 payload through bootstrap
- **WHEN** the cache addon is opened and `set` stores bytes that are not valid UTF-8
- **THEN** `get` and `get_many` return the same bytes

### Requirement: S3 list stays inside its prefix

`list` SHALL only return keys under `<prefix>/` and SHALL follow continuation tokens until `limit` keys are collected.

#### Scenario: Sibling prefix
- **WHEN** the bucket holds `app/a` and `app-staging/b` and the store prefix is `app`
- **THEN** `list()` returns `a` only

#### Scenario: More than one page
- **WHEN** more than 1000 keys exist under the prefix and `limit` is 1500
- **THEN** 1500 keys are returned

### Requirement: Redaction does not corrupt ordinary text

`RedactionPolicy` SHALL NOT rewrite decimal numbers, dates or times as phone numbers, SHALL NOT treat keys such as `max_tokens` or `input_tokens` as secrets, and SHALL NOT raise on a non-string mapping key. Existing redactions (emails, cards, bearer tokens, AWS key ids, secret-named keys, Vietnamese and E.164 phone numbers) SHALL be unchanged.

#### Scenario: Numbers and dates
- **WHEN** the text contains `0.123456789` and `01-02-2026 12:30`
- **THEN** it is returned unchanged

#### Scenario: Token counts
- **WHEN** a mapping has `max_tokens: 2048`
- **THEN** the value is kept

#### Scenario: Non-string key
- **WHEN** a nested mapping has an integer key
- **THEN** redaction completes without an exception

#### Scenario: Real phone numbers
- **WHEN** the text contains `0912345678` or `+84 912 345 678`
- **THEN** each is replaced by `[phone]`
