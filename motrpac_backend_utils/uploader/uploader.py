#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center
import shutil
from io import SEEK_END, SEEK_SET, BytesIO

from google.cloud.storage.client import Client as StorageClient
from smart_open import open
from motrpac_backend_utils.uploader.constants import (
    UPLOAD_BUFFER_SIZE,
    MAX_SINGLE_PART_SIZE,
)


class Uploader:
    """
    A utility class for uploading files in parallel
    """

    def __init__(
        self, storage_client: StorageClient, src_file: BytesIO,
        zip_location: str
    ):
        """
        Creates a new instance of the ParallelUploader
        """
        self.storage_client = storage_client
        self.src_file = src_file
        self.zip_location = zip_location

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

    def upload_file_single_part(self):
        """
        Uploads a file to Google Cloud Storage
        """
        with open(
            self.zip_location,
            mode="wb",
            transport_params={
                "min_part_size": UPLOAD_BUFFER_SIZE,
                "client": self.storage_client,
            },
        ) as gs_out:
            # reset the file pointer to the beginning of the file
            shutil.copyfileobj(self.src_file, gs_out, UPLOAD_BUFFER_SIZE)

        self.src_file.close()

    def upload_file_multi_part(self):
        """
        Uploads a single large file to Google Cloud Storage
        :return:
        """
        pass
