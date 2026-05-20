from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

FeedbackTargetType = Literal["llm_response", "rag_answer", "agent_run", "eval_run"]
FeedbackRating = Literal["positive", "negative", "neutral"]


def new_feedback_id() -> str:
    return f"fb_{uuid4().hex}"


class CreateFeedbackRequest(BaseModel):
    request_id: str
    trace_id: str
    target_type: FeedbackTargetType
    target_id: str
    rating: FeedbackRating
    labels: list[str] = Field(default_factory=list)
    comment: str | None = None


class FeedbackRecord(CreateFeedbackRequest):
    feedback_id: str
