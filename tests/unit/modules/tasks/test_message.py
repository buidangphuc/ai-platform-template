import pytest

from app.modules.messaging.queue.worker import NonRetryableMessageError
from app.modules.messaging.tasks.message import TaskMessage


def test_task_message_round_trips_through_the_flat_body():
    body = TaskMessage(task_id="t-1", type="completion").to_body()

    assert body == {"task_id": "t-1", "type": "completion"}
    assert TaskMessage.from_body(body) == TaskMessage(task_id="t-1", type="completion")


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"task_id": "t-1"},
        {"type": "completion"},
        {"task_id": "", "type": "completion"},
        {"task_id": 7, "type": "completion"},
        # The old outbox envelope: must be rejected, never silently accepted.
        {"id": "e", "type": "task.completion", "payload": {"task_id": "t-1"}},
    ],
)
def test_malformed_body_is_non_retryable(body):
    with pytest.raises(NonRetryableMessageError):
        TaskMessage.from_body(body)


def test_request_id_is_optional_and_round_trips():
    message = TaskMessage(task_id="t-1", type="completion", request_id="req_abc")

    assert message.to_body() == {
        "task_id": "t-1",
        "type": "completion",
        "request_id": "req_abc",
    }
    assert TaskMessage.from_body(message.to_body()) == message


@pytest.mark.parametrize("request_id", ["", 7])
def test_request_id_must_be_a_non_empty_string_when_present(request_id):
    body = {"task_id": "t-1", "type": "completion", "request_id": request_id}

    with pytest.raises(NonRetryableMessageError):
        TaskMessage.from_body(body)
