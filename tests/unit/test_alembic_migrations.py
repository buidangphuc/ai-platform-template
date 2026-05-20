from pathlib import Path


def test_alembic_tracks_foundation_schema_revision():
    revisions = sorted(Path("alembic/versions").glob("*.py"))

    assert revisions, "expected a tracked foundation Alembic revision"
    revision_text = "\n".join(
        revision.read_text(encoding="utf-8") for revision in revisions
    )
    assert "op.create_table(" in revision_text
    assert '"api_keys"' in revision_text
    assert '"feedback"' in revision_text
    assert "feedbacks" not in revision_text
    assert "platform" not in revision_text


def test_gitignore_does_not_hide_alembic_revisions():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "alembic/versions/" not in gitignore
