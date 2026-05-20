from fastapi import FastAPI

from app.api.router import build_api_router
from app.core.config import Settings, get_settings
from app.core.database import check_postgres_connection
from app.core.errors import register_exception_handlers
from app.core.health import HealthService
from app.core.logging import configure_logging
from app.core.redaction import RedactionPolicy
from app.core.redis import check_redis_connection
from app.core.registry import build_runtime_adapters
from app.core.request_context import RequestIdMiddleware
from app.modules.evals.rag import RAGEvaluationService
from app.modules.feedback.repository import FeedbackRepository
from app.modules.identity.repository import ApiKeyRepository
from app.modules.prompts.registry import InMemoryPromptRegistry
from app.modules.rag.chunking import TextChunker
from app.modules.rag.service import RagService
from app.modules.rate_limit.service import InMemoryRateLimiter
from app.modules.usage.tracker import InMemoryUsageTracker


def create_app(
    settings: Settings | None = None,
    *,
    init_resources: bool = True,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging()
    app = FastAPI(
        title=resolved_settings.PROJECT_NAME,
        version=resolved_settings.VERSION,
        description=resolved_settings.DESCRIPTION,
    )
    app.state.settings = resolved_settings
    app.state.usage_tracker = InMemoryUsageTracker()
    app.state.adapters = build_runtime_adapters(
        resolved_settings,
        usage_tracker=app.state.usage_tracker,
    )
    app.state.redaction_policy = RedactionPolicy.from_trace_content(
        resolved_settings.TRACE_CONTENT,
    )
    app.state.prompt_registry = InMemoryPromptRegistry.with_defaults()
    app.state.health_service = HealthService(
        check_external_dependencies=init_resources,
        postgres_check=lambda: check_postgres_connection(resolved_settings),
        redis_check=lambda: check_redis_connection(resolved_settings),
    )
    app.state.api_key_repository = ApiKeyRepository()
    app.state.feedback_repository = FeedbackRepository()
    app.state.rate_limiter = InMemoryRateLimiter(
        limit=resolved_settings.DEFAULT_RATE_LIMIT_PER_MINUTE,
    )
    app.state.rag_service = RagService(
        embeddings=app.state.adapters.embeddings,
        vector_store=app.state.adapters.vector_store,
        llm=app.state.adapters.llm,
        prompt_registry=app.state.prompt_registry,
        chunker=TextChunker(
            chunk_size=resolved_settings.RAG_CHUNK_SIZE,
            overlap=resolved_settings.RAG_CHUNK_OVERLAP,
        ),
        usage_tracker=app.state.usage_tracker,
        observability=app.state.adapters.observability,
        redaction_policy=app.state.redaction_policy,
    )
    app.state.rag_eval_service = RAGEvaluationService(
        rag_service=app.state.rag_service,
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(build_api_router(resolved_settings))
    return app
