#  Copyright (c) 2024. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""
Contains the ZipUploader class, used to create zip files and send them to Google Cloud Storage.

It also contains utilities for sending notifications via Pub/Sub upon completion.

When using this, make sure that package feature "zipper" is used.
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import threading
import time
from concurrent.futures import Future, as_completed
from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, datetime
from multiprocessing import JoinableQueue, Process, Value
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import TYPE_CHECKING, Self, TypedDict
from zipfile import ZIP_DEFLATED, ZipFile

from google.cloud.storage import Client as StorageClient
from opentelemetry import trace
from psutil import virtual_memory
from smart_open import open as _smart_open_fn

from motrpac_backend_utils.messages import send_notification_message
from motrpac_backend_utils.threadpool import threadpool
from motrpac_backend_utils.zipper.utils import get_path_dict

if TYPE_CHECKING:
    from google.cloud.pubsub_v1.subscriber.message import Message

    from motrpac_backend_utils.models import Requester
    from motrpac_backend_utils.zipper.cache import InProgressCache

MAX_IN_PROGRESS = max((os.cpu_count() or 1) - 3, 1)
# the longest an ack deadline extension can be, in seconds
MAX_ACK_EXTENSION_SECONDS = 600
# the shortest an ack deadline extension can be while work is ongoing, in seconds. An
# extension of 0 would nack the message, so the remaining estimate is never used below this
MIN_ACK_EXTENSION_SECONDS = 60
# the shortest ack deadline Pub/Sub accepts without advising against it, in seconds
MIN_ACK_DEADLINE_SECONDS = 10
# how far each heartbeat extends a message's ack deadline, in seconds. The heartbeat runs
# every half of this, so a crashed worker's message is redelivered within this time
ACK_HEARTBEAT_SECONDS = 120
# how long to wait for another download of the same file to make progress, in seconds
DOWNLOAD_STALL_TIMEOUT_SECONDS = 300

# setup local logging/Google Cloud Logging
logger = logging.getLogger()
tracer = trace.get_tracer(__name__)


class BlobNotFoundError(Exception):
    """Raised when the specified blob could not be found."""

    def __init__(self, blob_name: str) -> None:
        """Initialize the error with a human-readable message."""
        self.blob_name = blob_name
        super().__init__(f"Blob {blob_name} could not be found")


class ZipProcessResult(TypedDict):
    """Summary of details regarding the results of a zip process."""

    outputBucket: str
    outputPath: str
    manifest: list[str]
    fileHash: str
    requesters: list[str] | None


def zip_file_writer(
    queue: JoinableQueue[str | bool],
    archive: ZipFile,
    file_hash: str,
    processed_counter: type[Value] | None,
    file_path_prefix: Path,
) -> list[str]:
    """
    Writes files to a zip archive.

    :param queue: A `JoinableQueue` object of the file paths to be added to the archive.
    :param archive: A `ZipFile` object representing the archive to which the files will
        be added.
    :param file_hash: A string representing the hash of the file being processed.
    :param processed_counter: A `Value` object representing the number of files processed.
    :param file_path_prefix: A `Path` object representing the prefix of the file paths
        to be added to the archive.
    """
    manifest: list[str] = []

    while True:
        # get the latest message from the shared process queue
        f = queue.get()
        try:
            logger.debug(
                "[File Hash: %s] Received message from queue %s",
                file_hash,
                f,
            )
            if isinstance(f, BlobNotFoundError):
                raise f  # noqa: TRY301
            # sentinel to tell the multiprocessing to stop processing
            if isinstance(f, bool) and not f:
                break
            # create a file in the archive
            archive.write(
                f,
                # we want to replace "/tmp/file_cache" or whatever the base name of the
                # location of the downloaded files are
                arcname=f.replace(f"{str(file_path_prefix).rstrip('/')}/", ""),
            )
            manifest.append(f)
            logger.debug("[File Hash: %s] Finished archiving %s", file_hash, f)
        except BlobNotFoundError as e:
            logger.exception(
                "[File Hash: %s] Error while adding file to archive",
                file_hash,
            )
            manifest.append(f"{e.blob_name} [Error: unable to retrieve file]")
        except Exception:
            logger.exception(
                "[File Hash: %s] Error while adding file to archive",
                file_hash,
            )
            manifest.append(f"{f} [Error: unable to retrieve file]")
        finally:
            queue.task_done()
            if processed_counter is not None:
                with processed_counter.get_lock():
                    processed_counter.value += 1

    return manifest


