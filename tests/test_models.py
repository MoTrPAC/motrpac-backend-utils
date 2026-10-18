from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from motrpac_backend_utils.messages import decode_file_download_message
from motrpac_backend_utils.models import DownloadRequestModel, Requester
from motrpac_backend_utils.proto import FileDownloadMessage

REQUESTER_FIELDS: dict[str, Any] = {
    "name": "John Doe",
    "user_id": "1234567890",
    "email": "johndoe@example.com",
}


def test_download_request_without_files_fails_validation() -> None:
    with pytest.raises(ValidationError, match="files"):
        DownloadRequestModel(**REQUESTER_FIELDS)


def test_download_request_with_empty_files_fails_validation() -> None:
    with pytest.raises(ValidationError, match="files"):
        DownloadRequestModel(**REQUESTER_FIELDS, files=[])


def test_download_request_with_files_is_valid() -> None:
    model = DownloadRequestModel(
        **REQUESTER_FIELDS,
        files=[
            {"object": "b.txt", "object_size": 200},
            {"object": "a.txt", "object_size": 100},
        ],
    )

    assert [f.object for f in model.files] == ["a.txt", "b.txt"]


def test_decoding_message_without_files_fails_validation() -> None:
    message = FileDownloadMessage()
    message.requester.CopyFrom(
        Requester(
            name=REQUESTER_FIELDS["name"],
            email=REQUESTER_FIELDS["email"],
            id=REQUESTER_FIELDS["user_id"],
        ).to_proto(FileDownloadMessage.Requester),
    )

    with pytest.raises(ValidationError, match="files"):
        decode_file_download_message(message.SerializeToString())
