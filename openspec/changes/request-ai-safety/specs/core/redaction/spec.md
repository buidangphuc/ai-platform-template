## Purpose

What `RedactionPolicy` masks in `redacted` mode.

## ADDED Requirements

### Requirement: Redaction covers lists, secret keys and common PII

In `redacted` mode the policy SHALL redact strings nested in lists, mask values of keys containing
`authorization`, `cookie`, `api_key`, `apikey`, `x-api-key`, `token`, `password`, `secret` or
`pepper`, and mask email addresses, bearer and `sk-` secrets, AWS access key ids (`AKIA…`), phone
numbers (including Vietnamese `0xxxxxxxxx` and `+84…`) and Luhn-valid 13 to 19 digit card numbers.

#### Scenario: String inside a list
- **WHEN** a mapping contains a list with an email address
- **THEN** the address is masked

#### Scenario: Vietnamese phone number
- **WHEN** text contains `0912345678` or `+84 912 345 678`
- **THEN** it is replaced by `[phone]`

#### Scenario: Digits that are not a card
- **WHEN** text contains a 16-digit number that fails the Luhn check
- **THEN** it is left unchanged
