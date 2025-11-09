"""API request/response models for the main file download service."""

from __future__ import annotations

from hashlib import md5
from typing import Annotated, Self, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, computed_field

from motrpac_backend_utils.proto import FileDownloadMessage, UserNotificationMessage

# Type variable for protobuf File message types
ProtoFileType = TypeVar("ProtoFileType")


class DownloadRequestFileModel(BaseModel):
    """Model for a file in the POST-message body expected by endpoint."""

    object: str
    object_size: int

    @classmethod
    def from_proto(cls, proto_file: ProtoFileType) -> Self:
        """
        Construct a DownloadRequestFileModel from a protobuf File message.

        :param proto_file: The protobuf File message
        :return: A DownloadRequestFileModel instance
        """
        return cls(object=proto_file.object, object_size=proto_file.object_size)

    def to_proto(self, parent_cls: type[ProtoFileType]) -> ProtoFileType:
        """
        Convert this model to a protobuf File message.

        :param parent_cls: The protobuf File message class
        :return: A protobuf File message instance
        """
        return parent_cls(object=self.object, object_size=self.object_size)


def sort_files(files: list[DownloadRequestFileModel]) -> list[DownloadRequestFileModel]:
    """Sort the files by object size."""
    return sorted(files, key=lambda x: x.object_size)


class DownloadRequestModel(BaseModel):
    """
    Model for the POST-message body expected by the endpoint.

    Files are sorted by object size upon model initialization.
    """

    name: str
    user_id: str | None = None
    email: str
    files: Annotated[list[DownloadRequestFileModel], AfterValidator(sort_files)] = Field(
        default_factory=list,
        min_length=1,
    )

    @computed_field
    @property
    def filenames(self) -> list[str]:
        """Get the list of filenames, alphabetically sorted."""
        return sorted(f.object for f in self.files)

    @computed_field
    @property
    def total_size(self) -> int:
        """Get the total size of the files."""
        return sum(f.object_size for f in self.files)

    @computed_field
    @property
    def hash(self) -> str:
        """
        Generate an MD5 hash of the list of files to be uploaded.

        Joins the (alphabetically sorted) list with a comma separating the files.
        """
        return md5(
            ",".join(self.filenames).encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()

    @classmethod
    def from_message(cls, msg: FileDownloadMessage) -> Self:
        """
        Construct a DownloadRequestModel from a FileDownloadMessage protobuf.

        :param msg: The FileDownloadMessage protobuf message
        :return: A DownloadRequestModel instance
        """
        # Import here to avoid circular imports
        files = [DownloadRequestFileModel.from_proto(f) for f in msg.files]
        requester = Requester.from_proto(msg.requester)

        return cls(
            name=requester.name,
            user_id=requester.id,
            email=requester.email,
            files=files,
        )

    def to_message(self) -> FileDownloadMessage:
        """
        Convert this model to a FileDownloadMessage protobuf.

        :return: A FileDownloadMessage protobuf instance
        """
        message = FileDownloadMessage()
        message.requester.CopyFrom(
            Requester(name=self.name, email=self.email, id=self.user_id).to_proto(
                FileDownloadMessage.Requester,
            ),
        )
        # Convert each file model to proto and add to message
        for file_model in self.files:
            proto_file = file_model.to_proto(FileDownloadMessage.File)
            message.files.append(proto_file)

        return message

    def to_requester(self) -> Requester:
        """
        Extract a Requester namedtuple from this model.

        :return: A Requester instance with name, email, and id from this model
        """
        return Requester(name=self.name, email=self.email, id=self.user_id)

    def __repr__(self) -> str:
        """Returns a string representation of the request."""
        return (
            f"{self.name}{f' ({self.user_id})' if self.user_id else ''} <{self.email}> "
            f"[{len(self.files)} files, total size: {self.total_size} bytes, hash: {self.hash}]"
        )


T = TypeVar("T", bound="Requester")
U = TypeVar(
    "U",
    UserNotificationMessage.Requester,
    FileDownloadMessage.Requester,
)


class Requester(BaseModel):
    """A Pydantic model representing a single requester."""

    model_config = ConfigDict(frozen=True)

    name: str
    email: str
    id: str | None = None

    def to_proto(self, parent_cls: type[U]) -> U:
        """Converts this Requester object to a protobuf object."""
        return parent_cls(name=self.name, email=self.email, id=self.id)

    @classmethod
    def from_proto(cls, proto: U) -> Self:
        """Converts a protobuf object to this Requester object."""
        return cls(name=proto.name, email=proto.email, id=proto.id)

    @classmethod
    def from_model(cls, model: DownloadRequestModel) -> Self:
        """
        Extract a Requester from a DownloadRequestModel.

        :param model: The DownloadRequestModel instance
        :return: A Requester instance
        """
        return cls(name=model.name, email=model.email, id=model.user_id)

    def __repr__(self) -> str:
        """Returns a string representation of the requester."""
        return f"{self.name} ({self.id}) <{self.email}>"
