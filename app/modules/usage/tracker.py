from app.modules.usage.schemas import UsageRecord


class InMemoryUsageTracker:
    def __init__(self) -> None:
        self.records: list[UsageRecord] = []

    async def record(self, record: UsageRecord) -> UsageRecord:
        self.records.append(record)
        return record
