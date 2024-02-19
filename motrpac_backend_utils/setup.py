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
from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.cloud_trace_propagator import CloudTraceFormatPropagator
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .flask_logger import FlaskCloudTraceIDFilter


IS_PROD = bool(int(os.getenv("PRODUCTION_DEPLOYMENT", "0")))


def setup_logging_and_tracing(
    log_level: int = logging.INFO, is_prod: bool = IS_PROD,
) -> None:
    """
    Setup local logging/Google Cloud Logging and tracing. It reads an environment
    variable called `PRODUCTION_DEPLOYMENT` to determine whether to send logs and
    traces to the Google Cloud Logging and Google Cloud Tracing services. This can be
    a boolean value, or a string that can be 0 or 1.

    :param log_level: The log level to use. Defaults to logging.INFO
    :param is_prod: Whether to set up logging and tracing for production. Defaults to
        the value of the `PRODUCTION_DEPLOYMENT` environment variable, which defaults
        to False if not set to "1".
    """
    if is_prod:
        client = LoggingClient()
        handler = client.get_default_handler()
        handler.addFilter(FlaskCloudTraceIDFilter())
        setup_logging(handler, log_level=log_level)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
        logging.getLogger("urllib3.util.retry").setLevel(logging.WARNING)
    else:
        log_format = "%(levelname) %(asctime)s %(name):%(funcName):%(lineno) %(message)"
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
    if is_prod:
        trace_exporter = CloudTraceSpanExporter()
        trace.get_tracer_provider().add_span_processor(
            BatchSpanProcessor(trace_exporter),
        )
        set_global_textmap(CloudTraceFormatPropagator())
