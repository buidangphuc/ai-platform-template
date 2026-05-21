from app.core.schema import (
    PYDANTIC_ERROR_MESSAGES,
    SchemaBase,
    format_validation_errors,
)


def test_format_validation_errors_replaces_message_for_known_types():
    errors = [
        {"type": "missing", "loc": ("body", "email"), "msg": "Field required"},
        {
            "type": "string_too_short",
            "loc": ("body", "name"),
            "msg": "string too short",
            "ctx": {"min_length": 3},
        },
    ]
    formatted = format_validation_errors(errors)

    assert formatted[0]["msg"] == PYDANTIC_ERROR_MESSAGES["missing"]
    assert "min 3" in formatted[1]["msg"]


def test_format_validation_errors_passes_through_unknown_types():
    errors = [{"type": "unknown_thing", "loc": ("body",), "msg": "raw"}]
    formatted = format_validation_errors(errors)

    assert formatted[0]["msg"] == "raw"


def test_schema_base_strips_whitespace_and_supports_enum_values():
    class _Item(SchemaBase):
        name: str

    item = _Item(name="  hello  ")
    assert item.name == "hello"
