from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

FeedbackTargetType = Literal["llm_response", "rag_answer", "agent_run", "eval_run"]
FeedbackRating = Literal["positive", "negative", "neutral"]
FeedbackIdentifier = Annotated[str, Field(min_length=1, max_length=128)]
FeedbackLabel = Annotated[str, Field(min_length=1, max_length=64)]
FeedbackComment = Annotated[str, Field(max_length=2000)]


def new_feedback_id() -> str:
    return f"fb_{uuid4().hex}"


class CreateFeedbackRequest(BaseModel):
    request_id: FeedbackIdentifier
    trace_id: FeedbackIdentifier
    target_type: FeedbackTargetType
    target_id: FeedbackIdentifier
    rating: FeedbackRating
    labels: list[FeedbackLabel] = Field(default_factory=list)
    comment: FeedbackComment | None = None


class FeedbackRecord(CreateFeedbackRequest):
    feedback_id: str
