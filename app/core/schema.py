from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

PYDANTIC_ERROR_MESSAGES: dict[str, str] = {
    "bool_parsing": "Could not parse boolean value",
    "bool_type": "Expected a boolean",
    "bytes_too_long": "Bytes value is too long",
    "bytes_too_short": "Bytes value is too short",
    "bytes_type": "Expected bytes",
    "date_from_datetime_inexact": "Datetime must have zero time component",
    "date_from_datetime_parsing": "Could not parse date from datetime",
    "date_future": "Date must be in the future",
    "date_parsing": "Could not parse date",
    "date_past": "Date must be in the past",
    "date_type": "Expected a date",
    "datetime_future": "Datetime must be in the future",
    "datetime_object_invalid": "Invalid datetime object",
    "datetime_parsing": "Could not parse datetime",
    "datetime_past": "Datetime must be in the past",
    "datetime_type": "Expected a datetime",
    "decimal_max_digits": "Too many decimal digits",
    "decimal_max_places": "Too many decimal places",
    "decimal_parsing": "Could not parse decimal",
    "decimal_type": "Expected a decimal",
    "decimal_whole_digits": "Invalid decimal whole digits",
    "dict_type": "Expected a dictionary",
    "enum": "Invalid enum value, allowed values are {expected}",
    "extra_forbidden": "Extra fields are not allowed",
    "finite_number": "Expected a finite number",
    "float_parsing": "Could not parse float",
    "float_type": "Expected a float",
    "frozen_field": "Field is frozen and cannot be changed",
    "greater_than": "Value must be greater than {gt}",
    "greater_than_equal": "Value must be greater than or equal to {ge}",
    "int_from_float": "Expected an integer, got a float",
    "int_parsing": "Could not parse integer",
    "int_parsing_size": "Integer is out of range",
    "int_type": "Expected an integer",
    "invalid_key": "Invalid key",
    "is_instance_of": "Expected an instance of {class_name}",
    "json_invalid": "Invalid JSON: {error}",
    "json_type": "Expected a JSON value",
    "less_than": "Value must be less than {lt}",
    "less_than_equal": "Value must be less than or equal to {le}",
    "list_type": "Expected a list",
    "literal_error": "Expected one of: {expected}",
    "mapping_type": "Expected a mapping",
    "missing": "Field is required",
    "missing_argument": "Missing required argument",
    "model_attributes_type": "Invalid model attributes",
    "model_type": "Invalid model instance",
    "multiple_of": "Value must be a multiple of {multiple_of}",
    "none_required": "Value must be None",
    "set_type": "Expected a set",
    "string_pattern_mismatch": "String does not match pattern {pattern}",
    "string_too_long": "String is too long (max {max_length})",
    "string_too_short": "String is too short (min {min_length})",
    "string_type": "Expected a string",
    "time_parsing": "Could not parse time",
    "time_type": "Expected a time",
    "timezone_aware": "Datetime must include timezone information",
    "timezone_naive": "Datetime must not include timezone information",
    "too_long": "Value is too long",
    "too_short": "Value is too short",
    "tuple_type": "Expected a tuple",
    "url_parsing": "Could not parse URL",
    "url_scheme": "Invalid URL scheme",
    "url_syntax_violation": "URL has invalid syntax",
    "url_too_long": "URL is too long",
    "url_type": "Expected a URL",
    "uuid_parsing": "Could not parse UUID",
    "uuid_type": "Expected a UUID",
    "uuid_version": "Invalid UUID version",
    "value_error": "Invalid value",
}


def format_validation_errors(
    errors: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for error in errors:
        message_template = PYDANTIC_ERROR_MESSAGES.get(error.get("type", ""))
        if message_template:
            ctx = error.get("ctx") or {}
            try:
                error["msg"] = message_template.format(**ctx)
            except (KeyError, IndexError):
                error["msg"] = message_template
        formatted.append(error)
    return formatted


class SchemaBase(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
        str_strip_whitespace=True,
    )
