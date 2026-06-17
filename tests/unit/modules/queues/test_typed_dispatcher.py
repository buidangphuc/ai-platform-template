import pytest

from app.modules.messaging.queue.gateway import QueueMessage
from app.modules.messaging.queue.worker import TypedMessageDispatcher


async def test_typed_dispatcher_routes_to_handler_by_type():
    calls: list[tuple[str, str]] = []

    async def completion_handler(message: QueueMessage) -> None:
        calls.append(("completion", message.id))

    async def eval_handler(message: QueueMessage) -> None:
        calls.append(("eval", message.id))

    dispatcher = TypedMessageDispatcher(
        handlers={
            "completion": completion_handler,
            "eval.completion": eval_handler,
        }
    )

    await dispatcher(QueueMessage(id="m1", body={"type": "completion"}))
    await dispatcher(QueueMessage(id="m2", body={"type": "eval.completion"}))

    assert calls == [("completion", "m1"), ("eval", "m2")]


async def test_typed_dispatcher_raises_when_type_missing():
    async def handler(message: QueueMessage) -> None:
        pytest.fail("unreachable")

    dispatcher = TypedMessageDispatcher(handlers={"x": handler})

    with pytest.raises(ValueError, match="missing 'type' field"):
        await dispatcher(QueueMessage(id="m1", body={}))


async def test_typed_dispatcher_raises_for_unknown_type_when_no_fallback():
    async def handler(message: QueueMessage) -> None:
        pytest.fail("unreachable")

    dispatcher = TypedMessageDispatcher(handlers={"x": handler})

    with pytest.raises(ValueError, match="no handler registered"):
        await dispatcher(QueueMessage(id="m1", body={"type": "unknown"}))


async def test_typed_dispatcher_uses_unknown_type_handler_when_provided():
    seen: list[str] = []

    async def fallback(message: QueueMessage) -> None:
        seen.append(message.body["type"])

    dispatcher = TypedMessageDispatcher(
        handlers={"completion": fallback},
        unknown_type=fallback,
    )

    await dispatcher(QueueMessage(id="m1", body={"type": "mystery"}))

    assert seen == ["mystery"]


def test_typed_dispatcher_rejects_empty_handlers():
    with pytest.raises(ValueError, match="must not be empty"):
        TypedMessageDispatcher(handlers={})
