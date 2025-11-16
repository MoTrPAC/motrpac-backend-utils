#  Copyright (c) 2024. Mihir Samdarshi/MoTrPAC Bioinformatics Center
"""Integration tests for setup_logging_and_tracing with Functions Framework."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from motrpac_backend_utils.setup import setup_logging_and_tracing, setup_tracing

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

NOISY_LOGGERS = [
    "requests",
    "urllib3.connectionpool",
    "urllib3.util.retry",
]


@pytest.fixture(autouse=True)
def clear_functions_framework_env(monkeypatch) -> None:
    """Ensure FF detection env vars are unset before each test."""
    for var in ("LOG_EXECUTION_ID", "FUNCTION_TARGET"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def root_logger() -> Generator[logging.Logger, None, None]:
    """Reset the root logger to avoid leaking handlers across tests."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    root.handlers.clear()
    yield root
    root.handlers.clear()
    root.setLevel(original_level)
    for handler in original_handlers:
        root.addHandler(handler)


@pytest.fixture
def reset_noisy_loggers() -> Generator[None, None, None]:
    """Restore noisy logger levels and handlers after each test."""
    originals = {name: logging.getLogger(name).level for name in NOISY_LOGGERS}
    for name in NOISY_LOGGERS:
        logging.getLogger(name).handlers.clear()
    yield
    for name, level in originals.items():
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.handlers.clear()


@pytest.fixture
def mock_setup_tracing(monkeypatch) -> mock.Mock:
    """Stub out setup_tracing to avoid real instrumentation."""
    mocked = mock.Mock()
    monkeypatch.setattr("motrpac_backend_utils.setup.setup_tracing", mocked)
    return mocked


@pytest.mark.parametrize(
    ("env_key", "env_value"),
    [("LOG_EXECUTION_ID", "1"), ("FUNCTION_TARGET", "my_function")],
)
def test_setup_logging_defers_to_functions_framework(
    env_key: str,
    env_value: str,
    mock_setup_tracing: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
    root_logger: logging.Logger,
) -> None:
    monkeypatch.setenv(env_key, env_value)
    logging_client = mock.Mock()
    setup_logging_mock = mock.Mock()
    monkeypatch.setattr("motrpac_backend_utils.setup.LoggingClient", logging_client)
    monkeypatch.setattr("motrpac_backend_utils.setup.setup_logging", setup_logging_mock)
    initial_handlers = list(root_logger.handlers)

    setup_logging_and_tracing(is_prod=True)

    logging_client.assert_not_called()
    setup_logging_mock.assert_not_called()
    assert list(root_logger.handlers) == initial_handlers
    mock_setup_tracing.assert_called_once_with(is_prod=True, resource_attributes=None)


