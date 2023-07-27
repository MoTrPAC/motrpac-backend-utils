#  Copyright (c) 2023. Mihir Samdarshi/MoTrPAC Bioinformatics Center

import math
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from motrpac_backend_utils.zipper import estimate_remaining_time, ZipUploader


class TestEstimateRemainingTime(unittest.TestCase):
    def test_estimate_remaining_time(self):
        # Arrange
        current_file_count = 5
        total_file_count = 20
        elapsed_time = 60.0

        # Act
        remaining_time = estimate_remaining_time(
            current_file_count, total_file_count, elapsed_time
        )

        # Assert
        expected_remaining_time = math.ceil(
            (elapsed_time / current_file_count)
            * (total_file_count - current_file_count)
            * 1.5
        )
        expected_remaining_time = min(expected_remaining_time, 600)
        self.assertEqual(remaining_time, expected_remaining_time)


class TestZipUploader(unittest.TestCase):
    def test_create_zip(self):
        files = ["file1.txt", "file2.txt"]
        file_hash = "hash123"
        notification_url = "https://example.com/notification"
        storage_client = MagicMock()
        input_bucket = "input_bucket"
        output_bucket = "output_bucket"
        scratch_location = Path("/tmp/scratch")
        file_dl_location = Path("/tmp/file_cache")
        in_progress_cache = MagicMock()
        requesters = [MagicMock(), MagicMock()]
        message = MagicMock()
        ack_deadline = 600

        zip_uploader = ZipUploader(
            files=files,
            file_hash=file_hash,
            notification_url=notification_url,
            storage_client=storage_client,
            input_bucket=input_bucket,
            output_bucket=output_bucket,
            scratch_location=scratch_location,
            file_dl_location=file_dl_location,
            in_progress_cache=in_progress_cache,
            requesters=requesters,
            message=message,
            ack_deadline=ack_deadline,
        )

        # Mock the necessary methods and attributes
        zip_uploader.setup_processing = MagicMock()
        zip_uploader.create_zip = MagicMock()
        zip_uploader.check_zip_exists_in_bucket = MagicMock()
        zip_uploader.send_notification = MagicMock()
        zip_uploader.successful_result = MagicMock()

        zip_uploader.process_and_notify_requesters()

        # Assertions
        zip_uploader.setup_processing.assert_called_once()
        zip_uploader.create_zip.assert_called_once()
        zip_uploader.check_zip_exists_in_bucket.assert_called_once()
        zip_uploader.send_notification.assert_called_once()
        zip_uploader.successful_result.assert_called_once()


if __name__ == "__main__":
    unittest.main()
