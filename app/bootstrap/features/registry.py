from app.bootstrap.features.base import Feature
from app.bootstrap.features.completions import completions_feature

FEATURES: tuple[Feature, ...] = (completions_feature(),)
