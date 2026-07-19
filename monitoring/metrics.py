"""
Metrics Engine for M365Mind
===========================
Reads traces.jsonl and computes:

  - p50 / p95 / p99 latency (total + per pipeline stage)
  - Request count + error rate
  - Token throughput
  - Cost-per-request (local = £0, but shows token proxy)

Exposed via GET /metrics in backend/main.py.

Usage
-----
    from monitoring.metrics import compute_metrics
    metrics = compute_metrics()
"""

from __future__ import annotations

import json
from pathlib import Path

TRACES_FILE = Path(__file__).parent / "traces.jsonl"

# Pipeline stages we track
STAGES = ["embed", "vector_search", "bm25", "rerank", "llm", "citation_check"]


def _percentile(data: list[float], p: float) -> float:
    """Compute the p-th percentile of data without numpy."""
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (k - lo) * (s[hi] - s[lo]), 2)


def _mean(data: list[float]) -> float:
    return round(sum(data) / len(data), 2) if data else 0.0


def compute_metrics(last_n: int = 1000) -> dict:
    """
    Read up to last_n trace records and return a metrics summary dict.
    Returns sensible zeros if no traces exist yet.
    """
    if not TRACES_FILE.exists():
        return _empty_metrics()

    records: list[dict] = []
    with open(TRACES_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not records:
        return _empty_metrics()

    # Take the most recent N
    records = records[-last_n:]

    total_ms       = [r["total_ms"] for r in records if "total_ms" in r]
    error_count    = sum(1 for r in records if r.get("status", 200) >= 400)
    tokens         = [r["tokens_generated"] for r in records if r.get("tokens_generated", 0) > 0]
    confidences    = [r["confidence"] for r in records if r.get("confidence", 0) > 0]

    # Per-stage p95
    stage_p95: dict[str, float] = {}
    for stage in STAGES:
        key = f"{stage}_ms"
        vals = [r[key] for r in records if key in r]
        if vals:
            stage_p95[key] = _percentile(vals, 95)

    return {
        "window":       f"last {len(records)} requests",
        "total_requests": len(records),
        "error_rate":   round(error_count / len(records), 4) if records else 0.0,
        "latency_ms": {
            "p50":  _percentile(total_ms, 50),
            "p95":  _percentile(total_ms, 95),
            "p99":  _percentile(total_ms, 99),
            "mean": _mean(total_ms),
        },
        "stage_latency_p95_ms": stage_p95,
        "tokens": {
            "total_generated":   sum(tokens),
            "mean_per_request":  _mean(tokens),
            "p95_per_request":   _percentile(tokens, 95),
        },
        "quality": {
            "mean_confidence":   _mean(confidences),
            "p50_confidence":    _percentile(confidences, 50),
        },
        "cost_per_request": {
            "api_cost_usd":  0.0,
            "note": "Fully local — zero API cost. Token count is the resource proxy.",
            "mean_tokens":   _mean(tokens),
        },
    }


def _empty_metrics() -> dict:
    return {
        "window": "no data",
        "total_requests": 0,
        "error_rate": 0.0,
        "latency_ms": {"p50": 0, "p95": 0, "p99": 0, "mean": 0},
        "stage_latency_p95_ms": {},
        "tokens": {"total_generated": 0, "mean_per_request": 0, "p95_per_request": 0},
        "quality": {"mean_confidence": 0, "p50_confidence": 0},
        "cost_per_request": {"api_cost_usd": 0.0, "note": "Fully local.", "mean_tokens": 0},
    }
