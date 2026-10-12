## Purpose

Correlating worker logs with the HTTP request that submitted a task.

## ADDED Requirements

### Requirement: Task messages carry the submitting request id

`TaskMessage` SHALL accept an optional non-empty `request_id`, omit it from the body
when absent, and keep rejecting any other unknown field. `TaskService.submit` SHALL
take the request id as an explicit argument and pass it to the dispatcher; business
code SHALL NOT read the HTTP request context itself.

#### Scenario: Submit with a request id
- **WHEN** a task is submitted with `request_id="req_abc"`
- **THEN** the queued message body is `{"task_id": ..., "type": ..., "request_id": "req_abc"}`

#### Scenario: Message without a request id
- **WHEN** a task is re-announced by the reclaim loop
- **THEN** the message body has no `request_id` key and the worker still processes it

### Requirement: Worker logs carry the request id

The worker SHALL set the request-id context for the duration of a message that has a
`request_id`, and restore it afterwards.

#### Scenario: Worker processes a task
- **WHEN** the worker handles a message with `request_id="req_abc"`
- **THEN** the completion runs with the request id `req_abc` and the id is `-` again after the message
