# messaging/worker-entry Specification

## Purpose
What the worker entry point accepts, how worker settings are validated, and which addons the worker opens.

## Requirements

### Requirement: Worker entry point takes no arguments

`python -m scripts.run_worker` SHALL start the worker and SHALL reject every command-line argument with a non-zero exit. Worker settings SHALL be validated when the worker starts (`validate_worker_runtime_settings` inside `worker_context`), not by a separate mode.

#### Scenario: Unknown argument
- **WHEN** the entry point is called with `--check` or any other argument
- **THEN** it exits non-zero with `unknown arguments: ...` and starts nothing

#### Scenario: Invalid settings at start
- **WHEN** `worker_context` is entered with `TASKS_ENABLED` false
- **THEN** it raises before any resource is opened

### Requirement: Worker and API open the same addons

`worker_context` SHALL always open `default_resource_addons()`; it SHALL NOT accept an addon list of its own.

#### Scenario: Worker opens the default addons
- **WHEN** `worker_context(settings, features=...)` is entered
- **THEN** the resources it yields were opened with `default_resource_addons()`

### Requirement: Rate limiter is built by its constructor

The rate-limit addon SHALL build `RedisRateLimiter(redis=, limit=, window_seconds=, prefix=)` directly. Limits, window, key prefix and the 429 response SHALL be unchanged.

#### Scenario: Limit still enforced
- **WHEN** `RATE_LIMIT_ENABLED` is true and a principal exceeds its limit inside one window
- **THEN** the request is rejected with 429 as before
