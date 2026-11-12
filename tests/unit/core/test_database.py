from io import StringIO
from pathlib import Path

from sqlalchemy.engine import URL, make_url

from alembic import command
from alembic.config import Config
from app.core.database.engine import build_engine
from tests.factories import build_test_settings


def test_postgres_url_round_trips_reserved_characters():
    password = "".join(["p", "@", "s", "/", "s", ":", "w", "#", "d", "%", "x y"])
    user = "us" + "@" + "er"
    database = "db" + "/" + "name"
    settings = build_test_settings(
        POSTGRES_HOST="db.internal",
        POSTGRES_PORT=6543,
        POSTGRES_USER=user,
        POSTGRES_PASSWORD=password,
        POSTGRES_DB=database,
    )

    url = make_url(settings.POSTGRES_URL)

    assert url.drivername == "postgresql+asyncpg"
    assert url.host == "db.internal"
    assert url.port == 6543
    assert url.username == user
    assert url.password == password
    assert url.database == database


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


def test_alembic_env_accepts_a_percent_encoded_url():
    root = Path(__file__).resolve().parents[3]
    password = "".join(["p", "%", "s", "@", "s", "/", "w"])
    url = URL.create(
        "postgresql+asyncpg",
        username="u",
        password=password,
        host="db.internal",
        database="app",
    ).render_as_string(hide_password=False)
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.attributes["database_url"] = url
    config.output_buffer = StringIO()

    command.upgrade(config, "head", sql=True)

    assert "CREATE TABLE" in config.output_buffer.getvalue()
