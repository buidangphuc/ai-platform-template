import pytest
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts.prompt import PromptTemplate as LangChainPromptTemplate

from app.modules.prompts.registry import InMemoryPromptRegistry
from app.modules.prompts.schemas import PromptTemplate


def test_prompt_registry_renders_named_prompt_version():
    registry = InMemoryPromptRegistry()
    registry.register(
        PromptTemplate(
            name="rag.answer",
            version="v1",
            template="Question: {question}\nContext: {context}",
            variables=["question", "context"],
        )
    )

    rendered = registry.render(
        "rag.answer",
        variables={"question": "What changed?", "context": "Contracts added."},
    )

    assert rendered.name == "rag.answer"
    assert rendered.version == "v1"
    assert rendered.content == "Question: What changed?\nContext: Contracts added."


def test_prompt_registry_rejects_missing_variables():
    registry = InMemoryPromptRegistry()
    registry.register(
        PromptTemplate(
            name="rag.answer",
            version="v1",
            template="Question: {question}\nContext: {context}",
            variables=["question", "context"],
        )
    )

    with pytest.raises(ValueError, match="Missing prompt variables: context"):
        registry.render("rag.answer", variables={"question": "What changed?"})


def test_default_prompt_registry_contains_rag_answer_prompt():
    registry = InMemoryPromptRegistry.with_defaults()

    rendered = registry.render(
        "rag.answer",
        variables={"question": "What changed?", "context": "Contracts added."},
    )

    assert rendered.name == "rag.answer"
    assert "Contracts added." in rendered.content


def test_prompt_registry_returns_langchain_chat_prompt_template():
    registry = InMemoryPromptRegistry.with_defaults()

    prompt = registry.get_langchain_prompt("rag.answer")
    messages = prompt.format_messages(
        question="What changed?",
        context="LangChain runtime convention.",
    )

    assert isinstance(prompt, ChatPromptTemplate)
    assert "What changed?" in str(messages[0].content)


def test_prompt_registry_returns_langchain_string_prompt_template():
    registry = InMemoryPromptRegistry()
    registry.register(
        PromptTemplate(
            name="judge.grounding",
            version="v1",
            template="Score answer: {answer}",
            variables=["answer"],
            template_type="string",
        )
    )

    prompt = registry.get_langchain_prompt("judge.grounding")

    assert isinstance(prompt, LangChainPromptTemplate)
    assert prompt.format(answer="grounded") == "Score answer: grounded"
