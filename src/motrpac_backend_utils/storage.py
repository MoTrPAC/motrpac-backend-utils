#  Copyright (c) 2025. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""Abstractions/utilities for common interaction patterns with Google Cloud Storage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from requests.adapters import HTTPAdapter

if TYPE_CHECKING:
    from google.cloud.storage import Client as StorageClient


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
