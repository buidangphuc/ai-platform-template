from app.transport.grpc._pb.platform.common.v1 import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ListingStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    LISTING_STATUS_UNSPECIFIED: _ClassVar[ListingStatus]
    LISTING_STATUS_DRAFT: _ClassVar[ListingStatus]
    LISTING_STATUS_PUBLISHED: _ClassVar[ListingStatus]
    LISTING_STATUS_REJECTED: _ClassVar[ListingStatus]
LISTING_STATUS_UNSPECIFIED: ListingStatus
LISTING_STATUS_DRAFT: ListingStatus
LISTING_STATUS_PUBLISHED: ListingStatus
LISTING_STATUS_REJECTED: ListingStatus

class Listing(_message.Message):
    __slots__ = ("id", "title", "description", "price", "currency", "status")
    ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    id: str
    title: str
    description: str
    price: int
    currency: str
    status: ListingStatus
    def __init__(self, id: _Optional[str] = ..., title: _Optional[str] = ..., description: _Optional[str] = ..., price: _Optional[int] = ..., currency: _Optional[str] = ..., status: _Optional[_Union[ListingStatus, str]] = ...) -> None: ...

class GetListingRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    def __init__(self, id: _Optional[str] = ...) -> None: ...

class GetListingResponse(_message.Message):
    __slots__ = ("listing",)
    LISTING_FIELD_NUMBER: _ClassVar[int]
    listing: Listing
    def __init__(self, listing: _Optional[_Union[Listing, _Mapping]] = ...) -> None: ...

class ListListingsRequest(_message.Message):
    __slots__ = ("page",)
    PAGE_FIELD_NUMBER: _ClassVar[int]
    page: _common_pb2.PageRequest
    def __init__(self, page: _Optional[_Union[_common_pb2.PageRequest, _Mapping]] = ...) -> None: ...

class ListListingsResponse(_message.Message):
    __slots__ = ("listings", "page")
    LISTINGS_FIELD_NUMBER: _ClassVar[int]
    PAGE_FIELD_NUMBER: _ClassVar[int]
    listings: _containers.RepeatedCompositeFieldContainer[Listing]
    page: _common_pb2.PageResponse
    def __init__(self, listings: _Optional[_Iterable[_Union[Listing, _Mapping]]] = ..., page: _Optional[_Union[_common_pb2.PageResponse, _Mapping]] = ...) -> None: ...
