from fastapi import APIRouter, Request, status

from app.modules.feedback.repository import FeedbackRepository
from app.modules.feedback.schemas import CreateFeedbackRequest, FeedbackRecord

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _repository(request: Request) -> FeedbackRepository:
    return request.app.state.feedback_repository


@router.post(
    "",
    response_model=FeedbackRecord,
    status_code=status.HTTP_201_CREATED,
)
async def create_feedback(payload: CreateFeedbackRequest, request: Request):
    return await _repository(request).create(payload)
