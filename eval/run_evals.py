#!/usr/bin/env python3
"""
M365Mind Evaluation Pipeline
============================
Measures three axes of quality using LLM-as-judge scoring:

  Faithfulness  — does the answer stick to retrieved sources?
  Relevance     — does the answer address the question vs. ground truth?
  Pass Rate     — fraction of cases meeting min_confidence threshold

Modes
-----
  --quick   Mock the LLM (tests pipeline wiring only). CI-safe, no GPU.
  --full    Call real backend + real LLM judge. Requires Ollama running.

Score history is appended to eval/scores_history.jsonl on every --full run
so regression curves can be tracked across commits.

Exit codes
----------
  0  All thresholds met
  1  One or more thresholds failed
  2  Configuration / setup error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

EVAL_DIR     = Path(__file__).parent
CASES_FILE   = EVAL_DIR / "test_cases.json"
HISTORY_FILE = EVAL_DIR / "scores_history.jsonl"
CITATION_RE  = re.compile(r'\[([^\],]+),\s*page\s*(\d+)\]', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def answer_faithfulness_heuristic(answer: str) -> float:
    """Quick heuristic: 1.0 if answer contains a citation tag, else 0.5."""
    return 1.0 if CITATION_RE.search(answer) else 0.5


def check_refusal(answer: str, keywords: list[str]) -> bool:
    al = answer.lower()
    return any(k.lower() in al for k in keywords)


# ---------------------------------------------------------------------------
# Quick mode (mocked)
# ---------------------------------------------------------------------------

def run_case_quick(case: dict) -> dict:
    mock_answer = (
        f"Based on the document, {case.get('ground_truth_answer', 'the answer is in the sources')} "
        f"[{case.get('expected_source_filenames', ['sample.pdf'])[0]}, page 1]"
        if not case.get("check_refusal")
        else "I could not find sufficient information in the loaded policies."
    )

    faith = answer_faithfulness_heuristic(mock_answer)
    passed = True
    notes  = []

    if case.get("check_refusal"):
        if not check_refusal(mock_answer, ["could not find", "insufficient"]):
            passed = False
            notes.append("Expected refusal not detected.")

    return {
        "id":           case["id"],
        "description":  case.get("description", ""),
        "faithfulness": faith,
        "relevance":    1.0,   # trivially 1.0 in mock
        "composite":    round((faith + 1.0) / 2, 3),
        "confidence":   0.75,
        "passed":       passed,
        "notes":        notes,
        "answer_snippet": mock_answer[:120],
    }


# ---------------------------------------------------------------------------
# Full mode (real backend + LLM judge)
# ---------------------------------------------------------------------------

def run_case_full(case: dict, backend_url: str) -> dict:
    import httpx
    from eval.llm_judge import judge

    # Call backend
    try:
        resp = httpx.post(
            f"{backend_url}/query",
            json={"question": case["question"], "top_k": 5},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return _error_result(case, f"Backend error: {exc}")

    answer  = data.get("answer", "")
    sources = data.get("sources", [])
    conf    = data.get("confidence", 0.0)

    # LLM judge
    try:
        scores = judge(
            question      = case["question"],
            ground_truth  = case.get("ground_truth_answer", ""),
            system_answer = answer,
            source_chunks = [s.get("chunk_text", "") for s in sources],
        )
    except Exception as exc:
        scores = {"faithfulness": 0.0, "relevance": 0.0, "composite": 0.0,
                  "reasoning": {"faithfulness": str(exc), "relevance": str(exc)}}

    passed = True
    notes  = []

    if conf < case.get("min_confidence", 0.0):
        passed = False
        notes.append(f"Confidence {conf:.3f} below threshold {case['min_confidence']:.3f}")

    if case.get("check_refusal"):
        if not check_refusal(answer, ["could not find", "insufficient"]):
            passed = False
            notes.append("Expected refusal not detected.")
    elif scores["composite"] < 0.5:
        passed = False
        notes.append(f"Composite judge score {scores['composite']:.3f} below 0.5")

    return {
        "id":             case["id"],
        "description":    case.get("description", ""),
        "faithfulness":   scores["faithfulness"],
        "relevance":      scores["relevance"],
        "composite":      scores["composite"],
        "confidence":     round(conf, 3),
        "passed":         passed,
        "notes":          notes,
        "answer_snippet": answer[:120],
        "reasoning":      scores.get("reasoning", {}),
        "retrieval_stats": data.get("retrieval_stats", {}),
    }


def _error_result(case: dict, msg: str) -> dict:
    return {
        "id": case["id"], "description": case.get("description", ""),
        "faithfulness": 0.0, "relevance": 0.0, "composite": 0.0,
        "confidence": 0.0, "passed": False, "notes": [msg], "answer_snippet": "",
    }


# ---------------------------------------------------------------------------
# Reporting + history
# ---------------------------------------------------------------------------

def save_history(results: list[dict], commit_sha: str = "") -> None:
    mean_f = sum(r["faithfulness"] for r in results) / len(results)
    mean_r = sum(r["relevance"]    for r in results) / len(results)
    mean_c = sum(r["composite"]    for r in results) / len(results)
    passing = sum(1 for r in results if r["passed"])

    entry = {
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "commit":       commit_sha,
        "n_cases":      len(results),
        "mean_faithfulness": round(mean_f, 3),
        "mean_relevance":    round(mean_r, 3),
        "mean_composite":    round(mean_c, 3),
        "pass_rate":         round(passing / len(results), 3),
        "cases": [
            {"id": r["id"], "composite": r["composite"], "passed": r["passed"]}
            for r in results
        ],
    }

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "a") as fh:
        fh.write(json.dumps(entry) + "\n")

    print(f"\nScore history appended → {HISTORY_FILE}")


def print_report(results: list[dict], thresholds: dict) -> bool:
    print("\n" + "=" * 64)
    print("M365Mind Eval Report  (LLM-as-Judge)")
    print("=" * 64)

    total   = len(results)
    passing = sum(1 for r in results if r["passed"])

    for r in results:
        status = "✓ PASS" if r["passed"] else "✗ FAIL"
        print(f"\n[{status}] {r['id']} — {r['description']}")
        print(f"  Faithfulness : {r['faithfulness']:.3f}")
        print(f"  Relevance    : {r['relevance']:.3f}")
        print(f"  Composite    : {r['composite']:.3f}")
        if "confidence" in r:
            print(f"  Confidence   : {r['confidence']:.3f}")
        if r.get("notes"):
            for note in r["notes"]:
                print(f"  ⚠  {note}")
        if r.get("reasoning"):
            print(f"  Judge (faith): {r['reasoning'].get('faithfulness','')}")
            print(f"  Judge (rel)  : {r['reasoning'].get('relevance','')}")
        if r.get("retrieval_stats"):
            rs = r["retrieval_stats"]
            print(f"  Retrieval    : vec={rs.get('vector_hits',0)} "
                  f"bm25={rs.get('bm25_hits',0)} "
                  f"rrf={rs.get('after_rrf',0)} "
                  f"rerank={rs.get('after_rerank',0)}")

    mean_f  = sum(r["faithfulness"] for r in results) / total
    mean_r  = sum(r["relevance"]    for r in results) / total
    mean_c  = sum(r["composite"]    for r in results) / total
    pass_rt = passing / total

    print("\n" + "-" * 64)
    print("Aggregate")
    print(f"  Mean Faithfulness : {mean_f:.3f}  (threshold ≥ {thresholds['min_answer_faithfulness']})")
    print(f"  Mean Relevance    : {mean_r:.3f}")
    print(f"  Mean Composite    : {mean_c:.3f}")
    print(f"  Pass Rate         : {pass_rt:.3f}  ({passing}/{total})  (threshold ≥ {thresholds['min_cases_passing']})")

    ok = (
        mean_f  >= thresholds["min_answer_faithfulness"]
        and pass_rt >= thresholds["min_cases_passing"]
    )
    print("\n" + ("✓ ALL THRESHOLDS MET" if ok else "✗ THRESHOLDS NOT MET — CI gate FAILS"))
    print("=" * 64 + "\n")
    return ok


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="M365Mind eval pipeline")
    parser.add_argument("--quick",       action="store_true")
    parser.add_argument("--full",        action="store_true")
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--output",      default=None)
    parser.add_argument("--commit",      default="", help="Git SHA for history tracking")
    args = parser.parse_args()

    if not args.quick and not args.full:
        print("Specify --quick or --full", file=sys.stderr)
        sys.exit(2)

    if not CASES_FILE.exists():
        print(f"No test cases found at {CASES_FILE}. Run eval/generate_cases.py first.", file=sys.stderr)
        sys.exit(2)

    with open(CASES_FILE) as fh:
        config = json.load(fh)

    cases      = config["test_cases"]
    thresholds = config["thresholds"]

    if not cases:
        print("test_cases.json has no cases. Run eval/generate_cases.py first.", file=sys.stderr)
        sys.exit(2)

    results: list[dict] = []

    if args.quick:
        print(f"Running QUICK mode on {len(cases)} cases (mocked LLM) …")
        for case in cases:
            results.append(run_case_quick(case))
    else:
        print(f"Running FULL mode on {len(cases)} cases against {args.backend_url} …")
        for case in cases:
            print(f"  Evaluating: {case['id']} …")
            results.append(run_case_full(case, args.backend_url))
        save_history(results, commit_sha=args.commit)

    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2))
        print(f"Results written to {args.output}")

    ok = print_report(results, thresholds)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
