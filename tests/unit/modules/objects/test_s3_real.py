"""S3 gateway against a real S3-compatible server (LocalStack in CI).

Skipped unless ``S3_TEST_ENDPOINT_URL`` is set, e.g. ``http://localhost:4566``.
Needs ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` (any value) in the env.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from app.modules.platform.objects.adapters.s3 import S3ObjectGateway

aioboto3 = pytest.importorskip("aioboto3")
ENDPOINT = os.environ.get("S3_TEST_ENDPOINT_URL")
REGION = "us-east-1"

pytestmark = pytest.mark.skipif(not ENDPOINT, reason="S3_TEST_ENDPOINT_URL not set")


@pytest_asyncio.fixture
async def bucket() -> AsyncIterator[str]:
    name = f"test-{uuid.uuid4().hex[:12]}"
    async with aioboto3.Session().client(
        "s3", region_name=REGION, endpoint_url=ENDPOINT
    ) as client:
        await client.create_bucket(Bucket=name)
        yield name
        await client.delete_bucket(Bucket=name)


async def test_open_succeeds_for_an_existing_bucket(bucket):
    gateway = await S3ObjectGateway(
        bucket=bucket, region_name=REGION, endpoint_url=ENDPOINT
    ).open()
    try:
        await gateway.put("a.txt", b"x")
        assert await gateway.get("a.txt") == b"x"
        await gateway.delete("a.txt")
    finally:
        await gateway.close()


async def test_open_fails_for_a_missing_bucket():
    with pytest.raises(RuntimeError, match="no-such-bucket"):
        await S3ObjectGateway(
            bucket="no-such-bucket", region_name=REGION, endpoint_url=ENDPOINT
        ).open()
