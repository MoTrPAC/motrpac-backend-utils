#  Copyright (c) 2023. Mihir Samdarshi/MoTrPAC Bioinformatics Center

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from motrpac_backend_utils.zipper import (
    NotificationError,
    ZipUploader,
    ZipUploadError,
    estimate_remaining_time,
)

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


def test_zip_failure_raises_zip_upload_error(
    uploader_args: dict[str, Any],
    mocker: MockerFixture,
) -> None:
    zip_uploader = ZipUploader(**uploader_args)

    mocker.patch.object(zip_uploader, "setup_processing", side_effect=RuntimeError("fail"))
    mocker.patch.object(zip_uploader, "send_notification")
    mocker.patch("shutil.rmtree")

    with pytest.raises(ZipUploadError):
        zip_uploader.process_and_notify_requesters()

    zip_uploader.send_notification.assert_not_called()


def test_notification_failure_raises_notification_error(
    uploader_args: dict[str, Any],
    mocker: MockerFixture,
) -> None:
    zip_uploader = ZipUploader(**uploader_args)

    mocker.patch.object(zip_uploader, "setup_processing")
    mocker.patch.object(zip_uploader, "create_zip")
    mocker.patch.object(zip_uploader, "check_zip_exists_in_bucket")
    mocker.patch.object(
        zip_uploader,
        "send_notification",
        side_effect=RuntimeError("notify fail"),
    )
    mocker.patch.object(zip_uploader, "successful_result")

    with pytest.raises(NotificationError):
        zip_uploader.process_and_notify_requesters()

    zip_uploader.successful_result.assert_not_called()


def test_temp_dir_cleanup_on_zip_failure_not_notification(
    uploader_args: dict[str, Any],
    mocker: MockerFixture,
) -> None:
    mock_rmtree = mocker.patch("shutil.rmtree")

    # Test zip failure: rmtree should be called
    zip_uploader = ZipUploader(**uploader_args)
    zip_uploader.tmp_dir_path = "/tmp/test_dir"
    mocker.patch.object(zip_uploader, "setup_processing", side_effect=RuntimeError("fail"))

    with pytest.raises(ZipUploadError):
        zip_uploader.process_and_notify_requesters()

    mock_rmtree.assert_called_once_with("/tmp/test_dir")
    mock_rmtree.reset_mock()

    # Test notification failure: rmtree should NOT be called
    zip_uploader2 = ZipUploader(**uploader_args)
    mocker.patch.object(zip_uploader2, "setup_processing")
    mocker.patch.object(zip_uploader2, "create_zip")
    mocker.patch.object(zip_uploader2, "check_zip_exists_in_bucket")
    mocker.patch.object(
        zip_uploader2,
        "send_notification",
        side_effect=RuntimeError("notify fail"),
    )

    with pytest.raises(NotificationError):
        zip_uploader2.process_and_notify_requesters()

    mock_rmtree.assert_not_called()


def test_cache_finished_before_notification(
    uploader_args: dict[str, Any],
    mocker: MockerFixture,
) -> None:
    zip_uploader = ZipUploader(**uploader_args)

    mocker.patch.object(zip_uploader, "setup_processing")
    mocker.patch.object(zip_uploader, "create_zip")
    mocker.patch.object(zip_uploader, "check_zip_exists_in_bucket")
    mocker.patch.object(
        zip_uploader,
        "send_notification",
        side_effect=RuntimeError("notify fail"),
    )

    with pytest.raises(NotificationError):
        zip_uploader.process_and_notify_requesters()

    # finish_file should have been called even though notification failed
    zip_uploader.in_progress_cache.finish_file.assert_called_once_with("hash123")


def test_notify_only_raises_notification_error(
    uploader_args: dict[str, Any],
    mocker: MockerFixture,
) -> None:
    zip_uploader = ZipUploader(**uploader_args)

    mocker.patch.object(zip_uploader, "send_notification", side_effect=RuntimeError("fail"))
    mocker.patch.object(zip_uploader, "successful_result")

    with pytest.raises(NotificationError):
        zip_uploader.notify_only()

    zip_uploader.successful_result.assert_not_called()


def test_notify_only_success(
    uploader_args: dict[str, Any],
    mocker: MockerFixture,
) -> None:
    zip_uploader = ZipUploader(**uploader_args)

    mocker.patch.object(zip_uploader, "send_notification")
    mocker.patch.object(zip_uploader, "successful_result")

    zip_uploader.notify_only()

    zip_uploader.send_notification.assert_called_once()
    zip_uploader.successful_result.assert_called_once()
