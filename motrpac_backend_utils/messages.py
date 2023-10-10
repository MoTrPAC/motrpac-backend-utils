#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""
Contains the messaging functions for the backend. When using this,
make sure that package features "messaging" or "zipper" are used.
"""
import json
import logging

from google.api_core.exceptions import GoogleAPICallError
from google.auth.transport.requests import AuthorizedSession
from google.cloud.pubsub_v1 import PublisherClient
from google.protobuf.message import Error
from opentelemetry import trace
from opentelemetry.instrumentation.utils import http_status_to_status_code
from opentelemetry.trace import Status

from .proto import FileDownloadMessage, UserNotificationMessage
from .requester import Requester
from .utils import get_authorized_session

logger = logging.getLogger(__name__)


def decode_file_download_message(message: bytes) -> tuple[list[str], Requester]:
    """
    Parses a File Download Protobuf message into a List of requested files and a named
    tuple of type Requester.

    :param message: The Protobuf message (encoded as bytes)
    :return: The decoded message
    """
    try:
        message_data = FileDownloadMessage()
        message_data.ParseFromString(message)
        requested_files = list(message_data.files)
        requester = Requester.from_proto(message_data.requester)
    except Error as e:
        msg = "Failed to decode protobuf message"
        raise ValueError(msg) from e

    return requested_files, requester


def publish_file_download_message(
    name: str,
    user_id: str | None,
    email: str,
    files: list[str],
    topic_id: str,
    client: PublisherClient,
) -> None:
    """
    Publishes a FileDownloadMessage protobuf message to the topic id provided.

    :param name: The name of the requester
    :param user_id: The ID of the requester
    :param email: The email of the requester
    :param files: A list of files that are being downloaded
    :param topic_id: The Pub/Sub topic to publish messages to
    :param client: The Pub/Sub PublisherClient
    :return:
    """
    try:
        # Instantiate a protoc-generated class defined in `us-states.proto`.
        message = FileDownloadMessage()
        message.files.extend(files)
        message.requester.CopyFrom(
            Requester(name=name, email=email, id=user_id).to_proto(
                FileDownloadMessage.Requester,
            ),
        )
        # Encode the data according to the message serialization type.
        msg_data = message.SerializeToString()
        logger.debug("Preparing a binary-encoded message:\n%s", msg_data)

        tracer = trace.get_tracer(__name__)

        # Create a new span and yield it
        with tracer.start_as_current_span(
            f"{topic_id} publisher", attributes={"data": str(msg_data)},
        ) as span:
            try:
                attrs = {
                    "googclient_OpenTelemetrySpanContext": json.dumps(
                        span.get_span_context().__dict__,
                    ),
                }
                future = client.publish(topic_id, msg_data, **attrs)
            except GoogleAPICallError as error:
                if error.code is not None:
                    span.set_status(Status(http_status_to_status_code(error.code)))
                raise

        logger.info("Published message ID: %s", future.result())
    # pylint: disable=broad-except
    except Exception as e:
        logger.exception("Exception occurred while publishing message.")
        raise e from e


def send_notification_message(
    name: str,
    user_id: str | None,
    email: str,
    output_filename: str,
    manifest: list[str],
    url: str,
    session: AuthorizedSession | None = None,
) -> None:
    """
    Publishes a message to the topic.

    :param name: The name of the requester
    :param user_id: The ID of the requester
    :param email: The email of the requester
    :param output_filename: The name of the output zip file
    :param manifest: A list of files that were requested
    :param url: The URL to send the notification to
    :param session: An authorized session (authorized for the URL) to send the message
    """
    try:
        # create the ProtoBuf message
        message = UserNotificationMessage()
        message.requester.CopyFrom(
            Requester(name=name, email=email, id=user_id).to_proto(
                UserNotificationMessage.Requester,
            ),
        )
        message.zipfile = output_filename
        message.files.extend(manifest)
        # serialize the message to bytes
        msg_data = message.SerializeToString()

        if session is None:
            session = get_authorized_session(url)
        session.post(
            url=url,
            data=msg_data,
            headers={"Content-Type": "application/octet-stream"},
        )

    # pylint: disable=broad-except
    except Exception as e:
        logger.exception("Exception occurred while sending message.")
        raise e from e
