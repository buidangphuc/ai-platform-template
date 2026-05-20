import argparse
import asyncio
import json
import sys
from pathlib import Path

from llama_index.core.embeddings import MockEmbedding

from app.core.redaction import RedactionPolicy
from app.modules.evals.rag import RAGEvaluationService
from app.modules.evals.schemas import RAGEvalCase, RAGEvalRequest
from app.modules.rag.schemas import RagDocument, RagIndexRequest
from app.modules.rag.service import KnowledgeRetrievalService, build_rag_node_parser
from app.modules.usage.tracker import InMemoryUsageTracker


async def run_smoke(
    dataset: Path,
    report: Path,
    min_keyword_hit_rate: float = 1.0,
) -> dict[str, object]:
    records = [
        json.loads(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    knowledge_service = KnowledgeRetrievalService(
        embed_model=MockEmbedding(embed_dim=16),
        node_parser=build_rag_node_parser(chunk_size=64, chunk_overlap=8),
        usage_tracker=InMemoryUsageTracker(),
        redaction_policy=RedactionPolicy(mode="redacted"),
    )

    for record in records:
        await knowledge_service.index(
            RagIndexRequest(
                documents=[
                    RagDocument(id=document["id"], text=document["text"])
                    for document in record["documents"]
                ],
            )
        )

    evaluator = RAGEvaluationService(knowledge_service=knowledge_service)
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
    keyword_hit_rate = float(result.metrics["keyword_hit_rate"])
    succeeded = keyword_hit_rate >= min_keyword_hit_rate and all(
        item.passed for item in result.items
    )
    if not succeeded:
        raise RuntimeError(
            "keyword_hit_rate below threshold: "
            f"{keyword_hit_rate} < {min_keyword_hit_rate}"
        )
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
        help="Deprecated; kept for CLI compatibility.",
    )
    parser.add_argument(
        "--min-keyword-hit-rate",
        type=float,
        default=1.0,
    )
    args = parser.parse_args()

    try:
        result = asyncio.run(
            run_smoke(
                dataset=Path(args.dataset),
                report=Path(args.report),
                min_keyword_hit_rate=args.min_keyword_hit_rate,
            )
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result["metrics"], sort_keys=True))


if __name__ == "__main__":
    main()
