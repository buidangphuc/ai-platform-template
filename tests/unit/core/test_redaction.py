import pytest

from app.core.redaction import RedactionPolicy


def test_redaction_policy_masks_email_api_key_and_bearer_tokens():
    policy = RedactionPolicy(mode="redacted")

    redacted = policy.redact_text(
        "Email admin@example.com with key sk-test123 and Bearer token-value."
    )

    assert "admin@example.com" not in redacted
    assert "sk-test123" not in redacted
    assert "Bearer token-value" not in redacted
    assert "[email]" in redacted
    assert "[secret]" in redacted


def test_redaction_policy_can_hide_or_preserve_content():
    assert RedactionPolicy(mode="off").redact_text("secret text") == "[redacted]"
    assert RedactionPolicy(mode="full").redact_text("secret text") == "secret text"


def test_redaction_policy_redacts_nested_mapping():
    policy = RedactionPolicy(mode="redacted")

    payload = policy.redact_mapping(
        {
            "prompt": "Contact admin@example.com",
            "nested": {"api_key": "sk-test123"},  # pragma: allowlist secret
        }
    )

    assert payload == {
        "prompt": "Contact [email]",
        "nested": {"api_key": "[secret]"},
    }


def test_redaction_masks_strings_inside_lists():
    policy = RedactionPolicy(mode="redacted")

    payload = policy.redact_mapping(
        {
            "contacts": ["admin@example.com", {"note": "key sk-abc123"}],
            "nested": [["a@b.io"]],
        }
    )

    assert payload == {
        "contacts": ["[email]", {"note": "key [secret]"}],
        "nested": [["[email]"]],
    }


@pytest.mark.parametrize(
    "key",
    [
        "Authorization",
        "Cookie",
        "Set-Cookie",
        "api_key",
        "apikey",
        "X-API-Key",
        "access_token",
    ],
)
def test_redaction_masks_secret_header_and_key_names(key: str):
    policy = RedactionPolicy(mode="redacted")

    assert policy.redact_mapping({key: "value"}) == {key: "[secret]"}


@pytest.mark.parametrize(
    "text",
    [
        "goi 0912345678 nhe",
        "so dt 091 234 5678",
        "so dt 091.234.5678",
        "lien he +84912345678",
        "lien he +84 912 345 678",
        "call +1 415 555 2671",
    ],
)
def test_redaction_masks_phone_numbers_including_vietnamese(text: str):
    redacted = RedactionPolicy(mode="redacted").redact_text(text)

    assert "[phone]" in redacted
    assert "912" not in redacted and "415" not in redacted


def test_redaction_masks_luhn_valid_card_numbers_only():
    policy = RedactionPolicy(mode="redacted")

    assert policy.redact_text("card 4111 1111 1111 1111 ok") == "card [card] ok"
    assert policy.redact_text("card 4111-1111-1111-1111") == "card [card]"
    # Fails Luhn: an order id, not a card.
    assert policy.redact_text("order 4111111111111112") == "order 4111111111111112"


def test_redaction_masks_aws_access_key_ids():
    redacted = RedactionPolicy(mode="redacted").redact_text(
        "key AKIAIOSFODNN7EXAMPLE leaked"  # pragma: allowlist secret
    )

    assert redacted == "key [secret] leaked"


def test_redaction_leaves_plain_numbers_alone():
    text = "ticket 12345 on 2026-10-12 costs 1,500,000 dong"

    assert RedactionPolicy(mode="redacted").redact_text(text) == text
