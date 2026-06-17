import pytest
from pydantic import ValidationError

from app.core.pagination import ListResponse, PaginationParams, build_list_response


def test_pagination_defaults_are_offset_based():
    params = PaginationParams()

    assert params.limit == 50
    assert params.offset == 0


def test_pagination_rejects_invalid_bounds():
    with pytest.raises(ValidationError):
        PaginationParams(limit=0)

    with pytest.raises(ValidationError):
        PaginationParams(offset=-1)


def test_build_list_response_wraps_items_with_pagination_metadata():
    params = PaginationParams(limit=2, offset=4)

    response = build_list_response(
        items=[{"id": "a"}, {"id": "b"}], total=10, params=params
    )

    assert isinstance(response, ListResponse)
    assert response.model_dump() == {
        "items": [{"id": "a"}, {"id": "b"}],
        "pagination": {
            "limit": 2,
            "offset": 4,
            "total": 10,
        },
    }
