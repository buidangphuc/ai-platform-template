from pydantic import BaseModel, Field


class RAGEvalCase(BaseModel):
    id: str
    question: str = Field(min_length=1)
    expected_keywords: list[str] = Field(min_length=1)


class RAGEvalRequest(BaseModel):
    cases: list[RAGEvalCase] = Field(min_length=1)
    top_k: int = Field(default=5, gt=0)


class RAGEvalItemResult(BaseModel):
    id: str
    passed: bool
    matched_keywords: list[str]
    answer: str


class RAGEvalResult(BaseModel):
    run_id: str
    items: list[RAGEvalItemResult]
    metrics: dict[str, float]
