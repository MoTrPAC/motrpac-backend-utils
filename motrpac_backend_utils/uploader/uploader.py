#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center
import hashlib
import logging
import multiprocessing as mp
from concurrent.futures import Future, as_completed, ThreadPoolExecutor
from datetime import datetime, timezone
from io import SEEK_END, SEEK_SET, BytesIO
from queue import Queue
from typing import BinaryIO, List, TypeVar, Union, Generator

from google.cloud.storage import Blob
from google.cloud.storage.client import Client as StorageClient

from .constants import MAX_SINGLE_PART_SIZE, GCS_CHUNK_SIZE
from .file import FilePart, LockedFile, split_file, ceil_div
from ..utils import threadpool


logger = logging.getLogger()


class BoundedThreadPoolExecutor(ThreadPoolExecutor):
    """A wrapper around concurrent.futures.thread.py to add a bounded
    queue to ThreadPoolExecutor.
    """

    def __init__(self, *args, queue_size: int = 1000, **kwargs):
        """Construct a slightly modified ThreadPoolExecutor with a
        bounded queue for work. Causes submit() to block when full.
        Arguments:
            ThreadPoolExecutor {[type]} -- [description]
        """
        super().__init__(*args, **kwargs)
        self._work_queue = Queue(queue_size)


threads = mp.cpu_count()
executor = BoundedThreadPoolExecutor(max_workers=threads, queue_size=int(threads * 1.5))

T = TypeVar("T")


def ensure_results(maybe_futures: List[Union[T, Future[T]]]) -> List[T]:
    """Pass in a list that may contain futures, and if so, wait for
    the result of the future; for all other types in the list,
    simply append the value.

    :param maybe_futures: A list which may contain futures.
    :return List[Any]: A list with the values passed in, or Future.result() values.
    """
    results = []
    for mf in maybe_futures:
        if isinstance(mf, Future):
            results.append(mf.result())
        else:
            results.append(mf)
    return results


class Uploader:
    """
    A utility class for uploading files in parallel
    """

    def __init__(
        self,
        storage_client: StorageClient,
        src_file: BinaryIO,
        bucket: str,
        object_name: str,
        use_custom_time: bool = False,
    ):
        """
        Creates a new instance of the ParallelUploader
        :param storage_client: the Google Cloud Storage client
        :param src_file: the source file object (any file-like object)
        :param bucket: the bucket that the object will be uploaded to
        :param object_name: name of the object that will be created in Google Cloud Storage
        :param use_custom_time: whether to add custom time metadata to the object
        """
        self.src_file = LockedFile(src_file)
        self.object_name = object_name

        self.storage_client = storage_client
        self.bucket = storage_client.get_bucket(bucket)
        # the blob that will be created in Google Cloud Storage
        self.blob = self.bucket.blob(object_name)
        self.use_custom_time = use_custom_time

    @property
    def file_obj_size(self) -> int:
        # get the file object size by setting the cursor to 0 bytes from the end
        self.src_file.seek(0, SEEK_END)
        # then tell gets the current cursor position
        file_obj_size = self.src_file.tell()
        # reset the cursor to the beginning of the file
        self.src_file.seek(0, SEEK_SET)
        return file_obj_size

    def upload_file(self):
        """
        Uploads a file to Google Cloud Storage
        """
        if self.file_obj_size <= MAX_SINGLE_PART_SIZE:
            self.upload_file_single_part()
        else:
            self.upload_file_multi_part()

        if self.use_custom_time:
            self.add_custom_time_metadata()

    def add_custom_time_metadata(self):
        """
        Adds custom time metadata to the file in Google Cloud Storage. Useful for managing
        object lifecycle using this metadata
        """
        logger.debug("Adding custom time metadata to the file")
        self.blob.custom_time = datetime.now(timezone.utc)
        self.blob.patch()

    def upload_file_single_part(self):
        """
        Uploads a file to Google Cloud Storage
        """
        logger.info("Uploading %s as a single part", self.object_name)
        self.blob.upload_from_file(self.src_file)

    @threadpool(pool=executor)
    def upload_with_offset(self, file: FilePart):
        """
        Uploads a file part to Google Cloud Storage
        :param file: The file part to be uploaded
        :return: The blob that was created in Google Cloud Storage
        """
        self.src_file.seek(file.part_start, SEEK_SET)
        new_bytes = self.src_file.read(file.part_size)

        with BytesIO(new_bytes) as part_file:
            blob = self.bucket.blob(file.part_name)
            blob.upload_from_file(part_file)

        return blob

    @staticmethod
    @threadpool(pool=executor)
    def cleanup_blobs(blobs: List[Blob]):
        """
        Deletes the blobs that were created in Google Cloud Storage
        :param blobs: the blobs to be deleted
        """
        logger.debug("Deleting blobs")
        for blob in blobs:
            blob.delete()

    @threadpool(pool=executor)
    def create_composed_blob(self, blobs: List[Blob]) -> Blob:
        """
        Composes multiple blobs into a single blob
        :param blobs: the blobs to be composed
        :return: the composed blob
        """
        logger.debug("Composing multiple blobs into single blob")
        # compute the new filename
        file_hash = hashlib.blake2b()
        for blob in blobs:
            file_hash.update(blob.name)

        # compose a new blob
        blob = self.bucket.blob(file_hash.hexdigest()).compose(blobs)
        # remove the blobs
        self.cleanup_blobs(blobs)
        return blob

    def compose_blobs_from_list(self, blobs: List[Blob]) -> List[Blob]:
        """
        Composes multiple blobs into a list of at least 32 blobs
        :param blobs: the blobs to be composed
        :return: the composed blob
        """
        blobs_len = len(blobs)
        logger.debug("Composing %s blobs", blobs_len)
        # copy the blobs to a new list
        mutable_blob_slice = blobs[:]
        # create a list of futures
        future_blobs: List[Future[Blob]] = []

        while blobs_len <= 32:
            # take 32 blobs at a time
            sliced_blobs = mutable_blob_slice[:32]
            # remove the blobs from the list
            mutable_blob_slice[:32] = []
            # remove 31 blobs from the length of blob list (32 blobs -> 1)
            blobs_len = blobs_len - 31
            future_blobs.append(self.create_composed_blob(sliced_blobs))

            # if we have exceeded 32 blobs, we need to wait for them to finish
            if len(future_blobs) >= 32:
                logger.debug("Waiting for blobs to finish")
                # wait for the futures to finish
                for future_blob in as_completed(future_blobs):
                    # get the blob from the future and append back to the list
                    mutable_blob_slice.append(future_blob.result())
                # reset the list of futures
                future_blobs = []

        # combine the blob list
        all_blobs = mutable_blob_slice + future_blobs
        return ensure_results(all_blobs)

    def upload_file_multi_part(self):
        """
        Uploads a single large file to Google Cloud Storage
        """
        logger.info("Uploading %s as a multi-part upload", self.object_name)
        futures: List[Future[Blob]] = []

        num_parts = ceil_div(self.file_obj_size, GCS_CHUNK_SIZE)
        for f in split_file(self.object_name, self.file_obj_size):
            logger.debug(
                "Uploading %s %s/%s", self.object_name, f.part_num + 1, num_parts
            )
            b = self.upload_with_offset(f)
            futures.append(b)

        blobs: List[Blob] = [f.result() for f in as_completed(futures)]
        composed_blobs = self.compose_blobs_from_list(blobs)

        try:
            logger.debug("Composing multiple blobs into single blob")
            self.blob.compose(composed_blobs)
        finally:
            self.cleanup_blobs(composed_blobs).result()
