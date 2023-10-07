#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""
Contains the Requester helper class. When using this, make sure that
package features "messaging" or "zipper" are used.
"""

from typing import NamedTuple, TypeVar, Any

from google.protobuf.message import Message

from .proto import FileDownloadMessage, UserNotificationMessage


T = TypeVar("T", bound="Requester")
U = TypeVar(
    "U",
    type[UserNotificationMessage.Requester],
    type[FileDownloadMessage.Requester],
)


class Requester(NamedTuple):
    """
    A named tuple that represents a single requester.
    """

    name: str
    email: str
    id: str

    def to_proto(self, parent_cls: U) -> Message:
        """
        Converts this Requester object to a protobuf object.
        """
        return parent_cls(name=self.name, email=self.email, id=self.id)

    @classmethod
    def from_proto(
        cls: type[T],
        proto: UserNotificationMessage.Requester | FileDownloadMessage.Requester,
    ) -> T:
        """
        Converts a protobuf object to this Requester object.
        """
        return cls(name=proto.name, email=proto.email, id=proto.id)

    def __repr__(self) -> str:
        """
        Returns a string representation of the requester.
        """
        return f"{self.name} ({self.id}) <{self.email}>"

    # implementing the __hash__ and __eq__ methods allows us to use this object as a
    # member of a set
    def __hash__(self) -> int:
        """
        Returns a hash of the requester.

        :return: The hash of the requester
        """
        return hash((self.name, self.email, self.id))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, type(self)):
            raise NotImplementedError
        return self.name == other.name and self.email == other.email and self.id == other.id
