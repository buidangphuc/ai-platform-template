import pytest
from httpx import AsyncClient

from app.bootstrap.application import create_app
from app.core.config import Settings
from tests.factories import api_client_for, build_test_settings
from tests.http_server import local_http_server as local_http_server
from tests.infra import (
    infra_settings as infra_settings,
    mongo_gateway as mongo_gateway,
    pg_engine as pg_engine,
    pg_sessionmaker as pg_sessionmaker,
    pg_url as pg_url,
    pytest_collection_modifyitems as pytest_collection_modifyitems,
    rabbitmq_queue_name as rabbitmq_queue_name,
    rabbitmq_url as rabbitmq_url,
    rag_service as rag_service,
    rag_settings as rag_settings,
    redis_client as redis_client,
    redis_prefix as redis_prefix,
    redis_queue as redis_queue,
    s3_target as s3_target,
    sqs_queue as sqs_queue,
    task_store as task_store,
    worker_settings as worker_settings,
)


@pytest.fixture()
def test_settings() -> Settings:
    return build_test_settings()


@pytest.fixture()
async def client(test_settings: Settings):
    app = create_app(settings=test_settings, init_resources=False)
    async with api_client_for(app) as test_client:
        yield test_client


@pytest.fixture()
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}
