"""
Hybrid retrieval pipeline for M365Mind.

Flow
----
1. Embed the question with nomic-embed-text → vector search (ChromaDB, top-N)
2. Sparse search via BM25 (top-N)
3. Reciprocal Rank Fusion (RRF) to merge the two ranked lists
4. Cross-encoder reranking of the fused top-M candidates → final top-K
5. Build cited prompt → call Ollama LLM
6. Citation enforcement: verify every [filename, page N] tag in the answer
   maps to an actual retrieved source; strip any hallucinated citations
7. Return {answer, sources, confidence, retrieval_stats}
"""

from __future__ import annotations

import re

from backend.ingest import get_chroma_collection
from backend.bm25_store import get_bm25_store
from backend.embeddings import embed
from backend.generation import generate
from monitoring.tracer import Tracer, write_trace
from backend.reranker import rerank

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# How many candidates each retriever returns before fusion
_RETRIEVAL_CANDIDATES = 20

# RRF smoothing constant (standard value)
_RRF_K = 60

# How many candidates go into the cross-encoder after RRF
_RERANK_CANDIDATES = int(__import__('os').getenv('M365_RERANK_CANDIDATES', '8'))

SYSTEM_PROMPT = """You are M365Mind, an AI assistant for Microsoft 365 architects and IT administrators.
You will be given policy context followed by a question. Answer clearly and specifically using only the information in the context.
If the context contains relevant policies, summarise what they say in plain language.
If the context truly contains no relevant information, say so briefly.
Do not invent policies or settings that are not in the context. Be concise."""

