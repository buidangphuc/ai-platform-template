from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    PROMPT = "prompt"
    MODEL = "model"
    RETRIEVER = "retriever"
    EVAL_DATASET = "eval_dataset"
    AGENT = "agent"


class ArtifactManifest(BaseModel):
    name: str
    version: str
    type: ArtifactType
    owner: str
    created_at: datetime
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    runtime_dependencies: list[str] = Field(min_length=1)
    eval_report: str
    risk_notes: list[str] = Field(default_factory=list)
    artifact_uri: str
