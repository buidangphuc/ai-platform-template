from app.transport.grpc._pb.platform.common.v1 import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SearchListingsRequest(_message.Message):
    __slots__ = ("query", "page", "filters")
    class FiltersEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    QUERY_FIELD_NUMBER: _ClassVar[int]
    PAGE_FIELD_NUMBER: _ClassVar[int]
    FILTERS_FIELD_NUMBER: _ClassVar[int]
    query: str
    page: _common_pb2.PageRequest
    filters: _containers.ScalarMap[str, str]
    def __init__(self, query: _Optional[str] = ..., page: _Optional[_Union[_common_pb2.PageRequest, _Mapping]] = ..., filters: _Optional[_Mapping[str, str]] = ...) -> None: ...

class SearchHit(_message.Message):
    __slots__ = ("listing_id", "score")
    LISTING_ID_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    listing_id: str
    score: float
    def __init__(self, listing_id: _Optional[str] = ..., score: _Optional[float] = ...) -> None: ...

class SearchListingsResponse(_message.Message):
    __slots__ = ("hits", "page")
    HITS_FIELD_NUMBER: _ClassVar[int]
    PAGE_FIELD_NUMBER: _ClassVar[int]
    hits: _containers.RepeatedCompositeFieldContainer[SearchHit]
    page: _common_pb2.PageResponse
    def __init__(self, hits: _Optional[_Iterable[_Union[SearchHit, _Mapping]]] = ..., page: _Optional[_Union[_common_pb2.PageResponse, _Mapping]] = ...) -> None: ...
