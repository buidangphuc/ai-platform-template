import json
from pathlib import Path

import yaml
from research.artifacts.schemas import ArtifactManifest, ArtifactType


def test_research_workspace_has_required_phase_4_structure():
    required_paths = [
        "research/README.md",
        "research/datasets/samples/rag_smoke.jsonl",
        "research/datasets/schemas/rag_eval_case.schema.json",
        "research/training/train_template.py",
        "research/evaluation/run_rag_smoke.py",
        "research/evaluation/metrics/keyword_hit_rate.py",
        "research/artifacts/sample_prompt_manifest.yaml",
    ]

    missing = [path for path in required_paths if not Path(path).exists()]

    assert missing == []


def test_sample_artifact_manifest_matches_contract():
    manifest_path = Path("research/artifacts/sample_prompt_manifest.yaml")
    raw_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    manifest = ArtifactManifest.model_validate(raw_manifest)

    assert manifest.type == ArtifactType.PROMPT
    assert manifest.runtime_dependencies
    assert manifest.eval_report
    assert manifest.artifact_uri
    assert Path(manifest.eval_report).exists()


def test_rag_smoke_dataset_matches_json_schema():
    schema = json.loads(
        Path("research/datasets/schemas/rag_eval_case.schema.json").read_text(
            encoding="utf-8",
        )
    )
    required = set(schema["required"])

    for line in (
        Path("research/datasets/samples/rag_smoke.jsonl")
        .read_text(
            encoding="utf-8",
        )
        .splitlines()
    ):
        record = json.loads(line)
        assert required <= record.keys()
        assert isinstance(record["expected_keywords"], list)


def test_research_generated_artifacts_are_ignored():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    assert "research/artifacts/generated/" in gitignore


def test_eval_logic_lives_in_research_not_app_runtime():
    assert not Path("app/modules/evals").exists()


def test_prompt_management_lives_outside_app_runtime():
    assert not Path("app/modules/prompts").exists()

    manifest_path = Path("research/artifacts/sample_prompt_manifest.yaml")
    raw_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    assert "app.modules.prompts.registry" not in raw_manifest["runtime_dependencies"]
    assert not raw_manifest["artifact_uri"].startswith("app/modules/prompts")


def test_usage_tracking_lives_outside_app_runtime():
    assert not Path("app/modules/usage").exists()


def test_rag_uses_llamaindex_primitives_without_local_schema_layers():
    assert not Path("app/modules/rag/schemas.py").exists()
    assert not Path("app/modules/rag/reranking.py").exists()
