import subprocess


def test_eval_smoke_command_runs_without_cloud_dependencies():
    completed = subprocess.run(
        ["make", "eval-smoke"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0
    assert "keyword_hit_rate" in completed.stdout


def test_eval_smoke_command_fails_when_keyword_threshold_is_not_met(tmp_path):
    dataset = tmp_path / "bad_rag_smoke.jsonl"
    report = tmp_path / "report.json"
    tracker_root = tmp_path / "runs"
    dataset.write_text(
        "\n".join(
            [
                "{"
                '"id":"bad-case",'
                '"question":"What is missing?",'
                '"expected_keywords":["missing keyword"],'
                '"documents":[{"id":"doc-1","text":"irrelevant source text"}]'
                "}"
            ]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "research.evaluation.run_rag_smoke",
            "--dataset",
            str(dataset),
            "--report",
            str(report),
            "--tracker-root",
            str(tracker_root),
            "--min-keyword-hit-rate",
            "1.0",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 1
    assert "keyword_hit_rate below threshold" in completed.stderr