def test_setup_logging_configures_cloud_logging_when_ff_inactive(
    mock_setup_tracing: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_instance = mock.Mock()
    handler = mock.Mock()
    logging_client = mock.Mock(return_value=client_instance)
    client_instance.get_default_handler.return_value = handler
    setup_logging_mock = mock.Mock()
    monkeypatch.setattr("motrpac_backend_utils.setup.LoggingClient", logging_client)
    monkeypatch.setattr("motrpac_backend_utils.setup.setup_logging", setup_logging_mock)

    setup_logging_and_tracing(is_prod=True)

    logging_client.assert_called_once_with()
    client_instance.get_default_handler.assert_called_once_with()
    setup_logging_mock.assert_called_once_with(handler, log_level=logging.INFO)
    mock_setup_tracing.assert_called_once_with(is_prod=True, resource_attributes=None)


@pytest.mark.parametrize("is_prod", [True, False])
def test_setup_logging_and_tracing_invokes_tracing(
    is_prod: bool,
    mock_setup_tracing: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOG_EXECUTION_ID", "1")

    setup_logging_and_tracing(is_prod=is_prod)

    mock_setup_tracing.assert_called_once_with(is_prod=is_prod, resource_attributes=None)


def test_setup_logging_logs_debug_message_when_ff_detected(
    mock_setup_tracing: mock.Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOG_EXECUTION_ID", "1")
    logger = mock.Mock()
    real_get_logger = logging.getLogger

    def fake_get_logger(name: str | None = None) -> logging.Logger:
        if name == "motrpac_backend_utils.setup":
            return logger
        return real_get_logger(name)

    monkeypatch.setattr("motrpac_backend_utils.setup.logging.getLogger", fake_get_logger)

    setup_logging_and_tracing(is_prod=True)

    logger.debug.assert_called_once_with(
        "Functions Framework detected, deferring to its logging configuration",
    )


def test_setup_logging_respects_custom_log_level(
    mock_setup_tracing: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    client_instance = mock.Mock()
    handler = mock.Mock()
    logging_client = mock.Mock(return_value=client_instance)
    client_instance.get_default_handler.return_value = handler
    setup_logging_mock = mock.Mock()
    monkeypatch.setattr("motrpac_backend_utils.setup.LoggingClient", logging_client)
    monkeypatch.setattr("motrpac_backend_utils.setup.setup_logging", setup_logging_mock)

    setup_logging_and_tracing(log_level=logging.DEBUG, is_prod=True)

    assert setup_logging_mock.call_args.kwargs["log_level"] == logging.DEBUG
    mock_setup_tracing.assert_called_once_with(is_prod=True, resource_attributes=None)


def test_adjusts_noisy_library_loggers_when_ff_active(
    monkeypatch: pytest.MonkeyPatch,
    mock_setup_tracing: mock.Mock,
    reset_noisy_loggers: Generator[None, None, None],
) -> None:
    monkeypatch.setenv("LOG_EXECUTION_ID", "1")
    for name in NOISY_LOGGERS:
        logger = logging.getLogger(name)
        logger.setLevel(logging.NOTSET)
        logger.handlers.clear()

    setup_logging_and_tracing(is_prod=True)

    for name in NOISY_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING


def test_adjusts_noisy_library_loggers_when_ff_inactive(
    monkeypatch: pytest.MonkeyPatch,
    mock_setup_tracing: mock.Mock,
    reset_noisy_loggers: Generator[None, None, None],
) -> None:
    client_instance = mock.Mock()
    handler = mock.Mock()
    logging_client = mock.Mock(return_value=client_instance)
    client_instance.get_default_handler.return_value = handler
    setup_logging_mock = mock.Mock()
    monkeypatch.setattr("motrpac_backend_utils.setup.LoggingClient", logging_client)
    monkeypatch.setattr("motrpac_backend_utils.setup.setup_logging", setup_logging_mock)

    for name in NOISY_LOGGERS:
        logger = logging.getLogger(name)
        logger.setLevel(logging.NOTSET)
        logger.handlers.clear()

    setup_logging_and_tracing(is_prod=True)

    for name in NOISY_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING


@pytest.mark.parametrize(
    "env",
    [
        {
            "FUNCTION_TARGET": "my_function",
            "LOG_EXECUTION_ID": "true",
            "GOOGLE_CLOUD_PROJECT": "my-project",
            "K_SERVICE": "my-function",
            "K_REVISION": "my-function-001",
        },
        {
            "LOG_EXECUTION_ID": "1",
            "GOOGLE_CLOUD_PROJECT": "my-project",
            "K_SERVICE": "my-service",
            "K_REVISION": "my-service-001",
        },
    ],
)
def test_functions_framework_scenarios_defer_logging(
    env: Mapping[str, str], monkeypatch: pytest.MonkeyPatch, mock_setup_tracing: mock.Mock
) -> None:
    logging_client = mock.Mock()
    monkeypatch.setattr("motrpac_backend_utils.setup.LoggingClient", logging_client)

    for key, value in env.items():
        monkeypatch.setenv(key, value)

    setup_logging_and_tracing(is_prod=True)

    logging_client.assert_not_called()


def test_cloud_run_fastapi_scenario_sets_up_logging(monkeypatch, mock_setup_tracing):
    env = {
        "GOOGLE_CLOUD_PROJECT": "my-project",
        "K_SERVICE": "my-service",
        "K_REVISION": "my-service-001",
        "PRODUCTION_DEPLOYMENT": "1",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    client_instance = mock.Mock()
    handler = mock.Mock()
    logging_client = mock.Mock(return_value=client_instance)
    client_instance.get_default_handler.return_value = handler
    setup_logging_mock = mock.Mock()
    monkeypatch.setattr("motrpac_backend_utils.setup.LoggingClient", logging_client)
    monkeypatch.setattr("motrpac_backend_utils.setup.setup_logging", setup_logging_mock)

    setup_logging_and_tracing(is_prod=True)

    logging_client.assert_called_once_with()
    setup_logging_mock.assert_called_once_with(handler, log_level=logging.INFO)


def test_local_development_scenario_uses_basic_config(mock_setup_tracing, monkeypatch):
    mock_basic_config = mock.Mock()
    monkeypatch.setattr(
        "motrpac_backend_utils.setup.logging.basicConfig",
        mock_basic_config,
    )

    setup_logging_and_tracing(is_prod=False)

    mock_basic_config.assert_called_once()
    kwargs = mock_basic_config.call_args.kwargs
    assert kwargs["level"] == logging.INFO
    assert "format" in kwargs
    assert "datefmt" in kwargs


def test_local_development_with_functions_framework_skips_basic_config(
    mock_setup_tracing,
    monkeypatch,
):
    monkeypatch.setenv("FUNCTION_TARGET", "my_function")
    mock_basic_config = mock.Mock()
    monkeypatch.setattr(
        "motrpac_backend_utils.setup.logging.basicConfig",
        mock_basic_config,
    )

    setup_logging_and_tracing(is_prod=False)

    mock_basic_config.assert_not_called()


@pytest.mark.parametrize("is_prod", [True, False])
def test_setup_tracing_configures_tracer_provider(monkeypatch, is_prod):
    base_resource = mock.Mock(name="base_resource")
    custom_resource = mock.Mock(name="custom_resource")
    detected_resource = mock.Mock(name="detected_resource")
    merged_resource = mock.Mock(name="merged_resource")

    resource_create = mock.Mock(side_effect=[base_resource, custom_resource])
    monkeypatch.setattr("motrpac_backend_utils.setup.Resource.create", resource_create)

    detector_instance = mock.Mock(name="detector")
    detector_cls = mock.Mock(return_value=detector_instance)
    monkeypatch.setattr(
        "motrpac_backend_utils.setup.GoogleCloudResourceDetector",
        detector_cls,
    )

    aggregated_resources = mock.Mock(return_value=detected_resource)
    monkeypatch.setattr(
        "motrpac_backend_utils.setup.get_aggregated_resources",
        aggregated_resources,
    )
    detected_resource.merge.return_value = merged_resource

    tracer_provider = mock.Mock()
    tracer_provider_cls = mock.Mock(return_value=tracer_provider)
    monkeypatch.setattr("motrpac_backend_utils.setup.TracerProvider", tracer_provider_cls)

    trace_module = mock.Mock()
    monkeypatch.setattr("motrpac_backend_utils.setup.trace", trace_module)

    url_instrumentor = mock.Mock()
    threading_instrumentor = mock.Mock()
    logging_instrumentor = mock.Mock()
    monkeypatch.setattr(
        "motrpac_backend_utils.setup.URLLib3Instrumentor",
        mock.Mock(return_value=url_instrumentor),
    )
    monkeypatch.setattr(
        "motrpac_backend_utils.setup.ThreadingInstrumentor",
        mock.Mock(return_value=threading_instrumentor),
    )
    monkeypatch.setattr(
        "motrpac_backend_utils.setup.LoggingInstrumentor",
        mock.Mock(return_value=logging_instrumentor),
    )

    exporter = mock.Mock()
    cloud_trace_exporter = mock.Mock(return_value=exporter)
    monkeypatch.setattr(
        "motrpac_backend_utils.setup.CloudTraceSpanExporter",
        cloud_trace_exporter,
    )

    propagator = mock.Mock()
    propagator_cls = mock.Mock(return_value=propagator)
    monkeypatch.setattr(
        "motrpac_backend_utils.setup.CloudTraceFormatPropagator",
        propagator_cls,
    )

    batch_processor = mock.Mock()
    batch_processor_cls = mock.Mock(return_value=batch_processor)
    monkeypatch.setattr(
        "motrpac_backend_utils.setup.BatchSpanProcessor",
        batch_processor_cls,
    )

    set_textmap = mock.Mock()
    monkeypatch.setattr("motrpac_backend_utils.setup.set_global_textmap", set_textmap)

    resource_attributes = {"service.namespace": "omics"}
    setup_tracing(is_prod=is_prod, resource_attributes=resource_attributes)

    resource_create.assert_has_calls(
        [
            mock.call({}),
            mock.call(resource_attributes),
        ],
    )
    detector_cls.assert_called_once_with(raise_on_error=False)
    aggregated_resources.assert_called_once_with(
        [detector_instance],
        initial_resource=base_resource,
    )
    detected_resource.merge.assert_called_once_with(custom_resource)
    tracer_provider_cls.assert_called_once_with(resource=merged_resource)
    trace_module.set_tracer_provider.assert_called_once_with(tracer_provider)
    url_instrumentor.instrument.assert_called_once_with()
    threading_instrumentor.instrument.assert_called_once_with()
    logging_instrumentor.instrument.assert_called_once_with(
        set_logging_format=is_prod,
    )

    if is_prod:
        cloud_trace_exporter.assert_called_once_with()
        batch_processor_cls.assert_called_once_with(exporter)
        tracer_provider.add_span_processor.assert_called_once_with(batch_processor)
        set_textmap.assert_called_once_with(propagator)
    else:
        cloud_trace_exporter.assert_not_called()
        batch_processor_cls.assert_not_called()
        tracer_provider.add_span_processor.assert_not_called()
        set_textmap.assert_not_called()
