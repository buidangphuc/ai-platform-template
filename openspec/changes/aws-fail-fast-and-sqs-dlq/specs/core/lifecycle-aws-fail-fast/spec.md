## ADDED Requirements

### Requirement: S3 and SQS verify their target when opened
`S3ObjectGateway.open()` SHALL verify the bucket with one `head_bucket` call and `SQSQueueGateway.open()` SHALL verify the queue with one `get_queue_attributes` call requesting `QueueArn`. When the call fails, `open()` SHALL close the client it created and raise a `RuntimeError` that names the bucket or queue URL and the endpoint, chained from the original error.

#### Scenario: Missing bucket at boot
- **WHEN** `OBJECT_BACKEND=s3` and the bucket does not exist
- **THEN** opening the object gateway raises `RuntimeError` naming the bucket and the client is closed

#### Scenario: Wrong queue URL at boot
- **WHEN** `QUEUE_BACKEND=sqs` and the queue does not exist or the endpoint is unreachable
- **THEN** opening the queue gateway raises `RuntimeError` naming the queue URL and the client is closed

#### Scenario: Reachable target
- **WHEN** the bucket or queue exists and the credentials allow the verification call
- **THEN** `open()` returns the gateway ready for use
