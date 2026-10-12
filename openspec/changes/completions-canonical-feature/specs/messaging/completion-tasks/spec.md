## Purpose

Completion tasks scoped by type and stored with their full result.

## ADDED Requirements

### Requirement: Completion task routes are type-scoped

`COMPLETION_TASK_TYPE` SHALL be defined in `app/modules/business/completions/schemas.py`. `TaskService.require_owned` SHALL take the expected `type` and report not-found on mismatch.

#### Scenario: Another task type
- **WHEN** a principal requests `GET /api/v1/completions/tasks/{id}` for a task of another type they own
- **THEN** the response is `404 task_not_found`

### Requirement: Worker keeps the full result

The worker SHALL store `CompletionResult.model_dump(mode="json")` as the task result.

#### Scenario: Usage survives the queue
- **WHEN** a completion task finishes
- **THEN** its stored result includes `usage` and `finish_reason`
