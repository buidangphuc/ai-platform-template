from argparse import Namespace

from scripts.run_eval import _run


async def test_run_eval_default_smoke_returns_summary_counts():
    result = await _run(Namespace(cases=""))

    assert result == {
        "passed_scores": 3,
        "total_cases": 2,
        "total_scores": 4,
    }
