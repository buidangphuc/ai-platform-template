from collections.abc import Callable, Sequence
from typing import Any

from app.api.v1.completions.router import router as completions_router
from app.api.v1.completions.tasks import router as completion_tasks_router
from app.bootstrap.features.base import Feature
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.business.completions.guards import CompletionGuard
from app.modules.business.completions.handlers.echo import EchoCompletionHandler
from app.modules.business.completions.handlers.llm import LlmCompletionHandler
from app.modules.business.completions.ports import CompletionHandler
from app.modules.business.completions.schemas import (
    COMPLETION_TASK_TYPE,
    CompletionRequest,
)
from app.modules.business.completions.service import CompletionService, StreamPolicy
from app.modules.messaging.tasks.store import TaskRecord

CompletionHandlerFactory = Callable[[ApplicationResources, Settings], CompletionHandler]
CompletionGuardsFactory = Callable[
    [ApplicationResources, Settings], Sequence[CompletionGuard]
]


def _stream_policy(settings: Settings) -> StreamPolicy:
    return StreamPolicy(
        first_token_timeout=settings.STREAM_FIRST_TOKEN_TIMEOUT_SECONDS,
        idle_timeout=settings.STREAM_IDLE_TIMEOUT_SECONDS,
    )


def default_completion_guards_factory(
    resources: ApplicationResources,
    settings: Settings,
) -> Sequence[CompletionGuard]:
    """Scaffold ships no guards; products add theirs (input/output checks)."""
    return ()


def default_completion_handler_factory(
    resources: ApplicationResources,
    settings: Settings,
) -> CompletionHandler:
    """Model-backed when ``LLM_ENABLED``, else the echo scaffold; products pass their own factory."""
    if resources.llm is not None:
        return LlmCompletionHandler(resources.llm, _stream_policy(settings))
    return EchoCompletionHandler()


async def complete_task(
    resources: ApplicationResources, task: TaskRecord
) -> dict[str, Any]:
    result = await resources.service(CompletionService).complete(
        CompletionRequest(**task.payload)
    )
    return result.model_dump(mode="json")


def completions_feature(
    handler_factory: CompletionHandlerFactory = default_completion_handler_factory,
    guards_factory: CompletionGuardsFactory = default_completion_guards_factory,
) -> Feature:
    def build(resources: ApplicationResources, settings: Settings) -> CompletionService:
        return CompletionService(
            handler_factory(resources, settings),
            guards=guards_factory(resources, settings),
            policy=_stream_policy(settings),
        )

    return Feature(
        name="completions",
        service=CompletionService,
        build=build,
        routers=(completions_router,),
        task_routers=(completion_tasks_router,),
        tasks={COMPLETION_TASK_TYPE: complete_task},
    )
