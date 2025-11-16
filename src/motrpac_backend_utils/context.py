#  Copyright (c) 2024. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""
Execution context and logging integration utilities.

Provides:
- Detection of Functions Framework environment
- Execution ID context management (compatible with Functions Framework)
- Optional middleware for FastAPI/Flask execution context tracking
- Logging filters for adding execution context to log records
"""

from __future__ import annotations

import contextvars
import logging
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from werkzeug.datastructures.headers import Headers


# Context variable for execution ID (compatible with Functions Framework's pattern)
_execution_id_var = contextvars.ContextVar[str | None]("execution_id", default=None)


def is_functions_framework_active() -> bool:
    """
    Detect if Functions Framework is managing logging.

    Returns True if:
    - Functions Framework's execution ID logging is enabled (LOG_EXECUTION_ID)
    - Running in Cloud Functions (FUNCTION_TARGET is set)
    - Functions Framework module is imported and has configured logging

    This is used to prevent duplicate log handlers when Functions Framework
    is already managing logging configuration.

    :return: True if Functions Framework is managing logging, False otherwise
    """
    # Check if FF's execution ID logging is enabled
    # Based on distutils.util.strtobool (same as FF uses)
    truthy_values = ("y", "yes", "t", "true", "on", "1")
    if os.getenv("LOG_EXECUTION_ID") in truthy_values:
        return True

    # Check if running under Cloud Functions
    if os.getenv("FUNCTION_TARGET"):
        return True

    # Check if FF is imported and has configured logging
    if "functions_framework" in sys.modules:
        try:
            from functions_framework.execution_id import (  # noqa: PLC0415
                LoggingHandlerAddExecutionId,
            )

            # Check if FF's handler is already registered
            root_logger = logging.getLogger()
            for handler in root_logger.handlers:
                # Check if this handler's stream is FF's logging handler
                if hasattr(handler, "stream") and isinstance(
                    handler.stream,
                    LoggingHandlerAddExecutionId,
                ):
                    return True
        except (ImportError, AttributeError):
            # FF not available or doesn't have expected structure
            pass

    return False


def get_execution_id() -> str | None:
    """
    Get current execution ID from context.

    First checks our context variable, then falls back to Functions Framework's
    execution context if available. This allows reading execution IDs whether
    they were set by Functions Framework or by our own middleware.

    :return: Execution ID string if available, None otherwise
    """
    # Try our context variable first
    exec_id = _execution_id_var.get()
    if exec_id:
        return exec_id

    # Try Functions Framework's context if available
    try:
        from functions_framework.execution_id import execution_context_var  # noqa: PLC0415

        context = execution_context_var.get()
        if context and context.execution_id:
            return context.execution_id
    except ImportError:
        # Functions Framework not installed
        pass

    return None


def set_execution_id(execution_id: str) -> contextvars.Token:
    """
    Set execution ID for the current context.

    This is used by middleware to propagate execution IDs from request headers
    into the context for the duration of request processing.

    :param execution_id: The execution ID to set
    :return: A token that can be used to reset the context later
    """
    return _execution_id_var.set(execution_id)


def clear_execution_id(token: contextvars.Token) -> None:
    """
    Clear execution ID from context using the provided token.

    This should be called in a finally block or teardown handler to ensure
    the context is properly cleaned up after request processing.

    :param token: The token returned by set_execution_id()
    """
    _execution_id_var.reset(token)


def extract_execution_id_from_headers(headers: Mapping[str, str] | Headers) -> str | None:
    """
    Extract execution ID from request headers.

    Checks multiple header formats:
    - Function-Execution-Id (Functions Framework format)
    - function-execution-id (lowercase variant)
    - X-Execution-Id (custom header)

    :param headers: Request headers (dict-like object)
    :return: Execution ID if found, None otherwise
    """
    # Try Functions Framework header format first
    exec_id = headers.get("Function-Execution-Id")
    if exec_id:
        return exec_id

    # Try lowercase variant
    exec_id = headers.get("function-execution-id")
    if exec_id:
        return exec_id

    # Try custom header
    exec_id = headers.get("X-Execution-Id")
    if exec_id:
        return exec_id

    return None


class ExecutionIdFilter(logging.Filter):
    """
    Logging filter that adds execution_id to log records.

    This is OPTIONAL and only needed if you're using FastAPI/Flask and want
    execution IDs to appear in your log records. Functions Framework already
    handles this automatically.

    Usage:
        import logging
        from motrpac_backend_utils.context import ExecutionIdFilter

        handler = logging.StreamHandler()
        handler.addFilter(ExecutionIdFilter())
        logging.root.addHandler(handler)

    The execution_id will be available as record.execution_id and can be
    included in your log format string:

        formatter = logging.Formatter(
            '%(levelname)s [%(execution_id)s] %(message)s'
        )
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Add execution_id attribute to the log record if available."""
        exec_id = get_execution_id()
        if exec_id:
            record.execution_id = exec_id
        else:
            # Provide a default to prevent format string errors
            record.execution_id = "-"
        return True


def add_fastapi_execution_context(app) -> None:
    """
    Add execution context middleware to a FastAPI app.

    This is OPTIONAL - only use if you want execution ID tracking in FastAPI
    similar to what Functions Framework provides automatically.

    The middleware will extract execution IDs from request headers and
    propagate them through the request context, making them available via
    get_execution_id().

    Example:
        from motrpac_backend_utils.setup import setup_logging_and_tracing
        from motrpac_backend_utils.context import add_fastapi_execution_context
        from fastapi import FastAPI

        setup_logging_and_tracing()

        app = FastAPI()
        add_fastapi_execution_context(app)  # OPTIONAL

        @app.get("/")
        def read_root():
            from motrpac_backend_utils.context import get_execution_id
            exec_id = get_execution_id()
            return {"execution_id": exec_id}

    :param app: FastAPI application instance
    """  # noqa: D413
    from starlette.middleware.base import BaseHTTPMiddleware  # noqa: PLC0415

    if TYPE_CHECKING:
        from collections.abc import Awaitable  # noqa: PLC0415

        from starlette.requests import Request  # noqa: PLC0415
        from starlette.responses import Response  # noqa: PLC0415

    class ExecutionContextMiddleware(BaseHTTPMiddleware):
        """Middleware to propagate execution IDs from request headers."""

        async def dispatch(
            self,
            request: Request,
            call_next: Callable[[Request], Awaitable[Response]],
        ) -> Response:
            execution_id = extract_execution_id_from_headers(request.headers)

            if execution_id:
                token = set_execution_id(execution_id)
                try:
                    return await call_next(request)
                finally:
                    clear_execution_id(token)
            else:
                return await call_next(request)

    app.add_middleware(ExecutionContextMiddleware)


def add_flask_execution_context(app) -> None:
    """
    Add execution context hooks to a Flask app.

    This is OPTIONAL - only use if you want execution ID tracking in Flask
    similar to what Functions Framework provides automatically.

    The hooks will extract execution IDs from request headers and propagate
    them through the request context, making them available via get_execution_id().

    Example:
        from motrpac_backend_utils.setup import setup_logging_and_tracing
        from motrpac_backend_utils.context import add_flask_execution_context
        from flask import Flask

        setup_logging_and_tracing()

        app = Flask(__name__)
        add_flask_execution_context(app)  # OPTIONAL

        @app.route("/")
        def hello():
            from motrpac_backend_utils.context import get_execution_id
            exec_id = get_execution_id()
            return f"Execution ID: {exec_id}"

    :param app: Flask application instance
    """  # noqa: D413
    from flask import g, request  # noqa: PLC0415

    @app.before_request
    def _set_execution_context() -> None:
        """Extract and set execution ID before request processing."""
        execution_id = extract_execution_id_from_headers(request.headers)
        if execution_id:
            g.execution_id_token = set_execution_id(execution_id)

    @app.teardown_request
    def _clear_execution_context(exception: Exception | None = None) -> None:  # noqa: ARG001
        """Clear execution ID after request processing."""
        token = g.pop("execution_id_token", None)
        if token:
            clear_execution_id(token)
