import pytest

from app.modules.feedback.models import Feedback


async def test_create_feedback_returns_created_record(client):
    payload = {
        "request_id": "req_123",
        "trace_id": "trace_456",
        "target_type": "llm_response",
        "target_id": "completion_789",
        "rating": "positive",
        "labels": ["helpful", "grounded"],
        "comment": "Good answer.",
    }

    response = await client.post("/api/v1/feedback", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["feedback_id"].startswith("fb_")
    assert body["request_id"] == payload["request_id"]
    assert body["trace_id"] == payload["trace_id"]
    assert body["target_type"] == payload["target_type"]
    assert body["target_id"] == payload["target_id"]
    assert body["rating"] == payload["rating"]
    assert body["labels"] == payload["labels"]
    assert body["comment"] == payload["comment"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("request_id", ""),
        ("trace_id", ""),
        ("target_id", ""),
        ("target_id", "x" * 129),
        ("target_type", "unsupported_target"),
        ("rating", "unsupported_rating"),
        ("labels", [""]),
        ("labels", ["x" * 65]),
        ("comment", ""),
        ("comment", "x" * 2001),
    ],
)
async def test_create_feedback_rejects_invalid_payload_values(client, field, value):
    payload = {
        "request_id": "req_123",
        "trace_id": "trace_456",
        "target_type": "llm_response",
        "target_id": "completion_789",
        "rating": "positive",
        "labels": ["helpful"],
        "comment": "Good answer.",
    }
    payload[field] = value

    response = await client.post("/api/v1/feedback", json=payload)

    assert response.status_code == 422


def test_feedback_model_indexes_lookup_identifiers():
    assert Feedback.__table__.c.request_id.index is True
    assert Feedback.__table__.c.trace_id.index is True
    assert Feedback.__table__.c.target_id.index is True


def test_feedback_model_uses_planned_identifier_lengths():
    assert Feedback.__table__.c.request_id.type.length == 128
    assert Feedback.__table__.c.trace_id.type.length == 128
    assert Feedback.__table__.c.target_id.type.length == 128
