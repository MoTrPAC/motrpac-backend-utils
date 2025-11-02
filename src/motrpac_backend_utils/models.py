"""API request/response models for the main file download service."""

from enum import StrEnum
from hashlib import md5
from typing import Annotated

from motrpac_backend_utils.utils import generate_file_hash
from pydantic import AfterValidator, BaseModel, Field, computed_field


class DownloadRequestFileModel(BaseModel):
    """Model for a file in the POST-message body expected by endpoint."""

    object: str
    object_size: int


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
        default_factory=list, min_length=1
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
        """Generate an MD5 hash of the list of files to be uploaded.
        Joins the (alphabetically sorted) list with a comma separating the files."""
        return md5(
            ",".join(self.filenames).encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()
