"""
Generation module for M365Mind.

Uses Ollama for local LLM inference — fast, simple, model stays loaded in memory.

Setup (one time):
    1. Install Ollama: https://ollama.com
    2. ollama pull qwen2.5:0.5b
    3. ollama serve

Model: qwen2.5:0.5b — ~390 MB, 5-15 s per response on CPU, no GPU needed.
"""

from __future__ import annotations

import logging
import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"
MODEL_NAME      = "qwen2.5:1.5b"
MAX_TOKENS      = 300


def generate(system_prompt: str, user_message: str) -> str:
    """
    Generate a response via Ollama's chat API.

    Returns
    -------
    Generated text string (assistant turn only).
    """
    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model":    MODEL_NAME,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
                "stream": False,
                "options": {
                    "temperature": 0,
                    "num_predict": MAX_TOKENS,
                },
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip()
    except httpx.ConnectError:
        return (
            "Ollama is not running. Start it with `ollama serve` in a terminal, "
            "then try again."
        )
    except Exception as exc:
        logger.error("Generation error: %s", exc)
        return f"Generation failed: {exc}"
