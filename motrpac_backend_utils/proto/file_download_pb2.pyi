from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar, Iterable, Mapping, Optional, Union

DESCRIPTOR: _descriptor.FileDescriptor

class FileDownloadMessage(_message.Message):
    __slots__ = ["files", "requester"]
    class Requester(_message.Message):
        __slots__ = ["email", "name"]
        EMAIL_FIELD_NUMBER: ClassVar[int]
        NAME_FIELD_NUMBER: ClassVar[int]
        email: str
        name: str
        def __init__(self, email: Optional[str] = ..., name: Optional[str] = ...) -> None: ...
    FILES_FIELD_NUMBER: ClassVar[int]
    REQUESTER_FIELD_NUMBER: ClassVar[int]
    files: _containers.RepeatedScalarFieldContainer[str]
    requester: FileDownloadMessage.Requester
    def __init__(self, requester: Optional[Union[FileDownloadMessage.Requester, Mapping]] = ..., files: Optional[Iterable[str]] = ...) -> None: ...
