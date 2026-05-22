from pathlib import Path
from subprocess import run


def test_template_hygiene_script_accepts_supported_optional_backends() -> None:
    root = Path(__file__).resolve().parents[2]

    result = run(
        ["./scripts/check_template_hygiene.sh"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
