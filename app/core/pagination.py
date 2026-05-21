from typing import Generic, TypeVar

from pydantic import BaseModel, Field

ItemT = TypeVar("ItemT")


class PaginationParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PaginationMeta(BaseModel):
    limit: int
    offset: int
    total: int = Field(ge=0)


class ListResponse(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    pagination: PaginationMeta


def build_list_response(
    *,
    items: list[ItemT],
    total: int,
    params: PaginationParams,
) -> ListResponse[ItemT]:
    return ListResponse(
        items=items,
        pagination=PaginationMeta(
            limit=params.limit,
            offset=params.offset,
            total=total,
        ),
    )
