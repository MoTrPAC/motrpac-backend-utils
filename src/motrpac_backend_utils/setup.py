#  Copyright (c) 2024. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""A utility module for setting up logging and tracing."""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING

from google.cloud.logging import Client as LoggingClient
from google.cloud.logging_v2.handlers import StructuredLogHandler
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
    Setup logging and tracing for the application.

    This function configures both structured logging and OpenTelemetry tracing for
    production environments. It works seamlessly with Cloud Run, Cloud Functions,
    Functions Framework, FastAPI, Flask, and other web frameworks.

    Logging Behavior:
    - Production (PRODUCTION_DEPLOYMENT=1):
        * Cloud Run/Functions/Functions Framework: Uses StructuredLogHandler with stdout
          (structured JSON logs ingested by Google Cloud Logging agent)
        * Other environments: Uses Cloud Logging API handler
        * Adds ExecutionIdFilter to inject execution_id into log records
        * Forces override of any existing handlers (including Functions Framework's)
    - Development: Uses local text-based logging with timestamp and context

    Tracing Behavior:
    - Always sets up OpenTelemetry tracing
    - Integrates with Cloud Trace in production
    - Instruments urllib3, threading, and logging
    - Uses Cloud Trace propagator for distributed tracing

    Functions Framework Integration:
    - Disables Functions Framework's built-in logging (LOG_EXECUTION_ID)
    - Uses our own structured logging with ExecutionIdFilter
    - Requires @functions_framework_execution_context decorator on function handlers
    - Provides consistent logging format across all frameworks

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
    # Always setup tracing
    setup_tracing(is_prod=is_prod, resource_attributes=resource_attributes)

    # Always setup logging, even with Functions Framework
    # This gives us full control over structured logging format
    if is_prod:
        from motrpac_backend_utils.context import (  # noqa: PLC0415
            ExecutionIdFilter,
            is_functions_framework_active,
        )

        client = LoggingClient()

        # For Cloud Run and Cloud Functions, write structured JSON to stdout
        # The Google Cloud Logging agent ingests these automatically
        is_cloud_run = bool(os.getenv("K_SERVICE"))
        is_cloud_functions = bool(os.getenv("FUNCTION_TARGET"))

        if is_cloud_run or is_cloud_functions or is_functions_framework_active():
            # Use stdout for environments with logging agents
            handler = StructuredLogHandler(stream=sys.stdout)
            logger_msg = "Cloud Run/Functions: Using StructuredLogHandler with stdout"
        else:
            # For other environments (GCE, GKE, local with credentials), use API
            handler = client.get_default_handler()
            logger_msg = "Production: Using Cloud Logging API handler"

        # Add execution ID filter to inject execution context into logs
        handler.addFilter(ExecutionIdFilter())

        # Configure logging - force=True overrides any existing handlers (including FF's)
        logging.basicConfig(
            handlers=[handler],
            level=log_level,
            force=True,
        )

        # Reduce noise from verbose libraries
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
        logging.getLogger("urllib3.util.retry").setLevel(logging.WARNING)

        logger = logging.getLogger(__name__)
        logger.debug(logger_msg)
    else:
        # Development: Use simple text logging
        log_format = "%(levelname)s %(asctime)s %(name)s:%(funcName)s:%(lineno)s %(message)s"
        logging.basicConfig(
            format=log_format,
            datefmt="%I:%M:%S %p",
            level=log_level,
        )
        logger = logging.getLogger(__name__)
        logger.debug("Development: Setting up local logging")


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
    # Start with a base resource with the service name and service version, which the
    # Google Cloud Resource Detector doesn't detect.
    if os.getenv("K_SERVICE") and os.getenv("K_REVISION"):
        base_resource = Resource.create(
            attributes={
                "service.name": os.getenv("K_SERVICE", "unknown"),
                "service.version": os.getenv("K_REVISION", "unknown"),
            },
        )
    else:
        base_resource = Resource.create({})
    # Use the official Google Cloud resource detector
    # This automatically detects Cloud Run, GCE, GKE, Cloud Functions, etc.
    gcp_detector = GoogleCloudResourceDetector(raise_on_error=False)
    detected_resource = get_aggregated_resources([gcp_detector], initial_resource=base_resource)

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
    LoggingInstrumentor().instrument(set_logging_format=False)
    if is_prod:
        trace_exporter = CloudTraceSpanExporter()
        tracer_provider.add_span_processor(
            BatchSpanProcessor(trace_exporter),
        )
        set_global_textmap(CloudTraceFormatPropagator())
