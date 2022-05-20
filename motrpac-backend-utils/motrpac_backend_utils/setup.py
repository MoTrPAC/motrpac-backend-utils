import logging

from google.cloud.logging import Client as LoggingClient
from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.cloud_trace_propagator import CloudTraceFormatPropagator
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from constants import IS_PROD


def setup_logging_and_tracing(log_level=logging.INFO):
    # setup local logging/Google Cloud Logging
    # setup local logging/Google Cloud Logging
    log_format = "{levelname} {asctime} {name}:{funcName}:{lineno} {message}"
    logging.basicConfig(
        style="{", format=log_format, datefmt="%I:%M:%S %p", level=log_level
    )
    if IS_PROD:
        client = LoggingClient()
        client.setup_logging(log_level=log_level)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
        logging.getLogger("urllib3.util.retry").setLevel(logging.WARNING)
    else:
        logging.basicConfig(level=log_level)

    # setup tracing/Google Cloud Tracing if we are in production
    tracer_provider = TracerProvider()
    trace.set_tracer_provider(tracer_provider)
    RequestsInstrumentor().instrument()
    if IS_PROD:
        trace_exporter = CloudTraceSpanExporter()
        trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(trace_exporter))
        set_global_textmap(CloudTraceFormatPropagator())
