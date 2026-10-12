from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from pymongo.errors import DuplicateKeyError

from app.bootstrap.addons.quota import QuotaAddon
from app.bootstrap.resources import ApplicationResources
from app.core.mongo import build_mongo_client
from app.modules.platform.quota.adapters.mongo import MongoQuotaStore
from app.modules.platform.quota.models import (
    QuotaReservationStatus,
    QuotaUsageQuery,
    ReserveQuota,
)
from app.modules.platform.quota.service import QuotaService
from tests.factories import build_test_settings
from tests.mongo_fake import FakeCollection, FakeMongoGateway, _matches


class RacyCollection(FakeCollection):
    """Fake with real suspension points and unique-index enforcement.

    Each operation yields to the event loop first (so ``asyncio.gather`` can
    interleave callers) but stays atomic afterwards, like a single Mongo command.
    """

    def __init__(self) -> None:
        super().__init__()
        self.unique_keys: list[tuple[str, ...]] = []
        self.indexes: list[dict[str, Any]] = []

    async def create_index(self, keys, **options) -> str:
        self.indexes.append({"keys": keys, **options})
        return options.get("name", "")

    async def find_one(self, query):
        await asyncio.sleep(0)
        return await super().find_one(query)

    async def find_one_and_update(self, query, update, return_document=None):
        await asyncio.sleep(0)
        return await super().find_one_and_update(query, update, return_document)

    async def find_one_and_delete(self, query):
        await asyncio.sleep(0)
        for index, doc in enumerate(self.docs):
            if _matches(doc, query):
                return self.docs.pop(index)
        return None

    async def insert_one(self, document) -> None:
        await asyncio.sleep(0)
        for keys in self.unique_keys:
            if any(document.get(k) is None for k in keys):
                continue
            if any(all(d.get(k) == document[k] for k in keys) for d in self.docs):
                raise DuplicateKeyError("duplicate")
        await super().insert_one(document)


class RacyGateway(FakeMongoGateway):
    def collection(self, name: str) -> RacyCollection:
        return self._collections.setdefault(name, RacyCollection())  # type: ignore[return-value]


RESET = datetime.now(UTC) + timedelta(minutes=5)


def _store() -> tuple[MongoQuotaStore, RacyCollection, RacyCollection]:
    gateway = RacyGateway()
    store = MongoQuotaStore(gateway)  # type: ignore[arg-type]
    return (
        store,
        gateway.collection("quota_counters"),
        gateway.collection("quota_reservations"),
    )


def _command(
    reservation_id: str, *, key: str | None = None, window: str = "w1"
) -> ReserveQuota:
    return ReserveQuota(
        subject_id="s",
        resource="r",
        window_key=window,
        limit=5,
        cost=1,
        reset_at=RESET,
        reservation_id=reservation_id,
        idempotency_key=key,
    )


def test_build_mongo_client_is_tz_aware(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_client(uri, **kwargs):
        captured.update(kwargs)
        return object()

    fake_module = SimpleNamespace(AsyncIOMotorClient=fake_client)
    monkeypatch.setitem(sys.modules, "motor.motor_asyncio", fake_module)

    build_mongo_client(build_test_settings())

    assert captured["tz_aware"] is True
    assert captured["tzinfo"] is UTC


async def test_refund_concurrent_decrements_counter_once():
    store, counters, _ = _store()
    assert await store.reserve(_command("r1")) is not None

    results = await asyncio.gather(
        store.refund("r1"), store.refund("r1"), return_exceptions=True
    )

    assert all(not isinstance(r, Exception) for r in results)
    assert counters.docs[0]["used"] == 0


async def test_finalize_then_refund_is_rejected_and_keeps_usage():
    store, counters, _ = _store()
    await store.reserve(_command("r1"))

    await store.finalize("r1")
    with pytest.raises(ValueError):
        await store.refund("r1")

    assert counters.docs[0]["used"] == 1


async def test_refund_missing_reservation_raises_key_error():
    store, _, _ = _store()
    with pytest.raises(KeyError):
        await store.refund("nope")


async def test_concurrent_refund_and_finalize_has_single_winner():
    store, counters, reservations = _store()
    await store.reserve(_command("r1"))

    results = await asyncio.gather(
        store.refund("r1"), store.finalize("r1"), return_exceptions=True
    )

    if reservations.docs[0]["status"] == QuotaReservationStatus.REFUNDED.value:
        assert counters.docs[0]["used"] == 0
        assert isinstance(results[1], ValueError)
    else:
        assert counters.docs[0]["used"] == 1
        assert isinstance(results[0], ValueError)


async def test_reserve_same_idempotency_key_returns_existing_without_leak():
    store, counters, reservations = _store()
    reservations.unique_keys.append(
        ("subject_id", "resource", "window_key", "idempotency_key")
    )

    first, second = await asyncio.gather(
        store.reserve(_command("a", key="k")),
        store.reserve(_command("b", key="k")),
    )

    assert first is not None and second is not None
    assert first.id == second.id
    assert len(reservations.docs) == 1
    assert counters.docs[0]["used"] == 1


async def test_migration_moves_usage_once_under_concurrency():
    store, counters, reservations = _store()
    await store.reserve(_command("r1", window="w1"))
    await store.reserve(_command("r2", window="w1"))

    query = QuotaUsageQuery(
        subject_id="s", resource="r", window_key="w2", limit=5, reset_at=RESET
    )
    await asyncio.gather(store.get_usage(query), store.get_usage(query))

    assert [d["window_key"] for d in counters.docs] == ["w2"]
    assert counters.docs[0]["used"] == 2
    assert {d["window_key"] for d in reservations.docs} == {"w2"}


async def test_ensure_indexes_declares_unique_partial_and_ttl_indexes():
    store, counters, reservations = _store()

    await store.ensure_indexes()
    await store.ensure_indexes()

    counter_unique = [i for i in counters.indexes if i.get("unique")]
    assert counter_unique[0]["keys"] == [
        ("subject_id", 1),
        ("resource", 1),
        ("window_key", 1),
    ]
    reservation_unique = [i for i in reservations.indexes if i.get("unique")]
    assert reservation_unique[0]["partialFilterExpression"] == {
        "idempotency_key": {"$type": "string"}
    }
    assert reservation_unique[0]["keys"][-1] == ("idempotency_key", 1)
    assert any("expireAfterSeconds" in i for i in counters.indexes)
    assert any("expireAfterSeconds" in i for i in reservations.indexes)


async def test_quota_addon_ensures_mongo_indexes_when_opening():
    gateway = RacyGateway()
    resources = ApplicationResources(mongo=gateway)  # type: ignore[arg-type]

    await QuotaAddon().open(
        resources,
        build_test_settings(
            QUOTA_ENABLED=True, QUOTA_BACKEND="mongo", MONGO_ENABLED=True
        ),
    )

    assert isinstance(resources.quota, QuotaService)
    assert gateway.collection("quota_counters").indexes
    assert gateway.collection("quota_reservations").indexes
