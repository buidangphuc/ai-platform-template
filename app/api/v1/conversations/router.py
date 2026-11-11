from fastapi import APIRouter, Depends, Request

from app.bootstrap.state import get_app_resources
from app.core.pagination import ListResponse, PaginationParams, build_list_response
from app.modules.business.conversations.schemas import (
    ConversationCreate,
    ConversationView,
    MessageView,
    SendMessageRequest,
    SendMessageResponse,
)
from app.modules.business.conversations.service import ConversationService
from app.modules.platform.identity.auth import require_principal
from app.modules.platform.identity.schemas import Principal

router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
    dependencies=[Depends(require_principal)],
)


@router.post("", response_model=ConversationView, status_code=201)
async def create_conversation(
    payload: ConversationCreate,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> ConversationView:
    service = get_app_resources(request.app).service(ConversationService)
    conversation = await service.create(principal.id, payload.title)
    return ConversationView.model_validate(conversation, from_attributes=True)


@router.get("", response_model=ListResponse[ConversationView])
async def list_conversations(
    request: Request,
    params: PaginationParams = Depends(),
    principal: Principal = Depends(require_principal),
) -> ListResponse[ConversationView]:
    service = get_app_resources(request.app).service(ConversationService)
    items, total = await service.list_for_principal(
        principal.id, limit=params.limit, offset=params.offset
    )
    return build_list_response(
        items=[
            ConversationView.model_validate(item, from_attributes=True)
            for item in items
        ],
        total=total,
        params=params,
    )


@router.get("/{conversation_id}/messages", response_model=list[MessageView])
async def list_messages(
    conversation_id: str,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> list[MessageView]:
    service = get_app_resources(request.app).service(ConversationService)
    messages = await service.messages(principal.id, conversation_id)
    return [
        MessageView.model_validate(message, from_attributes=True)
        for message in messages
    ]


@router.post("/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conversation_id: str,
    payload: SendMessageRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> SendMessageResponse:
    service = get_app_resources(request.app).service(ConversationService)
    user, assistant = await service.send(principal.id, conversation_id, payload.content)
    return SendMessageResponse(
        user_message=MessageView.model_validate(user, from_attributes=True),
        assistant_message=MessageView.model_validate(assistant, from_attributes=True),
    )
