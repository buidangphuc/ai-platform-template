from typing import Any

from llama_index.core.vector_stores.types import (
    FilterOperator,
    MetadataFilter,
)
from llama_index.vector_stores.postgres import PGVectorStore


class ParameterizedPGVectorStore(PGVectorStore):
    def setup(self) -> None:
        self._initialize()

    def _build_filter_clause(self, filter_: MetadataFilter) -> Any:
        if filter_.operator != FilterOperator.EQ:
            raise ValueError(
                f"unsupported metadata filter operator: {filter_.operator.value}"
            )
        return self._table_class.metadata_[filter_.key].astext == str(filter_.value)
