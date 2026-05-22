from pathlib import Path


def test_ci_target_runs_typecheck_and_hygiene() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "typecheck:" in makefile
    assert "ci: check check-env typecheck hygiene test" in makefile
