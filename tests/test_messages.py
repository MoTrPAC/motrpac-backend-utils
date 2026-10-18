from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import GoogleAPICallError
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from requests import Response
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import HTTPError, Timeout

from motrpac_backend_utils.messages import (
    _NOTIFICATION_MAX_RETRIES,
    _NOTIFICATION_TIMEOUT,
    decode_file_download_message,
    publish_file_download_message,
    send_notification_message,
)
from motrpac_backend_utils.models import (
    DownloadRequestFileModel,
    DownloadRequestModel,
    Requester,
)
from motrpac_backend_utils.proto import FileDownloadMessage

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
        "files": [
            {"object": "file1.txt", "object_size": 100},
            {"object": "file2.txt", "object_size": 200},
        ],
        "topic_id": "my-topic",
    }


@pytest.fixture
def sample_model(sample_request: dict[str, Any]) -> DownloadRequestModel:
    return DownloadRequestModel(
        name=sample_request["name"],
        user_id=sample_request["user_id"],
        email=sample_request["email"],
        files=[DownloadRequestFileModel(**f) for f in sample_request["files"]],
    )


@pytest.mark.parametrize(
    "files",
    [
        [("file1.txt", 100)],
        [("file1.txt", 100), ("file2.txt", 200), ("file3.txt", 300)],
    ],
)
def test_decode_file_download_message(files: list[tuple[str, int]]) -> None:
    # Arrange
    name = "John Doe"
    user_id = "1234567890"
    email = "johndoe@example.com"
    message = FileDownloadMessage()

    # Add files with size metadata
    for filename, size in files:
        file_msg = message.files.add()
        file_msg.object = filename
        file_msg.object_size = size

    message.requester.CopyFrom(
        Requester(name=name, email=email, id=user_id).to_proto(
            FileDownloadMessage.Requester,
        ),
    )
    encoded_message = message.SerializeToString()

    # Act
    req_model = decode_file_download_message(encoded_message)

    # Assert
    assert isinstance(req_model, DownloadRequestModel)
    assert req_model.name == name
    assert req_model.email == email
    assert req_model.user_id == user_id
    assert len(req_model.files) == len(files)
    for i, (filename, size) in enumerate(files):
        assert req_model.files[i].object == filename
        assert req_model.files[i].object_size == size


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
    sample_model: DownloadRequestModel,
    mock_pubsub: tuple[Any, Any],
) -> None:
    client, future = mock_pubsub
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span(
        "test_publish_file_download_message_success",
    ) as span:
        span.set_attribute("printed_string", "hello")
        publish_file_download_message(
            sample_model,
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
    sample_model: DownloadRequestModel,
    mock_pubsub: tuple[Any, Any],
) -> None:
    client, _ = mock_pubsub
    error = GoogleAPICallError("Error occurred.")
    client.publish.side_effect = error

    with pytest.raises(GoogleAPICallError):
        publish_file_download_message(
            sample_model,
            sample_request["topic_id"],
            client,
        )


@pytest.fixture
def span_exporter(mocker: MockerFixture) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    mocker.patch(
        "motrpac_backend_utils.messages.trace.get_tracer",
        return_value=provider.get_tracer(__name__),
    )
    return exporter


