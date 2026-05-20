import inspect
from uuid import uuid4

from app.contracts.jobs import JobHandler, JobRecord, JobRequest, JobStatus, JobTicket


class InProcessJobQueue:
    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}
        self._jobs: dict[str, JobRecord] = {}

    def register_handler(self, name: str, handler: JobHandler) -> None:
        self._handlers[name] = handler

    async def enqueue(self, request: JobRequest) -> JobTicket:
        job_id = str(uuid4())
        record = JobRecord(
            job_id=job_id,
            name=request.name,
            payload=request.payload,
            queue=request.queue,
            status=JobStatus.QUEUED,
        )
        self._jobs[job_id] = record

        handler = self._handlers.get(request.name)
        if handler is None:
            return JobTicket(job_id=job_id, status=record.status)

        record = record.model_copy(update={"status": JobStatus.RUNNING})
        self._jobs[job_id] = record
        try:
            result = handler(dict(request.payload))
            if inspect.isawaitable(result):
                result = await result
            record = record.model_copy(
                update={
                    "status": JobStatus.SUCCEEDED,
                    "result": result,
                },
            )
        except Exception as exc:
            record = record.model_copy(
                update={
                    "status": JobStatus.FAILED,
                    "error": str(exc),
                },
            )
        self._jobs[job_id] = record
        return JobTicket(job_id=job_id, status=record.status)

    async def get_status(self, job_id: str) -> JobRecord:
        return self._jobs[job_id]
