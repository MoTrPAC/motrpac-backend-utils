#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""
This module contains the Requester helper class. When using this, make sure that
package features "messaging" or "zipper" are used
"""

from typing import NamedTuple, Type, TypeVar, Union

from .proto import FileDownloadMessage, UserNotificationMessage

T = TypeVar("T", bound="Requester")
U = TypeVar("U")


class Requester(NamedTuple):
    """
    A named tuple that represents a single requester.
    """

    name: str
    email: str

    def to_proto(self, parent_cls: U) -> U:
        """
        Converts this Requester object to a protobuf object.
        """
        return parent_cls(name=self.name, email=self.email)

    @classmethod
    def from_proto(
        cls: Type[T],
        proto: Union[UserNotificationMessage.Requester, FileDownloadMessage.Requester],
    ) -> T:
        """
        Converts a protobuf object to this Requester object.
        """

        return cls(name=proto.name, email=proto.email)

    def __repr__(self) -> str:
        """
        Returns a string representation of the requester.
        """
        return f"{self.name} <{self.email}>"

    # implementing the __hash__ and __eq__ methods allows us to use this object as a
    # member of a set
    def __hash__(self):
        return hash((self.name, self.email))

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return NotImplemented
        return self.name == other.name and self.email == other.email
