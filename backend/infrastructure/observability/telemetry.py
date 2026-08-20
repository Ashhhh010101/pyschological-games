"""Optional OpenTelemetry setup with application-level HTTP metrics."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.metrics import Counter, Histogram
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.settings import Settings


class Observability:
    def __init__(
        self,
        request_counter: Counter | None = None,
        error_counter: Counter | None = None,
        latency: Histogram | None = None,
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
    ) -> None:
        self.request_counter = request_counter
        self.error_counter = error_counter
        self.latency = latency
        self.tracer_provider = tracer_provider
        self.meter_provider = meter_provider

    def record_request(self, method: str, route: str, status: int, duration_ms: float) -> None:
        attributes: dict[str, Any] = {
            "http.request.method": method,
            "http.route": route,
            "http.response.status_code": status,
        }
        if self.request_counter:
            self.request_counter.add(1, attributes)
        if status >= 500 and self.error_counter:
            self.error_counter.add(1, attributes)
        if self.latency:
            self.latency.record(duration_ms, attributes)

    def shutdown(self) -> None:
        if self.tracer_provider:
            self.tracer_provider.shutdown()
        if self.meter_provider:
            self.meter_provider.shutdown()


def configure_telemetry(app: FastAPI, settings: Settings, engine: AsyncEngine | None) -> Observability:
    if not settings.otel_enabled:
        return Observability()
    resource = Resource.create({SERVICE_NAME: settings.otel_service_name})
    tracer_provider = TracerProvider(resource=resource)
    readers = []
    if settings.otel_exporter_otlp_endpoint:
        endpoint = settings.otel_exporter_otlp_endpoint
        insecure = endpoint.startswith("http://")
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=insecure)))
        readers.append(PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint, insecure=insecure)))
    meter_provider = MeterProvider(resource=resource, metric_readers=readers)
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(meter_provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, meter_provider=meter_provider)
    if engine is not None:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, tracer_provider=tracer_provider)
    RedisInstrumentor().instrument(tracer_provider=tracer_provider, meter_provider=meter_provider)
    meter = meter_provider.get_meter(settings.otel_service_name)
    return Observability(
        request_counter=meter.create_counter("http.server.requests", unit="{request}"),
        error_counter=meter.create_counter("http.server.errors", unit="{error}"),
        latency=meter.create_histogram("http.server.duration", unit="ms"),
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )
