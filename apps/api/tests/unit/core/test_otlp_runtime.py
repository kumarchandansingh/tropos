from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from tropos.core.adapters.observability.runtime import build_live_span_recorder


def test_observability_export_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TROPOS_OTEL_CONSOLE", raising=False)
    monkeypatch.delenv("TROPOS_OTEL_OTLP_ENDPOINT", raising=False)
    assert build_live_span_recorder() is None


def test_console_mode_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TROPOS_OTEL_CONSOLE", "1")
    monkeypatch.delenv("TROPOS_OTEL_OTLP_ENDPOINT", raising=False)
    assert build_live_span_recorder() is not None


def test_invalid_endpoint_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TROPOS_OTEL_OTLP_ENDPOINT", "file:///tmp/spans")
    with pytest.raises(ValueError, match="HTTP"):
        build_live_span_recorder()


def test_otlp_exporter_constructed_with_configured_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    module = types.ModuleType("opentelemetry.exporter.otlp.proto.http.trace_exporter")

    class FakeExporter:
        def __init__(self, *, endpoint: str) -> None:
            calls.append(endpoint)

        def export(self, spans: Any) -> Any:
            from opentelemetry.sdk.trace.export import SpanExportResult

            return SpanExportResult.SUCCESS

        def shutdown(self, timeout_millis: int = 30000) -> None:
            pass

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            return True

    module.OTLPSpanExporter = FakeExporter  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setenv("TROPOS_OTEL_OTLP_ENDPOINT", "http://127.0.0.1:4318/v1/traces")
    monkeypatch.delenv("TROPOS_OTEL_CONSOLE", raising=False)
    assert build_live_span_recorder() is not None
    assert calls == ["http://127.0.0.1:4318/v1/traces"]
