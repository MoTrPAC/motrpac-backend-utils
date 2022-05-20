import logging
from typing import List, Optional

from google.auth.transport.requests import AuthorizedSession
from google.cloud.pubsub_v1 import PublisherClient

from . import get_authorized_session
from .proto.file_download_pb2 import FileDownloadMessage
from .proto.notification_pb2 import UserNotificationMessage
from .zipper import Requester

logger = logging.getLogger(__name__)


# pylint: disable=no-member
def publish_file_download_message(
    name: str, email: str, files: List[str], topic_id: str, client: PublisherClient
):
    try:
        # Instantiate a protoc-generated class defined in `us-states.proto`.
        message = FileDownloadMessage()
        message.files.extend(files)
        message.requester.CopyFrom(
            Requester(name=name, email=email).to_proto(FileDownloadMessage.Requester)
        )
        # Encode the data according to the message serialization type.
        msg_data = message.SerializeToString()
        logger.debug("Preparing a binary-encoded message:\n%s", msg_data)

        future = client.publish(topic_id, msg_data)
        logger.info("Published message ID: %s", future.result())
    # pylint: disable=broad-except
    except Exception as e:
        logger.error("Exception occurred while publishing message: %s", str(e))


def send_notification_message(
    name: str,
    email: str,
    output_path: str,
    manifest: List[str],
    url: str,
    session: Optional[AuthorizedSession] = None,
):
    """
    Publishes a message to the topic.
    """
    try:
        # create the ProtoBuf message
        message = UserNotificationMessage()
        message.requester.CopyFrom(
            Requester(name=name, email=email).to_proto(
                UserNotificationMessage.Requester
            )
        )
        message.zipfile = output_path
        message.files.extend(manifest)
        # serialize the message to bytes
        msg_data = message.SerializeToString()

        if session is None:
            session = get_authorized_session(url)
        session.post(
            url=url, data=msg_data, headers={"Content-Type": "application/octet-stream"}
        )

    # pylint: disable=broad-except
    except Exception as e:
        logger.error("Exception occurred while sending message: %s", str(e))
