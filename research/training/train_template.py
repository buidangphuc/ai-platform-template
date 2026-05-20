import argparse
from datetime import UTC, datetime
from pathlib import Path

import yaml


def write_manifest(output: Path) -> None:
    manifest = {
        "name": "sample-model",
        "version": "0.1.0",
        "type": "model",
        "owner": "ai-platform",
        "created_at": datetime.now(UTC).isoformat(),
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "runtime_dependencies": ["app.modules.llm.runtime"],
        "eval_report": "research/evaluation/reports/rag_smoke.json",
        "risk_notes": ["Template output only; replace with real training evaluation."],
        "artifact_uri": "research/artifacts/sample-model",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="research/artifacts/sample_model_manifest.yaml",
    )
    args = parser.parse_args()
    write_manifest(Path(args.output))
    print(f"Wrote manifest to {args.output}")


if __name__ == "__main__":
    main()
