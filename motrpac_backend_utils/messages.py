#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""
Contains the messaging functions for the backend. When using this,
make sure that package features "messaging" or "zipper" are used.
"""
import logging

from google.auth.transport.requests import AuthorizedSession
from google.cloud.pubsub_v1 import PublisherClient
from google.protobuf.message import Error

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


# pylint: disable=no-member
def publish_file_download_message(
    name: str,
    email: str,
    files: list[str],
    topic_id: str,
    client: PublisherClient,
) -> None:
    """
    Publishes a FileDownloadMessage protobuf message to the topic id provided.

    :param name: The name of the requester
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
            Requester(name=name, email=email).to_proto(FileDownloadMessage.Requester),
        )
        # Encode the data according to the message serialization type.
        msg_data = message.SerializeToString()
        logger.debug("Preparing a binary-encoded message:\n%s", msg_data)

        future = client.publish(topic_id, msg_data)
        logger.info("Published message ID: %s", future.result())
    # pylint: disable=broad-except
    except Exception as e:
        logger.exception(
            "Exception occurred while publishing message.",
            stack_info=True,
        )
        raise e from e


def send_notification_message(
    name: str,
    email: str,
    output_filename: str,
    manifest: list[str],
    url: str,
    session: AuthorizedSession | None = None,
) -> None:
    """
    Publishes a message to the topic.

    :param name: The name of the requester
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
            Requester(name=name, email=email).to_proto(
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
            url=url, data=msg_data, headers={"Content-Type": "application/octet-stream"},
        )

    # pylint: disable=broad-except
    except Exception as e:
        logger.exception(
            "Exception occurred while sending message.",
            stack_info=True,
        )
        raise e from e
