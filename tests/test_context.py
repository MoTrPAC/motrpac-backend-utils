#  Copyright (c) 2024. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""Tests for execution context and Functions Framework integration."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import TYPE_CHECKING
from unittest import mock

import pytest

import motrpac_backend_utils.context as context_module
from motrpac_backend_utils.context import (
    ExecutionIdFilter,
    add_fastapi_execution_context,
    add_flask_execution_context,
    clear_execution_id,
    extract_execution_id_from_headers,
    get_execution_id,
    is_functions_framework_active,
    set_execution_id,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

TRUTHY_EXECUTION_VALUES = ("true", "1", "yes", "on")
FALSY_EXECUTION_VALUES = ("false", "0")


@pytest.fixture(autouse=True)
def clear_functions_framework_env(monkeypatch) -> None:
    for var in ("LOG_EXECUTION_ID", "FUNCTION_TARGET"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def log_record() -> Callable[[str], logging.LogRecord]:
    def _make(name: str = "test") -> logging.LogRecord:
        return logging.LogRecord(
            name=name,
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )

    return _make


@pytest.mark.parametrize("value", TRUTHY_EXECUTION_VALUES)
def test_is_functions_framework_active_detects_truthy_log_execution_id(
    monkeypatch, value
) -> None:
    monkeypatch.setenv("LOG_EXECUTION_ID", value)
    assert is_functions_framework_active() is True


def test_is_functions_framework_active_detects_function_target(monkeypatch) -> None:
    monkeypatch.setenv("FUNCTION_TARGET", "my_function")
    assert is_functions_framework_active() is True


@pytest.mark.parametrize("value", FALSY_EXECUTION_VALUES)
def test_is_functions_framework_inactive_for_falsey_log_execution_id(
    monkeypatch, value
) -> None:
    monkeypatch.setenv("LOG_EXECUTION_ID", value)
    assert is_functions_framework_active() is False


def test_is_functions_framework_inactive_without_indicators() -> None:
    assert is_functions_framework_active() is False


def test_is_functions_framework_active_detects_registered_handler(monkeypatch) -> None:
    class MockLoggingHandlerAddExecutionId:
        pass

    handler = mock.Mock()
    handler.stream = MockLoggingHandlerAddExecutionId()

    ff_execution_module = mock.Mock()
    ff_execution_module.LoggingHandlerAddExecutionId = MockLoggingHandlerAddExecutionId
    ff_module = mock.Mock()
    ff_module.execution_id = ff_execution_module

    mock_logger = mock.Mock()
    mock_logger.handlers = [handler]

    monkeypatch.setitem(sys.modules, "functions_framework", ff_module)
    monkeypatch.setitem(sys.modules, "functions_framework.execution_id", ff_execution_module)
    monkeypatch.setattr(
        "motrpac_backend_utils.context.logging.getLogger",
        mock.Mock(return_value=mock_logger),
    )

    assert is_functions_framework_active() is True


def test_set_and_get_execution_id() -> None:
    token = set_execution_id("test-exec-id-123")
    try:
        assert get_execution_id() == "test-exec-id-123"
    finally:
        clear_execution_id(token)


def test_clear_execution_id() -> None:
    token = set_execution_id("test-exec-id-456")
    assert get_execution_id() == "test-exec-id-456"
    clear_execution_id(token)
    assert get_execution_id() is None


def test_get_execution_id_returns_none_when_not_set() -> None:
    assert get_execution_id() is None


def test_execution_id_isolated_across_contexts() -> None:
    async def task(name: str) -> str | None:
        token = set_execution_id(name)
        await asyncio.sleep(0.01)
        result = get_execution_id()
        clear_execution_id(token)
        return result

    async def run_tasks() -> tuple[str | None, str | None]:
        return await asyncio.gather(task("task1-id"), task("task2-id"))

    results = asyncio.run(run_tasks())
    assert "task1-id" in results
    assert "task2-id" in results


def test_get_execution_id_falls_back_to_ff_context(monkeypatch) -> None:
    mock_context = mock.Mock(execution_id="ff-exec-id-789")
    mock_context_var = mock.Mock()
    mock_context_var.get.return_value = mock_context

    ff_execution_module = mock.Mock()
    ff_execution_module.execution_context_var = mock_context_var
    monkeypatch.setitem(sys.modules, "functions_framework", mock.Mock())
    monkeypatch.setitem(sys.modules, "functions_framework.execution_id", ff_execution_module)

    monkeypatch.setattr(
        context_module,
        "_execution_id_var",
        mock.Mock(get=mock.Mock(return_value=None)),
    )

    assert get_execution_id() == "ff-exec-id-789"


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Function-Execution-Id": "header-id-123"}, "header-id-123"),
        ({"function-execution-id": "header-id-456"}, "header-id-456"),
        ({"X-Execution-Id": "header-id-789"}, "header-id-789"),
        (
            {
                "Function-Execution-Id": "ff-header-id",
                "function-execution-id": "lowercase-id",
                "X-Execution-Id": "custom-id",
            },
            "ff-header-id",
        ),
        ({"Content-Type": "application/json"}, None),
        ({}, None),
    ],
)
def test_extract_execution_id_from_headers(
    headers: Mapping[str, str], expected: str | None
) -> None:
    assert extract_execution_id_from_headers(headers) == expected


def test_execution_id_filter_adds_execution_id_to_record(
    log_record: Callable[[], logging.LogRecord],
) -> None:
    token = set_execution_id("filter-test-id")
    try:
        record = log_record()
        log_filter = ExecutionIdFilter()
        assert log_filter.filter(record) is True
        assert record.execution_id == "filter-test-id"
    finally:
        clear_execution_id(token)


def test_execution_id_filter_adds_default_when_missing(
    log_record: Callable[[], logging.LogRecord],
) -> None:
    record = log_record()
    log_filter = ExecutionIdFilter()
    assert log_filter.filter(record) is True
    assert record.execution_id == "-"


def test_execution_id_filter_can_be_used_with_handler(
    log_record: Callable[[str], logging.LogRecord],
) -> None:
    token = set_execution_id("handler-test-id")
    handler = logging.StreamHandler()
    handler.addFilter(ExecutionIdFilter())
    try:
        record = log_record("test_filter_logger")
        handler.filter(record)
        assert record.execution_id == "handler-test-id"
    finally:
        clear_execution_id(token)


def test_fastapi_middleware_can_be_imported() -> None:
    assert callable(add_fastapi_execution_context)


def test_flask_hooks_can_be_imported() -> None:
    assert callable(add_flask_execution_context)
