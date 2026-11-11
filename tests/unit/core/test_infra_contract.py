import pytest
from sqlalchemy import text

from app.core.redis import build_redis_client
from tests import infra
from tests.factories import build_test_settings


def test_require_skips_when_variable_missing(monkeypatch):
    monkeypatch.delenv("TEST_REDIS_URL", raising=False)
    monkeypatch.delenv("TEST_INFRA_REQUIRED", raising=False)
    with pytest.raises(pytest.skip.Exception, match="TEST_REDIS_URL not set"):
        infra.require("redis")


def test_require_fails_when_variable_missing_and_required(monkeypatch):
    monkeypatch.delenv("TEST_REDIS_URL", raising=False)
    monkeypatch.setenv("TEST_INFRA_REQUIRED", "1")
    with pytest.raises(pytest.fail.Exception, match="TEST_REDIS_URL not set"):
        infra.require("redis")


def test_require_returns_value(monkeypatch):
    monkeypatch.setenv("TEST_REDIS_URL", "redis://localhost:6379/0")
    assert infra.require("redis") == "redis://localhost:6379/0"


def test_redis_client_uses_configured_username():
    settings = build_test_settings(REDIS_USERNAME="aipt")
    client = build_redis_client(settings)
    assert client.connection_pool.connection_kwargs["username"] == "aipt"


def test_redis_client_without_username_sends_none():
    client = build_redis_client(build_test_settings())
    assert client.connection_pool.connection_kwargs["username"] is None


def test_infra_settings_parses_env_urls(monkeypatch):
    monkeypatch.setenv("TEST_POSTGRES_URL", "postgresql+asyncpg://u:p@db.local:15432/x")
    redis_url = "redis://ru:rp@cache.local:16379/3"  # pragma: allowlist secret
    monkeypatch.setenv("TEST_REDIS_URL", redis_url)
    settings = infra.settings_from_env(MONGO_ENABLED=False)
    assert (settings.POSTGRES_HOST, settings.POSTGRES_PORT) == ("db.local", 15432)
    assert (settings.POSTGRES_USER, settings.POSTGRES_PASSWORD) == ("u", "p")
    assert settings.POSTGRES_DB == "x"
    assert (settings.REDIS_HOST, settings.REDIS_PORT) == ("cache.local", 16379)
    assert (settings.REDIS_USERNAME, settings.REDIS_PASSWORD) == ("ru", "rp")
    assert settings.REDIS_DATABASE == 3


async def test_alembic_created_the_schema(pg_sessionmaker):
    async with pg_sessionmaker() as session:
        rows = await session.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
    tables = {row[0] for row in rows}
    assert {"tasks", "conversations", "alembic_version"} <= tables


async def _insert_same_conversation(pg_sessionmaker) -> int:
    async with pg_sessionmaker() as session:
        await session.execute(
            text(
                "INSERT INTO conversations (id, principal_id, title, created_at,"
                " updated_at) VALUES ('same-id', 'p', 't', now(), now())"
            )
        )
        await session.commit()
        count = await session.execute(text("SELECT count(*) FROM conversations"))
        return count.scalar_one()


async def test_pg_rows_do_not_leak_first(pg_sessionmaker):
    assert await _insert_same_conversation(pg_sessionmaker) == 1


async def test_pg_rows_do_not_leak_second(pg_sessionmaker):
    assert await _insert_same_conversation(pg_sessionmaker) == 1


async def test_pg_engine_targets_throwaway_database(pg_engine, pg_url):
    assert pg_url.rsplit("/", 1)[1].startswith("aipt_t_")
    async with pg_engine.connect() as conn:
        name = await conn.scalar(text("SELECT current_database()"))
    assert name == pg_url.rsplit("/", 1)[1]


_written_keys: list[bytes] = []


async def test_redis_keys_carry_prefix_first(redis_client, redis_prefix):
    for suffix in ("a", "b"):
        await redis_client.set(f"{redis_prefix}:{suffix}", "1")
    keys = [key async for key in redis_client.scan_iter(match=f"{redis_prefix}*")]
    assert len(keys) == 2
    assert all(key.decode().startswith(redis_prefix) for key in keys)
    _written_keys[:] = keys


async def test_redis_keys_gone_after_test(redis_client):
    assert _written_keys
    assert await redis_client.exists(*_written_keys) == 0


def test_redis_prefix_shape(redis_prefix):
    assert redis_prefix.startswith("aipt:test:")


async def test_infra_fixture_user_is_auto_marked(request, redis_client):
    assert request.node.get_closest_marker("infra") is not None


def test_plain_test_is_not_marked(request):
    assert request.node.get_closest_marker("infra") is None


async def test_infra_settings_uses_throwaway_database(infra_settings, pg_url):
    settings = infra_settings()
    assert pg_url.rsplit("/", 1)[1] == settings.POSTGRES_DB
    assert infra_settings(POSTGRES_DB="other").POSTGRES_DB == "other"


async def test_mongo_gateway_is_clean_and_usable(mongo_gateway):
    assert await mongo_gateway.database.list_collection_names() == []
    await mongo_gateway.collection("probe").insert_one({"k": 1})
    assert await mongo_gateway.collection("probe").count_documents({}) == 1


async def test_mongo_gateway_cleans_between_tests(mongo_gateway):
    assert await mongo_gateway.database.list_collection_names() == []


def test_s3_target_roundtrip(s3_target):
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=s3_target.endpoint_url,
        aws_access_key_id=s3_target.access_key,
        aws_secret_access_key=s3_target.secret_key,
        region_name=s3_target.region,
    )
    key = f"{s3_target.prefix}probe.txt"
    client.put_object(Bucket=s3_target.bucket, Key=key, Body=b"x")
    listed = client.list_objects_v2(Bucket=s3_target.bucket, Prefix=s3_target.prefix)
    assert [o["Key"] for o in listed["Contents"]] == [key]
    assert s3_target.prefix.startswith("test/") and s3_target.prefix.endswith("/")


def test_sqs_queue_roundtrip(sqs_queue):
    import boto3

    client = boto3.client(
        "sqs",
        endpoint_url=sqs_queue.endpoint_url,
        region_name="us-east-1",
        aws_access_key_id="x",
        aws_secret_access_key="x",
    )
    client.send_message(QueueUrl=sqs_queue.url, MessageBody="hi")
    received = client.receive_message(QueueUrl=sqs_queue.url, WaitTimeSeconds=1)
    assert received["Messages"][0]["Body"] == "hi"


def test_rabbitmq_fixtures(rabbitmq_url, rabbitmq_queue_name):
    assert rabbitmq_url.startswith("amqp")
    assert rabbitmq_queue_name.startswith("aipt.test.")
