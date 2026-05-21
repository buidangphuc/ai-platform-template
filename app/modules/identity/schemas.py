from typing import Literal

from pydantic import BaseModel


class Principal(BaseModel):
    id: str
    type: Literal["user", "service", "anonymous"] = "service"
    scopes: tuple[str, ...] = ()
