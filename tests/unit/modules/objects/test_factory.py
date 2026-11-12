from collections.abc import Callable

import pytest

from app.bootstrap.addons.objects import ObjectAddon
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.objects.adapters.s3 import S3ObjectGateway
from tests.factories import build_test_settings, open_addon
from tests.infra import S3Target

pytest.importorskip("aioboto3")


async def test_object_addon_attaches_gateway_when_enabled(
    infra_settings: Callable[..., Settings],
    s3_target: S3Target,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", s3_target.access_key)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", s3_target.secret_key)
    resources = ApplicationResources()
    settings = infra_settings(
        OBJECTS_ENABLED=True,
        OBJECT_PREFIX=s3_target.prefix,
        OBJECT_S3_BUCKET=s3_target.bucket,
        OBJECT_S3_REGION=s3_target.region,
        OBJECT_S3_ENDPOINT_URL=s3_target.endpoint_url,
    )

    stack = await open_addon(ObjectAddon(), resources, settings)

    assert isinstance(resources.objects, S3ObjectGateway)
    await stack.aclose()


def test_object_addon_respects_enabled_flag():
    addon = ObjectAddon()

    assert (
        addon.is_enabled(
            build_test_settings(OBJECTS_ENABLED=True, OBJECT_S3_BUCKET="bucket")
        )
        is True
    )
    assert addon.is_enabled(build_test_settings(OBJECTS_ENABLED=False)) is False
