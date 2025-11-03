#  Copyright (c) 2024. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""Utility functions for the MoTrPAC backend utility function package."""

import os

from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2 import id_token


def get_env(key: str, default: str | None = None) -> str:
    """
    Gets an environment variable, return a default value, or raise an error if no default.

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
    Returns a AuthorizedSession for the user to use to make requests to Google services with.

    AuthorizedSession is a Request object with the appropriate Authorization headers.

    :param audience: Used when running in compute engine, this is the HTTP endpoint of
    the service being accessed
    :param max_refresh_attempts: The maximum number of times to attempt refreshing the
    credentials
    :return: An AuthorizedSession instance to use to make requests to Google services
    """
    request = Request()
    credentials = id_token.fetch_id_token_credentials(audience, request)
    credentials.refresh(request)

    return AuthorizedSession(credentials, max_refresh_attempts=max_refresh_attempts)
