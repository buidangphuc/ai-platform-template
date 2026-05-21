from pathlib import Path


def test_alembic_tracks_foundation_schema_revision():
    revisions = sorted(Path("alembic/versions").glob("*.py"))

    assert revisions, "expected a tracked foundation Alembic revision"
    revision_text = "\n".join(
        revision.read_text(encoding="utf-8") for revision in revisions
    )
    assert '"api_keys"' not in revision_text
    assert '"feedback"' not in revision_text
    assert "feedbacks" not in revision_text
    assert "platform" not in revision_text
    assert "audit_events" in revision_text
    assert "idempotency_keys" in revision_text
    assert "tasks" in revision_text


def test_gitignore_does_not_hide_alembic_revisions():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "alembic/versions/" not in gitignore
