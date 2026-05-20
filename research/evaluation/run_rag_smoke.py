import argparse
import asyncio
import json
from pathlib import Path

from app.adapters.embeddings.fake import FakeEmbeddingClient
from app.adapters.llm.fake import FakeLLMClient
from app.adapters.mlops.local_tracker import LocalExperimentTracker
from app.adapters.observability.debug import DebugObservability
from app.adapters.vector_store.in_memory import InMemoryVectorStore
from app.contracts.experiment_tracker import (
    ArtifactRecord,
    ExperimentRunStatus,
    MetricRecord,
)
from app.core.redaction import RedactionPolicy
from app.modules.evals.rag import RAGEvaluationService
from app.modules.evals.schemas import RAGEvalCase, RAGEvalRequest
from app.modules.prompts.registry import InMemoryPromptRegistry
from app.modules.rag.chunking import TextChunker
from app.modules.rag.schemas import RagDocument, RagIndexRequest
from app.modules.rag.service import RagService
from app.modules.usage.tracker import InMemoryUsageTracker


async def run_smoke(
    dataset: Path, report: Path, tracker_root: Path
) -> dict[str, object]:
    records = [
        json.loads(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rag_service = RagService(
        embeddings=FakeEmbeddingClient(model="fake-embedding", dimensions=16),
        vector_store=InMemoryVectorStore(),
        llm=FakeLLMClient(model="fake-chat"),
        prompt_registry=InMemoryPromptRegistry.with_defaults(),
        chunker=TextChunker(chunk_size=64, overlap=8),
        usage_tracker=InMemoryUsageTracker(),
        observability=DebugObservability(),
        redaction_policy=RedactionPolicy(mode="redacted"),
    )
    tracker = LocalExperimentTracker(root=tracker_root)
    run = await tracker.start_run(
        "rag-smoke",
        metadata={"dataset": str(dataset)},
    )

    for record in records:
        await rag_service.index(
            RagIndexRequest(
                documents=[
                    RagDocument(id=document["id"], text=document["text"])
                    for document in record["documents"]
                ],
            )
        )

    evaluator = RAGEvaluationService(rag_service=rag_service)
    result = await evaluator.run(
        RAGEvalRequest(
            cases=[
                RAGEvalCase(
                    id=record["id"],
                    question=record["question"],
                    expected_keywords=record["expected_keywords"],
                )
                for record in records
            ],
            top_k=3,
        )
    )

    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        result.model_dump_json(indent=2),
        encoding="utf-8",
    )
    await tracker.log_metric(
        run.run_id,
        MetricRecord(
            name="keyword_hit_rate",
            value=result.metrics["keyword_hit_rate"],
        ),
    )
    await tracker.log_artifact(
        run.run_id,
        ArtifactRecord(name="rag-smoke-report", uri=str(report)),
    )
    await tracker.end_run(run.run_id, status=ExperimentRunStatus.SUCCEEDED)
    return result.model_dump(mode="json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        default="research/datasets/samples/rag_smoke.jsonl",
    )
    parser.add_argument(
        "--report",
        default="research/evaluation/reports/rag_smoke.json",
    )
    parser.add_argument(
        "--tracker-root",
        default="research/experiments/local",
    )
    args = parser.parse_args()

    result = asyncio.run(
        run_smoke(
            dataset=Path(args.dataset),
            report=Path(args.report),
            tracker_root=Path(args.tracker_root),
        )
    )
    print(json.dumps(result["metrics"], sort_keys=True))


if __name__ == "__main__":
    main()
