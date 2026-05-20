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
