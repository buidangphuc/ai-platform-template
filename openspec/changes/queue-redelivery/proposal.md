## Why

Two queue adapters break the worker's retry contract. The worker nacks with
`requeue = message.receive_count < max_attempts`, which only works if the adapter
reports an accurate `receive_count`.

- **RabbitMQ** never set `receive_count`, so it stayed at 1: the worker always
  requeued, and a poison message redelivered forever. No dead-letter exchange
  existed either.
- **Redis Streams** only read new entries (`>`), so entries left pending by a
  crashed consumer were orphaned forever (and the consumer name was random per
  process, so a restarted pod could not resume its own entries). Requeue was
  `XACK` then `XADD` as two separate commands, so a crash between them lost the
  message.

## What Changes

- RabbitMQ: derive `receive_count` from the `x-delivery-count` header (quorum
  queues), the adapter's own `x-attempt` header, and the broker `redelivered`
  flag, taking the highest. Requeue republishes with `x-attempt + 1` and acks the
  original (classic queues reset counters on nack-requeue). Declare a
  dead-letter exchange + queue derived from the queue name; `nack(requeue=False)`
  lands in the DLQ.
- Redis Streams: stable consumer name (setting, else `$HOSTNAME`, else random).
  Every `receive` first runs `XAUTOCLAIM` for entries idle longer than a
  configurable minimum and maps the stream's delivery counter (`XPENDING`) to
  `receive_count`. Entries delivered more than a configurable maximum, and
  entries nacked with `requeue=False`, move to `<stream>:dead` in one
  `MULTI/EXEC` with the `XACK`.
- Redis requeue no longer re-adds the entry. It keeps the entry pending and marks
  it idle (`XCLAIM ... IDLE <min-idle> JUSTID`) so the next receive reclaims it
  immediately. One command, same entry id, delivery counter preserved by Redis:
  simpler and atomic compared with a transaction that re-adds a copy and has to
  smuggle a counter in the payload.
- New settings: `RABBITMQ_DEAD_LETTER_ENABLED`, `RABBITMQ_DEAD_LETTER_EXCHANGE`,
  `RABBITMQ_DEAD_LETTER_QUEUE`, `QUEUE_REDIS_CONSUMER_NAME`,
  `QUEUE_REDIS_MIN_IDLE_SECONDS` (default 60), `QUEUE_REDIS_MAX_DELIVERIES`
  (default 5).
- Behavior notes: Redis requeued messages keep their entry id and no longer carry
  `original_message_id` in the body. Also fixed: a non-blocking receive
  (`wait_seconds=0`) previously passed `BLOCK 0`, which Redis treats as "block
  forever".

Not changed: `QueueMessage.receive_count` contract, `queue/worker.py`,
`queue/gateway.py`.

## Capabilities

### New Capabilities

- `messaging/queue`: delivery semantics of the queue gateway backends
  (redelivery count, dead-lettering, reclaim of abandoned messages).

### Modified Capabilities

None.

## Impact

- Code: `app/modules/messaging/queue/adapters/{rabbitmq,redis_stream}.py`,
  `queue/factory.py`, `app/core/config/messaging.py`, `.env.example`.
- Operations: RabbitMQ rejects re-declaring an existing queue with different
  arguments (`PRECONDITION_FAILED`). Deployments with an existing work queue must
  either delete/recreate it or set `RABBITMQ_DEAD_LETTER_ENABLED=false`.
  `QUEUE_REDIS_MIN_IDLE_SECONDS` must exceed the slowest handler, or live work is
  reclaimed and run twice (delivery is at-least-once). Redis needs >= 6.2.
- Unverified: quorum-queue `x-delivery-count` path (needs a quorum queue; covered
  only by a unit test with a fake). Classic-queue RabbitMQ and Redis 7 were
  smoke-tested against real containers.
