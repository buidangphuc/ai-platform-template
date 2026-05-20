from app.adapters.jobs.in_process import InProcessJobQueue
from app.contracts.jobs import JobQueue, JobRequest, JobStatus


async def test_in_process_job_queue_executes_registered_handlers():
    queue: JobQueue = InProcessJobQueue()
    seen_payloads: list[dict[str, object]] = []

    async def run_eval(payload: dict[str, object]) -> dict[str, object]:
        seen_payloads.append(payload)
        return {"ok": True, "run_id": payload["run_id"]}

    queue.register_handler("eval.run", run_eval)

    ticket = await queue.enqueue(
        JobRequest(name="eval.run", payload={"run_id": "run-1"}),
    )
    status = await queue.get_status(ticket.job_id)

    assert ticket.status == JobStatus.SUCCEEDED
    assert status.status == JobStatus.SUCCEEDED
    assert status.result == {"ok": True, "run_id": "run-1"}
    assert seen_payloads == [{"run_id": "run-1"}]


async def test_in_process_job_queue_keeps_unregistered_jobs_queued():
    queue = InProcessJobQueue()

    ticket = await queue.enqueue(
        JobRequest(name="eval.run", payload={"run_id": "run-1"}),
    )
    status = await queue.get_status(ticket.job_id)

    assert ticket.status == JobStatus.QUEUED
    assert status.status == JobStatus.QUEUED
    assert status.result is None
