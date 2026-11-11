from collections.abc import AsyncIterator, Callable

import boto3
import httpx
import pytest
from botocore.exceptions import ClientError

from app.core.config import Settings
from app.modules.platform.objects.adapters.s3 import S3ObjectGateway
from app.modules.platform.objects.factory import open_object_gateway
from tests.infra import S3Target

aioboto3 = pytest.importorskip("aioboto3")

UNREACHABLE_ENDPOINT = "http://127.0.0.1:1"


def _gateway(
    target: S3Target,
    *,
    bucket: str | None = None,
    endpoint_url: str | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
) -> S3ObjectGateway:
    return S3ObjectGateway(
        bucket=bucket or target.bucket,
        region_name=target.region,
        prefix=target.prefix,
        endpoint_url=endpoint_url or target.endpoint_url,
        session_factory=lambda: aioboto3.Session(
            aws_access_key_id=access_key or target.access_key,
            aws_secret_access_key=secret_key or target.secret_key,
        ),
    )


@pytest.fixture()
async def gateway(s3_target: S3Target) -> AsyncIterator[S3ObjectGateway]:
    opened = await _gateway(s3_target).open()
    try:
        yield opened
    finally:
        await opened.close()


def _boto_client(target: S3Target):
    return boto3.client(
        "s3",
        endpoint_url=target.endpoint_url,
        aws_access_key_id=target.access_key,
        aws_secret_access_key=target.secret_key,
        region_name=target.region,
    )


async def test_put_get_exists_and_delete_round_trip_under_the_prefix(
    gateway: S3ObjectGateway, s3_target: S3Target
):
    await gateway.put("reports/output.json", b"{}", content_type="application/json")

    stored = _boto_client(s3_target).head_object(
        Bucket=s3_target.bucket, Key=f"{s3_target.prefix}reports/output.json"
    )
    assert stored["ContentType"] == "application/json"
    assert await gateway.get("reports/output.json") == b"{}"
    assert await gateway.exists("reports/output.json") is True

    await gateway.delete("reports/output.json")

    assert await gateway.exists("reports/output.json") is False
    assert await gateway.get("reports/output.json") is None


async def test_get_and_exists_report_a_missing_key(gateway: S3ObjectGateway):
    assert await gateway.get("missing.txt") is None
    assert await gateway.exists("missing.txt") is False


async def test_list_is_scoped_to_the_prefix_and_limited(gateway: S3ObjectGateway):
    for name in ("a/1.txt", "a/2.txt", "b/1.txt"):
        await gateway.put(name, b"x")

    assert sorted(await gateway.list()) == ["a/1.txt", "a/2.txt", "b/1.txt"]
    assert sorted(await gateway.list("a/")) == ["a/1.txt", "a/2.txt"]
    assert len(await gateway.list(limit=2)) == 2
    with pytest.raises(ValueError, match="limit must be positive"):
        await gateway.list(limit=0)


async def test_presigned_urls_grant_scoped_access(gateway: S3ObjectGateway):
    put_url = await gateway.presign_put(
        "signed.txt", expires_seconds=60, content_type="text/plain"
    )
    async with httpx.AsyncClient() as http:
        uploaded = await http.put(
            put_url, content=b"signed", headers={"Content-Type": "text/plain"}
        )
        assert uploaded.status_code == 200

        get_url = await gateway.presign_get("signed.txt", expires_seconds=60)
        downloaded = await http.get(get_url)

    assert downloaded.content == b"signed"
    assert await gateway.get("signed.txt") == b"signed"


async def test_open_object_gateway_builds_the_s3_backend_from_settings(
    infra_settings: Callable[..., Settings],
    s3_target: S3Target,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", s3_target.access_key)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", s3_target.secret_key)
    settings = infra_settings(
        OBJECTS_ENABLED=True,
        OBJECT_BACKEND="s3",
        OBJECT_PREFIX=s3_target.prefix,
        OBJECT_S3_BUCKET=s3_target.bucket,
        OBJECT_S3_REGION=s3_target.region,
        OBJECT_S3_ENDPOINT_URL=s3_target.endpoint_url,
    )

    opened = await open_object_gateway(settings)
    try:
        await opened.put("from-settings.txt", b"ok")
        listed = _boto_client(s3_target).list_objects_v2(
            Bucket=s3_target.bucket, Prefix=s3_target.prefix
        )
    finally:
        await opened.close()

    assert [item["Key"] for item in listed["Contents"]] == [
        f"{s3_target.prefix}from-settings.txt"
    ]


async def test_open_fails_when_the_endpoint_is_unreachable(
    s3_target: S3Target, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("AWS_MAX_ATTEMPTS", "1")
    with pytest.raises(RuntimeError, match=s3_target.bucket) as excinfo:
        await _gateway(s3_target, endpoint_url=UNREACHABLE_ENDPOINT).open()

    assert UNREACHABLE_ENDPOINT in str(excinfo.value)
    assert excinfo.value.__cause__ is not None


@pytest.mark.parametrize(
    ("access_key", "secret_key"),
    [("not-an-access-key", None), (None, "wrong-secret")],
    ids=["unknown_access_key", "wrong_secret"],
)
async def test_open_fails_on_bad_credentials(
    s3_target: S3Target, access_key: str | None, secret_key: str | None
):
    gateway = _gateway(s3_target, access_key=access_key, secret_key=secret_key)

    with pytest.raises(RuntimeError, match=s3_target.bucket) as excinfo:
        await gateway.open()

    assert isinstance(excinfo.value.__cause__, ClientError)


async def test_open_tolerates_a_bucket_the_credentials_cannot_list(
    s3_target: S3Target,
):
    gateway = await _gateway(s3_target, bucket="aipt-test-foreign-bucket").open()

    try:
        with pytest.raises(ClientError) as excinfo:
            await gateway.put("k", b"v")
    finally:
        await gateway.close()

    assert excinfo.value.response["Error"]["Code"] == "AccessDenied"
