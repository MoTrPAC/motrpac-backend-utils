"""Tests for Functions Framework execution context integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest

from motrpac_backend_utils.context import (
    ExecutionIdFilter,
    extract_execution_id_from_headers,
    functions_framework_execution_context,
    get_execution_id,
)

if TYPE_CHECKING:
    from flask.wrappers import Request


def test_extract_execution_id_from_function_execution_id_header() -> None:
    """Test extraction from Function-Execution-Id header."""
    headers = {"Function-Execution-Id": "test-exec-123"}
    exec_id = extract_execution_id_from_headers(headers)
    assert exec_id == "test-exec-123"


def test_extract_execution_id_from_lowercase_header() -> None:
    """Test extraction from lowercase function-execution-id header."""
    headers = {"function-execution-id": "test-exec-456"}
    exec_id = extract_execution_id_from_headers(headers)
    assert exec_id == "test-exec-456"


def test_extract_execution_id_from_custom_header() -> None:
    """Test extraction from custom X-Execution-Id header."""
    headers = {"X-Execution-Id": "custom-exec-789"}
    exec_id = extract_execution_id_from_headers(headers)
    assert exec_id == "custom-exec-789"


def test_extract_execution_id_priority() -> None:
    """Test that Function-Execution-Id takes priority over trace context."""
    headers = {
        "Function-Execution-Id": "explicit-exec-id",
        "X-Cloud-Trace-Context": "trace123/span456;o=1",
    }
    exec_id = extract_execution_id_from_headers(headers)
    assert exec_id == "explicit-exec-id"


def test_extract_execution_id_no_headers() -> None:
    """Test that None is returned when no execution ID headers are present."""
    headers = {}
    exec_id = extract_execution_id_from_headers(headers)
    assert exec_id is None


def test_extract_execution_id_malformed_trace_context() -> None:
    """Test that malformed trace context is handled gracefully."""
    headers = {"X-Cloud-Trace-Context": "invalid"}
    exec_id = extract_execution_id_from_headers(headers)
    assert exec_id is None


def test_functions_framework_decorator_http() -> None:
    """Test decorator with HTTP function."""
    request_mock = Mock()
    request_mock.headers = {"Function-Execution-Id": "http-exec-123"}

    @functions_framework_execution_context
    def http_function(request: Request) -> str | None:
        # Execution ID should be set during function execution
        return get_execution_id()

    result = http_function(request_mock)
    assert result == "http-exec-123"

    # Execution ID should be cleared after function execution
    assert get_execution_id() is None


def test_functions_framework_decorator_no_execution_id() -> None:
    """Test decorator when no execution ID is present in headers."""
    request_mock = Mock()
    request_mock.headers = {}

    @functions_framework_execution_context
    def http_function(request: Request) -> str | None:
        return get_execution_id()

    result = http_function(request_mock)
    assert result is None


def test_functions_framework_decorator_cleanup_on_exception() -> None:
    """Test that execution context is cleaned up even on exception."""
    request_mock = Mock()
    request_mock.headers = {"Function-Execution-Id": "error-exec-123"}

    @functions_framework_execution_context
    def failing_function(request: Request) -> str | None:
        assert get_execution_id() == "error-exec-123"
        msg = "Test error"
        raise ValueError(msg)

    with pytest.raises(ValueError, match="Test error"):
        failing_function(request_mock)

    # Execution ID should still be cleared after exception
    assert get_execution_id() is None


def test_execution_id_filter_with_json_fields() -> None:
    """Test ExecutionIdFilter adds to json_fields for StructuredLogHandler."""
    with patch("motrpac_backend_utils.context.get_execution_id", return_value="filter-exec-123"):
        log_filter = ExecutionIdFilter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = log_filter.filter(record)

        assert result is True
        assert record.execution_id == "filter-exec-123"
        assert hasattr(record, "json_fields")
        assert record.json_fields["execution_id"] == "filter-exec-123"


def test_execution_id_filter_without_execution_id() -> None:
    """Test ExecutionIdFilter handles missing execution ID gracefully."""
    with patch("motrpac_backend_utils.context.get_execution_id", return_value=None):
        log_filter = ExecutionIdFilter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = log_filter.filter(record)

        assert result is True
        assert record.execution_id == "-"
        assert hasattr(record, "json_fields")
        # json_fields should not have execution_id when it's None
        assert "execution_id" not in record.json_fields


def test_execution_id_filter_preserves_existing_json_fields() -> None:
    """Test that ExecutionIdFilter preserves existing json_fields."""
    with patch("motrpac_backend_utils.context.get_execution_id", return_value="exec-456"):
        log_filter = ExecutionIdFilter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        # Pre-populate json_fields
        record.json_fields = {"custom_field": "custom_value"}

        result = log_filter.filter(record)

        assert result is True
        assert record.json_fields["execution_id"] == "exec-456"
        assert record.json_fields["custom_field"] == "custom_value"


def test_execution_id_filter_handles_non_dict_json_fields() -> None:
    """Test that ExecutionIdFilter handles non-dict json_fields gracefully."""
    with patch("motrpac_backend_utils.context.get_execution_id", return_value="exec-789"):
        log_filter = ExecutionIdFilter()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        # Set json_fields to a non-dict value
        record.json_fields = "not a dict"

        result = log_filter.filter(record)

        assert result is True
        # Should have replaced the non-dict with a dict
        assert isinstance(record.json_fields, dict)
        assert record.json_fields["execution_id"] == "exec-789"
