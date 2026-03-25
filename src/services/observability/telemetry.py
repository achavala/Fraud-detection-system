"""
OpenTelemetry integration — Prometheus metrics export and distributed tracing.

Initialises the OTEL SDK, instruments FastAPI / SQLAlchemy / Redis / Celery,
and exposes a ``/metrics`` Prometheus scrape endpoint.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from src.core.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)


def _otel_available() -> bool:
    try:
        import opentelemetry  # noqa: F401
        return True
    except ImportError:
        return False


def setup_telemetry(app: "FastAPI") -> None:
    """Wire OpenTelemetry into the FastAPI app.

    Safe to call even if the OTEL packages are not installed — it will
    log a warning and return without side-effects.
    """
    if not _otel_available():
        logger.warning("otel_not_installed", msg="OpenTelemetry packages not found; skipping telemetry setup")
        return

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry import metrics as otel_metrics

    service_name = os.getenv("OTEL_SERVICE_NAME", "fraud-detection-platform")
    resource = Resource.create({"service.name": service_name})

    # --- Tracing ---
    tracer_provider = TracerProvider(resource=resource)

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            tracer_provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
            )
            logger.info("otel_otlp_exporter", endpoint=otlp_endpoint)
        except ImportError:
            logger.warning("otel_otlp_not_installed")

    trace.set_tracer_provider(tracer_provider)

    # --- Metrics (Prometheus) ---
    try:
        from opentelemetry.exporter.prometheus import PrometheusMetricReader
        from prometheus_client import start_http_server

        prometheus_port = int(os.getenv("PROMETHEUS_PORT", "9464"))
        reader = PrometheusMetricReader()
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        otel_metrics.set_meter_provider(meter_provider)

        start_http_server(prometheus_port)
        logger.info("prometheus_metrics_server", port=prometheus_port)
    except ImportError:
        logger.warning("prometheus_exporter_not_installed")
    except OSError as exc:
        logger.warning("prometheus_port_in_use", error=str(exc))

    # --- Instrument FastAPI ---
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("otel_fastapi_instrumented")
    except ImportError:
        logger.warning("otel_fastapi_instrumentor_not_installed")

    # --- Instrument SQLAlchemy ---
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        SQLAlchemyInstrumentor().instrument()
        logger.info("otel_sqlalchemy_instrumented")
    except ImportError:
        pass

    # --- Instrument Redis ---
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        RedisInstrumentor().instrument()
        logger.info("otel_redis_instrumented")
    except ImportError:
        pass

    # --- Instrument Celery ---
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        CeleryInstrumentor().instrument()
        logger.info("otel_celery_instrumented")
    except ImportError:
        pass

    logger.info("otel_setup_complete", service=service_name)


# --- Custom metric helpers ---

_meter = None


def get_meter():
    global _meter
    if _meter is not None:
        return _meter
    if not _otel_available():
        return None
    from opentelemetry import metrics as otel_metrics
    _meter = otel_metrics.get_meter("fraud-detection-platform")
    return _meter


def create_scoring_metrics():
    """Create platform-specific OTEL metrics for scoring."""
    meter = get_meter()
    if meter is None:
        return {}

    return {
        "scoring_latency": meter.create_histogram(
            name="fraud.scoring.latency_ms",
            description="End-to-end scoring latency in milliseconds",
            unit="ms",
        ),
        "scoring_requests": meter.create_counter(
            name="fraud.scoring.requests_total",
            description="Total scoring requests",
        ),
        "scoring_decisions": meter.create_counter(
            name="fraud.scoring.decisions_total",
            description="Decision counts by type",
        ),
        "model_fallbacks": meter.create_counter(
            name="fraud.model.fallbacks_total",
            description="Model heuristic fallback count",
        ),
        "rule_fires": meter.create_counter(
            name="fraud.rules.fires_total",
            description="Rule fire count by rule ID",
        ),
        "active_cases": meter.create_up_down_counter(
            name="fraud.cases.active",
            description="Currently open fraud cases",
        ),
    }
