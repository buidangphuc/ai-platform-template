import json
from argparse import Namespace

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.modules.ai.llm import router as router_module
from scripts.run_eval import DEFAULT_CASES, _run
from tests.factories import build_test_settings


async def test_eval_gate_passes_on_default_dataset(capsys):
    """Deterministic cases pass; judge cases skip without JUDGE_CHAT_MODEL."""
    exit_code = await _run(
        Namespace(cases=DEFAULT_CASES, min_score=0.8), settings=build_test_settings()
    )
    out = capsys.readouterr().out

    assert exit_code == 0
    assert '"pass_rate": 1.0' in out
    assert '"skipped_judge": 2' in out


async def test_eval_gate_fails_below_threshold():
    exit_code = await _run(
        Namespace(cases=DEFAULT_CASES, min_score=1.01), settings=build_test_settings()
    )
    assert exit_code == 1


async def test_eval_gate_rejects_unknown_evaluator(tmp_path, capsys):
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        json.dumps(
            {
                "id": "typo-case",
                "input": {"messages": [{"role": "user", "content": "hi"}]},
                "expected": "echo: hi",
                "metadata": {"evaluator": "contain"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as excinfo:
        await _run(
            Namespace(cases=str(cases), min_score=0.8), settings=build_test_settings()
        )

    assert excinfo.value.code not in (0, None)
    assert "typo-case" in str(excinfo.value.code)
    assert "contain" in str(excinfo.value.code)
    assert capsys.readouterr().out == ""


async def test_eval_gate_counts_skipped_judge_cases(tmp_path, capsys):
    cases = tmp_path / "cases.jsonl"
    rows = [
        {
            "id": "ok",
            "input": {"messages": [{"role": "user", "content": "hi"}]},
            "expected": "echo: hi",
        },
        {
            "id": "judged",
            "input": {"messages": [{"role": "user", "content": "hi"}]},
            "expected": "criteria",
            "metadata": {"evaluator": "judge"},
        },
    ]
    cases.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    exit_code = await _run(
        Namespace(cases=str(cases), min_score=0.8), settings=build_test_settings()
    )
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert report["cases"] == 2
    assert report["scored"] == 1
    assert report["skipped_judge"] == 1


async def test_eval_gate_grades_the_model_backed_handler_when_llm_enabled(
    tmp_path, capsys, monkeypatch
):
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        json.dumps(
            {
                "id": "model-case",
                "input": {"messages": [{"role": "user", "content": "hi"}]},
                "expected": "answer from the model",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        router_module,
        "settings_model_builder",
        lambda settings: lambda target: FakeListChatModel(
            responses=["answer from the model"]
        ),
    )

    exit_code = await _run(
        Namespace(cases=str(cases), min_score=1.0),
        settings=build_test_settings(LLM_ENABLED=True, CHAT_MODEL="fake:model"),
    )
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert report["passed"] == 1
    assert report["failures"] == []