def patch_zip_blob_metadata(
    output_bucket: str,
    zip_loc: str,
    storage_client: StorageClient,
) -> None:
    """
    Patch the metadata of the zip blob to update the custom time to the current time.

    :param output_bucket: The name of the output bucket where the zip file is stored.
    :param zip_loc: The location of the zip file.
    :param storage_client: The Google Cloud Storage client.
    """
    bucket = storage_client.get_bucket(output_bucket)
    zip_blob = bucket.blob(os.path.basename(zip_loc))  # noqa: PTH119
    zip_blob.custom_time = datetime.now(UTC)
    zip_blob.patch()


def add_to_zip(  # noqa: PLR0913
    tmp_dir: str,
    zip_loc: str,
    output_bucket: str,
    file_path_prefix: Path,
    queue: JoinableQueue[str | bool],
    processed_counter: type[Value] | None,
) -> bool:
    """
    # Asynchronously add files to an archive, receiving processing instructions via a queue.

    :param tmp_dir: The name of the local temporary directory
    :param zip_loc: The name of the zip file to be created
    :param output_bucket: The name of the bucket to upload the final zip file to
    :param file_path_prefix: The local path prefix to strip from the local file paths
    :param queue: A queue to communicate with the parent process
    :param processed_counter: A counter to keep track of how many files have been
        processed
    :returns: True when the process has finished (there are no more messages to process/
        the queue has delivered a sentinel boolean value of False)
    """
    file_hash = os.path.basename(os.path.splitext(zip_loc)[0])  # noqa: PTH119, PTH122
    with tracer.start_as_current_span(file_hash):
        logger.debug(
            "[File Hash: %s] Spawned local zip file creator child process, PID: %s",
            file_hash,
            os.getpid(),
        )
        # Process-local instance of the Storage client.
        storage_client = StorageClient()
        upload_buffer_size = 2**8 * 256 * 1024

        # Figure out how much memory we have available to allocate the new zip file
        memory = virtual_memory()
        free_memory = int(memory.available / MAX_IN_PROGRESS)
        logger.debug(
            "[File Hash: %s] Allocating %s GB of memory for temp zip file",
            file_hash,
            round(free_memory / (1024**3), 4),
        )

        # A spooled zip file exists in memory, and is written to disk when it reaches a
        # certain size, which is what we allocated above
        with SpooledTemporaryFile(max_size=free_memory, dir=tmp_dir) as tmp_file:
            with ZipFile(tmp_file, mode="w", compression=ZIP_DEFLATED) as archive:
                manifest = zip_file_writer(
                    queue,
                    archive,
                    file_hash,
                    processed_counter,
                    file_path_prefix,
                )
                manifest_fn = f"{file_hash}.nested.manifest.json"
                archive.writestr(
                    manifest_fn,
                    json.dumps(get_path_dict(manifest), indent=2),
                )
                manifest_fn = f"{file_hash}.list.manifest.json"
                archive.writestr(manifest_fn, json.dumps(manifest, indent=2))

            with _smart_open_fn(
                zip_loc,
                mode="wb",
                transport_params={
                    "min_part_size": upload_buffer_size,
                    "client": storage_client,
                },
            ) as gs_out:
                # reset the file pointer to the beginning of the file
                tmp_file.seek(0)
                shutil.copyfileobj(tmp_file, gs_out, upload_buffer_size)

            patch_zip_blob_metadata(output_bucket, zip_loc, storage_client)

        return True