# Regex that matches [any text, page N] — used for citation verification
_CITATION_RE = re.compile(r'\[([^\],]+),\s*page\s*(\d+)\]', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _embed(text: str) -> list[float]:
    return embed(text)


def _doc_filter(doc_ids: list[str]) -> dict:
    if len(doc_ids) == 1:
        return {"doc_id": doc_ids[0]}
    return {"doc_id": {"$in": doc_ids}}


def _rrf_merge(
    vector_hits: list[dict],   # [{"chunk_id": str, "rank": int, "vector_score": float}]
    bm25_hits:   list[dict],   # [{"chunk_id": str, "rank": int, "score": float}]
    k: int = _RRF_K,
) -> list[dict]:
    """
    Reciprocal Rank Fusion.

    RRF(d) = Σ 1 / (k + rank_i(d))   for each retriever i

    Returns a list of {"chunk_id": str, "rrf_score": float} sorted descending.
    """
    scores: dict[str, float] = {}

    for hit in vector_hits:
        scores[hit["chunk_id"]] = scores.get(hit["chunk_id"], 0.0) + 1.0 / (k + hit["rank"])

    for hit in bm25_hits:
        scores[hit["chunk_id"]] = scores.get(hit["chunk_id"], 0.0) + 1.0 / (k + hit["rank"])

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [{"chunk_id": cid, "rrf_score": round(sc, 8)} for cid, sc in ranked]


def _verify_citations(answer: str, sources: list[dict]) -> str:
    """
    Enforce citation integrity: remove any [filename, page N] tag whose
    filename+page combination is not present in the retrieved sources.

    Also appends a warning if hallucinated citations were stripped.
    """
    # Build a set of valid (filename_lower, page) pairs
    valid: set[tuple[str, int]] = {
        (s["filename"].lower(), int(s["page_number"])) for s in sources
    }

    hallucinated: list[str] = []

    def _check(m: re.Match) -> str:
        fname = m.group(1).strip().lower()
        page  = int(m.group(2))
        if (fname, page) in valid:
            return m.group(0)   # keep
        hallucinated.append(m.group(0))
        return ""               # strip

    cleaned = _CITATION_RE.sub(_check, answer)

    if hallucinated:
        note = (
            "\n\n_Note: The following citations were removed because they did not "
            f"match any retrieved source: {', '.join(hallucinated)}_"
        )
        cleaned = cleaned + note

    return cleaned.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def answer_question(
    question: str,
    top_k: int = 5,
    doc_ids: list[str] | None = None,
    synthesize: bool = False,
) -> dict:
    """
    Full hybrid retrieval pipeline.

    Parameters
    ----------
    question : user question
    top_k    : number of chunks to pass to the LLM (after reranking)
    doc_ids  : if provided, restrict retrieval to these document IDs

    Returns
    -------
    {
        "answer"          : str,
        "sources"         : [...],
        "confidence"      : float,   # mean cross-encoder score (normalised 0-1)
        "retrieval_stats" : {
            "vector_hits" : int,
            "bm25_hits"   : int,
            "after_rrf"   : int,
            "after_rerank": int,
        }
    }
    """
    tracer = Tracer()

    # ------------------------------------------------------------------
    # Guard: no documents
    # ------------------------------------------------------------------
    if doc_ids is not None and len(doc_ids) == 0:
        return _empty("No policies loaded yet. Click Launch Demo, or Sync Policies from your tenant.")

    collection = get_chroma_collection()

    if doc_ids:
        scoped = collection.get(where=_doc_filter(doc_ids), include=[], limit=100_000)
        total = len(scoped["ids"])
    else:
        total = collection.count()

    if total == 0:
        return _empty("No policies loaded yet. Click Launch Demo to explore sample M365 policies, or connect your tenant and Sync Policies.")

    # ------------------------------------------------------------------
    # Step 1 — Vector search
    # ------------------------------------------------------------------
    n_vec = min(_RETRIEVAL_CANDIDATES, total)
    with tracer.span("embed"):
        query_embedding = _embed(question)

    vec_kwargs: dict = dict(
        query_embeddings=[query_embedding],
        n_results=n_vec,
        include=["documents", "metadatas", "distances"],
    )
    if doc_ids:
        vec_kwargs["where"] = _doc_filter(doc_ids)

    with tracer.span("vector_search"):
        vec_results = collection.query(**vec_kwargs)

    vec_docs   = vec_results["documents"][0]
    vec_metas  = vec_results["metadatas"][0]
    vec_ids    = vec_results["ids"][0]
    vec_dists  = vec_results["distances"][0]

    # Build ranked list for RRF
    vector_hits = [
        {
            "chunk_id":     cid,
            "rank":         i + 1,
            "vector_score": round(1.0 - d / 2.0, 4),
            "text":         doc,
            "metadata":     meta,
        }
        for i, (cid, doc, meta, d) in enumerate(
            zip(vec_ids, vec_docs, vec_metas, vec_dists)
        )
    ]

    # ------------------------------------------------------------------
    # Step 2 — BM25 search
    # ------------------------------------------------------------------
    bm25_store = get_bm25_store()
    with tracer.span("bm25"):
        bm25_raw = bm25_store.query(question, top_k=_RETRIEVAL_CANDIDATES)

    # Filter to doc_ids scope if needed
    if doc_ids and bm25_raw:
        scoped_ids = set(scoped["ids"]) if doc_ids else None
        bm25_raw = [h for h in bm25_raw if h["chunk_id"] in scoped_ids]

    bm25_hits = [
        {"chunk_id": h["chunk_id"], "rank": h["rank"], "bm25_score": h["score"]}
        for h in bm25_raw
    ]

    # ------------------------------------------------------------------
    # Step 3 — RRF fusion
    # ------------------------------------------------------------------
    fused = _rrf_merge(vector_hits, bm25_hits)[:_RERANK_CANDIDATES]

    # Hydrate fused list with text + metadata (pull from vector results or ChromaDB)
    vec_lookup: dict[str, dict] = {h["chunk_id"]: h for h in vector_hits}

    # Any fused chunk not in vector results needs to be fetched from ChromaDB
    missing_ids = [f["chunk_id"] for f in fused if f["chunk_id"] not in vec_lookup]
    if missing_ids:
        extra = collection.get(ids=missing_ids, include=["documents", "metadatas"])
        for cid, doc, meta in zip(extra["ids"], extra["documents"], extra["metadatas"]):
            vec_lookup[cid] = {"chunk_id": cid, "text": doc, "metadata": meta, "vector_score": 0.0}

    candidates = []
    for f in fused:
        base = vec_lookup.get(f["chunk_id"], {})
        candidates.append({
            "chunk_id":    f["chunk_id"],
            "rrf_score":   f["rrf_score"],
            "text":        base.get("text", ""),
            "metadata":    base.get("metadata", {}),
            "vector_score": base.get("vector_score", 0.0),
        })

    # ------------------------------------------------------------------
    # Step 4 — Cross-encoder reranking
    # ------------------------------------------------------------------
    actual_k = min(top_k, len(candidates))
    with tracer.span("rerank"):
        reranked = rerank(question, candidates, top_k=actual_k)

    # ------------------------------------------------------------------
    # Sources are built the same way in both modes.
    sources = [
        {
            "filename":     chunk["metadata"].get("filename", "unknown"),
            "page_number":  chunk["metadata"].get("page_number", 0),
            "chunk_text":   chunk["text"],
            "rerank_score": chunk.get("rerank_score", 0.0),
        }
        for chunk in reranked
    ]

    # Confidence from the cross-encoder is mode-independent.
    rerank_scores = [c.get("rerank_score", 0.0) for c in reranked]
    if rerank_scores:
        mean_logit = sum(rerank_scores) / len(rerank_scores)
        confidence = round(max(0.0, min(1.0, (mean_logit + 10) / 20)), 4)
    else:
        confidence = 0.0

    # ------------------------------------------------------------------
    # Two answer modes:
    #   retrieval (default)  — return the ranked, cited policies directly.
    #     No LLM call, so it's sub-second once the models are warm. For a
    #     governance tool this is often preferable: the authoritative policy
    #     text with citations, no risk of a hallucinated summary.
    #   synthesize (opt-in)  — run the local LLM over the retrieved policies to
    #     produce a plain-English answer, with citation enforcement.
    # ------------------------------------------------------------------
    if synthesize:
        context_parts = []
        for i, chunk in enumerate(reranked):
            meta = chunk["metadata"]
            context_parts.append(
                f"[Source {i + 1}: {meta.get('filename', 'unknown')}, "
                f"page {meta.get('page_number', '?')}]\n{chunk['text']}"
            )
        context_str  = "\n\n---\n\n".join(context_parts)
        user_message = f"Context:\n{context_str}\n\nQuestion: {question}"

        with tracer.span("llm"):
            raw_answer = generate(SYSTEM_PROMPT, user_message)
        with tracer.span("citation_check"):
            answer = _verify_citations(raw_answer, sources)
        mode = "llm"
        tokens_generated = len(raw_answer.split())
    else:
        answer = _extractive_answer(reranked)
        mode = "retrieval"
        tokens_generated = 0

    write_trace(tracer.finish(), endpoint="/query", status="ok",
                tokens_generated=tokens_generated, confidence=confidence)

    return {
        "answer": answer,
        "sources": sources,
        "confidence": confidence,
        "mode": mode,
        "retrieval_stats": {
            "vector_hits":  len(vector_hits),
            "bm25_hits":    len(bm25_hits),
            "after_rrf":    len(fused),
            "after_rerank": len(reranked),
        },
    }


def _extractive_answer(reranked: list[dict]) -> str:
    """
    Build an instant answer from the retrieved policies — no LLM. Lists the top
    matching policies with a short snippet each, deduplicated by name.
    """
    if not reranked:
        return "No matching policies found."
    lines = ["**Top matching policies:**"]
    seen: set[str] = set()
    for chunk in reranked:
        name = chunk["metadata"].get("filename", "unknown")
        if name in seen:
            continue
        seen.add(name)
        snippet = " ".join(chunk["text"].split())[:220]
        page = chunk["metadata"].get("page_number", 1)
        lines.append(f"- **{name}** [{name}, page {page}] — {snippet}\u2026")
        if len(seen) >= 5:
            break
    lines.append("\n_Click **Explain with AI** for a plain-English summary._")
    return "\n".join(lines)


def _empty(msg: str) -> dict:
    return {
        "answer": msg,
        "sources": [],
        "confidence": 0.0,
        "retrieval_stats": {"vector_hits": 0, "bm25_hits": 0, "after_rrf": 0, "after_rerank": 0},
    }
