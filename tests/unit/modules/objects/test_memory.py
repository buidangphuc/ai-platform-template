import pytest

from app.modules.platform.objects.adapters.memory import MemoryObjectGateway


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


async def test_memory_object_gateway_presign_get_returns_stable_url():
    gateway = MemoryObjectGateway(prefix="app")

    assert (
        await gateway.presign_get("artifact.bin") == "memory://app/artifact.bin?op=get"
    )


async def test_memory_object_gateway_presign_put_includes_content_type():
    gateway = MemoryObjectGateway(prefix="app")

    url = await gateway.presign_put(
        "artifact.bin", content_type="application/octet-stream"
    )

    assert url.startswith("memory://app/artifact.bin?op=put")
    assert "content_type=application/octet-stream" in url


async def test_memory_object_gateway_list_returns_keys_relative_to_prefix():
    gateway = MemoryObjectGateway(prefix="app")
    await gateway.put("docs/a.txt", b"a")
    await gateway.put("docs/b.txt", b"b")
    await gateway.put("images/c.png", b"c")

    docs = await gateway.list("docs")
    everything = await gateway.list()

    assert docs == ["docs/a.txt", "docs/b.txt"]
    assert set(everything) == {"docs/a.txt", "docs/b.txt", "images/c.png"}


async def test_memory_object_gateway_list_honors_limit():
    gateway = MemoryObjectGateway(prefix="app")
    for i in range(5):
        await gateway.put(f"item-{i}.txt", b"x")

    page = await gateway.list(limit=3)

    assert len(page) == 3


async def test_memory_object_gateway_rejects_access_after_close():
    gateway = MemoryObjectGateway()
    await gateway.close()

    with pytest.raises(RuntimeError, match="closed"):
        await gateway.put("key", b"value")
