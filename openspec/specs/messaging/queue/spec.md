# messaging/queue Specification

## Purpose
Defines how the RabbitMQ and Redis Streams queue backends report redelivery and
handle messages that cannot be processed, so the worker's retry limit is
effective on every backend.

## Requirements

### Requirement: Redelivery count is accurate per backend

The queue gateway SHALL report, in each received message's receive count, the
number of times that message has been delivered, counting the current delivery.
A first delivery SHALL report 1, and every redelivery (requeue by the consumer, or
reclaim after a consumer failure) SHALL report a strictly higher value than the
previous delivery of the same message.

#### Scenario: RabbitMQ requeue increments the count
- **WHEN** a consumer receives a RabbitMQ message and nacks it with requeue, repeatedly
- **THEN** successive deliveries report 1, 2, 3, and so on

#### Scenario: RabbitMQ quorum queue delivery count is honored
- **WHEN** a RabbitMQ message arrives carrying a broker delivery count of N
- **THEN** its receive count is at least N + 1

#### Scenario: Redis requeue increments the count
- **WHEN** a consumer receives a Redis Streams entry and nacks it with requeue, repeatedly
- **THEN** successive deliveries of the same entry report 1, 2, 3, and so on

### Requirement: Messages exceeding max attempts go to a dead-letter destination

A message that a consumer rejects without requeue, or that a Redis Streams
backend has delivered more than the configured maximum number of times, SHALL be
moved to a dead-letter destination and SHALL NOT be delivered again. The
RabbitMQ dead-letter exchange and queue SHALL default to names derived from the
work queue name, be configurable, and be disableable. The Redis dead-letter
destination SHALL be a stream named after the work stream with a `:dead` suffix,
and moving an entry there SHALL be atomic with acknowledging it.

#### Scenario: RabbitMQ rejection lands in the dead-letter queue
- **WHEN** a consumer nacks a RabbitMQ message without requeue
- **THEN** the message is routed to the dead-letter queue and the work queue no longer holds it

#### Scenario: Redis rejection lands in the dead stream
- **WHEN** a consumer nacks a Redis Streams entry without requeue
- **THEN** the entry's payload and original id are appended to the dead stream and the entry is no longer pending

#### Scenario: Redis entry over the delivery maximum is dead-lettered
- **WHEN** a Redis Streams entry is reclaimed after more deliveries than the configured maximum
- **THEN** it is moved to the dead stream with its delivery count instead of being returned to a consumer

### Requirement: A crashed consumer's pending messages are reclaimed after min-idle

The Redis Streams backend SHALL, on every receive, first claim pending entries
that have been idle longer than the configured minimum idle time, regardless of
which consumer last held them, and deliver them before new entries. The consumer
identity SHALL be stable across restarts when the configured name or the host
name is available. Entries idle for less than the minimum SHALL NOT be claimed.

#### Scenario: Abandoned entry is reclaimed by another consumer
- **WHEN** one consumer receives an entry and never acknowledges it, and another consumer receives after the minimum idle time has passed
- **THEN** the second consumer is delivered the same entry with a receive count of at least 2

#### Scenario: Recently delivered entry is left alone
- **WHEN** a consumer receives an entry and a receive happens before the minimum idle time has passed
- **THEN** the entry is not delivered again

#### Scenario: Consumer name is stable
- **WHEN** no consumer name is configured and the host name environment variable is set
- **THEN** the consumer uses the host name as its identity
