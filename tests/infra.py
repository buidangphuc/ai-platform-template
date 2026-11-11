import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg
import boto3
import pytest
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from alembic import command
from alembic.config import Config
from app.core.config import Settings
from app.modules.platform.mongo.factory import build_mongo_gateway
from app.modules.platform.mongo.gateway import MongoGateway
from tests.factories import build_test_settings

ROOT = Path(__file__).resolve().parents[1]

ENGINE_VARS = {
    "postgres": "TEST_POSTGRES_URL",
    "redis": "TEST_REDIS_URL",
    "mongo": "TEST_MONGO_URI",
    "s3": "TEST_S3_ENDPOINT_URL",
    "sqs": "TEST_SQS_ENDPOINT_URL",
    "rabbitmq": "TEST_RABBITMQ_URL",
}

INFRA_FIXTURES = frozenset(
    {
        "pg_url",
        "pg_engine",
        "pg_sessionmaker",
        "redis_prefix",
        "redis_client",
        "mongo_gateway",
        "s3_target",
        "sqs_queue",
        "rabbitmq_url",
        "rabbitmq_queue_name",
    }
)


def _env(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    if os.environ.get("TEST_INFRA_REQUIRED") == "1":
        pytest.fail(f"{name} not set (TEST_INFRA_REQUIRED=1)")
    pytest.skip(f"{name} not set")


def require(engine: str) -> str:
    return _env(ENGINE_VARS[engine])


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        fixturenames = getattr(item, "fixturenames", ())
        if INFRA_FIXTURES.intersection(fixturenames):
            item.add_marker(pytest.mark.infra)


def settings_from_env(**overrides: object) -> Settings:
    values: dict[str, object] = {}
    postgres_url = os.environ.get("TEST_POSTGRES_URL")
    if postgres_url:
        url = make_url(postgres_url)
        values.update(
            POSTGRES_HOST=url.host or "localhost",
            POSTGRES_PORT=url.port or 5432,
            POSTGRES_USER=url.username or "",
            POSTGRES_PASSWORD=url.password or "",
            POSTGRES_DB=url.database or "",
        )
    redis_url = os.environ.get("TEST_REDIS_URL")
    if redis_url:
        url = make_url(redis_url)
        values.update(
            REDIS_HOST=url.host or "localhost",
            REDIS_PORT=url.port or 6379,
            REDIS_USERNAME=url.username or "",
            REDIS_PASSWORD=url.password or "",
            REDIS_DATABASE=int(url.database or 0),
        )
    values.update(overrides)
    return build_test_settings(**values)


def _admin_dsn(url_text: str, database: str | None = None) -> str:
    url = make_url(url_text).set(drivername="postgresql")
    if database:
        url = url.set(database=database)
    return url.render_as_string(hide_password=False)


async def _pg_admin(url_text: str, statement: str) -> None:
    connection = await asyncpg.connect(_admin_dsn(url_text))
    try:
        await connection.execute(statement)
    finally:
        await connection.close()


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    base_url = require("postgres")
    name = f"aipt_t_{uuid.uuid4().hex[:8]}"
    asyncio.run(_pg_admin(base_url, f'CREATE DATABASE "{name}"'))
    url = make_url(base_url).set(database=name).render_as_string(hide_password=False)
    try:
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "alembic"))
        cfg.attributes["database_url"] = url
        command.upgrade(cfg, "head")
        yield url
    finally:
        asyncio.run(
            _pg_admin(base_url, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        )


@pytest.fixture()
async def pg_engine(pg_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(pg_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture()
async def pg_sessionmaker(
    pg_engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield async_sessionmaker(pg_engine, expire_on_commit=False)
    async with pg_engine.begin() as conn:
        rows = await conn.execute(
            text(
                "SELECT quote_ident(tablename) FROM pg_tables"
                " WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        )
        tables = [row[0] for row in rows]
        if tables:
            await conn.execute(
                text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")
            )


@pytest.fixture()
def redis_prefix() -> str:
    return f"aipt:test:{uuid.uuid4().hex[:8]}"


@pytest.fixture()
async def redis_client(
    request: pytest.FixtureRequest, redis_prefix: str
) -> AsyncIterator[aioredis.Redis]:
    url = require("redis")
    client = aioredis.Redis.from_url(
        url, decode_responses=bool(getattr(request, "param", False))
    )
    try:
        yield client
    finally:
        keys = [key async for key in client.scan_iter(match=f"{redis_prefix}*")]
        if keys:
            await client.delete(*keys)
        await client.aclose()


async def _drop_collections(gateway: MongoGateway) -> None:
    for name in await gateway.database.list_collection_names():
        await gateway.database.drop_collection(name)


@pytest.fixture()
async def mongo_gateway() -> AsyncIterator[MongoGateway]:
    uri = require("mongo")
    database = _env("TEST_MONGO_DATABASE")
    gateway = build_mongo_gateway(
        settings_from_env(MONGODB_URI=uri, MONGODB_DATABASE=database)
    )
    try:
        await _drop_collections(gateway)
        yield gateway
    finally:
        await _drop_collections(gateway)
        await gateway.close()


@dataclass(frozen=True)
class S3Target:
    endpoint_url: str
    bucket: str
    access_key: str
    secret_key: str
    region: str
    prefix: str


def _s3_client(target: S3Target) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=target.endpoint_url,
        aws_access_key_id=target.access_key,
        aws_secret_access_key=target.secret_key,
        region_name=target.region,
    )


@pytest.fixture()
def s3_target() -> Iterator[S3Target]:
    target = S3Target(
        endpoint_url=require("s3"),
        bucket=_env("TEST_S3_BUCKET"),
        access_key=_env("TEST_S3_ACCESS_KEY"),
        secret_key=_env("TEST_S3_SECRET_KEY"),
        region="us-east-1",
        prefix=f"test/{uuid.uuid4().hex[:8]}/",
    )
    yield target
    client = _s3_client(target)
    for page in client.get_paginator("list_objects_v2").paginate(
        Bucket=target.bucket, Prefix=target.prefix
    ):
        objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=target.bucket, Delete={"Objects": objects})


@dataclass(frozen=True)
class SqsQueue:
    url: str
    name: str
    endpoint_url: str
    region: str = "us-east-1"


@pytest.fixture()
def sqs_queue() -> Iterator[SqsQueue]:
    endpoint = require("sqs")
    name = f"aipt-test-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "sqs",
        endpoint_url=endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",  # pragma: allowlist secret
    )
    url = client.create_queue(QueueName=name)["QueueUrl"]
    yield SqsQueue(url=url, name=name, endpoint_url=endpoint)
    client.delete_queue(QueueUrl=url)


@pytest.fixture()
def rabbitmq_url() -> str:
    return require("rabbitmq")


@pytest.fixture()
def rabbitmq_queue_name() -> str:
    return f"aipt.test.{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def infra_settings(request: pytest.FixtureRequest) -> Callable[..., Settings]:
    def build(**overrides: object) -> Settings:
        values: dict[str, object] = {}
        if "pg_url" in request.fixturenames:
            values["POSTGRES_DB"] = make_url(request.getfixturevalue("pg_url")).database
        values.update(overrides)
        return settings_from_env(**values)

    return build
