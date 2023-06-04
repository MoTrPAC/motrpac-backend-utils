#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""
Contains the ZipUploader class, which is used to zip files and send them to Google Cloud
Storage. It also contains utilities for sending notifications via Pub/Sub upon completion.
"""
import json
import logging
import math
import os
import shutil
import time
from concurrent.futures import Future, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from multiprocessing import JoinableQueue, Process, Value
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import TypedDict
from zipfile import ZIP_DEFLATED, ZipFile

from google.cloud.pubsub_v1.subscriber.message import Message
from google.cloud.storage import Client as StorageClient
from opentelemetry import trace
from psutil import virtual_memory
from smart_open import open

from motrpac_backend_utils.messages import send_notification_message
from motrpac_backend_utils.requester import Requester
from motrpac_backend_utils.threadpool import threadpool
from .cache import InProgressCache
from .utils import get_path_dict


MAX_IN_PROGRESS = max(os.cpu_count() - 3 or 1, 1)

# setup local logging/Google Cloud Logging
logger = logging.getLogger()
tracer = trace.get_tracer(__name__)


class ZipProcessResult(TypedDict):
    """
    A dictionary that contains a summary of details regarding the results of a zip process.
    """

    outputBucket: str
    outputPath: str
    manifest: list[str]
    fileHash: str
    requesters: list[str] | None


def add_to_zip(
    tmp_dir: str,
    zip_loc: str,
    output_bucket: str,
    file_path_prefix: os.PathLike,
    queue: "JoinableQueue[str | bool]",
    processed_counter: type[Value] | None,
) -> bool:
    """
    Adds files to an archive, working asynchronously, with another process which will
    tell it which files to process, and when it is done.

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
    file_hash = os.path.basename(os.path.splitext(zip_loc)[0])
    with tracer.start_as_current_span(file_hash):
        logger.debug(
            "[File Hash: %s] Spawned local zip file creator child process, PID: %s",
            file_hash,
            os.getpid(),
        )
        # Process-local instance of the Storage client.
        upload_buffer_size = 2 ** 8 * 256 * 1024

        # Figure out how much memory we have available to allocate the new zip file
        memory = virtual_memory()
        free_memory = int(memory.available / MAX_IN_PROGRESS)
        logger.debug(
            "[File Hash: %s] Allocating %s GB of memory for temp zip file",
            file_hash,
            round(free_memory / (1024 ** 3), 4),
        )
        manifest: list[str] = []
        storage_client = StorageClient()

        # A spooled zip file exists in memory, and is written to disk when it reaches a
        # certain size, which is what we allocated above
        with SpooledTemporaryFile(max_size=free_memory, dir=tmp_dir) as tmp_file:
            with ZipFile(tmp_file, mode="w", compression=ZIP_DEFLATED) as archive:
                while True:
                    # get the latest message from the shared process queue
                    f = queue.get()
                    logger.debug(
                        "[File Hash: %s] Received message from queue %s",
                        file_hash,
                        f,
                    )
                    # sentinel to tell the multiprocessing to stop processing
                    if isinstance(f, bool) and not f:
                        queue.task_done()
                        break
                    # create a file in the archive
                    archive.write(
                        f,
                        arcname=f.replace(f"{str(file_path_prefix).rstrip('/')}/", ""),
                    )
                    manifest.append(f)
                    queue.task_done()
                    if processed_counter is not None:
                        with processed_counter.get_lock():
                            processed_counter.value += 1
                    logger.debug("[File Hash: %s] Finished archiving %s", file_hash, f)

                manifest_fn = f"{file_hash}.nested.manifest.json"
                archive.writestr(
                    manifest_fn,
                    json.dumps(get_path_dict(manifest), indent=2),
                )
                manifest_fn = f"{file_hash}.list.manifest.json"
                archive.writestr(manifest_fn, json.dumps(manifest, indent=2))

            with open(
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

            bucket = storage_client.get_bucket(output_bucket)
            zip_blob = bucket.blob(os.path.basename(zip_loc))
            zip_blob.custom_time = datetime.now(timezone.utc)
            zip_blob.patch()

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
    """
    # calculate the estimated time remaining
    remaining_time = (elapsed_time / current_file_count) * (
        total_file_count - current_file_count
    )

    return min(math.ceil(remaining_time * 1.5), 600)


class ZipUploadError(Exception):
    """
    An exception class to represent errors that occur during the zip upload process.
    """
    pass


class ZipUploader:
    """
    A class to create and upload a zip file to Google Cloud Storage from a list of files
    (also in Google Cloud Storage).
    """

    def __init__(
        self,
        files: list[str],
        file_hash: str,
        notification_url: str,
        storage_client: StorageClient | None = None,
        input_bucket: str | None = None,
        output_bucket: str | None = None,
        scratch_location: Path = Path("/tmp"),
        file_dl_location: Path = Path("/tmp/file_cache"),
        in_progress_cache: InProgressCache | None = None,
        requesters: list[Requester] | None = None,
        message: Message | None = None,
        ack_deadline: int = 600,
    ) -> None:
        """
        Initialize the ZipUploader class. This has two functionalities: one to both create
        and upload a zip file to Google Cloud Storage, and one to just notify the
        requester, if the zip file was already created by the zip class.

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
        """
        self.files = files
        self.file_hash = file_hash

        # the url to push the notification URL to
        self.notification_url = notification_url

        # the file's requesters
        self.requesters = requesters
        self.in_progress_cache = in_progress_cache
        if self.in_progress_cache is None and self.requesters is None:
            msg = "Either in_progress_cache or requesters must be specified"
            raise ValueError(msg)

        # Names output zip file based on the hash of the files
        self.output_path = f"{file_hash}.zip"
        self.full_output_path = f"gs://{output_bucket}/{self.output_path}"

        # set up the storage client and input/output buckets
        self.storage_client = storage_client
        if self.storage_client is not None:
            self.input_bucket = storage_client.get_bucket(input_bucket)
            self.output_bucket = storage_client.get_bucket(output_bucket)

        # the queue to communicate with the separate zip file creation process
        self.queue: "JoinableQueue[str | bool]" = JoinableQueue()
        self.message = message

        # the location to store the files that are being downloaded/unzipped
        self.file_dl_location = file_dl_location
        self.tmp_dir_path = scratch_location.joinpath(Path(self.file_hash))

        # the message from the PubSub pull subscription if that is the source of the
        # ZipUploader
        if self.message is not None:
            deadline = datetime.fromtimestamp(message._received_timestamp)
            # set some attributes on the message for our own tracking use
            message.ack_deadline = ack_deadline
            message.ack_start_time = deadline

        logger.debug("%s Initialized ZipUploader", self.log_prefix)

    @property
    def log_prefix(self) -> str:
        """
        A prefix to use for logging statements.
        """
        return f"[File Hash: {self.file_hash}]"

    def setup_processing(self) -> None:
        """
        Set up processing the zip file.
        """
        logger.debug("%s Creating tmp directory", self.log_prefix)
        # the path to download the files to
        self.file_dl_location.mkdir(parents=True, exist_ok=True)
        self.tmp_dir_path.mkdir(parents=True, exist_ok=True)

    @threadpool
    def get_file(self, dl_object: str) -> Path | None:
        """
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
            # fetch files individually
            if blob is not None:
                # get the base name for the file
                blob_size = blob.size
                name = Path(dl_object)
                path = Path(self.file_dl_location).joinpath(name).resolve()
                path.parent.mkdir(parents=True, exist_ok=True)

                # check if the file already exists
                if path.exists():
                    logger.debug("%s File already exists at %s", self.log_prefix, path)
                    # does size of remote and local file match (the file may be currently
                    # downloading)
                    if path.stat().st_size < blob_size:
                        logger.debug(
                            "%s Waiting for other process to download %s",
                            self.log_prefix,
                            path,
                        )
                    # if it does exist but is currently downloading, wait
                    while path.stat().st_size < blob_size:
                        time.sleep(1)
                    logger.debug(
                        "%s Other process finished downloading %s",
                        self.log_prefix,
                        path,
                    )
                    return path

                logger.debug("%s Downloading file to %s", self.log_prefix, path)
                blob.download_to_filename(str(path))
                return path

            return None

    def create_zip(self) -> None:
        """
        Creates an async iterator that will yield the files in the zip archive.
        """
        futures: list[Future[Path | None]] = []

        for file in self.files:
            futures.append(self.get_file(file))

        atomic_counter = Value("i", 0, lock=True)
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

        for i, fut in enumerate(as_completed(futures)):
            tmp_file_path = str(fut.result())
            self.queue.put(tmp_file_path)
            logger.debug(
                "%s Finished downloading file %s",
                self.log_prefix,
                tmp_file_path,
            )
            # check if the time is getting dangerously close to the timeout
            if self.message is not None:
                self.check_message_deadline(i)

        # wait for the add to zip process to finish`
        while True:
            time.sleep(5)
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
        elapsed_time = (datetime.now() - self.message.ack_start_time).total_seconds()
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
            self.message.modify_ack_deadline(new_deadline)
            # reset the start time and new ack deadline
            self.message.ack_deadline = new_deadline
            self.message.ack_start_time = datetime.now()

    def cleanup_create_zip(self, proc: Process) -> None:
        """
        Closes/joins the queue and zip file creation process.
        """
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
        """
        if self.in_progress_cache is not None:
            self.requesters = list(
                self.in_progress_cache.get_requesters(self.file_hash),
            )
        logger.debug("%s Sending notification to %s", self.log_prefix, self.requesters)

        if len(self.requesters) > 0:
            for requester in self.requesters:
                send_notification_message(
                    requester.name,
                    requester.email,
                    self.output_path,
                    self.files,
                    self.notification_url,
                )

    def notify_only(self) -> None:
        """
        Only notifies the users that have requested the file.

        :return:
        """
        self.send_notification()
        self.successful_result()

    def process_and_notify_requesters(self) -> None:
        """
        Processes the request, constructs the zip archive to the storage bucket.
        """
        with tracer.start_as_current_span(self.file_hash):
            try:
                t1 = time.perf_counter()
                logger.info("%s Begin processing", self.log_prefix)
                self.setup_processing()
                self.create_zip()
                self.check_zip_exists_in_bucket()
                self.send_notification()
                self.successful_result()
                t2 = time.perf_counter()
                logger.info("%s REQUEST TIMER: %s seconds", self.log_prefix, t2 - t1)
            except Exception as e:
                logger.exception("Exception occurred while processing files.")
                if self.tmp_dir_path:
                    shutil.rmtree(self.tmp_dir_path)
                raise ZipUploadError from e
