## 1. RabbitMQ redelivery and dead-lettering

Owns: `app/modules/messaging/queue/adapters/rabbitmq.py`, `tests/unit/modules/queues/test_rabbitmq.py`

- [x] 1.1 Derive `receive_count` from `x-delivery-count`, `x-attempt` and `redelivered`
- [x] 1.2 Requeue = republish with `x-attempt + 1`, then ack the original
- [x] 1.3 Declare DLX + DLQ and attach `x-dead-letter-*` arguments to the work queue
- [x] 1.4 Verify: `uv run --all-extras pytest -q tests/unit/modules/queues/test_rabbitmq.py` (fake `aio_pika`); smoke-tested on `rabbitmq:3-management`

## 2. Redis Streams reclaim and dead stream

Owns: `app/modules/messaging/queue/adapters/redis_stream.py`, `tests/unit/modules/queues/test_redis_stream.py`

- [x] 2.1 Stable consumer name (setting, then `HOSTNAME`, then random)
- [x] 2.2 `XAUTOCLAIM` before `XREADGROUP`; delivery count from `XPENDING`
- [x] 2.3 Requeue via `XCLAIM IDLE` (no re-add); dead-letter via `MULTI/EXEC` `XADD` + `XACK`
- [x] 2.4 Non-blocking read when `wait_seconds=0` (was `BLOCK 0`)
- [x] 2.5 Verify: `uv run --all-extras pytest -q tests/unit/modules/queues/test_redis_stream.py` (fakeredis supports XAUTOCLAIM/XPENDING; it over-counts on `XCLAIM JUSTID`, so the exact `[1, 2, 3]` sequence was verified on real `redis:7`)

## 3. Settings and wiring

Owns: `app/core/config/messaging.py`, `.env.example`, `app/modules/messaging/queue/factory.py`

- [x] 3.1 Add `RABBITMQ_DEAD_LETTER_*` and `QUEUE_REDIS_*` settings with bounds
- [x] 3.2 Mirror them in `.env.example`
- [x] 3.3 Pass them from `build_queue_gateway` into the adapters
- [x] 3.4 Verify: `uvx pre-commit run --files <changed>` (includes `check-env-example`)
