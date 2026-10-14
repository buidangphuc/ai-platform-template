from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PrincipalType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PRINCIPAL_TYPE_UNSPECIFIED: _ClassVar[PrincipalType]
    PRINCIPAL_TYPE_ANONYMOUS: _ClassVar[PrincipalType]
    PRINCIPAL_TYPE_USER: _ClassVar[PrincipalType]
    PRINCIPAL_TYPE_SERVICE: _ClassVar[PrincipalType]
PRINCIPAL_TYPE_UNSPECIFIED: PrincipalType
PRINCIPAL_TYPE_ANONYMOUS: PrincipalType
PRINCIPAL_TYPE_USER: PrincipalType
PRINCIPAL_TYPE_SERVICE: PrincipalType

class Principal(_message.Message):
    __slots__ = ("id", "type", "scopes")
    ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    SCOPES_FIELD_NUMBER: _ClassVar[int]
    id: str
    type: PrincipalType
    scopes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, id: _Optional[str] = ..., type: _Optional[_Union[PrincipalType, str]] = ..., scopes: _Optional[_Iterable[str]] = ...) -> None: ...

class Error(_message.Message):
    __slots__ = ("code", "message", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    code: str
    message: str
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, code: _Optional[str] = ..., message: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class PageRequest(_message.Message):
    __slots__ = ("cursor", "page_size")
    CURSOR_FIELD_NUMBER: _ClassVar[int]
    PAGE_SIZE_FIELD_NUMBER: _ClassVar[int]
    cursor: str
    page_size: int
    def __init__(self, cursor: _Optional[str] = ..., page_size: _Optional[int] = ...) -> None: ...

class PageResponse(_message.Message):
    __slots__ = ("next_cursor", "total")
    NEXT_CURSOR_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    next_cursor: str
    total: int
    def __init__(self, next_cursor: _Optional[str] = ..., total: _Optional[int] = ...) -> None: ...
