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
