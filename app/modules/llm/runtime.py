from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import ParrotFakeChatModel

from app.core.config import Settings


def build_chat_model(settings: Settings) -> BaseChatModel:
    if not settings.CHAT_MODEL:
        return ParrotFakeChatModel()
    return init_chat_model(model=settings.CHAT_MODEL)
