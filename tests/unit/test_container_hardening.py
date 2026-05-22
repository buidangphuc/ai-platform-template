from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_compose_services_have_healthchecks_and_healthy_dependencies():
    compose = (ROOT / "docker-compose.local.yaml").read_text(encoding="utf-8")

    assert "condition: service_healthy" in compose
    assert "pg_isready" in compose
    assert "redis-cli ping" in compose
    assert "python -m scripts.run_worker --check" in compose
    assert "http://localhost:8000/healthz" in compose


def test_gitignore_excludes_local_artifacts():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".DS_Store" in gitignore
    assert "*.py[cod]" in gitignore
