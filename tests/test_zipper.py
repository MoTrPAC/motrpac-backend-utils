#  Copyright (c) 2023. Mihir Samdarshi/MoTrPAC Bioinformatics Center

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, TYPE_CHECKING

import pytest

from motrpac_backend_utils.zipper import estimate_remaining_time, ZipUploader

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("current_file_count", "total_file_count", "elapsed_time"),
    [
        (1, 10, 10.0),
        (5, 20, 60.0),
        (10, 10, 30.0),  # no remaining files => expect 0
    ],
)
def test_estimate_remaining_time(
    current_file_count: int,
    total_file_count: int,
    elapsed_time: float,
) -> None:
    # Act
    remaining_time = estimate_remaining_time(
        current_file_count,
        total_file_count,
        elapsed_time,
    )

    # Assert
    expected_remaining_time = (
        0
        if total_file_count == current_file_count
        else min(
            math.ceil(
                (elapsed_time / current_file_count)
                * (total_file_count - current_file_count)
                * 1.5,
            ),
            600,
        )
    )
    assert remaining_time == expected_remaining_time


@pytest.fixture
def uploader_args(mocker: MockerFixture) -> dict[str, Any]:
    return {
        "files": ["file1.txt", "file2.txt"],
        "file_hash": "hash123",
        "notification_url": "https://example.com/notification",
        "storage_client": mocker.MagicMock(),
        "input_bucket": "input_bucket",
        "output_bucket": "output_bucket",
        "scratch_location": Path("/tmp/scratch"),
        "file_dl_location": Path("/tmp/file_cache"),
        "in_progress_cache": mocker.MagicMock(),
        "requesters": [mocker.MagicMock(), mocker.MagicMock()],
        "message": mocker.MagicMock(),
        "ack_deadline": 600,
    }


def test_zip_uploader_process_flow(
    uploader_args: dict[str, Any],
    mocker: MockerFixture,
) -> None:
    zip_uploader = ZipUploader(**uploader_args)

    # Mock the necessary methods and attributes
    mocker.patch.object(zip_uploader, "setup_processing")
    mocker.patch.object(zip_uploader, "create_zip")
    mocker.patch.object(zip_uploader, "check_zip_exists_in_bucket")
    mocker.patch.object(zip_uploader, "send_notification")
    mocker.patch.object(zip_uploader, "successful_result")

    zip_uploader.process_and_notify_requesters()

    zip_uploader.setup_processing.assert_called_once()
    zip_uploader.create_zip.assert_called_once()
    zip_uploader.check_zip_exists_in_bucket.assert_called_once()
    zip_uploader.send_notification.assert_called_once()
    zip_uploader.successful_result.assert_called_once()
