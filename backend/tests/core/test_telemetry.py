from opentelemetry import trace

from app.core import telemetry
from app.core.settings import Settings


def test_configure_once_and_helpers() -> None:
    telemetry.configure_telemetry(Settings(_env_file=None), "api")
    provider = trace.get_tracer_provider()
    telemetry.configure_telemetry(Settings(_env_file=None), "worker")  # no-op the second time
    assert trace.get_tracer_provider() is provider
    assert telemetry.counter("app_test_total") is telemetry.counter("app_test_total")
    telemetry.histogram("app_test_seconds").record(0.1)
    with telemetry.tracer().start_as_current_span("test"):
        pass
