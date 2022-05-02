import logging
import os
from hashlib import md5
from typing import List, Tuple

from google.pubsub_v1 import PublisherClient

import pubsub_pb2

logger = logging.getLogger()
publisher_client = PublisherClient()


def parse_bucket_path(path: str) -> Tuple[str, str]:
    """
    Split a full GCS path in bucket and key strings.
    'gs://bucket/key' -> ('bucket', 'key')

    :param path: GCS path (e.g. gs://bucket/key).
    :return: Tuple of bucket and key strings
    """
    if path.startswith("gs://") is True:
        parts = path.replace("gs://", "").split("/", 1)
    else:
        raise ValueError(f"{path} is not a valid path. It MUST start with 'gs://'")

    bucket: str = parts[0]

    if bucket == "":
        raise ValueError("Empty bucket name received")
    if "/" in bucket or bucket == " ":
        raise ValueError(f"'{bucket}' is not a valid bucket name.")

    key: str = ""
    if len(parts) == 2:
        key = key if parts[1] is None else parts[1]

    return bucket, key


def generate_file_hash(files: List[str]):
    """
    Gets the MD5 hash of a list of files, generating the hash by sorting the list of files

    :param files: The list of file to get the hash of
    :return: The sorted list of files, and the MD5 hash of the file
    """
    # sort the list of files alphabetically (important for consistency/MD5 hashing)
    sorted_files = sorted(files)
    # Creates an MD5 hash of the files to be uploaded, joining the list with a comma
    # separating the files
    md5_hash = md5(",".join(sorted_files).encode("utf-8")).hexdigest()

    return sorted_files, md5_hash


def get_env(key: str) -> str:
    """
    Gets an environment variable, or throws an error if it is not set

    :param key: The name of the environment variable
    :raise ValueError: If the specified environment variable cannot be found
    :return: The environment variable
    """
    value = os.getenv(key)
    if value is None:
        raise ValueError(f"{key} environment variable is missing, please set it")
    return value


def publish_message(requester: str, files: List[str], metadata: dict):
    try:
        # Instantiate a protoc-generated class defined in `us-states.proto`.
        message = pubsub_pb2.FileDownloadMessage()
        message.files = files
        message.metadata = metadata
        message.requester = requester

        # Encode the data according to the message serialization type.
        data = message.SerializeToString()
        print(f"Preparing a binary-encoded message:\n{data}")

        future = publisher_client.publish(TOPIC_ID, data)
        print(f"Published message ID: {future.result()}")

    except Exception as e:
        logger.error(f"Exception occurred while publishing message: {e}")
