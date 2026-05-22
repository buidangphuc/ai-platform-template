import pytest

from app.modules.cache.adapters.memory import MemoryCacheGateway
from app.modules.cache.gateway import CacheGateway

from .conformance import CacheGatewayConformance


class TestMemoryCacheGateway(CacheGatewayConformance):
    @pytest.fixture
    def cache_factory(self):
        async def _build() -> CacheGateway:
            return MemoryCacheGateway(prefix="test", default_ttl_seconds=60)

        return _build
