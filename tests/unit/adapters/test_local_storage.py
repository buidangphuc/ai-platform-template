import pytest

from app.adapters.storage.local import LocalObjectStorage
from app.contracts.storage import ObjectStorage


async def test_local_storage_puts_gets_and_deletes_bytes(tmp_path):
    storage: ObjectStorage = LocalObjectStorage(root=tmp_path)

    stored = await storage.put_bytes(
        bucket="artifacts",
        key="runs/run-1/result.txt",
        data=b"hello",
        content_type="text/plain",
        metadata={"run_id": "run-1"},
    )

    assert stored.bucket == "artifacts"
    assert stored.key == "runs/run-1/result.txt"
    assert stored.size_bytes == 5
    assert await storage.exists("artifacts", "runs/run-1/result.txt")
    assert await storage.get_bytes("artifacts", "runs/run-1/result.txt") == b"hello"

    await storage.delete("artifacts", "runs/run-1/result.txt")

    assert not await storage.exists("artifacts", "runs/run-1/result.txt")


async def test_local_storage_blocks_path_traversal(tmp_path):
    storage = LocalObjectStorage(root=tmp_path)

    with pytest.raises(ValueError, match="unsafe"):
        await storage.put_bytes(
            bucket="artifacts",
            key="../secret.txt",
            data=b"secret",
            content_type="text/plain",
        )
