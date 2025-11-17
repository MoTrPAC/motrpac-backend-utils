"""Integration tests for Functions Framework with Cloud Logging."""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest

from motrpac_backend_utils.context import (
    ExecutionIdFilter,
    functions_framework_execution_context,
    get_execution_id,
    is_functions_framework_active,
    set_execution_id,
)
from motrpac_backend_utils.setup import setup_logging_and_tracing

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def mock_functions_framework_env() -> Generator[None, None, None]:
    """Set up environment to simulate Functions Framework."""
    with patch.dict(os.environ, {"FUNCTION_TARGET": "test_function"}, clear=False):
        yield


@pytest.fixture
def mock_production_env() -> Generator[None, None, None]:
    """Set up production environment."""
    with patch.dict(os.environ, {"PRODUCTION_DEPLOYMENT": "1"}, clear=False):
        yield


def test_is_functions_framework_active_with_function_target(
    mock_functions_framework_env: Generator[None, None, None],  # noqa: ARG001
) -> None:
    """Test detection with FUNCTION_TARGET set."""
    assert is_functions_framework_active() is True


def test_is_functions_framework_active_without_env() -> None:
    """Test detection without Functions Framework env vars."""
    # Clear FF-related env vars - use empty strings, not None
    env_vars = {
        "FUNCTION_TARGET": "",
        "LOG_EXECUTION_ID": "",
    }
    # Also ensure FF is not imported
    with (
        patch.dict(os.environ, env_vars, clear=False),
        patch.dict("sys.modules", {"functions_framework": None}),
    ):
        assert is_functions_framework_active() is False


def test_is_functions_framework_active_with_log_execution_id() -> None:
    """Test detection with LOG_EXECUTION_ID set."""
    env_vars = {
        "LOG_EXECUTION_ID": "1",
        "FUNCTION_TARGET": "",
    }
    with patch.dict(os.environ, env_vars, clear=False):
        assert is_functions_framework_active() is True


def test_structured_logging_setup_with_functions_framework(
    mock_functions_framework_env: Generator[None, None, None],  # noqa: ARG001
    mock_production_env: Generator[None, None, None],  # noqa: ARG001
) -> None:
    """Test that structured logging is configured for Functions Framework."""
    # Reset logging configuration
    logging.root.handlers = []

    # Mock the Cloud Logging client and tracing components
    with (
        patch("motrpac_backend_utils.setup.LoggingClient"),
        patch("motrpac_backend_utils.setup.StructuredLogHandler") as mock_handler_class,
        patch("motrpac_backend_utils.setup.CloudTraceSpanExporter"),
    ):
        mock_handler = Mock()
        mock_handler.level = logging.INFO  # Set real level to avoid comparison issues
        mock_handler_class.return_value = mock_handler

        # Setup logging
        setup_logging_and_tracing(log_level=logging.INFO, is_prod=True)

        # Verify StructuredLogHandler was created with stdout
        mock_handler_class.assert_called_once()
        call_kwargs = mock_handler_class.call_args.kwargs
        assert "stream" in call_kwargs

        # Verify ExecutionIdFilter was added
        mock_handler.addFilter.assert_called_once()
        filter_arg = mock_handler.addFilter.call_args.args[0]
        assert isinstance(filter_arg, ExecutionIdFilter)


def test_structured_logging_output_format() -> None:
    """Test that logs are output as structured JSON when using StructuredLogHandler."""
    # Create a mock output stream
    output = StringIO()

    # Create a structured log handler that writes to our mock stream
    # Don't patch LoggingClient, just import directly
    from google.cloud.logging_v2.handlers import StructuredLogHandler  # noqa: PLC0415

    handler = StructuredLogHandler(stream=output)
    handler.setLevel(logging.INFO)  # Set actual log level
    handler.addFilter(ExecutionIdFilter())

    # Configure logger - use a test logger to avoid interference from root logger
    logger = logging.getLogger("test_logger_unique")
    logger.handlers = []
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # Don't propagate to root logger

    # Mock execution context
    with patch("motrpac_backend_utils.context.get_execution_id", return_value="test-exec-123"):
        logger.info("Test log message", extra={"custom_field": "custom_value"})

    # Get the output - may have multiple JSON objects on separate lines
    output_value = output.getvalue().strip()

    # Parse the JSON logs (newline-delimited JSON)
    if output_value:
        log_lines = [line for line in output_value.split("\n") if line.strip()]
        # Get the first log entry (our test log)
        log_entry = json.loads(log_lines[0])

        # Verify structured log format - verify severity and execution_id are present
        # The exact field names may vary based on StructuredLogHandler version
        assert "severity" in log_entry
        assert log_entry["severity"] == "INFO"

        # execution_id should be in the log (most important for our use case)
        assert "execution_id" in log_entry or (
            "jsonPayload" in log_entry and "execution_id" in log_entry["jsonPayload"]
        )

        # Should be valid JSON (which we just parsed)
        assert isinstance(log_entry, dict)


def test_execution_context_with_http_function() -> None:
    """Test execution context extraction with HTTP function."""
    request_mock = Mock()
    request_mock.headers = {"Function-Execution-Id": "integration-http-123"}

    @functions_framework_execution_context
    def http_function(request) -> str:
        # Create a logger and log a message
        logger = logging.getLogger("test_http_function")

        # Create a log record
        record = logging.LogRecord(
            name="test_http_function",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="HTTP function invoked",
            args=(),
            exc_info=None,
        )

        # Apply ExecutionIdFilter
        filter_instance = ExecutionIdFilter()
        filter_instance.filter(record)

        # Verify execution_id is in the record
        assert record.execution_id == "integration-http-123"
        assert record.json_fields["execution_id"] == "integration-http-123"

        return "OK"

    result = http_function(request_mock)
    assert result == "OK"


