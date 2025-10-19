from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

import pytest
from google.api_core.exceptions import GoogleAPICallError
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from motrpac_backend_utils.messages import (
    publish_file_download_message,
    decode_file_download_message,
)
from motrpac_backend_utils.proto import FileDownloadMessage
from motrpac_backend_utils.requester import Requester

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def _setup_tracer() -> None:
    tracer_provider = TracerProvider()
    trace.set_tracer_provider(tracer_provider)
    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(ConsoleSpanExporter()),
    )


@pytest.fixture
def sample_request() -> dict[str, Any]:
    return {
        "name": "John Doe",
        "user_id": "1234567890",
        "email": "johndoe@example.com",
        "files": ["file1.txt", "file2.txt"],
        "topic_id": "my-topic",
    }


@pytest.mark.parametrize(
    "files",
    [["file1.txt"], ["file1.txt", "file2.txt", "file3.txt"]],
)
def test_decode_file_download_message(files: list[str]) -> None:
    # Arrange
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


def test_decode_file_download_message_invalid_message() -> None:
    # Arrange
    invalid_message = b"invalid_message"

    # Act & Assert
    with pytest.raises(ValueError, match="Failed to decode"):
        decode_file_download_message(invalid_message)


@pytest.fixture
def mock_pubsub(mocker: MockerFixture) -> tuple[Any, Any]:
    mock_client = mocker.MagicMock()
    mock_future = mocker.MagicMock()
    mock_client.publish.return_value = mock_future
    # Ensure future.result returns something stringifiable
    mock_future.result.return_value = "123"
    return mock_client, mock_future


def test_publish_file_download_message_success(
    sample_request: dict[str, Any],
    mock_pubsub: tuple[Any, Any],
) -> None:
    client, future = mock_pubsub
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span(
        "test_publish_file_download_message_success",
    ) as span:
        span.set_attribute("printed_string", "hello")
        publish_file_download_message(
            sample_request["name"],
            sample_request["user_id"],
            sample_request["email"],
            sample_request["files"],
            sample_request["topic_id"],
            client,
        )

    # Assert
    # The second positional arg is the encoded bytes; the attrs include span context json
    called_args, called_kwargs = client.publish.call_args
    assert called_args[0] == sample_request["topic_id"]
    assert isinstance(called_args[1], (bytes, bytearray))
    assert "googclient_OpenTelemetrySpanContext" in called_kwargs
    # Validate the value is JSON
    json.loads(called_kwargs["googclient_OpenTelemetrySpanContext"])  # no raise
    future.result.assert_called_once()


def test_publish_file_download_message_failure(
    sample_request: dict[str, Any],
    mock_pubsub: tuple[Any, Any],
) -> None:
    client, _ = mock_pubsub
    error = GoogleAPICallError("Error occurred.")
    client.publish.side_effect = error

    with pytest.raises(GoogleAPICallError):
        publish_file_download_message(
            sample_request["name"],
            sample_request["user_id"],
            sample_request["email"],
            sample_request["files"],
            sample_request["topic_id"],
            client,
        )
