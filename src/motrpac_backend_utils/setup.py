#  Copyright (c) 2024. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""
A utility module for setting up logging and tracing.
"""
import logging
import os

from google.cloud.logging import Client as LoggingClient
from google.cloud.logging_v2.handlers import setup_logging
from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.threading import ThreadingInstrumentor
from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.cloud_trace_propagator import CloudTraceFormatPropagator
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

IS_PROD = bool(int(os.getenv("PRODUCTION_DEPLOYMENT", "0")))


def get_hexadecimal_trace_id(trace_id: int) -> str:
    """
    Get the hexadecimal representation of the trace id.

    :param trace_id: The trace id to convert
    :return: The trace id in hexadecimal format
    """
    return format(trace_id, "032x")


def get_hexadecimal_span_id(span_id: int) -> str:
    """
    Get the hexadecimal representation of the span id.

    :param span_id: The span id to convert
    :return: The span id in hexadecimal format
    """
    return format(span_id, "016x")


class TraceIdInjectionFilter(logging.Filter):
    """
    Outputs JSON format to Stdout so Google Cloud Logging can consume and link logs to requests
     and traces.
    """

    def __init__(self) -> None:
        """
        Initialize handler.
        """
        super().__init__()

    def format(self, record: logging.LogRecord) -> bool:
        """
        Add OpenTelemetry span and trace info to the log.

        :param record: The log record to format
        :return: a JSON formatted string
        """
        current_span = trace.get_current_span()
        if current_span:
            trace_id = current_span.get_span_context().trace_id
            span_id = current_span.get_span_context().span_id
            record.trace = get_hexadecimal_trace_id(trace_id)
            record.span = get_hexadecimal_span_id(span_id)

        return True


def setup_logging_and_tracing(
        log_level: int = logging.INFO,
        *,
        is_prod: bool = IS_PROD,
) -> None:
    """
    Setup local logging/Google Cloud Logging and tracing. It reads an environment
    variable called `PRODUCTION_DEPLOYMENT` to determine whether to send logs and
    traces to the Google Cloud Logging and Google Cloud Tracing services. This can be
    a boolean value, or a string that can be 0 or 1. Do not use when running Google
    Cloud's Functions Framework, since that sets up its own logging, resulting in duplicate
    logs. Instead, in production, use the `LOG_EXECUTION_ID` environment variable to
    set the execution id for the function, and use `setup_tracing()` to set up tracing.

    :param log_level: The log level to use. Defaults to logging.INFO
    :param is_prod: Whether to set up logging and tracing for production. Defaults to
        the value of the `PRODUCTION_DEPLOYMENT` environment variable, which defaults
        to False if not set to "1".
    """
    if is_prod:
        client = LoggingClient()
        handler = client.get_default_handler()
        handler.filters = [TraceIdInjectionFilter(), *handler.filters]
        setup_logging(handler, log_level=log_level)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
        logging.getLogger("urllib3.util.retry").setLevel(logging.WARNING)
    else:
        log_format = "%(levelname)s %(asctime)s %(name)s:%(funcName)s:%(lineno)s %(message)s"
        logging.basicConfig(
            format=log_format,
            datefmt="%I:%M:%S %p",
            level=log_level,
        )

    # setup tracing/Google Cloud Tracing if we are in production
    tracer_provider = TracerProvider()
    trace.set_tracer_provider(tracer_provider)
    RequestsInstrumentor().instrument()
    URLLib3Instrumentor().instrument()
    ThreadingInstrumentor().instrument()
    if is_prod:
        trace_exporter = CloudTraceSpanExporter()
        trace.get_tracer_provider().add_span_processor(
            BatchSpanProcessor(trace_exporter),
        )
        set_global_textmap(CloudTraceFormatPropagator())


def setup_tracing(*, is_prod: bool = IS_PROD) -> None:
    """
    Set up only tracing for the application.
    """
    tracer_provider = TracerProvider()
    trace.set_tracer_provider(tracer_provider)
    RequestsInstrumentor().instrument()
    URLLib3Instrumentor().instrument()
    if is_prod:
        trace_exporter = CloudTraceSpanExporter()
        trace.get_tracer_provider().add_span_processor(
            BatchSpanProcessor(trace_exporter),
        )
        set_global_textmap(CloudTraceFormatPropagator())