def test_publish_file_download_message_keeps_pii_out_of_traces_and_logs(
    sample_request: dict[str, Any],
    sample_model: DownloadRequestModel,
    mock_pubsub: tuple[Any, Any],
    span_exporter: InMemorySpanExporter,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, _ = mock_pubsub

    with caplog.at_level(logging.DEBUG, logger="motrpac_backend_utils.messages"):
        publish_file_download_message(sample_model, sample_request["topic_id"], client)

    (span,) = span_exporter.get_finished_spans()
    assert dict(span.attributes) == {
        "request.hash": sample_model.hash,
        "request.file_count": len(sample_request["files"]),
        "request.total_size": sample_model.total_size,
        "request.user_id": sample_request["user_id"],
    }
    traced_and_logged = " ".join([*(str(v) for v in span.attributes.values()), caplog.text])
    assert sample_request["email"] not in traced_and_logged
    assert sample_request["name"] not in traced_and_logged
    assert sample_model.hash in caplog.text


def test_publish_file_download_message_omits_missing_user_id(
    sample_request: dict[str, Any],
    sample_model: DownloadRequestModel,
    mock_pubsub: tuple[Any, Any],
    span_exporter: InMemorySpanExporter,
) -> None:
    client, _ = mock_pubsub

    publish_file_download_message(
        sample_model.model_copy(update={"user_id": None}),
        sample_request["topic_id"],
        client,
    )

    (span,) = span_exporter.get_finished_spans()
    assert "request.user_id" not in span.attributes


@pytest.fixture
def mock_session(mocker: MockerFixture) -> MagicMock:
    mock_sess = mocker.MagicMock()
    mocker.patch(
        "motrpac_backend_utils.messages.get_authorized_session",
        return_value=mock_sess,
    )
    return mock_sess


def test_send_notification_message_success(mock_session: MagicMock) -> None:
    send_notification_message(
        name="John Doe",
        user_id="user123",
        email="john@example.com",
        output_filename="output.zip",
        manifest=["file1.txt", "file2.txt"],
        url="https://example.com/notify",
    )

    mock_session.post.assert_called_once()
    call_kwargs = mock_session.post.call_args
    assert call_kwargs.kwargs.get("timeout") == _NOTIFICATION_TIMEOUT


def test_send_notification_message_retries_on_connection_error(
    mock_session: MagicMock,
) -> None:
    mock_session.post.side_effect = [
        RequestsConnectionError(),
        RequestsConnectionError(),
        MagicMock(),
    ]

    send_notification_message(
        name="John Doe",
        user_id="user123",
        email="john@example.com",
        output_filename="output.zip",
        manifest=["file1.txt"],
        url="https://example.com/notify",
    )

    assert mock_session.post.call_count == _NOTIFICATION_MAX_RETRIES


def test_send_notification_message_retries_on_timeout(
    mock_session: MagicMock,
) -> None:
    mock_session.post.side_effect = [Timeout(), Timeout(), MagicMock()]

    send_notification_message(
        name="John Doe",
        user_id="user123",
        email="john@example.com",
        output_filename="output.zip",
        manifest=["file1.txt"],
        url="https://example.com/notify",
    )

    assert mock_session.post.call_count == _NOTIFICATION_MAX_RETRIES


def test_send_notification_message_raises_after_max_retries(
    mock_session: MagicMock,
) -> None:
    mock_session.post.side_effect = RequestsConnectionError()

    with pytest.raises(RequestsConnectionError):
        send_notification_message(
            name="John Doe",
            user_id="user123",
            email="john@example.com",
            output_filename="output.zip",
            manifest=["file1.txt"],
            url="https://example.com/notify",
        )

    assert mock_session.post.call_count == _NOTIFICATION_MAX_RETRIES


def test_send_notification_message_no_retry_on_non_network_error(
    mock_session: MagicMock,
) -> None:
    mock_session.post.side_effect = ValueError("unexpected error")

    with pytest.raises(ValueError, match="unexpected error"):
        send_notification_message(
            name="John Doe",
            user_id="user123",
            email="john@example.com",
            output_filename="output.zip",
            manifest=["file1.txt"],
            url="https://example.com/notify",
        )

    assert mock_session.post.call_count == 1


def test_send_notification_message_raises_on_http_error_status(
    mock_session: MagicMock,
) -> None:
    response = Response()
    response.status_code = 500
    mock_session.post.return_value = response

    with pytest.raises(HTTPError):
        send_notification_message(
            name="John Doe",
            user_id="user123",
            email="john@example.com",
            output_filename="output.zip",
            manifest=["file1.txt"],
            url="https://example.com/notify",
        )

    assert mock_session.post.call_count == 1
