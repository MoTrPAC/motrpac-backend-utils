#  Copyright (c) 2022. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""
Utility functions for the MoTrPAC backend utility function package. Recursive utilities, if you will.
"""

import os
from hashlib import md5

import google.auth
from google.auth.compute_engine import IDTokenCredentials
from google.auth.transport.requests import AuthorizedSession, Request


def get_env(key: str, default: str = None) -> str:
    """
    Gets an environment variable, or either returns a default value or throws an error
    if it is not set.

    :param key: The name of the environment variable
    :param default: The default value to return if the environment variable is not set
    :raise ValueError: If the specified environment variable cannot be found
    :return: The environment variable
    """
    value = os.getenv(key, default)
    if value is None:
        msg = f"{key} environment variable is missing, please set it"
        raise ValueError(msg)
    return value


def get_authorized_session(
    audience: str,
    max_refresh_attempts: int = 100,
) -> AuthorizedSession:
    """
    Returns a AuthorizedSession (a Request object with the appropriate
    Authorization  headers) for the user to use to make requests to Google services with.

    :param audience: Used when running in compute engine, this is the HTTP endpoint of
    the service being accessed
    :param max_refresh_attempts: The maximum number of times to attempt refreshing the
    credentials
    :return: An AuthorizedSession instance to use to make requests to Google services
    """
    if bool(int(os.getenv("PRODUCTION_DEPLOYMENT", "0"))):
        request = Request()
        credentials = IDTokenCredentials(request=request, target_audience=audience)
    else:
        credentials, _ = google.auth.default()

    return AuthorizedSession(credentials, max_refresh_attempts=max_refresh_attempts)


def generate_file_hash(files: list[str]) -> tuple[list[str], str]:
    """
    Gets the MD5 hash of a list of files, generating the hash by sorting the list of files.

    :param files: The list of file to get the hash of
    :return: The sorted list of files, and the MD5 hash of the file
    """
    # sort the list of files alphabetically (important for consistency/MD5 hashing)
    sorted_files = sorted(files)
    # Creates an MD5 hash of the files to be uploaded, joining the list with a comma
    # separating the files
    md5_hash = md5(
        ",".join(sorted_files).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()

    return sorted_files, md5_hash
