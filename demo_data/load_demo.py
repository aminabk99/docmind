"""
Demo data loader for M365Mind.

Loads sample_policies.json into ChromaDB so users can explore the app
without connecting a real Microsoft 365 tenant.

Usage
-----
Called automatically via the /demo/load endpoint (backend/main.py).
Can also be run directly for development:

    python -m demo_data.load_demo

The loader is idempotent: it uses stable doc_ids derived from the
policy's own 'id' field, so running it twice won't create duplicates —
it deletes any existing demo chunks before re-ingesting.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_DEMO_JSON = Path(__file__).parent / "sample_policies.json"

_TYPE_MAP = {
    "conditional_access": "conditional_access",
    "named_locations":    "named_location",
    "sensitivity_labels": "sensitivity_label",
}


def _delete_existing_demo(collection) -> int:
    """Remove any previously loaded demo chunks from ChromaDB."""
    results = collection.get(
        where={"source_type": "demo"},
        include=[],
        limit=10_000,
    )
    ids = results.get("ids", [])
    if ids:
        collection.delete(ids=ids)
        logger.info("Removed %d stale demo chunks.", len(ids))
    return len(ids)


def load_demo() -> dict:
    """
    Ingest all demo policies into ChromaDB.

    Returns
    -------
    {
        "loaded":  int,   # policies ingested
        "chunks":  int,   # total chunks created
        "deleted": int,   # stale demo chunks removed before reload
    }
    """
    from backend.ingest import get_chroma_collection, ingest_text
    from backend.policy_formatter import format_policy

    data = json.loads(_DEMO_JSON.read_text(encoding="utf-8"))

    collection = get_chroma_collection()
    deleted    = _delete_existing_demo(collection)

    total_policies = 0
    total_chunks   = 0

    for section_key, policy_type in _TYPE_MAP.items():
        items = data.get(section_key, [])
        for item in items:
            # Stable doc_id so re-runs don't duplicate data
            doc_id = f"demo_{policy_type}_{item.get('id', 'unknown')}"

            display_name, text = format_policy(policy_type, item)
            if not text.strip():
                continue

            result = ingest_text(
                text=text,
                display_name=display_name,
                source_type="demo",
                policy_type=policy_type,
                doc_id=doc_id,
            )

            total_policies += 1
            total_chunks   += result.get("chunk_count", 0)
            logger.debug(
                "Loaded demo policy: %s → %d chunk(s)",
                display_name, result.get("chunk_count", 0),
            )

    logger.info(
        "Demo load complete: %d policies, %d chunks total.", total_policies, total_chunks
    )
    return {
        "loaded":  total_policies,
        "chunks":  total_chunks,
        "deleted": deleted,
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(levelname)s  %(message)s")
    result = load_demo()
    print(
        f"\nDemo loaded ✓\n"
        f"  Policies ingested : {result['loaded']}\n"
        f"  Chunks created    : {result['chunks']}\n"
        f"  Old chunks removed: {result['deleted']}\n"
    )
