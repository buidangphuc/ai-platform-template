import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "app"
# Defines Settings itself rather than re-exporting it.
ALLOWED_CODE = {APP_ROOT / "core" / "config" / "__init__.py"}


def _is_docstring(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)


def test_package_inits_hold_no_code() -> None:
    offenders = [
        str(path.relative_to(APP_ROOT.parent))
        for path in APP_ROOT.rglob("__init__.py")
        if path not in ALLOWED_CODE
        and not all(_is_docstring(node) for node in ast.parse(path.read_text()).body)
    ]
    assert offenders == []


def test_no_dunder_all_in_app() -> None:
    offenders = [
        str(path.relative_to(APP_ROOT.parent))
        for path in APP_ROOT.rglob("*.py")
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
    ]
    assert offenders == []
