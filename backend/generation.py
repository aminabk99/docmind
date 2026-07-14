"""
Generation module for M365Mind.

Uses microsoft/Phi-3.5-mini-instruct via HuggingFace transformers.
No Ollama required — model downloads automatically on first use.

Hardware notes
--------------
- GPU (8 GB+ VRAM): fast, bfloat16, recommended
- CPU only: works, ~60-120 s per response, float32
- Apple Silicon: MPS backend used automatically via device_map="auto"

Model cache: ~/.cache/huggingface (~7.6 GB on first download)
"""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

MODEL_ID = "microsoft/Phi-3.5-mini-instruct"
MAX_NEW_TOKENS = 512


@lru_cache(maxsize=1)
def _get_pipeline():
    import torch
    from transformers import pipeline

    logger.info("Loading generation model: %s", MODEL_ID)

    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32

    pipe = pipeline(
        "text-generation",
        model=MODEL_ID,
        torch_dtype=dtype,
        device_map="auto",
        trust_remote_code=True,
    )
    logger.info("Generation model ready.")
    return pipe


def generate(system_prompt: str, user_message: str) -> str:
    """
    Generate a response given a system prompt and user message.

    Parameters
    ----------
    system_prompt : instruction context for the model
    user_message  : the user's query with retrieved context

    Returns
    -------
    Generated text string (assistant turn only).
    """
    pipe = _get_pipeline()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ]

    result = pipe(
        messages,
        max_new_tokens=MAX_NEW_TOKENS,
        do_sample=False,   # deterministic — important for governance answers
        temperature=None,
        top_p=None,
        return_full_text=False,
    )

    # transformers pipeline with return_full_text=False returns only the
    # assistant turn directly as a string
    output = result[0]["generated_text"]
    if isinstance(output, list):
        # Chat format: last message is the assistant turn
        return output[-1].get("content", "")
    return str(output)
