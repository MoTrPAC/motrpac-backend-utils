from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from motrpac_backend_utils.zipper import (
    ACK_HEARTBEAT_SECONDS,
    MAX_ACK_EXTENSION_SECONDS,
    MIN_ACK_DEADLINE_SECONDS,
    AckDeadlineHeartbeat,
    ZipUploader,
    ZipUploadError,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

HEARTBEAT_INTERVAL = 0.02
SLOW_STEP_SECONDS = 0.3
# a slow step should see roughly SLOW_STEP_SECONDS / HEARTBEAT_INTERVAL heartbeats; ask
# for far fewer so that the test is not flaky on a busy machine
MIN_HEARTBEATS = 4


class FakeMessage:
    """A Pub/Sub message that records ack deadline changes, acks, and nacks."""

    def __init__(self, modack_delay: float = 0) -> None:
        """Create a message whose modacks each take `modack_delay` seconds."""
        self.message_id = "message-1"
        self._received_timestamp = time.time()
        self.modack_delay = modack_delay
        self.modacks: list[int] = []
        self.modacks_after_settle: list[int] = []
        self.settled = False
        self._lock = threading.Lock()

    def modify_ack_deadline(self, seconds: int) -> None:
        time.sleep(self.modack_delay)
        with self._lock:
            self.modacks.append(seconds)
            if self.settled:
                self.modacks_after_settle.append(seconds)

    def ack(self) -> None:
        with self._lock:
            self.settled = True

    def nack(self) -> None:
        with self._lock:
            self.settled = True


def make_uploader(mocker: MockerFixture, message: FakeMessage) -> ZipUploader:
    """Build a ZipUploader for `message` whose processing steps are all mocked."""
    uploader = ZipUploader(
        files=["file1.txt"],
        file_hash="c" * 32,
        notification_url="https://example.com/notification",
        storage_client=mocker.MagicMock(),
        input_bucket="input_bucket",
        output_bucket="output_bucket",
        in_progress_cache=mocker.MagicMock(),
        message=message,
        ack_heartbeat_seconds=30,
    )
    assert uploader.ack_heartbeat is not None
    uploader.ack_heartbeat.interval = HEARTBEAT_INTERVAL
    for step in (
        "setup_processing",
        "create_zip",
        "check_zip_exists_in_bucket",
        "send_notification",
        "successful_result",
    ):
        mocker.patch.object(uploader, step)
    mocker.patch("shutil.rmtree")
    return uploader


def assert_heartbeat_stopped(uploader: ZipUploader, message: FakeMessage) -> None:
    count = len(message.modacks)
    time.sleep(HEARTBEAT_INTERVAL * 5)
    assert len(message.modacks) == count
    assert uploader.ack_heartbeat is not None
    assert uploader.ack_heartbeat._thread is not None
    assert not uploader.ack_heartbeat._thread.is_alive()


def test_slow_upload_keeps_getting_extended(mocker: MockerFixture) -> None:
    message = FakeMessage()
    uploader = make_uploader(mocker, message)
    # the final upload happens in create_zip (cleanup_create_zip joins the upload process)
    uploader.create_zip.side_effect = lambda: time.sleep(SLOW_STEP_SECONDS)

    uploader.process_and_notify_requesters()

    assert len(message.modacks) >= MIN_HEARTBEATS
    assert set(message.modacks) == {30}


def test_extension_stops_after_completion(mocker: MockerFixture) -> None:
    message = FakeMessage()
    uploader = make_uploader(mocker, message)
    uploader.create_zip.side_effect = lambda: time.sleep(SLOW_STEP_SECONDS)

    uploader.process_and_notify_requesters()

    assert_heartbeat_stopped(uploader, message)


def test_extension_stops_after_exception(mocker: MockerFixture) -> None:
    message = FakeMessage()
    uploader = make_uploader(mocker, message)

    def slow_failing_upload() -> None:
        time.sleep(SLOW_STEP_SECONDS)
        msg = "upload failed"
        raise RuntimeError(msg)

    uploader.create_zip.side_effect = slow_failing_upload

    with pytest.raises(ZipUploadError):
        uploader.process_and_notify_requesters()

    assert len(message.modacks) >= MIN_HEARTBEATS
    assert_heartbeat_stopped(uploader, message)


def test_nothing_extends_after_ack(mocker: MockerFixture) -> None:
    # a slow modack makes it likely that one is in flight when processing finishes
    message = FakeMessage(modack_delay=HEARTBEAT_INTERVAL)
    uploader = make_uploader(mocker, message)
    uploader.create_zip.side_effect = lambda: time.sleep(SLOW_STEP_SECONDS)

    uploader.process_and_notify_requesters()
    message.ack()
    # neither the heartbeat nor the estimate-based extension may extend after the ack
    uploader.message.ack_deadline = 1
    uploader.message.ack_start_time = datetime.now(tz=UTC) - timedelta(seconds=10)
    uploader.check_message_deadline(1)
    time.sleep(HEARTBEAT_INTERVAL * 5)

    assert message.modacks
    assert message.modacks_after_settle == []


def test_stop_waits_for_in_flight_extension() -> None:
    message = FakeMessage(modack_delay=0.1)
    heartbeat = AckDeadlineHeartbeat(message, extension_seconds=30, interval=0.001)
    heartbeat.start()
    # wait until the background thread is in the middle of a slow modack
    time.sleep(0.15)

    heartbeat.stop()
    message.nack()
    time.sleep(0.2)

    assert message.modacks_after_settle == []
    assert not heartbeat.extend(30)


def test_one_off_extension_never_shortens_heartbeat_deadline() -> None:
    message = FakeMessage()
    heartbeat = AckDeadlineHeartbeat(message, extension_seconds=600)

    assert heartbeat.extend(600)
    assert not heartbeat.extend(60)
    assert heartbeat.extend(60, shorten=True)
    assert message.modacks == [600, 60]


def test_check_message_deadline_goes_through_heartbeat(mocker: MockerFixture) -> None:
    message = FakeMessage()
    uploader = make_uploader(mocker, message)
    assert uploader.ack_heartbeat is not None
    uploader.ack_heartbeat.extend(MAX_ACK_EXTENSION_SECONDS)
    uploader.message.ack_deadline = 1
    uploader.message.ack_start_time = datetime.now(tz=UTC) - timedelta(seconds=10)

    # all files are processed, so the estimate is the 60 second floor, which would
    # shorten the heartbeat's 600 second deadline
    uploader.check_message_deadline(1)

    assert message.modacks == [MAX_ACK_EXTENSION_SECONDS]


@pytest.mark.parametrize(
    ("extension_seconds", "expected"),
    [
        (1, MIN_ACK_DEADLINE_SECONDS),
        (ACK_HEARTBEAT_SECONDS, ACK_HEARTBEAT_SECONDS),
        (3600, MAX_ACK_EXTENSION_SECONDS),
    ],
)
def test_heartbeat_extension_is_clamped(extension_seconds: int, expected: int) -> None:
    heartbeat = AckDeadlineHeartbeat(FakeMessage(), extension_seconds=extension_seconds)

    assert heartbeat.extension_seconds == expected
    assert heartbeat.interval == expected / 2


def test_uploader_without_message_has_no_heartbeat(mocker: MockerFixture) -> None:
    uploader = ZipUploader(
        files=["file1.txt"],
        file_hash="c" * 32,
        notification_url="https://example.com/notification",
        in_progress_cache=mocker.MagicMock(),
        scratch_location=Path("/tmp/scratch"),
    )

    assert uploader.ack_heartbeat is None
