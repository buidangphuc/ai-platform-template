"""Completion request contract: client roles, bounds, strict fields."""

import pytest
from pydantic import ValidationError

from app.modules.business.completions.schemas import (
    MAX_MESSAGE_CHARS,
    MAX_MESSAGES,
    MAX_METADATA_BYTES,
    MAX_METADATA_KEYS,
    CompletionRequest,
)


def _msg(content: str = "hi", role: str = "user") -> dict[str, str]:
    return {"role": role, "content": content}


def test_system_role_is_rejected_from_clients():
    with pytest.raises(ValidationError):
        CompletionRequest.model_validate({"messages": [_msg(role="system")]})


def test_user_and_assistant_roles_are_accepted():
    request = CompletionRequest.model_validate(
        {"messages": [_msg(), _msg("ok", role="assistant"), _msg("again")]}
    )

    assert [m.role for m in request.messages] == ["user", "assistant", "user"]


def test_message_count_is_bounded():
    CompletionRequest.model_validate({"messages": [_msg()] * MAX_MESSAGES})
    with pytest.raises(ValidationError):
        CompletionRequest.model_validate({"messages": [_msg()] * (MAX_MESSAGES + 1)})


def test_message_content_length_is_bounded():
    CompletionRequest.model_validate({"messages": [_msg("x" * MAX_MESSAGE_CHARS)]})
    with pytest.raises(ValidationError):
        CompletionRequest.model_validate(
            {"messages": [_msg("x" * (MAX_MESSAGE_CHARS + 1))]}
        )


def test_metadata_key_count_is_bounded():
    CompletionRequest.model_validate(
        {
            "messages": [_msg()],
            "metadata": {str(i): 1 for i in range(MAX_METADATA_KEYS)},
        }
    )
    with pytest.raises(ValidationError):
        CompletionRequest.model_validate(
            {
                "messages": [_msg()],
                "metadata": {str(i): 1 for i in range(MAX_METADATA_KEYS + 1)},
            }
        )


def test_metadata_serialized_size_is_bounded():
    with pytest.raises(ValidationError):
        CompletionRequest.model_validate(
            {"messages": [_msg()], "metadata": {"blob": "x" * MAX_METADATA_BYTES}}
        )


def test_unknown_fields_are_forbidden():
    with pytest.raises(ValidationError):
        CompletionRequest.model_validate({"messages": [_msg()], "temperature": 2})
    with pytest.raises(ValidationError):
        CompletionRequest.model_validate(
            {"messages": [{"role": "user", "content": "hi", "name": "x"}]}
        )
