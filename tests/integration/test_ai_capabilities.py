async def test_rag_endpoint_requires_api_key(client):
    response = await client.post(
        "/api/v1/rag/index",
        json={"documents": [{"id": "doc-1", "text": "protected"}]},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_rag_index_search_and_answer_endpoints(client, auth_headers):
    indexed = await client.post(
        "/api/v1/rag/index",
        headers=auth_headers,
        json={
            "documents": [
                {
                    "id": "doc-1",
                    "text": "Phase three adds prompt registry and RAG support.",
                    "metadata": {"source": "integration"},
                }
            ]
        },
    )
    search = await client.post(
        "/api/v1/rag/search",
        headers=auth_headers,
        json={"query": "prompt registry", "top_k": 1},
    )
    answer = await client.post(
        "/api/v1/rag/answer",
        headers=auth_headers,
        json={"question": "What does phase three add?", "top_k": 1},
    )

    assert indexed.status_code == 201
    assert indexed.json()["indexed_count"] == 1
    assert search.status_code == 200
    assert search.json()["matches"][0]["document_id"] == "doc-1"
    assert answer.status_code == 200
    assert "What does phase three add?" in answer.json()["answer"]


async def test_agent_and_eval_endpoints(client, auth_headers):
    indexed = await client.post(
        "/api/v1/rag/index",
        headers=auth_headers,
        json={
            "documents": [
                {
                    "id": "doc-1",
                    "text": "Phase three adds RAG evaluation support.",
                }
            ]
        },
    )
    agent = await client.post(
        "/api/v1/agents/run",
        headers=auth_headers,
        json={"task": "Summarize status", "input": {"status": "green"}},
    )
    eval_run = await client.post(
        "/api/v1/evals/rag",
        headers=auth_headers,
        json={
            "cases": [
                {
                    "id": "case-1",
                    "question": "What support was added?",
                    "expected_keywords": ["evaluation"],
                }
            ],
            "top_k": 1,
        },
    )

    assert indexed.status_code == 201
    assert agent.status_code == 200
    assert agent.json()["status"] == "completed"
    assert eval_run.status_code == 200
    assert eval_run.json()["metrics"]["keyword_hit_rate"] == 1.0
