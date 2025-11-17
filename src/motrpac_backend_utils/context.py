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
import functools
import inspect
import logging
import os
import sys
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

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

    Checks multiple header formats used by different Google Cloud services:
    - Function-Execution-Id (Functions Framework, Cloud Functions Gen 2)
    - function-execution-id (lowercase variant)
    - X-Execution-Id (custom header)
    - X-Cloud-Trace-Context (can be used as fallback - extracts span_id)

    The execution ID is used to correlate logs from a single request across
    different services and components.

    Note: When using X-Cloud-Trace-Context as a fallback, the span_id is extracted
    and used as the execution ID. This provides granular tracing at the span level,
    which can be useful for correlating logs with specific operations within a request.

    :param headers: Request headers (dict-like object or werkzeug Headers)
    :return: Execution ID if found, None otherwise
    """
    # Try Functions Framework header format first (most common)
    exec_id = headers.get("Function-Execution-Id")
    if exec_id:
        return exec_id

    # Try lowercase variant (some proxies lowercase headers)
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

    For Google Cloud Logging's StructuredLogHandler, this filter adds
    execution_id to the json_fields, which ensures it's properly indexed
    and searchable in Google Cloud Logging.

    For other handlers, it adds execution_id as a record attribute.

    This is compatible with:
    - Cloud Run
    - Cloud Functions
    - Functions Framework
    - FastAPI
    - Flask
    - Any other framework using standard Python logging

    Usage:
        import logging
        from google.cloud.logging_v2.handlers import StructuredLogHandler
        from motrpac_backend_utils.context import ExecutionIdFilter

        handler = StructuredLogHandler()
        handler.addFilter(ExecutionIdFilter())
        logging.root.addHandler(handler)

    The execution_id will be available in Google Cloud Logging and can be
    used to filter and correlate logs from a single request.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Add execution_id to the log record for structured logging."""
        exec_id = get_execution_id()

        # For StructuredLogHandler, add to json_fields
        if not hasattr(record, "json_fields"):
            record.json_fields = {}
        elif not isinstance(record.json_fields, dict):
            # Safety check - ensure it's a dict
            record.json_fields = {}

        if exec_id:
            record.json_fields["execution_id"] = exec_id
            record.execution_id = exec_id
        else:
            # Provide a default to prevent format string errors
            record.execution_id = "-"

        return True


def add_fastapi_execution_context(app) -> None:  # noqa: ANN001
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


def add_flask_execution_context(app) -> None:  # noqa: ANN001
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


P = ParamSpec("P")
T = TypeVar("T")


def functions_framework_execution_context(func: Callable[[P], T]) -> Callable[[P], T]:  # noqa: C901
    """
    Decorator to extract and set execution context for Functions Framework functions.

    This decorator should be applied to Functions Framework function handlers to ensure
    execution IDs and other context are properly captured from request headers and
    propagated to logging and tracing systems.

    Works with all Functions Framework signature types:
    - HTTP functions: @functions_framework.http
    - CloudEvent functions: @functions_framework.cloud_event
    - Background event functions: (data, context signature)

    Usage with HTTP functions:
        import functions_framework
        from motrpac_backend_utils.context import functions_framework_execution_context

        @functions_framework.http
        @functions_framework_execution_context
        def my_function(request):
            import logging
            logging.info("This log will have execution_id")
            return "OK"

    Usage with CloudEvent functions:
        import functions_framework
        from motrpac_backend_utils.context import functions_framework_execution_context
        from cloudevents.http import CloudEvent

        @functions_framework.cloud_event
        @functions_framework_execution_context
        def my_function(cloud_event: CloudEvent):
            import logging
            logging.info("CloudEvent received", extra={"event_id": cloud_event["id"]})

    The execution ID will be automatically added to all log entries and will be
    searchable in Google Cloud Logging.

    :param func: The Functions Framework function to wrap
    :return: Wrapped function with execution context management
    """
    # Check if this is an async function
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Extract execution ID from request
            # For HTTP functions, first arg is request
            # For CloudEvent functions, we can access flask.request
            exec_id = None

            if args and hasattr(args[0], "headers"):
                # HTTP function or similar
                exec_id = extract_execution_id_from_headers(args[0].headers)
            else:
                # Try flask request context (works for CloudEvent functions too)
                try:
                    from flask import request  # noqa: PLC0415

                    if request:
                        exec_id = extract_execution_id_from_headers(request.headers)
                except (ImportError, RuntimeError):
                    # No flask context available
                    pass

            if exec_id:
                token = set_execution_id(exec_id)
                try:
                    return await func(*args, **kwargs)
                finally:
                    clear_execution_id(token)
            else:
                return await func(*args, **kwargs)

        return async_wrapper

    @functools.wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        # Extract execution ID from request
        exec_id = None

        if args and hasattr(args[0], "headers"):
            # HTTP function or similar
            exec_id = extract_execution_id_from_headers(args[0].headers)
        else:
            # Try flask request context (works for CloudEvent functions too)
            try:
                from flask import request  # noqa: PLC0415

                if request:
                    exec_id = extract_execution_id_from_headers(request.headers)
            except (ImportError, RuntimeError):
                # No flask context available
                pass

        if exec_id:
            token = set_execution_id(exec_id)
            try:
                return func(*args, **kwargs)
            finally:
                clear_execution_id(token)
        else:
            return func(*args, **kwargs)

    return sync_wrapper
