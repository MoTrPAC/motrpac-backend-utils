from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class UserNotificationMessage(_message.Message):
    __slots__ = ["files", "requester", "zipfile"]
    class Requester(_message.Message):
        __slots__ = ["email", "name"]
        EMAIL_FIELD_NUMBER: _ClassVar[int]
        NAME_FIELD_NUMBER: _ClassVar[int]
        email: str
        name: str
        def __init__(self, email: _Optional[str] = ..., name: _Optional[str] = ...) -> None: ...
    FILES_FIELD_NUMBER: _ClassVar[int]
    REQUESTER_FIELD_NUMBER: _ClassVar[int]
    ZIPFILE_FIELD_NUMBER: _ClassVar[int]
    files: _containers.RepeatedScalarFieldContainer[str]
    requester: UserNotificationMessage.Requester
    zipfile: str
    def __init__(self, requester: _Optional[_Union[UserNotificationMessage.Requester, _Mapping]] = ..., zipfile: _Optional[str] = ..., files: _Optional[_Iterable[str]] = ...) -> None: ...
