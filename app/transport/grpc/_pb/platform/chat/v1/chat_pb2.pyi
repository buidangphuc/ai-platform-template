from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class StreamChatRequest(_message.Message):
    __slots__ = ("session_id", "message")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    message: str
    def __init__(self, session_id: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...

class StreamChatResponse(_message.Message):
    __slots__ = ("delta", "done")
    DELTA_FIELD_NUMBER: _ClassVar[int]
    DONE_FIELD_NUMBER: _ClassVar[int]
    delta: str
    done: bool
    def __init__(self, delta: _Optional[str] = ..., done: bool = ...) -> None: ...
