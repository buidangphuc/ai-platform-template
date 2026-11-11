from app.bootstrap.features.base import Feature
from app.bootstrap.features.completions import completions_feature
from app.bootstrap.features.conversations import conversations_feature

FEATURES: tuple[Feature, ...] = (completions_feature(), conversations_feature())
