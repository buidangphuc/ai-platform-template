from pydantic import BaseModel, Field


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CreateApiKeyResponse(BaseModel):
    api_key_id: str
    name: str
    api_key: str


class AuthenticatedPrincipal(BaseModel):
    auth_type: str
    api_key_id: str
    name: str
