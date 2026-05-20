from app.modules.feedback.schemas import (
    CreateFeedbackRequest,
    FeedbackRecord,
    new_feedback_id,
)


class FeedbackRepository:
    def __init__(self) -> None:
        self._memory: dict[str, FeedbackRecord] = {}

    async def create(self, payload: CreateFeedbackRequest) -> FeedbackRecord:
        record = FeedbackRecord(
            feedback_id=new_feedback_id(),
            **payload.model_dump(),
        )
        self._memory[record.feedback_id] = record
        return record
