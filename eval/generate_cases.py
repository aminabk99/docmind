#!/usr/bin/env python3
"""
Automatic Eval Case Generator
==============================
Pulls chunks from ChromaDB, calls Ollama to synthesise one Q&A pair per
chunk, and writes the results to eval/test_cases.json.

No manual labelling needed — the pipeline evaluates itself.

Usage
-----
    # Generate up to 20 cases from whatever is currently ingested
    python -m eval.generate_cases

    # Generate from a specific document
    python -m eval.generate_cases --doc-id <uuid>

    # Control how many cases to generate
    python -m eval.generate_cases --max-cases 30

How it works
------------
For each sampled chunk, we send this prompt to the LLM:

    "Given this passage, write ONE question a user might ask whose answer
     is contained entirely within the passage, then write the answer using
     only information from the passage. Reply in JSON:
     {\"question\": \"...\", \"answer\": \"...\"}"

The LLM response is parsed as JSON. Malformed responses are skipped.
Generated cases are merged with any manually-written cases already in
test_cases.json (manual cases are preserved and never overwritten).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from llama_index.llms.ollama import Ollama
from llama_index.core.llms import ChatMessage

from backend.config import OLLAMA_BASE_URL, LLM_MODEL
from backend.ingest import get_chroma_collection

CASES_FILE = Path(__file__).parent / "test_cases.json"

GENERATION_PROMPT = """\
You are an evaluation dataset builder.

Read the passage below and write ONE question that:
- A user might realistically ask about this content
- Can be answered completely using ONLY information in the passage
- Is specific, not vague

Then write the correct answer using only information from the passage.

Passage:
\"\"\"
{chunk}
\"\"\"

Reply with valid JSON only, no extra text:
{{"question": "<your question>", "answer": "<your answer>"}}"""


def _parse_json_from_response(text: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown code fences."""
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()
    # Find the first {...} block
    match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        if "question" in data and "answer" in data:
            return data
    except json.JSONDecodeError:
        pass
    return None


def generate_cases(
    max_cases: int = 20,
    doc_id: str | None = None,
    seed: int = 42,
) -> list[dict]:
    """
    Sample chunks from ChromaDB, generate Q&A pairs via Ollama.
    Returns a list of test case dicts ready for test_cases.json.
    """
    collection = get_chroma_collection()

    # Fetch chunks (scoped to doc_id if provided)
    if doc_id:
        results = collection.get(
            where={"doc_id": doc_id},
            include=["documents", "metadatas"],
            limit=100_000,
        )
    else:
        results = collection.get(include=["documents", "metadatas"], limit=100_000)

    ids   = results["ids"]
    docs  = results["documents"]
    metas = results["metadatas"]

    if not docs:
        print("No chunks found in ChromaDB. Load policies first (POST /demo/load) or upload a document.", file=sys.stderr)
        return []

    # Sample up to max_cases chunks, prefer longer chunks (more content)
    random.seed(seed)
    scored = sorted(zip(ids, docs, metas), key=lambda x: len(x[1]), reverse=True)
    pool   = scored[:max_cases * 3]   # over-sample to account for failures
    sample = random.sample(pool, min(max_cases * 2, len(pool)))

    llm = Ollama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, request_timeout=60.0)

    cases: list[dict] = []
    attempted = 0

    for chunk_id, chunk_text, meta in sample:
        if len(cases) >= max_cases:
            break

        attempted += 1
        prompt = GENERATION_PROMPT.format(chunk=chunk_text[:1200])  # cap chunk length

        try:
            response = llm.chat([ChatMessage(role="user", content=prompt)])
            parsed   = _parse_json_from_response(response.message.content)
        except Exception as exc:
            print(f"  LLM error on chunk {chunk_id}: {exc}")
            continue

        if not parsed:
            print(f"  Skipping chunk {chunk_id} — could not parse JSON response")
            continue

        case = {
            "id":                    f"auto_{chunk_id}",
            "description":           f"Auto-generated from {meta.get('filename','?')} p{meta.get('page_number','?')}",
            "question":              parsed["question"],
            "ground_truth_answer":   parsed["answer"],
            "source_chunk_id":       chunk_id,
            "fixture_pdf":           meta.get("filename", ""),
            "expected_source_filenames": [meta.get("filename", "")],
            "min_confidence":        0.3,
            "generated_at":          datetime.now(timezone.utc).isoformat(),
            "generated":             True,
        }
        cases.append(case)
        print(f"  [{len(cases)}/{max_cases}] {parsed['question'][:80]}")

    print(f"\nGenerated {len(cases)} cases from {attempted} attempts.")
    return cases


def save_cases(new_cases: list[dict]) -> None:
    """
    Merge new auto-generated cases with existing file.
    Manual cases (generated=False or missing) are always preserved.
    Auto cases are replaced (matched by source_chunk_id).
    """
    existing: dict = {"test_cases": [], "thresholds": {
        "min_context_precision":   0.50,
        "min_answer_faithfulness": 0.80,
        "min_cases_passing":       0.67,
    }}

    if CASES_FILE.exists():
        with open(CASES_FILE) as fh:
            existing = json.load(fh)

    # Keep manual cases
    manual = [c for c in existing.get("test_cases", []) if not c.get("generated")]

    # Index new auto cases by chunk_id for dedup
    auto_by_chunk = {c["source_chunk_id"]: c for c in new_cases}

    # Also keep old auto cases for chunks not re-generated
    old_auto = [
        c for c in existing.get("test_cases", [])
        if c.get("generated") and c.get("source_chunk_id") not in auto_by_chunk
    ]

    merged = manual + old_auto + list(auto_by_chunk.values())
    existing["test_cases"] = merged

    CASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CASES_FILE, "w") as fh:
        json.dump(existing, fh, indent=2)

    print(f"Saved {len(merged)} total cases ({len(manual)} manual, "
          f"{len(old_auto) + len(auto_by_chunk)} auto) → {CASES_FILE}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-generate eval cases from ingested docs")
    parser.add_argument("--max-cases", type=int, default=20)
    parser.add_argument("--doc-id",    type=str, default=None)
    parser.add_argument("--seed",      type=int, default=42)
    args = parser.parse_args()

    print(f"Generating up to {args.max_cases} eval cases…\n")
    cases = generate_cases(args.max_cases, args.doc_id, args.seed)

    if cases:
        save_cases(cases)
    else:
        print("No cases generated.")
        sys.exit(1)


if __name__ == "__main__":
    main()
