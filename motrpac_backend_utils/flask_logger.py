#  Copyright (c) 2024. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""
Flask extension to parse or generate the id of each request.
"""
import logging
from collections.abc import Callable
from typing import Any

import flask
from flask import request, g, current_app, Flask

logger = logging.getLogger(__name__)


class ExecutedOutsideContextError(Exception):
    """
    Exception to be raised if a fetcher was called outside its context.
    """


class MultiContextRequestIdFetcher:
    """
    A callable that can fetch request id from different context as Flask, Celery etc.
    """

    def __init__(self) -> None:
        """
        Initialize all the context fetchers.
        """
        self.ctx_fetchers: list[Callable[..., Any]] = []

    def __call__(self) -> Any | None:
        """
        Fetch something from the current context.

        :return: The id or None if not found.
        """
        for ctx_fetcher in self.ctx_fetchers:
            try:
                return ctx_fetcher()
            except ExecutedOutsideContextError:
                continue
        return None

    def register_fetcher(self, ctx_fetcher: Callable[..., Any]) -> None:
        """
        Register another context-specialized fetcher.

        :param ctx_fetcher: A callable that will return the id or raise
            ExecutedOutsideContextError if it was executed outside its context.
        """
        if ctx_fetcher not in self.ctx_fetchers:
            self.ctx_fetchers.append(ctx_fetcher)


def generic_http_header_parser_for(header_name: str) -> Callable[[], str | None]:
    """
    A parser factory to extract the request id from an HTTP header.

    :param header_name: The name of the header to extract the id from.
    :return: A parser that can be used to extract the request id from the current request context
    :rtype: ()->str|None.
    """

    def parser() -> str | None:
        request_id = request.headers.get(header_name, "").strip()

        if not request_id:
            # If the request id is empty return None
            return None
        return request_id

    return parser


def x_cloud_trace_id() -> str | None:
    """
    Parser for generic X-Request-ID header.

    :rtype: str|None.
    """
    return generic_http_header_parser_for("X-Cloud-Trace-Context")()


def flask_ctx_get_request_id() -> str | None:
    """
    Get request id from flask's G object.

    :return: The id or None if not found.
    """
    # from flask import _app_ctx_stack as stack  # We do not support < Flask 0.9
    if hasattr(flask, "globals") and hasattr(flask.globals, "request_ctx"):
        # update session for Flask >= 2.2
        ctx = flask.globals.request_ctx._get_current_object()
    else:  # pragma: no cover
        # update session for Flask < 2.2
        ctx = flask._request_ctx_stack.top

    if ctx is None:
        raise ExecutedOutsideContextError()

    g_object_attr = ctx.app.config["LOG_REQUEST_ID_G_OBJECT_ATTRIBUTE"]
    return g.get(g_object_attr, None)


current_request_id = MultiContextRequestIdFetcher()
current_request_id.register_fetcher(flask_ctx_get_request_id)


class RequestID:
    """
    Flask extension to parse or generate the id of each request.
    """

    def __init__(self, app: Flask = None) -> None:
        """
        Initialize extension
        :param flask.Application | None app: The flask application or None if you want to initialize later
        the default auto_parser() will be used that will try all known parsers.
        """
        self.app = app
        self._request_id = None

        self._request_id_parser = x_cloud_trace_id

        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        """
        Initialize the extension with a Flask application.

        :param app: The Flask application.
        :return: None
        """
        # Default configuration
        app.config.setdefault("LOG_REQUEST_ID_GENERATE_IF_NOT_FOUND", True)
        app.config.setdefault("LOG_REQUEST_ID_G_OBJECT_ATTRIBUTE", "log_request_id")

        # Register before request callback
        @app.before_request
        def _persist_request_id() -> None:
            """
            It will parse and persist the RequestID from the HTTP request. If not
            found it will generate a new one if requestsed.
            To be used as a consumer of Flask.before_request event.
            """
            g_object_attr = current_app.config["LOG_REQUEST_ID_G_OBJECT_ATTRIBUTE"]

            setattr(g, g_object_attr, self._request_id_parser())


class FlaskCloudTraceIDFilter(logging.Filter):
    """
    Log filter to inject the current request id of the request under `log_record.request_id`.
    """

    def filter(self, log_record: logging.LogRecord) -> logging.LogRecord:
        """
        Although filters are supposed to be used to determine whether to log or not,
        we are using it to inject the request id in the log record.
        :param log_record: The log record to inject the request id into.
        :return: The log record with the request id injected.
        """
        log_record.request_id = current_request_id()
        return log_record
