from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FileDownloadMessage(_message.Message):
    __slots__ = ["files", "requester"]
    class Requester(_message.Message):
        __slots__ = ["email", "name"]
        EMAIL_FIELD_NUMBER: _ClassVar[int]
        NAME_FIELD_NUMBER: _ClassVar[int]
        email: str
        name: str
        def __init__(self, email: _Optional[str] = ..., name: _Optional[str] = ...) -> None: ...
    FILES_FIELD_NUMBER: _ClassVar[int]
    REQUESTER_FIELD_NUMBER: _ClassVar[int]
    files: _containers.RepeatedScalarFieldContainer[str]
    requester: FileDownloadMessage.Requester
    def __init__(self, requester: _Optional[_Union[FileDownloadMessage.Requester, _Mapping]] = ..., files: _Optional[_Iterable[str]] = ...) -> None: ...
