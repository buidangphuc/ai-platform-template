## ADDED Requirements

### Requirement: SQS can dead-letter explicitly
When `SQS_DEAD_LETTER_QUEUE_URL` is set, `SQSQueueGateway.nack(message, requeue=False)` SHALL send the original message body to that queue with the message attributes `reason`, `original_message_id` and `receive_count`, and only then delete the original from the work queue. If the send fails the error SHALL propagate and the original SHALL NOT be deleted.

#### Scenario: Non-retryable message dead-letters immediately
- **WHEN** a message is received once and nacked with `requeue=False` and a DLQ URL is configured
- **THEN** the DLQ holds the same body with the original id and receive count 1 as attributes, and the work queue no longer delivers it

#### Scenario: DLQ send fails
- **WHEN** the send to the DLQ raises
- **THEN** the error propagates and the original message is not deleted

### Requirement: Without a DLQ URL the queue's RedrivePolicy governs
When `SQS_DEAD_LETTER_QUEUE_URL` is empty, `nack(requeue=False)` SHALL leave the message in place so that the work queue's RedrivePolicy (`maxReceiveCount`, `deadLetterTargetArn`) moves it to the dead-letter queue; the gateway SHALL document that the RedrivePolicy must be configured.

#### Scenario: Redrive after maxReceiveCount
- **WHEN** a message is repeatedly received and nacked with requeue on a queue whose RedrivePolicy has `maxReceiveCount` 2
- **THEN** it is delivered twice and then appears in the redrive dead-letter queue

### Requirement: Requeue makes the message visible again
`nack(message, requeue=True)` SHALL set the message's visibility timeout to 0 regardless of the DLQ setting.

#### Scenario: Requeue with a DLQ configured
- **WHEN** a message is nacked with `requeue=True`
- **THEN** nothing is sent to the DLQ and the message is visible again at once
