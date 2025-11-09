#  Copyright (c) 2024. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""A utility module for setting up logging and tracing."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from google.cloud.logging import Client as LoggingClient
from google.cloud.logging_v2.handlers import setup_logging
from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.threading import ThreadingInstrumentor
from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.cloud_trace_propagator import CloudTraceFormatPropagator
from opentelemetry.resourcedetector.gcp_resource_detector import GoogleCloudResourceDetector
from opentelemetry.sdk.resources import Resource, get_aggregated_resources
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if TYPE_CHECKING:
    from collections.abc import Mapping

IS_PROD = bool(int(os.getenv("PRODUCTION_DEPLOYMENT", "0")))


def setup_logging_and_tracing(
    log_level: int = logging.INFO,
    *,
    is_prod: bool = IS_PROD,
    resource_attributes: Mapping[str, str | bool | int | float] | None = None,
) -> None:
    """
    Setup local logging/Google Cloud Logging and tracing.

    It reads an environment variable called `PRODUCTION_DEPLOYMENT` to determine whether to
    send logs and traces to the Google Cloud Logging and Google Cloud Tracing services.
    This can be a boolean value, or a string that can be 0 or 1. Do not use when running Google
    Cloud's Functions Framework, since that sets up its own logging, resulting in duplicate
    logs. Instead, in production, use the `LOG_EXECUTION_ID` environment variable to
    set the execution id for the function, and use `setup_tracing()` to set up tracing.

    When running on Google Cloud Platform (GCP), the function automatically detects the
    environment using the official GoogleCloudResourceDetector and populates the Resource
    with service name, version, region, and other metadata. This works for Cloud Run,
    GCE, GKE, Cloud Functions, and other GCP environments.
    You can override or extend these attributes using the `resource_attributes` parameter.

    See: https://google-cloud-opentelemetry.readthedocs.io/en/latest/examples/cloud_resource_detector/README.html

    :param log_level: The log level to use. Defaults to logging.INFO
    :param is_prod: Whether to set up logging and tracing for production. Defaults to
        the value of the `PRODUCTION_DEPLOYMENT` environment variable, which defaults
        to False if not set to "1".
    :param resource_attributes: Optional dictionary of resource attributes to override
        or extend the auto-detected GCP attributes. These will be merged with detected
        attributes, with explicitly provided values taking precedence.
    """
    # setup tracing/Google Cloud Tracing if we are in production
    setup_tracing(is_prod=is_prod, resource_attributes=resource_attributes)

    if is_prod:
        client = LoggingClient()
        handler = client.get_default_handler()
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


def setup_tracing(
    *,
    is_prod: bool = IS_PROD,
    resource_attributes: Mapping[str, str | bool | int | float] | None = None,
) -> None:
    """
    Set up only tracing for the application.

    When running on Google Cloud Platform (GCP), automatically detects the environment
    using the official GoogleCloudResourceDetector and populates the Resource with
    service metadata. This works for Cloud Run, GCE, GKE, Cloud Functions, and other
    GCP environments. Custom resource attributes can be provided to override or extend
    the auto-detected attributes.

    See: https://google-cloud-opentelemetry.readthedocs.io/en/latest/examples/cloud_resource_detector/README.html

    :param is_prod: Whether to set up tracing for production. Defaults to
        the value of the `PRODUCTION_DEPLOYMENT` environment variable.
    :param resource_attributes: Optional dictionary of resource attributes to override
        or extend the auto-detected GCP attributes. These will be merged with detected
        attributes, with explicitly provided values taking precedence.
    """
    # Use the official Google Cloud resource detector
    # This automatically detects Cloud Run, GCE, GKE, Cloud Functions, etc.
    gcp_detector = GoogleCloudResourceDetector(raise_on_error=False)
    detected_resource = get_aggregated_resources([gcp_detector])

    # Merge with custom resource attributes if provided
    if resource_attributes:
        custom_resource = Resource.create(resource_attributes)
        # Custom attributes take precedence over detected ones
        resource = detected_resource.merge(custom_resource)
    else:
        resource = detected_resource

    # Create tracer provider with the resource
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)
    URLLib3Instrumentor().instrument()
    ThreadingInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=is_prod)
    if is_prod:
        trace_exporter = CloudTraceSpanExporter()
        tracer_provider.add_span_processor(
            BatchSpanProcessor(trace_exporter),
        )
        set_global_textmap(CloudTraceFormatPropagator())
