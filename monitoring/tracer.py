"""
Request Tracer for M365Mind
===========================
Lightweight span-based tracer. No external dependencies.

Usage inside retrieval.py
-------------------------
    from monitoring.tracer import Tracer

    tracer = Tracer()
    with tracer.span("embed"):
        embedding = _embed(question)
    with tracer.span("vector_search"):
        results = collection.query(...)

    timings = tracer.finish()   # {"embed_ms": 42, "vector_search_ms": 11, ...}

Traces are written to monitoring/traces.jsonl by the FastAPI middleware.
Each line is one JSON object representing one request.
"""

from __future__ import annotations

import json
import time
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

TRACES_FILE = Path(__file__).parent / "traces.jsonl"
_write_lock = threading.Lock()


class Tracer:
    """Accumulates named timing spans for a single request."""

    def __init__(self) -> None:
        self._spans: dict[str, float] = {}
        self._start_times: dict[str, float] = {}
        self._request_start = time.perf_counter()

    @contextmanager
    def span(self, name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self._spans[f"{name}_ms"] = round((time.perf_counter() - t0) * 1000, 2)

    def finish(self) -> dict:
        """Return all span timings + total elapsed ms."""
        total = round((time.perf_counter() - self._request_start) * 1000, 2)
        return {"total_ms": total, **self._spans}


def write_trace(
    trace: dict,
    endpoint: str,
    status: int,
    tokens_generated: int = 0,
    confidence: float = 0.0,
) -> None:
    """Append one trace record to traces.jsonl (thread-safe)."""
    record = {
        "ts":               datetime.now(timezone.utc).isoformat(),
        "endpoint":         endpoint,
        "status":           status,
        "tokens_generated": tokens_generated,
        "confidence":       confidence,
        **trace,
    }
    TRACES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        with open(TRACES_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
