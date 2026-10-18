#  Copyright (c) 2023. Mihir Samdarshi/MoTrPAC Bioinformatics Center

from __future__ import annotations

import time
from ctypes import c_char
from datetime import UTC, datetime, timedelta
from multiprocessing import Array, Value
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from motrpac_backend_utils.models import Requester
from motrpac_backend_utils.zipper import (
    MAX_ACK_EXTENSION_SECONDS,
    MIN_ACK_EXTENSION_SECONDS,
    NotificationError,
    ZipUploader,
    ZipUploadError,
    estimate_remaining_time,
)
from motrpac_backend_utils.zipper.cache import InProgressCache

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("current_file_count", "total_file_count", "elapsed_time", "expected"),
    [
        (1, 10, 10.0, 135),
        (5, 20, 60.0, 270),
        # the estimate exceeds the maximum
        (1, 100, 100.0, MAX_ACK_EXTENSION_SECONDS),
        # the estimate is below the floor
        (1, 2, 1.0, MIN_ACK_EXTENSION_SECONDS),
        # no remaining files, but the upload is still ongoing, so never 0
        (10, 10, 30.0, MIN_ACK_EXTENSION_SECONDS),
    ],
)
def test_estimate_remaining_time(
    current_file_count: int,
    total_file_count: int,
    elapsed_time: float,
    expected: int,
) -> None:
    remaining_time = estimate_remaining_time(
        current_file_count,
        total_file_count,
        elapsed_time,
    )

    assert remaining_time == expected


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


FILE_HASH = "b" * 32
ALICE = Requester(name="Alice", email="alice@example.com", id="1")
BOB = Requester(name="Bob", email="bob@example.com", id="2")
CAROL = Requester(name="Carol", email="carol@example.com", id="3")
BLOB_SIZE = 10


@pytest.fixture
def cache() -> InProgressCache:
    return InProgressCache(Value("I", 0), Array(c_char, 1024))


