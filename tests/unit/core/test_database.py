from app.core.database.engine import build_engine
from tests.factories import build_test_settings


def test_build_engine_applies_pool_settings():
    settings = build_test_settings(
        DB_POOL_SIZE=7,
        DB_MAX_OVERFLOW=14,
        DB_POOL_TIMEOUT_SECONDS=42,
        DB_POOL_RECYCLE_SECONDS=600,
    )

    engine = build_engine(settings)

    pool = engine.sync_engine.pool
    assert pool.size() == 7
    assert pool._max_overflow == 14
    assert pool._timeout == 42
    assert pool._recycle == 600
