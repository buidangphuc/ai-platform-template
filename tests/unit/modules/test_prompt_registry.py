import pytest

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
