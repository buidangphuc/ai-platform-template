from app.adapters.llm.fake import FakeLLMClient
from app.contracts.llm import ChatMessage, LLMClient, LLMRequest


async def test_fake_llm_returns_deterministic_response():
    client: LLMClient = FakeLLMClient(model="fake-chat")

    response = await client.complete(
        LLMRequest(
            messages=[
                ChatMessage(role="system", content="Answer briefly."),
                ChatMessage(role="user", content="hello"),
            ],
        ),
    )

    assert response.model == "fake-chat"
    assert response.content == "fake-chat response: hello"
    assert response.finish_reason == "stop"
    assert response.usage.input_tokens > 0
    assert response.usage.output_tokens > 0


async def test_fake_llm_uses_default_prompt_when_user_message_is_missing():
    client = FakeLLMClient(model="fake-chat")

    response = await client.complete(
        LLMRequest(messages=[ChatMessage(role="system", content="No user turn.")]),
    )

    assert response.content == "fake-chat response: no user message"
