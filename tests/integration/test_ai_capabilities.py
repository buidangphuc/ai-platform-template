async def test_rag_index_search_and_answer_endpoints(client):
    indexed = await client.post(
        "/api/v1/rag/index",
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
        json={"query": "prompt registry", "top_k": 1},
    )
    answer = await client.post(
        "/api/v1/rag/answer",
        json={"question": "What does phase three add?", "top_k": 1},
    )

    assert indexed.status_code == 201
    assert indexed.json()["indexed_count"] == 1
    assert search.status_code == 200
    assert search.json()["matches"][0]["document_id"] == "doc-1"
    assert answer.status_code == 200
    assert answer.json()["answer"].startswith("fake-chat response:")


async def test_agent_and_eval_endpoints(client):
    indexed = await client.post(
        "/api/v1/rag/index",
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
        json={"task": "Summarize status", "input": {"status": "green"}},
    )
    eval_run = await client.post(
        "/api/v1/evals/rag",
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
