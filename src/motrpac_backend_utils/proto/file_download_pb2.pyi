from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FileDownloadMessage(_message.Message):
    __slots__ = ()
    class Requester(_message.Message):
        __slots__ = ()
        EMAIL_FIELD_NUMBER: _ClassVar[int]
        NAME_FIELD_NUMBER: _ClassVar[int]
        ID_FIELD_NUMBER: _ClassVar[int]
        email: str
        name: str
        id: str
        def __init__(self, email: _Optional[str] = ..., name: _Optional[str] = ..., id: _Optional[str] = ...) -> None: ...
    class File(_message.Message):
        __slots__ = ()
        OBJECT_FIELD_NUMBER: _ClassVar[int]
        OBJECT_SIZE_FIELD_NUMBER: _ClassVar[int]
        object: str
        object_size: int
        def __init__(self, object: _Optional[str] = ..., object_size: _Optional[int] = ...) -> None: ...
    REQUESTER_FIELD_NUMBER: _ClassVar[int]
    FILES_FIELD_NUMBER: _ClassVar[int]
    requester: FileDownloadMessage.Requester
    files: _containers.RepeatedCompositeFieldContainer[FileDownloadMessage.File]
    def __init__(self, requester: _Optional[_Union[FileDownloadMessage.Requester, _Mapping]] = ..., files: _Optional[_Iterable[_Union[FileDownloadMessage.File, _Mapping]]] = ...) -> None: ...
