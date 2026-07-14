"""
Embedding module for M365Mind.

Replaces Ollama nomic-embed-text with sentence-transformers.
Uses the same underlying model (nomic-embed-text-v1.5) so existing
ChromaDB collections remain compatible.

Model downloads automatically on first use (~270 MB, cached in
~/.cache/huggingface after that).
"""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

_MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer

    logger.info("Loading embedding model: %s", _MODEL_NAME)
    model = SentenceTransformer(_MODEL_NAME, trust_remote_code=True)
    logger.info("Embedding model ready.")
    return model


def embed(text: str) -> list[float]:
    """Embed a single string. Returns a normalised float list."""
    return _get_model().encode(text, normalize_embeddings=True).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings efficiently. Returns list of float lists."""
    return _get_model().encode(
        texts, normalize_embeddings=True, show_progress_bar=False
    ).tolist()
