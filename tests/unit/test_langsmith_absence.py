from pathlib import Path


def test_template_does_not_configure_langsmith():
    checked_files = [
        Path(".env.example"),
        Path("README.md"),
    ]
    content = "\n".join(path.read_text(encoding="utf-8") for path in checked_files)

    assert "LANGSMITH" not in content
    assert "LangSmith" not in content


def test_first_party_code_does_not_import_langsmith():
    source_roots = [Path("app"), Path("research")]
    python_files = [
        path
        for root in source_roots
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    ]

    offenders = [
        str(path)
        for path in python_files
        if "langsmith" in path.read_text(encoding="utf-8").lower()
    ]

    assert offenders == []
