#  Copyright (c) 2023. Mihir Samdarshi/MoTrPAC Bioinformatics Center

import unittest
from unittest import mock
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import GoogleAPICallError
from google.cloud.pubsub_v1 import PublisherClient
from google.cloud.pubsub_v1.publisher.futures import Future
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

from motrpac_backend_utils.messages import (
    publish_file_download_message,
    decode_file_download_message,
)
from motrpac_backend_utils.proto import FileDownloadMessage
from motrpac_backend_utils.requester import Requester

tracer_provider = TracerProvider()
trace.set_tracer_provider(tracer_provider)

trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
tracer = trace.get_tracer(__name__)


class TestDecodeFileDownloadMessage(unittest.TestCase):
    def test_decode_file_download_message(self) -> None:
        # Arrange
        files = ["file1.txt", "file2.txt"]
        name = "John Doe"
        user_id = "1234567890"
        email = "johndoe@example.com"
        message = FileDownloadMessage()
        message.files.extend(files)
        message.requester.CopyFrom(
            Requester(name=name, email=email, id=user_id).to_proto(
                FileDownloadMessage.Requester,
            ),
        )
        encoded_message = message.SerializeToString()

        # Act
        decoded_files, requester = decode_file_download_message(encoded_message)

        # Assert
        assert decoded_files == files
        assert requester.name == name
        assert requester.email == email

    def test_decode_file_download_message_invalid_message(self) -> None:
        # Arrange
        invalid_message = b"invalid_message"

        # Act & Assert
        with pytest.raises(ValueError):
            decode_file_download_message(invalid_message)


class TestPublishFileDownloadMessage(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_client = MagicMock(spec=PublisherClient)
        self.mock_future = MagicMock(spec=Future)
        self.mock_client.publish.return_value = self.mock_future

    def test_publish_file_download_message_success(self) -> None:
        # Arrange
        name = "John Doe"
        user_id = "1234567890"
        email = "johndoe@example.com"
        files = ["file1.txt", "file2.txt"]
        topic_id = "my-topic"

        with tracer.start_as_current_span(
            "test_publish_file_download_message_success",
        ) as span:
            span.set_attribute("printed_string", "hello")
            publish_file_download_message(
                name,
                user_id,
                email,
                files,
                topic_id,
                self.mock_client,
            )

        # Assert
        self.mock_client.publish.assert_called_once_with(
            topic_id,
            mock.ANY,
            googclient_OpenTelemetrySpanContext=mock.ANY,
        )
        self.mock_future.result.assert_called_once()

    def test_publish_file_download_message_failure(self) -> None:
        # Arrange
        name = "John Doe"
        user_id = "1234567890"
        email = "johndoe@example.com"
        files = ["file1.txt", "file2.txt"]
        topic_id = "my-topic"
        error = GoogleAPICallError("Error occurred.")

        self.mock_client.publish.side_effect = error

        # Act & Assert
        with pytest.raises(GoogleAPICallError), tracer.start_as_current_span(  # noqa: PT012
            "test_publish_file_download_message_failure",
        ) as span:
            span.set_attribute("printed_string", "hello")
            publish_file_download_message(
                name,
                user_id,
                email,
                files,
                topic_id,
                self.mock_client,
            )


if __name__ == "__main__":
    unittest.main()
