import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NAME = "sample_orders"


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("project")
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for directory in ("app", "tests", "scripts"):
        shutil.copytree(ROOT / directory, target / directory, ignore=ignore)
    for name in (".env.example", "pyproject.toml"):
        shutil.copy(ROOT / name, target / name)
    result = _run(ROOT, "-m", "scripts.new_domain", NAME, "--root", str(target))
    assert result.returncode == 0, result.stderr
    return target


def test_generated_domain_passes_every_check(project: Path) -> None:
    assert _run(project, "-m", "scripts.check_env_example").returncode == 0
    generated = [
        f"app/modules/business/{NAME}",
        f"app/api/v1/{NAME}",
        f"app/bootstrap/features/{NAME}.py",
        f"app/core/config/{NAME}.py",
        f"tests/integration/test_{NAME}.py",
    ]
    assert _run(project, "-m", "ruff", "check", *generated).returncode == 0
    tests = _run(project, "-m", "pytest", f"tests/integration/test_{NAME}.py", "-q")
    assert tests.returncode == 0, tests.stdout
    lint = _run(
        project,
        "-c",
        "from importlinter.cli import lint_imports_command; lint_imports_command()",
    )
    assert lint.returncode == 0, lint.stdout


def test_second_run_fails_and_changes_nothing(project: Path) -> None:
    before = _snapshot(project)
    result = _run(ROOT, "-m", "scripts.new_domain", NAME, "--root", str(project))
    assert result.returncode != 0
    assert _snapshot(project) == before


def test_invalid_name_fails(project: Path) -> None:
    result = _run(ROOT, "-m", "scripts.new_domain", "Bad-Name", "--root", str(project))
    assert result.returncode != 0
    assert "invalid name" in result.stderr
