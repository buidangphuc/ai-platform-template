## ADDED Requirements

### Requirement: S3 and SQS verify their target when opened
`S3ObjectGateway.open()` SHALL probe the bucket with one `list_objects_v2` call (app prefix, `MaxKeys=1`) and `SQSQueueGateway.open()` SHALL probe the queue with one `get_queue_attributes` call requesting `QueueArn`. When the probe is denied by policy (`AccessDenied`, `AccessDeniedException`, `AllAccessDisabled`, `Forbidden`), `open()` SHALL log a warning and succeed. On any other failure, `open()` SHALL close the client it created and raise a `RuntimeError` that names the bucket or queue URL and the endpoint, chained from the original error.

#### Scenario: Missing bucket at boot
- **WHEN** `OBJECT_BACKEND=s3` and the bucket does not exist
- **THEN** opening the object gateway raises `RuntimeError` naming the bucket and the client is closed

#### Scenario: Wrong queue URL at boot
- **WHEN** `QUEUE_BACKEND=sqs` and the queue does not exist or the endpoint is unreachable
- **THEN** opening the queue gateway raises `RuntimeError` naming the queue URL and the client is closed

#### Scenario: Reachable target
- **WHEN** the bucket or queue exists and the credentials allow the verification call
- **THEN** `open()` returns the gateway ready for use

#### Scenario: Probe denied by a least-privilege policy
- **WHEN** the identity may read/write objects (or send/receive messages) but not list the bucket (or read queue attributes)
- **THEN** `open()` logs a warning and succeeds without requiring the extra permission
