#!/usr/bin/env python3
"""
LLM-as-Judge Scorer
====================
Uses a local Ollama model to score system answers against ground truth
on two axes:

  Faithfulness  — does the answer contain only information that is
                  supported by the retrieved sources? (hallucination check)
                  Score: 0.0 – 1.0

  Relevance     — does the answer actually address the question?
                  Score: 0.0 – 1.0

No external API needed — runs entirely with Ollama.

Usage
-----
    from eval.llm_judge import judge

    result = judge(
        question        = "Which policies require MFA?",
        ground_truth    = "Refunds are issued within 30 days.",
        system_answer   = "The Require MFA for All Users policy enforces MFA. [Require MFA for All Users, page 1]",
        source_chunks   = ["Policy: Require MFA for All Users. Status: Enabled. Grant controls: Require multifactor authentication."],
    )
    # result -> {"faithfulness": 0.9, "relevance": 1.0, "reasoning": "..."}
"""

from __future__ import annotations

import json
import re

from llama_index.core.llms import ChatMessage
from llama_index.llms.ollama import Ollama

from backend.config import OLLAMA_BASE_URL, LLM_MODEL

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_FAITHFULNESS_PROMPT = """\
You are an impartial judge evaluating an AI assistant's answer for faithfulness.

QUESTION: {question}

RETRIEVED SOURCE CHUNKS:
{sources}

SYSTEM ANSWER:
{answer}

Task: Score how faithfully the answer sticks to the retrieved sources.
- 1.0 = every claim in the answer is directly supported by the sources
- 0.5 = most claims are supported but there are minor unsupported additions
- 0.0 = the answer contains significant information not found in the sources

Reply with valid JSON only:
{{"score": <float 0.0-1.0>, "reasoning": "<one sentence>"}}"""

_RELEVANCE_PROMPT = """\
You are an impartial judge evaluating an AI assistant's answer for relevance.

QUESTION: {question}

GROUND TRUTH ANSWER: {ground_truth}

SYSTEM ANSWER: {answer}

Task: Score how well the system answer addresses the question compared to the ground truth.
- 1.0 = fully answers the question, consistent with ground truth
- 0.5 = partially answers the question or misses some key points
- 0.0 = does not answer the question or contradicts the ground truth

Reply with valid JSON only:
{{"score": <float 0.0-1.0>, "reasoning": "<one sentence>"}}"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_score(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
    if not match:
        return {"score": 0.0, "reasoning": "Could not parse judge response."}
    try:
        data = json.loads(match.group())
        score = float(data.get("score", 0.0))
        score = max(0.0, min(1.0, score))
        return {"score": round(score, 3), "reasoning": data.get("reasoning", "")}
    except (json.JSONDecodeError, ValueError):
        return {"score": 0.0, "reasoning": "Malformed judge response."}


def _call_llm(prompt: str, llm: Ollama) -> str:
    response = llm.chat([ChatMessage(role="user", content=prompt)])
    return response.message.content


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def judge(
    question:      str,
    ground_truth:  str,
    system_answer: str,
    source_chunks: list[str] | None = None,
) -> dict:
    """
    Score a system answer on faithfulness and relevance.

    Parameters
    ----------
    question      : the user's original question
    ground_truth  : the expected / reference answer (from generate_cases)
    system_answer : the answer produced by the RAG pipeline
    source_chunks : the retrieved chunk texts (for faithfulness scoring)

    Returns
    -------
    {
        "faithfulness" : float,   # 0.0 – 1.0
        "relevance"    : float,   # 0.0 – 1.0
        "composite"    : float,   # mean of both
        "reasoning"    : {
            "faithfulness": str,
            "relevance":    str,
        }
    }
    """
    llm = Ollama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, request_timeout=60.0)

    # Faithfulness
    sources_str = "\n---\n".join(source_chunks) if source_chunks else "(no sources provided)"
    faith_result = _parse_score(
        _call_llm(
            _FAITHFULNESS_PROMPT.format(
                question=question,
                sources=sources_str[:3000],   # cap to avoid context overflow
                answer=system_answer,
            ),
            llm,
        )
    )

    # Relevance
    rel_result = _parse_score(
        _call_llm(
            _RELEVANCE_PROMPT.format(
                question=question,
                ground_truth=ground_truth,
                answer=system_answer,
            ),
            llm,
        )
    )

    composite = round((faith_result["score"] + rel_result["score"]) / 2, 3)

    return {
        "faithfulness": faith_result["score"],
        "relevance":    rel_result["score"],
        "composite":    composite,
        "reasoning": {
            "faithfulness": faith_result["reasoning"],
            "relevance":    rel_result["reasoning"],
        },
    }