@pytest.fixture
def mock_send(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("motrpac_backend_utils.zipper.send_notification_message")


def fake_storage_client(mocker: MockerFixture, *, zip_exists: bool) -> MagicMock:
    """Build a fake GCS client whose output bucket does or does not hold the zip."""
    client = mocker.MagicMock()
    bucket = mocker.MagicMock()
    bucket.name = "output_bucket"
    bucket.get_blob.return_value = mocker.MagicMock() if zip_exists else None
    client.get_bucket.return_value = bucket
    return client


def notified_emails(mock_send: MagicMock) -> list[str]:
    return [c.args[2] for c in mock_send.call_args_list]


def make_processor(
    mocker: MockerFixture,
    cache: InProgressCache,
    *,
    fail: bool,
) -> ZipUploader:
    """Build a ZipUploader for processing whose zip creation succeeds or fails."""
    uploader = ZipUploader(
        files=["file1.txt"],
        file_hash=FILE_HASH,
        notification_url="https://example.com/notification",
        storage_client=fake_storage_client(mocker, zip_exists=True),
        input_bucket="input_bucket",
        output_bucket="output_bucket",
        in_progress_cache=cache,
    )
    mocker.patch.object(uploader, "setup_processing")
    mocker.patch.object(
        uploader,
        "create_zip",
        side_effect=RuntimeError("zip failed") if fail else None,
    )
    mocker.patch("shutil.rmtree")
    return uploader


def make_notifier(
    mocker: MockerFixture,
    cache: InProgressCache,
    *,
    zip_exists: bool,
) -> ZipUploader:
    return ZipUploader(
        files=["file1.txt"],
        file_hash=FILE_HASH,
        notification_url="https://example.com/notification",
        storage_client=fake_storage_client(mocker, zip_exists=zip_exists),
        output_bucket="output_bucket",
        in_progress_cache=cache,
    )


def test_zip_failure_does_not_mark_file_finished(
    cache: InProgressCache,
    mock_send: MagicMock,
    mocker: MockerFixture,
) -> None:
    cache.add_requester(FILE_HASH, ALICE)

    with pytest.raises(ZipUploadError):
        make_processor(mocker, cache, fail=True).process_and_notify_requesters()

    assert not cache.file_is_finished(FILE_HASH)
    assert not cache.file_is_in_progress(FILE_HASH)
    mock_send.assert_not_called()


def test_notify_only_requires_storage_client(
    cache: InProgressCache,
    mock_send: MagicMock,
) -> None:
    cache.add_requester(FILE_HASH, ALICE)
    cache.finish_file(FILE_HASH)
    uploader = ZipUploader(
        files=["file1.txt"],
        file_hash=FILE_HASH,
        notification_url="https://example.com/notification",
        in_progress_cache=cache,
    )

    with pytest.raises(ValueError, match="storage_client"):
        uploader.notify_only()

    mock_send.assert_not_called()


def test_notify_only_does_not_email_when_zip_is_missing(
    cache: InProgressCache,
    mock_send: MagicMock,
    mocker: MockerFixture,
) -> None:
    cache.add_requester(FILE_HASH, ALICE)
    cache.finish_file(FILE_HASH)

    with pytest.raises(FileNotFoundError):
        make_notifier(mocker, cache, zip_exists=False).notify_only()

    mock_send.assert_not_called()
    assert cache.get_requesters(FILE_HASH) == [ALICE]


def test_notify_only_emails_when_zip_exists(
    cache: InProgressCache,
    mock_send: MagicMock,
    mocker: MockerFixture,
) -> None:
    cache.add_requester(FILE_HASH, ALICE)
    cache.finish_file(FILE_HASH)

    make_notifier(mocker, cache, zip_exists=True).notify_only()

    assert notified_emails(mock_send) == [ALICE.email]
    assert cache.file_is_finished(FILE_HASH)


def test_one_of_many_requesters_failing_clears_in_progress_and_retry_notifies_all(
    cache: InProgressCache,
    mock_send: MagicMock,
    mocker: MockerFixture,
) -> None:
    # Alice's message starts processing, Bob joins while it is in progress
    cache.add_requester(FILE_HASH, ALICE)
    cache.add_requester(FILE_HASH, BOB)

    with pytest.raises(ZipUploadError):
        make_processor(mocker, cache, fail=True).process_and_notify_requesters()

    # the in-progress flag polled by the VM is cleared, and nobody was told it worked
    assert cache.atomic_in_progress.value == 0
    assert cache.atomic_processing_hashes.value.decode() == ""
    mock_send.assert_not_called()

    # Alice's message is redelivered, which retries the hash
    cache.add_requester(FILE_HASH, ALICE)
    assert cache.atomic_in_progress.value == 1
    make_processor(mocker, cache, fail=False).process_and_notify_requesters()

    assert sorted(notified_emails(mock_send)) == [ALICE.email, BOB.email]
    assert cache.file_is_finished(FILE_HASH)
    assert cache.atomic_in_progress.value == 0


def test_notified_requesters_are_removed_from_cache(
    cache: InProgressCache,
    mock_send: MagicMock,
    mocker: MockerFixture,
) -> None:
    cache.add_requester(FILE_HASH, ALICE)
    cache.add_requester(FILE_HASH, BOB)
    make_processor(mocker, cache, fail=False).process_and_notify_requesters()
    assert sorted(notified_emails(mock_send)) == [ALICE.email, BOB.email]
    assert cache.get_requesters(FILE_HASH) == []
    mock_send.reset_mock()

    # a later request for the same files only notifies the new requester
    cache.add_requester(FILE_HASH, CAROL)
    make_notifier(mocker, cache, zip_exists=True).notify_only()

    assert notified_emails(mock_send) == [CAROL.email]
    assert cache.get_requesters(FILE_HASH) == []


def test_notification_retry_only_notifies_remaining_requesters(
    cache: InProgressCache,
    mock_send: MagicMock,
    mocker: MockerFixture,
) -> None:
    cache.add_requester(FILE_HASH, ALICE)
    cache.add_requester(FILE_HASH, BOB)
    failed: list[str] = []

    def fail_bob_once(*args: Any) -> None:
        if args[2] == BOB.email and not failed:
            failed.append(args[2])
            msg = "notifier returned 500"
            raise RuntimeError(msg)

    mock_send.side_effect = fail_bob_once

    with pytest.raises(NotificationError):
        make_processor(mocker, cache, fail=False).process_and_notify_requesters()
    assert cache.get_requesters(FILE_HASH) == [BOB]
    mock_send.reset_mock()

    make_notifier(mocker, cache, zip_exists=True).notify_only()

    assert notified_emails(mock_send) == [BOB.email]
    assert cache.get_requesters(FILE_HASH) == []


def test_estimate_remaining_time_with_no_processed_files() -> None:
    assert estimate_remaining_time(0, 10, 500.0) == MAX_ACK_EXTENSION_SECONDS


def test_check_message_deadline_with_no_processed_files(
    uploader_args: dict[str, Any],
) -> None:
    zip_uploader = ZipUploader(**uploader_args)
    message = zip_uploader.message
    message.ack_deadline = 600
    message.ack_start_time = datetime.now(tz=UTC) - timedelta(seconds=500)

    zip_uploader.check_message_deadline(0)

    message.modify_ack_deadline.assert_called_once_with(MAX_ACK_EXTENSION_SECONDS)


def make_downloader(
    mocker: MockerFixture,
    tmp_path: Path,
    blob_size: int,
) -> tuple[ZipUploader, MagicMock]:
    """Build a ZipUploader whose input bucket holds one blob of `blob_size` bytes."""
    blob = mocker.MagicMock()
    blob.size = blob_size
    blob.download_to_filename.side_effect = lambda fn: Path(fn).write_bytes(
        b"x" * blob_size,
    )
    client = mocker.MagicMock()
    client.get_bucket.return_value.get_blob.return_value = blob
    uploader = ZipUploader(
        files=["data/file1.txt"],
        file_hash=FILE_HASH,
        notification_url="https://example.com/notification",
        storage_client=client,
        input_bucket="input_bucket",
        output_bucket="output_bucket",
        file_dl_location=tmp_path,
        in_progress_cache=mocker.MagicMock(),
        download_stall_timeout=0.2,
    )
    return uploader, blob


def test_get_file_redownloads_stalled_partial_file(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    real_sleep = time.sleep
    mocker.patch(
        "motrpac_backend_utils.zipper.time.sleep",
        side_effect=lambda _: real_sleep(0.05),
    )
    uploader, blob = make_downloader(mocker, tmp_path, blob_size=BLOB_SIZE)
    partial = tmp_path / "data" / "file1.txt"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"xxx")

    path = uploader.get_file("data/file1.txt").result(timeout=10)

    assert path == partial.resolve()
    assert path.stat().st_size == BLOB_SIZE
    blob.download_to_filename.assert_called_once()


def test_get_file_reuses_complete_local_file(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    uploader, blob = make_downloader(mocker, tmp_path, blob_size=BLOB_SIZE)
    local = tmp_path / "data" / "file1.txt"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"x" * BLOB_SIZE)

    path = uploader.get_file("data/file1.txt").result(timeout=10)

    assert path == local.resolve()
    blob.download_to_filename.assert_not_called()
