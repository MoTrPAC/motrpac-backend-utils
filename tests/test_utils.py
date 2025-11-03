#  Copyright (c) 2025. Mihir Samdarshi/MoTrPAC Bioinformatics Center

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from motrpac_backend_utils.utils import get_authorized_session, get_env

if TYPE_CHECKING:
    from pytest_mock import MockFixture


@pytest.mark.parametrize(
    ("env_key", "env_val", "default", "expected"),
    [
        ("SOME_KEY", "value", None, "value"),
        ("ANOTHER_KEY", None, "fallback", "fallback"),
    ],
)
def test_get_env_with_and_without_default(
    env_key: str,
    env_val: str | None,
    default: str | None,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Ensure a clean environment state for the key first
    monkeypatch.delenv(env_key, raising=False)
    if env_val is not None:
        monkeypatch.setenv(env_key, env_val)

    assert get_env(env_key, default) == expected


def test_get_env_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    key = "MISSING_KEY_FOR_TEST"
    monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="environment variable is missing"):
        get_env(key)


def test_get_authorized_session(
    mocker: MockFixture,
) -> None:
    # Mock the Request object
    mock_request = mocker.patch("motrpac_backend_utils.utils.Request")
    mock_request_instance = mock_request.return_value

    # Mock the credentials returned by fetch_id_token_credentials
    fake_creds = mocker.MagicMock()
    mock_fetch_credentials = mocker.patch(
        "motrpac_backend_utils.utils.id_token.fetch_id_token_credentials",
        return_value=fake_creds,
    )

    # Mock AuthorizedSession
    mock_authorized_session = mocker.patch(
        "motrpac_backend_utils.utils.AuthorizedSession",
    )

    audience = "https://service.example.com"
    session = get_authorized_session(audience)

    # Verify Request was instantiated
    mock_request.assert_called_once()

    # Verify fetch_id_token_credentials was called with the audience and request
    mock_fetch_credentials.assert_called_once_with(audience, mock_request_instance)

    # Verify credentials.refresh was called
    fake_creds.refresh.assert_called_once_with(mock_request_instance)

    # Verify AuthorizedSession was created with the credentials
    mock_authorized_session.assert_called_once_with(fake_creds, max_refresh_attempts=100)

    # Verify the session is returned
    assert session == mock_authorized_session.return_value


def test_get_authorized_session_custom_refresh_attempts(
    mocker: MockFixture,
) -> None:
    # Test with custom max_refresh_attempts parameter
    mocker.patch("motrpac_backend_utils.utils.Request")

    fake_creds = mocker.MagicMock()
    mocker.patch(
        "motrpac_backend_utils.utils.id_token.fetch_id_token_credentials",
        return_value=fake_creds,
    )

    mock_authorized_session = mocker.patch(
        "motrpac_backend_utils.utils.AuthorizedSession",
    )

    session = get_authorized_session("https://service", max_refresh_attempts=50)

    # Verify AuthorizedSession was created with custom max_refresh_attempts
    mock_authorized_session.assert_called_once_with(fake_creds, max_refresh_attempts=50)
    assert session == mock_authorized_session.return_value
