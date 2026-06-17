import pytest

from app.core.errors import ForbiddenError
from app.modules.platform.identity.auth import require_scopes
from app.modules.platform.identity.schemas import Principal


async def test_require_scopes_returns_principal_when_all_present():
    principal = Principal(id="svc", type="service", scopes=("admin", "billing"))
    dependency = require_scopes("admin")

    result = await dependency(principal=principal)

    assert result is principal


async def test_require_scopes_raises_when_any_scope_missing():
    principal = Principal(id="svc", type="service", scopes=("billing",))
    dependency = require_scopes("admin", "billing")

    with pytest.raises(ForbiddenError) as exc_info:
        await dependency(principal=principal)

    assert exc_info.value.code == "insufficient_scope"
    assert exc_info.value.status_code == 403
    assert exc_info.value.data == {
        "required": ["admin", "billing"],
        "missing": ["admin"],
    }


async def test_require_scopes_with_empty_required_always_allows():
    principal = Principal(id="svc", type="service", scopes=())
    dependency = require_scopes()

    result = await dependency(principal=principal)

    assert result is principal
