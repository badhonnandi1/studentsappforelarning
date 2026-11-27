"""OpenTelemetry tracer and meter setup, plus small metric helpers.

Without ``OTEL_EXPORTER_OTLP_ENDPOINT`` the SDK providers are installed with no exporter, so
instrumented code runs unchanged locally and in tests. The OTLP exporter package is added with
the deployment work (19), which keeps B1's dependency set small.
"""

from __future__ import annotations

from functools import cache

from opentelemetry import metrics, trace
from opentelemetry.metrics import Counter, Histogram, Meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from app.core.settings import Settings

_configured = False


def configure_telemetry(settings: Settings, service: str) -> None:
    global _configured
    if _configured:
        return
    resource = Resource.create(
        {
            "service.name": f"{settings.otel_service_name}-{service}",
            "deployment.environment": settings.app_env,
        }
    )
    trace.set_tracer_provider(TracerProvider(resource=resource))
    metrics.set_meter_provider(MeterProvider(resource=resource))
    _configured = True


def meter() -> Meter:
    return metrics.get_meter("studyplatform")


@cache
def counter(name: str, description: str = "") -> Counter:
    return meter().create_counter(name, description=description)


@cache
def histogram(name: str, unit: str = "s", description: str = "") -> Histogram:
    return meter().create_histogram(name, unit=unit, description=description)


def tracer() -> trace.Tracer:
    return trace.get_tracer("studyplatform")
