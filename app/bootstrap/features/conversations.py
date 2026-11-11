from app.api.v1.conversations.router import router as conversations_router
from app.bootstrap.features.base import Feature
from app.bootstrap.resources import ApplicationResources, opened
from app.core.config import Settings
from app.modules.business.conversations.service import ConversationService
from app.modules.business.conversations.stores import ConversationStore


def build(resources: ApplicationResources, settings: Settings) -> ConversationService:
    return ConversationService(
        ConversationStore(opened(resources.sessionmaker, "sessionmaker")),
        opened(resources.llm, "llm"),
    )


def conversations_feature() -> Feature:
    return Feature(
        name="conversations",
        service=ConversationService,
        build=build,
        routers=(conversations_router,),
        models=("app.modules.business.conversations.models",),
        enabled=lambda settings: settings.CONVERSATIONS_ENABLED,
    )
