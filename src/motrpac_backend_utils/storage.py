#  Copyright (c) 2025. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""Abstractions/utilities for common interaction patterns with Google Cloud Storage."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from requests.adapters import HTTPAdapter

if TYPE_CHECKING:
    from google.cloud.storage import Client as StorageClient


class GcsPath(NamedTuple):
    """Represents a GCS path."""

    bucket: str
    key: str


def parse_bucket_path(path: str) -> GcsPath:
    """
    Split a full GCS path in bucket and key strings. `'gs://bucket/key'` -> `('bucket', 'key')`.

    :param path: GCS path (e.g., gs://bucket/key).
    :return: Tuple of bucket and key strings
    :raises ValueError: If the path is not a valid GCS path.
    """
    gcs_prefix = "gs://"

    if not path.startswith(gcs_prefix):
        msg = f"'{path}' is not a valid path. It MUST start with 'gs://'"
        raise ValueError(msg)

    parts = path.replace(gcs_prefix, "").split("/", 1)

    bucket: str = parts[0]
    if not bucket:
        msg = "Empty bucket name received"
        raise ValueError(msg)
    if "/" in bucket or bucket == " ":
        msg = f"'{bucket}' is not a valid bucket name."
        raise ValueError(msg)

    key: str = ""
    if len(parts) == 2:  # noqa: PLR2004
        key = key if parts[1] is None else parts[1]

    return GcsPath(bucket, key)


def modify_storage_client_adapters(
    storage_client: StorageClient,
    pool_connections: int = 128,
    max_retries: int = 3,
    *,
    pool_block: bool = True,
) -> StorageClient:
    """
    Returns a modified google.cloud.storage.Client object.

    Due to many concurrent GCS connections, the default connection pool can become
    overwhelmed, introducing delays.

    Solution described in https://github.com/googleapis/python-storage/issues/253.
    This code is adapted from https://github.com/google/osv.dev/pull/3248.

    These affect the urllib3.HTTPConnectionPool underpinning the storage.Client's
    HTTP requests.

    :param storage_client: An existing google.cloud.storage.Client object.
    :param pool_connections: Number of pool_connections desired.
    :param max_retries: Maximum retries.
    :param pool_block: Whether to block when the pool is exhausted

    :returns: The google.cloud.storage.Client appropriately modified.
    """
    adapter = HTTPAdapter(
        pool_connections=pool_connections, max_retries=max_retries, pool_block=pool_block
    )
    storage_client._http.mount("https://", adapter)  # noqa: SLF001
    storage_client._http._auth_request.session.mount("https://", adapter)  # noqa: SLF001
    return storage_client
