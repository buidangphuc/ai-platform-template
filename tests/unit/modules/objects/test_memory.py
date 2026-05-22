import pytest

from app.modules.objects.adapters.memory import MemoryObjectGateway


async def test_memory_object_gateway_put_get_exists_delete_round_trip():
    gateway = MemoryObjectGateway(prefix="app")

    await gateway.put(
        "artifact.bin", b"payload", content_type="application/octet-stream"
    )

    assert await gateway.exists("artifact.bin") is True
    assert await gateway.get("artifact.bin") == b"payload"

    await gateway.delete("artifact.bin")

    assert await gateway.exists("artifact.bin") is False
    assert await gateway.get("artifact.bin") is None


async def test_memory_object_gateway_presign_returns_stable_object_url():
    gateway = MemoryObjectGateway(prefix="app")

    assert await gateway.presign_get("artifact.bin") == "memory://app/artifact.bin"


async def test_memory_object_gateway_rejects_access_after_close():
    gateway = MemoryObjectGateway()
    await gateway.close()

    with pytest.raises(RuntimeError, match="closed"):
        await gateway.put("key", b"value")
