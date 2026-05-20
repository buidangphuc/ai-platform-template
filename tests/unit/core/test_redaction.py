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