def test_execution_context_with_cloud_event_function() -> None:
    """Test execution context extraction with CloudEvent function."""
    # Manually set the execution ID since flask context mocking is complex
    from motrpac_backend_utils.context import (  # noqa: PLC0415
        clear_execution_id,
        set_execution_id,
    )

    token = set_execution_id("integration-ce-456")
    try:
        # Now test within the execution context
        logger = logging.getLogger("test_cloud_event_function")

        # Create a log record
        record = logging.LogRecord(
            name="test_cloud_event_function",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="CloudEvent function invoked",
            args=(),
            exc_info=None,
        )

        # Apply ExecutionIdFilter
        filter_instance = ExecutionIdFilter()
        filter_instance.filter(record)

        # Verify execution_id is in the record
        assert record.execution_id == "integration-ce-456"
        assert record.json_fields["execution_id"] == "integration-ce-456"
    finally:
        clear_execution_id(token)


def test_concurrent_execution_contexts() -> None:
    """Test that execution contexts don't mix between concurrent requests."""

    def process_request(exec_id: str) -> str:
        """Simulate processing a request with an execution ID."""
        token = set_execution_id(exec_id)
        try:
            # Simulate some work
            import time  # noqa: PLC0415

            time.sleep(0.01)
            return get_execution_id() or ""
        finally:
            from motrpac_backend_utils.context import clear_execution_id  # noqa: PLC0415

            clear_execution_id(token)

    # Run multiple requests concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        exec_ids = [f"exec-{i}" for i in range(10)]
        results = list(executor.map(process_request, exec_ids))

    # Verify each request got its own execution ID
    assert results == exec_ids


def test_logging_setup_without_functions_framework(
    mock_production_env: Generator[None, None, None],  # noqa: ARG001
) -> None:
    """Test logging setup in production without Functions Framework."""
    # Clear FF env vars AND K_SERVICE to ensure API-based handler is used
    with patch.dict(
        os.environ,
        {"FUNCTION_TARGET": "", "K_SERVICE": "", "LOG_EXECUTION_ID": ""},
        clear=False,
    ):
        # Reset logging
        logging.root.handlers = []

        # Mock the Cloud Logging client and tracing components
        with (
            patch("motrpac_backend_utils.setup.LoggingClient") as mock_client,
            patch("motrpac_backend_utils.setup.StructuredLogHandler"),
            patch("motrpac_backend_utils.setup.CloudTraceSpanExporter"),
        ):
            mock_client_instance = Mock()
            mock_client.return_value = mock_client_instance
            mock_default_handler = Mock()
            mock_default_handler.level = logging.INFO  # Set real level to avoid comparison issues
            mock_client_instance.get_default_handler.return_value = mock_default_handler

            # Setup logging
            setup_logging_and_tracing(log_level=logging.INFO, is_prod=True)

            # Should use get_default_handler (API-based) instead of stdout
            mock_client_instance.get_default_handler.assert_called_once()


def test_logging_setup_development_mode() -> None:
    """Test logging setup in development mode."""
    # Reset logging
    logging.root.handlers = []

    # Setup logging in development mode
    setup_logging_and_tracing(log_level=logging.DEBUG, is_prod=False)

    # Verify local logging is configured
    assert len(logging.root.handlers) > 0

    # Log a message
    logger = logging.getLogger("test_dev_logger")
    logger.info("Development log message")

    # Should not raise an exception


def test_execution_id_filter_integration() -> None:
    """Test ExecutionIdFilter works end-to-end."""
    from motrpac_backend_utils.context import (  # noqa: PLC0415
        get_execution_id,
        set_execution_id,
    )

    # Set execution ID
    token = set_execution_id("integration-filter-123")

    try:
        # Create a logger with ExecutionIdFilter
        logger = logging.getLogger("test_filter_integration")
        logger.handlers = []

        handler = logging.StreamHandler()
        handler.addFilter(ExecutionIdFilter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Log a message
        logger.info("Test message with execution ID")

        # Verify execution ID is accessible
        assert get_execution_id() == "integration-filter-123"

    finally:
        from motrpac_backend_utils.context import clear_execution_id  # noqa: PLC0415

        clear_execution_id(token)

    # Verify cleanup
    assert get_execution_id() is None


def test_functions_framework_detection_methods() -> None:
    """Test all methods of detecting Functions Framework."""
    # Test with LOG_EXECUTION_ID
    with patch.dict(os.environ, {"LOG_EXECUTION_ID": "true"}, clear=False):
        assert is_functions_framework_active() is True

    with patch.dict(os.environ, {"LOG_EXECUTION_ID": "1"}, clear=False):
        assert is_functions_framework_active() is True

    with patch.dict(os.environ, {"LOG_EXECUTION_ID": "yes"}, clear=False):
        assert is_functions_framework_active() is True

    # Test with FUNCTION_TARGET
    with patch.dict(
        os.environ, {"LOG_EXECUTION_ID": "", "FUNCTION_TARGET": "my_func"}, clear=False
    ):
        assert is_functions_framework_active() is True

    # Test with neither set
    with (
        patch.dict(os.environ, {"LOG_EXECUTION_ID": "", "FUNCTION_TARGET": ""}, clear=False),
        patch.dict("sys.modules", {"functions_framework": None}),
    ):
        assert is_functions_framework_active() is False
