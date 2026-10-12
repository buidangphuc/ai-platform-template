from fastapi import APIRouter, Depends, Request

from app.bootstrap.state import get_task_services
from app.core.request_context import get_request_id
from app.modules.business.completions.schemas import (
    COMPLETION_TASK_TYPE,
    CompletionRequest,
)
from app.modules.messaging.tasks.schemas import TaskResponse, TaskSubmitResponse
from app.modules.platform.identity.auth import require_principal
from app.modules.platform.identity.schemas import Principal

# Mounted only when TASKS_ENABLED (see app/api/router.py).
router = APIRouter(prefix="/completions", tags=["completions"])


@router.post("/tasks", response_model=TaskSubmitResponse, status_code=202)
async def submit_completion(
    payload: CompletionRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> TaskSubmitResponse:
    service = get_task_services(request.app).service
    task = await service.submit(
        type=COMPLETION_TASK_TYPE,
        payload=payload.model_dump(mode="json"),
        principal_id=principal.id,
        request_id=get_request_id(),
    )
    return TaskSubmitResponse.model_validate(task)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_completion_task(
    task_id: str,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> TaskResponse:
    service = get_task_services(request.app).service
    task = await service.require_owned(
        task_id, principal_id=principal.id, type=COMPLETION_TASK_TYPE
    )
    return TaskResponse.model_validate(task)
