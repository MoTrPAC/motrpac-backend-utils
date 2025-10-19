"""API request/response models for the main file download service."""

from enum import StrEnum
from typing import Annotated

from motrpac_backend_utils.utils import generate_file_hash
from pydantic import AfterValidator, BaseModel, Field, computed_field


class DownloadRequestFileModel(BaseModel):
    """Model for a file in the POST-message body expected by endpoint."""

    object: str
    object_size: int
    key: str


def sort_files(files: list[DownloadRequestFileModel]) -> list[DownloadRequestFileModel]:
    """Sort the files by object size."""
    return sorted(files, key=lambda x: x.object_size)


class DownloadRequestModel(BaseModel):
    """Model for the POST-message body expected by endpoint."""

    name: str
    user_id: str | None = None
    email: str
    files: Annotated[list[DownloadRequestFileModel], AfterValidator(sort_files)] = Field(
        default_factory=list, min_length=1
    )

    @property
    def filenames(self) -> list[str]:
        """Get the list of filenames."""
        return [f.object for f in self.files]

    @computed_field
    @property
    def total_size(self) -> int:
        """Get the total size of the files."""
        return sum(f.object_size for f in self.files)

    def to_list_hash(self) -> tuple[list[str], str]:
        """Generate a hash of the list of files."""
        return generate_file_hash(self.filenames)
