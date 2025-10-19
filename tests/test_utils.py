#  Copyright (c) 2025. Mihir Samdarshi/MoTrPAC Bioinformatics Center

from __future__ import annotations

import hashlib

import pytest
from motrpac_backend_utils.utils import (
    get_env,
    generate_file_hash,
    get_authorized_session,
)
from typing import TYPE_CHECKING

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


@pytest.mark.parametrize(
    "files",
    [
        [],
        ["b.txt"],
        ["b.txt", "a.txt", "c.txt"],
    ],
)
def test_generate_file_hash(files: list[str]) -> None:
    sorted_files, md5_hash = generate_file_hash(files)
    assert sorted_files == sorted(files)
    expected = hashlib.md5(
        ",".join(sorted(files)).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()
    assert md5_hash == expected


def test_get_authorized_session_non_production(
    mocker: MockFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # PRODUCTION_DEPLOYMENT not set or 0
    monkeypatch.setenv("PRODUCTION_DEPLOYMENT", "0")

    fake_creds = object()
    mock_default = mocker.patch(
        "motrpac_backend_utils.utils.google.auth.default",
        return_value=(fake_creds, "proj"),
    )
    mock_authorized_session = mocker.patch(
        "motrpac_backend_utils.utils.AuthorizedSession",
    )

    session = get_authorized_session("https://service")

    mock_default.assert_called_once()
    mock_authorized_session.assert_called_once_with(fake_creds, max_refresh_attempts=100)
    assert session == mock_authorized_session.return_value


def test_get_authorized_session_production(
    mocker: MockFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # PRODUCTION_DEPLOYMENT=1 triggers ID token path
    monkeypatch.setenv("PRODUCTION_DEPLOYMENT", "1")

    mock_request = mocker.patch("motrpac_backend_utils.utils.Request")
    mock_id_token_credentials = mocker.patch(
        "motrpac_backend_utils.utils.IDTokenCredentials",
    )
    mock_authorized_session = mocker.patch(
        "motrpac_backend_utils.utils.AuthorizedSession",
    )

    session = get_authorized_session("https://service")

    mock_request.assert_called_once()
    mock_id_token_credentials.assert_called_once()
    _creds_args, creds_kwargs = mock_id_token_credentials.call_args
    assert "target_audience" in creds_kwargs
    assert creds_kwargs["target_audience"] == "https://service"
    mock_authorized_session.assert_called_once_with(
        mock_id_token_credentials.return_value,
        max_refresh_attempts=100,
    )
    assert session == mock_authorized_session.return_value
