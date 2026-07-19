#!/usr/bin/env python3
"""
M365Mind — Multi-Model Inference Benchmark
==========================================
Runs a fixed prompt suite through 3 local SLMs via Ollama and records
real performance metrics straight from the Ollama response payload:

  eval_count      — tokens generated
  eval_duration   — generation time in nanoseconds
  → tokens/sec    = eval_count / (eval_duration / 1e9)

  prompt_eval_duration — time to process the prompt (nanoseconds)
  → TTFT (approx)      = prompt_eval_duration / 1e9

Models benchmarked
------------------
  tinyllama   1.1B params  ~638 MB   speed champion
  phi3:mini   3.8B params  ~2.3 GB   balanced
  mistral:7b  7B   params  ~4.1 GB   quality champion

Usage
-----
    python -m benchmark.run_benchmark
    python -m benchmark.run_benchmark --models tinyllama phi3:mini
    python -m benchmark.run_benchmark --output benchmark/results/run_001.json
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from backend.config import OLLAMA_BASE_URL

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_MODELS = ["tinyllama", "phi3:mini", "mistral:7b"]

# Prompt suite — covers the main M365Mind use cases
PROMPTS = [
    {
        "id": "factual_recall",
        "category": "Factual",
        "prompt": (
            "Answer concisely: What are the three main branches of the US government "
            "and what is the primary function of each?"
        ),
    },
    {
        "id": "summarisation",
        "category": "Summarisation",
        "prompt": (
            "Summarise the following passage in two sentences:\n\n"
            "The transformer architecture, introduced in the 2017 paper 'Attention Is All You Need', "
            "replaced recurrent networks with self-attention mechanisms. This allowed models to process "
            "sequences in parallel rather than sequentially, dramatically reducing training time and "
            "enabling the scaling that led to large language models like GPT and BERT."
        ),
    },
    {
        "id": "reasoning",
        "category": "Reasoning",
        "prompt": (
            "A store sells apples for £0.50 each and oranges for £0.75 each. "
            "If a customer buys 4 apples and 3 oranges, and pays with a £5 note, "
            "how much change do they receive? Show your working."
        ),
    },
    {
        "id": "instruction_following",
        "category": "Instruction Following",
        "prompt": (
            "List exactly 5 privacy advantages of running an LLM locally rather than "
            "using a cloud API. Number each point. Keep each point to one sentence."
        ),
    },
    {
        "id": "citation_format",
        "category": "Citation Format",
        "prompt": (
            "You are a document assistant. Given this context:\n\n"
            "[Source: Block Legacy Authentication, page 1]\nThis policy blocks legacy authentication clients such as Exchange ActiveSync.\n\n"
            "Answer this question and cite your source using the format [filename, page N]:\n"
            "Does this tenant block legacy authentication?"
        ),
    },
]

SYSTEM_PROMPT = (
    "You are a helpful, concise assistant. Answer questions accurately and briefly."
)


# ---------------------------------------------------------------------------
# Ollama REST client
# ---------------------------------------------------------------------------

def _pull_model(model: str, base_url: str) -> None:
    """Pull a model if not already present. Streams progress."""
    print(f"  Checking / pulling {model} …", end="", flush=True)
    with httpx.stream(
        "POST",
        f"{base_url}/api/pull",
        json={"name": model, "stream": True},
        timeout=600,
    ) as r:
        for line in r.iter_lines():
            if line:
                data = json.loads(line)
                if data.get("status") == "success":
                    print(" done.")
                    return
    print(" done.")


def _generate(model: str, prompt: str, system: str, base_url: str) -> dict:
    """
    Call Ollama /api/generate (non-streaming) and return the full response dict.
    Raises httpx.HTTPError on failure.
    """
    payload = {
        "model":  model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 300},
    }
    resp = httpx.post(
        f"{base_url}/api/generate",
        json=payload,
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Metrics extraction
# ---------------------------------------------------------------------------

def _extract_metrics(response: dict, wall_time: float) -> dict:
    """
    Pull real timing data out of the Ollama response.

    Ollama returns durations in nanoseconds.
    """
    ns = 1e9
    eval_count    = response.get("eval_count",    0)
    eval_dur_ns   = response.get("eval_duration", 1)   # avoid div/0
    prompt_dur_ns = response.get("prompt_eval_duration", 0)
    total_dur_ns  = response.get("total_duration", 0)

    tokens_per_sec = round(eval_count / (eval_dur_ns / ns), 2) if eval_dur_ns else 0.0
    ttft_s         = round(prompt_dur_ns / ns, 3)
    generation_s   = round(eval_dur_ns / ns, 3)
    total_s        = round(total_dur_ns / ns, 3) if total_dur_ns else round(wall_time, 3)

    return {
        "tokens_generated":  eval_count,
        "tokens_per_sec":    tokens_per_sec,
        "ttft_s":            ttft_s,
        "generation_s":      generation_s,
        "total_s":           total_s,
        "wall_time_s":       round(wall_time, 3),
    }


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def run_benchmark(
    models: list[str] = DEFAULT_MODELS,
    base_url: str = OLLAMA_BASE_URL,
    pull: bool = True,
) -> dict:
    """
    Run all prompts through all models. Returns a results dict.
    """
    if pull:
        print("\nEnsuring models are available …")
        for model in models:
            _pull_model(model, base_url)

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url":  base_url,
        "models":    models,
        "prompts":   [p["id"] for p in PROMPTS],
        "runs":      [],
    }

    for model in models:
        print(f"\n{'='*56}")
        print(f"Model: {model}")
        print(f"{'='*56}")

        model_totals = {
            "model":           model,
            "prompt_results":  [],
            "mean_tokens_per_sec": 0.0,
            "mean_ttft_s":         0.0,
            "mean_total_s":        0.0,
            "total_tokens":        0,
        }

        for p in PROMPTS:
            print(f"  [{p['id']}] … ", end="", flush=True)
            try:
                t0       = time.perf_counter()
                response = _generate(model, p["prompt"], SYSTEM_PROMPT, base_url)
                wall     = time.perf_counter() - t0

                metrics = _extract_metrics(response, wall)
                answer  = response.get("response", "").strip()

                result = {
                    "prompt_id":  p["id"],
                    "category":   p["category"],
                    "answer":     answer[:300],   # cap for storage
                    **metrics,
                }
                model_totals["prompt_results"].append(result)

                print(
                    f"{metrics['tokens_per_sec']:.1f} tok/s  "
                    f"TTFT {metrics['ttft_s']:.2f}s  "
                    f"total {metrics['total_s']:.2f}s"
                )

            except Exception as exc:
                print(f"ERROR: {exc}")
                model_totals["prompt_results"].append({
                    "prompt_id": p["id"],
                    "category":  p["category"],
                    "error":     str(exc),
                    "tokens_per_sec": 0, "ttft_s": 0,
                    "generation_s": 0, "total_s": 0,
                    "tokens_generated": 0, "wall_time_s": 0,
                })

        # Aggregate
        ok = [r for r in model_totals["prompt_results"] if "error" not in r]
        if ok:
            model_totals["mean_tokens_per_sec"] = round(
                sum(r["tokens_per_sec"] for r in ok) / len(ok), 2)
            model_totals["mean_ttft_s"] = round(
                sum(r["ttft_s"] for r in ok) / len(ok), 3)
            model_totals["mean_total_s"] = round(
                sum(r["total_s"] for r in ok) / len(ok), 3)
            model_totals["total_tokens"] = sum(r["tokens_generated"] for r in ok)

        results["runs"].append(model_totals)
        print(f"\n  Summary → {model_totals['mean_tokens_per_sec']} tok/s avg  "
              f"TTFT {model_totals['mean_ttft_s']}s avg")

    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="M365Mind multi-model benchmark")
    parser.add_argument("--models",  nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--base-url", default=OLLAMA_BASE_URL)
    parser.add_argument("--no-pull", action="store_true")
    parser.add_argument("--output",  default=None,
                        help="Save results JSON to this path")
    args = parser.parse_args()

    results = run_benchmark(args.models, args.base_url, pull=not args.no_pull)

    output_path = args.output or (
        f"benchmark/results/benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(results, indent=2))
    print(f"\nResults saved → {output_path}")

    # Print quick summary table
    from benchmark.report import print_summary_table
    print_summary_table(results)


if __name__ == "__main__":
    main()
