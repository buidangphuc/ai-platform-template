from fastapi import APIRouter, Depends, Request, status

from app.modules.feedback.repository import FeedbackRepository
from app.modules.feedback.schemas import CreateFeedbackRequest, FeedbackRecord
from app.modules.identity.auth import require_authenticated_request
from app.modules.identity.schemas import AuthenticatedPrincipal

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _repository(request: Request) -> FeedbackRepository:
    return request.app.state.feedback_repository


@router.post(
    "",
    response_model=FeedbackRecord,
    status_code=status.HTTP_201_CREATED,
)
async def create_feedback(
    payload: CreateFeedbackRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_authenticated_request),
):
    return await _repository(request).create(payload, api_key_id=principal.api_key_id)
