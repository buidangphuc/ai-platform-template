## 1. Fail fast at open

Owns: `app/modules/platform/objects/adapters/s3.py`, `app/modules/messaging/queue/adapters/sqs.py`

- [x] 1.1 S3 `open()` verifies the bucket with `head_bucket`; failure closes the client and raises
- [x] 1.2 SQS `open()` verifies the queue with `get_queue_attributes(QueueArn)`; failure closes the client and raises
- [x] 1.3 Verify: `uv run --all-extras pytest -q tests/unit/modules/objects/test_s3.py tests/unit/modules/queues/test_sqs.py` (fakes)

## 2. SQS dead-letter parity

Owns: `sqs.py`, `queue/factory.py`, `app/core/config/messaging.py`, `.env.example`

- [x] 2.1 Setting `SQS_DEAD_LETTER_QUEUE_URL`, passed from `open_queue_gateway`
- [x] 2.2 `nack(requeue=False)` with a DLQ URL: send with attributes, then delete; docstring states the RedrivePolicy requirement otherwise
- [x] 2.3 Verify: same unit tests

## 3. Real-server verification

Owns: `tests/unit/modules/queues/test_sqs_real.py`, `tests/unit/modules/objects/test_s3_real.py`, `.github/workflows/test.yml` (new job)

- [x] 3.1 Env-gated tests (`SQS_TEST_ENDPOINT_URL`, `S3_TEST_ENDPOINT_URL`): redrive after `maxReceiveCount`, explicit DLQ with attributes, open fails for unknown queue/bucket, open succeeds for an existing bucket
- [x] 3.2 CI job `aws-adapters` with ElasticMQ and LocalStack service containers
- [x] 3.3 Verify: ran against `softwaremill/elasticmq-native:1.6.9` and `localstack/localstack:3.8`
