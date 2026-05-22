"""Async completion endpoints — submit a task, poll for the result."""

from fastapi import APIRouter, Depends, Request

from app.api.v1.completions.schemas import CompletionRequest
from app.bootstrap.state import require_app_resource
from app.modules.identity.auth import require_principal
from app.modules.tasks.schemas import TaskResponse, TaskSubmitResponse
from app.modules.tasks.service import TaskService

router = APIRouter(
    prefix="/acompletions",
    tags=["acompletions"],
    dependencies=[Depends(require_principal)],
)

TASK_TYPE = "completion"


def get_task_service(request: Request) -> TaskService:
    return require_app_resource(
        request.app,
        "task_service",
        code="task_service_not_configured",
        message="Async task service is disabled or lifespan has not opened it",
    )


@router.post("", response_model=TaskSubmitResponse, status_code=202)
async def submit_completion(
    payload: CompletionRequest,
    request: Request,
):
    service = get_task_service(request)
    task = await service.submit(
        type=TASK_TYPE,
        payload=payload.model_dump(mode="json"),
    )
    return TaskSubmitResponse(
        task_id=task.id,
        status=task.status,
        expires_at=task.expires_at,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_completion_task(task_id: str, request: Request):
    service = get_task_service(request)
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
