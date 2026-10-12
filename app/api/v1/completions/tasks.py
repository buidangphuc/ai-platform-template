from fastapi import APIRouter, Request

from app.bootstrap.state import get_task_services
from app.core.request_context import get_request_id
from app.modules.business.completions.schemas import CompletionRequest
from app.modules.messaging.tasks.schemas import TaskResponse, TaskSubmitResponse

TASK_TYPE = "completion"

router = APIRouter()


@router.post("/tasks", response_model=TaskSubmitResponse, status_code=202)
async def submit_completion(
    payload: CompletionRequest,
    request: Request,
) -> TaskSubmitResponse:
    service = get_task_services(request.app).service
    task = await service.submit(
        type=TASK_TYPE,
        payload=payload.model_dump(mode="json"),
        request_id=get_request_id(),
    )
    return TaskSubmitResponse(
        task_id=task.id,
        status=task.status,
        expires_at=task.expires_at,
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_completion_task(
    task_id: str,
    request: Request,
) -> TaskResponse:
    service = get_task_services(request.app).service
    task = await service.require(task_id)
    return TaskResponse(
        id=task.id,
        type=task.type,
        status=task.status,
        payload=task.payload,
        result=task.result,
        error=task.error,
        attempts=task.attempts,
        created_at=task.created_at,
        updated_at=task.updated_at,
        expires_at=task.expires_at,
    )