def estimate_remaining_time(
    current_file_count: int,
    total_file_count: int,
    elapsed_time: float,
) -> int:
    """
    Estimate the remaining time for the current file to be processed.

    :param current_file_count: The number of files that have been processed
    :param total_file_count: The total number of files to be processed
    :param elapsed_time: The time since the process started.
    :return: The number of seconds to extend the ack deadline by, between
        `MIN_ACK_EXTENSION_SECONDS` and `MAX_ACK_EXTENSION_SECONDS`. Work such as the zip
        upload continues after every file is processed, so this is never 0.
    """
    # without any processed files there is no rate to estimate from, so use the maximum
    if current_file_count <= 0:
        return MAX_ACK_EXTENSION_SECONDS

    # calculate the estimated time remaining
    remaining_time = (elapsed_time / current_file_count) * (
        total_file_count - current_file_count
    )

    return max(
        min(math.ceil(remaining_time * 1.5), MAX_ACK_EXTENSION_SECONDS),
        MIN_ACK_EXTENSION_SECONDS,
    )


class AckDeadlineHeartbeat:
    """
    Keeps extending the ack deadline of a Pub/Sub message while work is ongoing.

    Pub/Sub's subscriber client stops extending a message's lease after the subscriber's
    `max_lease_duration`, and gaps between manual extensions (e.g. during the final upload)
    let the deadline expire. While started, a background thread calls
    `modify_ack_deadline(extension_seconds)` every `interval` seconds.

    All extensions go through `extend`, which holds a lock and does nothing once `stop` was
    called. Since `stop` takes the same lock, no extension is sent after `stop` returns, so
    the message can then be acked or nacked safely. One-off extensions never shorten a
    deadline set through `extend`. The periodic heartbeat always sends, so its schedule
    alone keeps the deadline alive, whatever the subscriber client last sent.
    """

    def __init__(
        self,
        message: Message,
        extension_seconds: int = ACK_HEARTBEAT_SECONDS,
        interval: float | None = None,
    ) -> None:
        """
        Create a heartbeat for a message, which does nothing until started.

        :param message: The Pub/Sub message to extend the ack deadline of
        :param extension_seconds: How far each heartbeat extends the deadline, between
            `MIN_ACK_DEADLINE_SECONDS` and `MAX_ACK_EXTENSION_SECONDS`
        :param interval: How often to extend the deadline, in seconds. Defaults to half of
            `extension_seconds`.
        """
        self.message = message
        self.extension_seconds = max(
            min(extension_seconds, MAX_ACK_EXTENSION_SECONDS),
            MIN_ACK_DEADLINE_SECONDS,
        )
        self.interval = self.extension_seconds / 2 if interval is None else interval
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._expires_at = 0.0
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Extend the deadline now, then keep extending it in a background thread."""
        self.extend(self.extension_seconds, shorten=True)
        self._thread = threading.Thread(
            target=self._run,
            name=f"ack-heartbeat-{self.message.message_id}",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stopped.wait(self.interval):
            self.extend(self.extension_seconds, shorten=True)

    def extend(self, seconds: int, *, shorten: bool = False) -> bool:
        """
        Extend the ack deadline to `seconds` from now.

        :param seconds: The new deadline, in seconds from now
        :param shorten: Whether to send the extension even if it ends before a deadline
            previously set through this method
        :return: Whether the deadline was extended
        """
        with self._lock:
            if self._stopped.is_set():
                return False
            expires_at = time.monotonic() + seconds
            if not shorten and expires_at <= self._expires_at:
                return False
            try:
                self.message.modify_ack_deadline(seconds)
            except Exception:
                logger.exception(
                    "Failed to extend ack deadline of message %s",
                    self.message.message_id,
                )
                return False
            self._expires_at = expires_at
            return True

    def stop(self) -> None:
        """Stop extending the deadline. No extension is sent after this returns."""
        with self._lock:
            self._stopped.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join()

    def __enter__(self) -> Self:
        """Start the heartbeat."""
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        """Stop the heartbeat, whether or not the work raised an exception."""
        self.stop()


class ZipUploadError(Exception):
    """An exception class to represent errors that occur during the zip upload process."""


class NotificationError(Exception):
    """Raised when notification delivery fails after the zip was successfully created."""


class ZipUploader:
    """
    Class for uploading, managing, and notifying requesters about ZIP file archives.

    Handles the creation, management, and uploading of zip archives to Google Cloud Storage
    based on an input list of files. Also manages notification of requesters upon successful
    upload, tracks ongoing processing via a cache, and supports integration with Pub/Sub
    messaging and temporary file handling.
    """

    def __init__(  # noqa: PLR0913
        self,
        files: list[str],
        file_hash: str,
        notification_url: str,
        storage_client: StorageClient | None = None,
        input_bucket: str | None = None,
        output_bucket: str | None = None,
        scratch_location: Path = Path("/tmp"),  # noqa: S108
        file_dl_location: Path = Path("/tmp/file_cache"),  # noqa: S108
        in_progress_cache: InProgressCache | None = None,
        requesters: list[Requester] | None = None,
        message: Message | None = None,
        ack_deadline: int = 600,
        download_stall_timeout: float = DOWNLOAD_STALL_TIMEOUT_SECONDS,
        ack_heartbeat_seconds: int = ACK_HEARTBEAT_SECONDS,
    ) -> None:
        """
        Initialize the ZipUploader class.

        This class can be initialized to either create and upload a zip file to Google
        Cloud Storage, or to just notify the requester, if the zip file was already
        created by the zip class.

        :param files: A list of files to be zipped and uploaded to Google Cloud Storage
        :param file_hash: The hash of the files to be zipped and uploaded. Ideally, the
            file hash should be consistent to ensure that there are no namespace collisions.
            Suggested naming for this hash is the hash of the concatenation of the file names
            with some sort of delimiter (e.g. '_' or ',).
        :param storage_client: A Google Cloud Storage client
        :param input_bucket: The bucket where the files to be zipped are located
        :param output_bucket: The bucket where the final zip file will be uploaded
        :param notification_url: The URL to send a POST request with the notification
            ProtoBuf message (encoded as bytes) when the zip file is uploaded
        :param scratch_location: The location where temporary files will be stored
        :param file_dl_location: The location where files will be downloaded to
        :param in_progress_cache: An InProgressCache object to store the files that are
            being processed. This is used to prevent duplicate work from being processed.
            If this is not present, the `requesters` parameter must be provided.
        :param requesters: A list of requesters to notify when the zip file is ready
        :param message: If instantiating this class from a PubSub Pull subscription, this
            is the message that was received from the subscription.
        :param ack_deadline: If a message is present, this parameter is used to determine
            the process needs to extend the acknowledgement deadline of the message. Set this
            parameter to the acknowledgement deadline of the subscription. By default, it is
            set to 600 seconds.
        :param download_stall_timeout: How long (in seconds) to wait for a partially
            downloaded local file to grow before assuming its download was abandoned and
            downloading it again.
        :param ack_heartbeat_seconds: If a message is present, how far (in seconds) the
            background heartbeat extends its ack deadline while the request is processed.
            The heartbeat runs every half of this.
        """
        self.files = files
        self.file_hash = file_hash

        # the url to push the notification URL to
        self.notification_url = notification_url

        # the file's requesters
        self.requesters = requesters or []
        self.in_progress_cache = in_progress_cache
        if self.in_progress_cache is None and self.requesters is None:
            msg = "Either in_progress_cache or requesters must be specified"
            raise ValueError(msg)

        # Names output zip file based on the hash of the files
        self.output_path = f"{file_hash}.zip"
        self.full_output_path = f"gs://{output_bucket}/{self.output_path}"

        # set up the storage client and input/output buckets
        self.storage_client = storage_client
        self.input_bucket = None
        self.output_bucket = None
        if self.storage_client is not None:
            if input_bucket is not None:
                self.input_bucket = storage_client.get_bucket(input_bucket)
            if output_bucket is not None:
                self.output_bucket = storage_client.get_bucket(output_bucket)
        self.download_stall_timeout = download_stall_timeout

        # the queue to communicate with the separate zip file creation process
        self.queue: JoinableQueue[str | bool | BlobNotFoundError] = JoinableQueue()
        self.message = message

        # the location to store the files that are being downloaded/unzipped
        self.file_dl_location = file_dl_location
        self.tmp_dir_path = scratch_location / self.file_hash

        # the message from the PubSub pull subscription if that is the source of the
        # ZipUploader
        self.ack_heartbeat: AckDeadlineHeartbeat | None = None
        if self.message is not None:
            self.ack_heartbeat = AckDeadlineHeartbeat(message, ack_heartbeat_seconds)
            deadline = datetime.fromtimestamp(message._received_timestamp, tz=UTC)  # noqa: SLF001
            # set some attributes on the message for our own tracking use
            message.ack_deadline = ack_deadline
            message.ack_start_time = deadline

        logger.debug("%s Initialized ZipUploader", self.log_prefix)

    @property
    def log_prefix(self) -> str:
        """A prefix to use for logging statements."""
        return f"[File Hash: {self.file_hash}]"

    def setup_processing(self) -> None:
        """Set up processing the zip file."""
        logger.debug("%s Creating tmp directory", self.log_prefix)
        # the path to download the files to
        self.file_dl_location.mkdir(parents=True, exist_ok=True)
        self.tmp_dir_path.mkdir(parents=True, exist_ok=True)

    @threadpool
    def get_file(self, dl_object: str) -> Path | None:
        """
        Asynchronously downloads a file from Google Cloud Storage to the local filesystem.

        Downloads a file from Google Cloud Storage to the local filesystem, returns early
        if the file already exists, pauses if the file is currently being downloaded.

        :param dl_object: The filename of the file to download (with path style
        gs://bucket/path/to/file)
        :return: The local path to the file
        """
        with tracer.start_as_current_span(dl_object):
            blob = self.input_bucket.get_blob(dl_object)
            # parse the bucket and path from each file in the request
            logger.debug(
                "%s Fetching file info for %s",
                self.log_prefix,
                f"gs://{self.input_bucket.name}/{dl_object}",
            )
            path = (Path(self.file_dl_location) / dl_object).resolve()
            if blob is None:
                raise BlobNotFoundError(dl_object)
            # get the base name for the file
            blob_size = blob.size
            path.parent.mkdir(parents=True, exist_ok=True)

            # check if the file already exists
            if path.exists():
                logger.debug("%s File already exists at %s", self.log_prefix, path)
                # if it does exist but is currently downloading, wait
                if self.wait_for_local_file(path, blob_size):
                    return path
                path.unlink(missing_ok=True)

            logger.debug("%s Downloading file to %s", self.log_prefix, path)
            blob.download_to_filename(str(path))
            return path

    def wait_for_local_file(self, path: Path, blob_size: int) -> bool:
        """
        Waits for another download of the same file to finish.

        The wait ends when the local file reaches the size of the remote blob, or when it
        stops growing for `download_stall_timeout` seconds.

        :param path: The local path of the file being downloaded
        :param blob_size: The size of the remote blob, in bytes
        :return: True if the local file is complete, False if the other download was
            abandoned and the file should be downloaded again
        """
        last_size = -1
        last_progress = time.monotonic()
        while True:
            try:
                current_size = path.stat().st_size
            except FileNotFoundError:
                logger.warning(
                    "%s Partial file %s disappeared while waiting for it",
                    self.log_prefix,
                    path,
                )
                return False
            if current_size >= blob_size:
                if last_size >= 0:
                    logger.debug(
                        "%s Other process finished downloading %s",
                        self.log_prefix,
                        path,
                    )
                return True
            if current_size != last_size:
                if last_size < 0:
                    logger.debug(
                        "%s Waiting for other process to download %s",
                        self.log_prefix,
                        path,
                    )
                last_size = current_size
                last_progress = time.monotonic()
            elif time.monotonic() - last_progress > self.download_stall_timeout:
                logger.warning(
                    "%s Download of %s stalled at %s / %s bytes, downloading it again",
                    self.log_prefix,
                    path,
                    current_size,
                    blob_size,
                )
                return False
            time.sleep(1)

    def create_zip(self) -> None:
        """
        Create a process that will zip files.

        This process will watch a queue for messages sent from the queue and write them to the
        archive. This method will concurrently download the files that a user has requested to
        download and, once each file has downloaded, will place a message in the queue with the
        local file path of the zipped file.
        """
        # Asynchronously download each file in the request using a threadpool
        futures: list[Future[Path | None]] = [self.get_file(file) for file in self.files]

        # Create an atomic counter to track the number of files that have been processed
        atomic_counter = Value("i", 0, lock=True)
        # Start a separate process to add files to the zip file
        p = Process(
            target=add_to_zip,
            kwargs={
                "tmp_dir": self.tmp_dir_path,
                "zip_loc": self.full_output_path,
                "output_bucket": self.output_bucket.name,
                "file_path_prefix": self.file_dl_location,
                "queue": self.queue,
                "processed_counter": atomic_counter,
            },
        )
        p.start()

        # as the files finish downloading, add them to the queue, ensuring that
        # time is not wasted waiting for files to download
        for i, fut in enumerate(as_completed(futures)):
            try:
                tmp_file_path = fut.result()
                tmp_file_path = str(tmp_file_path)
                self.queue.put(tmp_file_path)
                logger.debug(
                    "%s Finished downloading file %s",
                    self.log_prefix,
                    tmp_file_path,
                )
                # if the file does not exist in GCS (which is when None is returned), skip it
            except BlobNotFoundError as e:
                self.queue.put(e)

            # If this class has a message (e.g. we are pulling messages from the Pub/Sub
            # subscription rather than receiving `Push`-ed messages), check if the time
            # is getting dangerously close to the timeout
            if self.message is not None:
                self.check_message_deadline(i + 1)

        # wait for the add to zip process to finish
        while True:
            time.sleep(5)
            # while waiting for the zip process to finish log the number of files
            # and if running in Pull mode, extend the message deadline if needed
            with atomic_counter.get_lock():
                current_num_files = int(deepcopy(atomic_counter.value))
            logger.debug(
                "%s Process counter is at %s / %s",
                self.log_prefix,
                current_num_files,
                len(self.files),
            )
            if self.message is not None:
                self.check_message_deadline(current_num_files)
            # break if the queue is empty (process is about to finish)
            if self.queue.empty():
                break

        self.cleanup_create_zip(p)

    def check_message_deadline(self, current_num_files: int) -> None:
        """
        Checks if the message is about to expire, and modifies the message if it is.

        :param current_num_files: The number of files that have been downloaded/processed
        """
        # calculate the time elapsed since the process started
        elapsed_time = (datetime.now(tz=UTC) - self.message.ack_start_time).total_seconds()
        logger.debug(
            "%s Elapsed time/ack deadline threshold: %s seconds / %s seconds",
            self.log_prefix,
            elapsed_time,
            self.message.ack_deadline * 0.75,
        )
        # check if the time is getting dangerously close to the timeout
        if elapsed_time > (self.message.ack_deadline * 0.75):
            new_deadline = estimate_remaining_time(
                current_num_files,
                len(self.files),
                elapsed_time,
            )
            logger.debug(
                "%s Modifying ack deadline to %s seconds from now",
                self.log_prefix,
                new_deadline,
            )
            # go through the heartbeat, so that this never races it, never shortens a
            # deadline it set, and never extends after processing finished
            if self.ack_heartbeat is not None:
                if not self.ack_heartbeat.extend(new_deadline):
                    return
            else:
                self.message.modify_ack_deadline(new_deadline)
            # reset the start time and new ack deadline
            self.message.ack_deadline = new_deadline
            self.message.ack_start_time = datetime.now(tz=UTC)

    def cleanup_create_zip(self, proc: Process) -> None:
        """Closes/joins the queue and zip file creation process."""
        self.queue.put(obj=False)
        self.queue.join()
        self.queue.close()
        self.queue.join_thread()
        proc.join()

    def check_zip_exists_in_bucket(self) -> None:
        """
        Verifies that the zip archive exists in the Google Cloud Storage Bucket.

        :return: Whether the file exists
        """
        logger.debug(
            "%s Confirming existence of zip file at %s",
            self.log_prefix,
            self.full_output_path,
        )

        output_blob = self.output_bucket.get_blob(self.output_path)
        if output_blob is None:
            msg = "Zip file does not exist in bucket"
            raise FileNotFoundError(msg)

    def successful_result(self) -> ZipProcessResult:
        """
        Returns the output from the result of the zip file.

        :return: The result of the file processing
        """
        logger.info("%s Processed %s", self.log_prefix, self.full_output_path)
        if self.in_progress_cache is not None:
            self.in_progress_cache.finish_file(self.file_hash)
        return {
            "outputBucket": self.output_bucket.name,
            "outputPath": self.full_output_path,
            "manifest": self.files,
            "fileHash": self.file_hash,
            "requesters": [str(r) for r in self.requesters],
        }

    def send_notification(self) -> None:
        """
        Sends a notification to the user.

        When an in-progress cache is used, each requester is removed from the cache as soon
        as their notification is sent, so a retry only notifies the requesters that were
        not notified yet. A failed notification does not stop the other requesters from
        being notified.

        :raises Exception: The first notification error, after every requester was tried
        """
        if self.in_progress_cache is not None:
            self.requesters = list(
                self.in_progress_cache.get_requesters(self.file_hash),
            )
        logger.debug("%s Sending notification to %s", self.log_prefix, self.requesters)

        first_error: Exception | None = None
        for requester in self.requesters:
            try:
                send_notification_message(
                    requester.name,
                    requester.id,
                    requester.email,
                    self.output_path,
                    self.files,
                    self.notification_url,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("%s Failed to notify %s", self.log_prefix, requester)
                first_error = first_error or e
                continue
            if self.in_progress_cache is not None:
                self.in_progress_cache.remove_requester(self.file_hash, requester)

        if first_error is not None:
            raise first_error

    def notify_only(self) -> None:
        """
        Only notifies the users that have requested the file.

        The zip file must already exist in the output bucket, so this requires the
        `storage_client` and `output_bucket` parameters.

        :raises ValueError: If no storage client or output bucket was given
        :raises FileNotFoundError: If the zip file does not exist in the output bucket. No
            notifications are sent in that case.
        :raises NotificationError: If sending a notification fails
        """
        if self.output_bucket is None:
            msg = "notify_only requires a storage_client and output_bucket"
            raise ValueError(msg)
        self.check_zip_exists_in_bucket()
        try:
            self.send_notification()
        except Exception as e:
            raise NotificationError from e
        self.successful_result()

    def process_and_notify_requesters(self) -> None:
        """
        Processes the request, constructs the zip archive to the storage bucket.

        If a message is present, its ack deadline is extended in the background for the
        whole request, including the final upload and the notifications. The extension
        stops before this returns or raises, so the caller can then ack or nack it.
        """
        with self.ack_heartbeat or nullcontext():
            self._process_and_notify_requesters()

    def _process_and_notify_requesters(self) -> None:
        with tracer.start_as_current_span(self.file_hash):
            t1 = time.perf_counter()
            try:
                logger.info("%s Begin processing", self.log_prefix)
                self.setup_processing()
                self.create_zip()
                self.check_zip_exists_in_bucket()
            except Exception as e:
                logger.exception("Exception occurred while processing files.")
                if self.in_progress_cache is not None:
                    self.in_progress_cache.fail_file(self.file_hash)
                if self.tmp_dir_path:
                    shutil.rmtree(self.tmp_dir_path)
                raise ZipUploadError from e

            if self.in_progress_cache is not None:
                self.in_progress_cache.finish_file(self.file_hash)

            try:
                self.send_notification()
            except Exception as e:
                logger.exception(
                    "%s Zip created successfully but notification failed.",
                    self.log_prefix,
                )
                raise NotificationError from e

            self.successful_result()
            t2 = time.perf_counter()
            logger.info("%s REQUEST TIMER: %s seconds", self.log_prefix, t2 - t1)
