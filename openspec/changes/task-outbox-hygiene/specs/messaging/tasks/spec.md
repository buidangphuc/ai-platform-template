## ADDED Requirements

### Requirement: Reclaim is capped by attempts

Reclaiming an expired-lease PROCESSING task whose `attempts` is at least
`TASKS_MAX_ATTEMPTS` SHALL set it to FAILED with error `max_attempts_exceeded`
and SHALL NOT announce it again. Tasks under the cap SHALL be requeued and
announced as before. One pass SHALL settle at most the batch size of tasks,
failed and requeued together. A FAILED task SHALL NOT be claimable.

#### Scenario: Worker crashes on every attempt
- **WHEN** a task has been claimed `TASKS_MAX_ATTEMPTS` times and its lease expired again
- **THEN** reclaim marks it FAILED with `max_attempts_exceeded`, publishes no new task message, and a later claim returns false

#### Scenario: Task under the cap
- **WHEN** an expired-lease task has fewer attempts than the cap
- **THEN** it is QUEUED and announced again

### Requirement: The worker purges expired tasks and old published outbox events

While the worker runs, it SHALL periodically delete tasks past `expires_at` and,
when the outbox is enabled, outbox events with status published older than
`OUTBOX_RETENTION_SECONDS`. Deletes SHALL be bounded batches that repeat until a
batch is short. Pending and failed outbox events SHALL NOT be deleted. The loop
SHALL stop with the worker and continue after a failed iteration.

#### Scenario: Old published events
- **WHEN** published outbox events older than the retention exist alongside recent published, pending and failed ones
- **THEN** only the old published ones are deleted, at most the batch size per statement

#### Scenario: Backlog larger than a batch
- **WHEN** more expired rows exist than the batch size
- **THEN** one cleanup tick deletes them over several batches
