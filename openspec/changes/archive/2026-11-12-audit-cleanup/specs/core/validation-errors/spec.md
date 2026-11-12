## ADDED Requirements

### Requirement: Validation errors carry the template's messages

A request that fails validation SHALL get status 422 with the standard error envelope, `code` `validation_error`, `message` `Request validation failed`, and `data` set to the Pydantic error list where `msg` is replaced by the entry of `PYDANTIC_ERROR_MESSAGES` for that error `type`, formatted with the error's `ctx`. An error type without an entry SHALL keep Pydantic's `msg`. A template whose placeholders are missing from `ctx` SHALL be used unformatted.

#### Scenario: Missing field
- **WHEN** a request body omits a required field
- **THEN** the response is 422 and the entry for that field has `type` `missing`, its `loc`, and `msg` equal to `PYDANTIC_ERROR_MESSAGES["missing"]`

#### Scenario: Message formatted from ctx
- **WHEN** a string field is shorter than its `min_length`
- **THEN** `msg` is the `string_too_short` template with the limit filled in

#### Scenario: Unknown error type
- **WHEN** `format_validation_errors` gets an error whose `type` has no entry
- **THEN** its `msg` is unchanged

#### Scenario: Placeholder missing from ctx
- **WHEN** `format_validation_errors` gets a known `type` with an empty `ctx`
- **THEN** `msg` is the unformatted template and no exception is raised
