## Why

- `S3ObjectGateway.open()` and `SQSQueueGateway.open()` only build the aioboto3
  client, which touches no network. A wrong endpoint, credentials, bucket or queue
  URL therefore surfaced on the first request, inside a handler, although the
  eager-open lifecycle exists to fail at boot.
- `SQSQueueGateway.nack(requeue=False)` left the message in place and relied on a
  RedrivePolicy on the queue that the template never verifies. Redis Streams and
  RabbitMQ dead-letter immediately (the worker uses `requeue=False` for
  non-retryable and malformed messages), so SQS behaved differently, and without a
  RedrivePolicy a poison message looped until retention expired.

## What Changes

- S3 `open()` creates the client, then calls `head_bucket(Bucket=...)`. SQS
  `open()` calls `get_queue_attributes(QueueUrl=..., AttributeNames=["QueueArn"])`.
  On failure the client is closed and a `RuntimeError` naming the bucket/queue and
  endpoint is raised from the original error.
- New optional setting `SQS_DEAD_LETTER_QUEUE_URL` (default empty). When set,
  `nack(requeue=False)` sends the original body to that queue with message
  attributes `reason`, `original_message_id` and `receive_count`, then deletes the
  original; a failed send leaves the original in place. When unset the behavior is
  unchanged and the work queue's own RedrivePolicy must be configured (now stated
  in the `nack` docstring). `nack(requeue=True)` is unchanged: visibility timeout
  set to 0.

## Capabilities

### New Capabilities

- `core/lifecycle-aws-fail-fast`: S3 and SQS verify their target when opened.
- `messaging/queue-sqs-dead-letter`: explicit dead-letter destination for SQS.

### Modified Capabilities

None.

## Impact

- Code: `app/modules/platform/objects/adapters/s3.py`,
  `app/modules/messaging/queue/adapters/sqs.py`, `queue/factory.py`,
  `app/core/config/messaging.py`, `.env.example`; tests under `tests/unit/modules/`.
- **Behavior change, failure timing**: with `OBJECT_BACKEND=s3` or
  `QUEUE_BACKEND=sqs`, a missing/forbidden bucket or queue (or bad endpoint or
  credentials) now fails startup (API lifespan and worker) instead of the first
  use. The IAM identity needs `s3:ListBucket` (HeadBucket) and
  `sqs:GetQueueAttributes` on the target. A DLQ URL additionally needs
  `sqs:SendMessage` on the DLQ. The DLQ queue itself is not verified at open.
  This supersedes the note in `fallback-chain-and-eager-clients` that SQS/S3 open
  only builds the client.
- CI: new `aws-adapters` job runs the env-gated real-server tests
  (`SQS_TEST_ENDPOINT_URL`, `S3_TEST_ENDPOINT_URL`) against ElasticMQ and
  LocalStack.
- Not changed: the `QueueGateway` and `ObjectGateway` contracts; pyright still
  excludes `sqs.py` and `s3.py` (optional-import `None` fallbacks).
