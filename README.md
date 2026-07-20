<div align="center">

# 🧠 M365Mind

### Ask your Microsoft 365 governance a question — get the exact policies back, ranked, cited, and private

A **FastAPI** backend + single-page web UI that turns your Conditional Access policies, Sensitivity Labels, and Named Locations into something you can just *ask*. Questions are answered by a **hybrid retrieval** pipeline — dense vectors fused with keyword search, reranked by a cross-encoder — that returns the governing policies with citations in milliseconds. An optional one-click **AI summary** runs a local LLM over those same sources. Everything runs on your machine; no tenant data leaves the box.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_Store-FF6B6B?style=for-the-badge)
![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-000000?style=for-the-badge&logo=ollama&logoColor=white)
![Sentence Transformers](https://img.shields.io/badge/Embeddings-MiniLM-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white)
![MS 365](https://img.shields.io/badge/Microsoft_365-Governance-0078D4?style=for-the-badge&logo=microsoft&logoColor=white)
![Private](https://img.shields.io/badge/100%25-Local_·_Offline-4CAF50?style=for-the-badge)

<!-- Drop a screenshot of the web UI here, e.g.
<img width="880" alt="M365Mind web UI" src="https://github.com/user-attachments/assets/YOUR-IMAGE-ID" /> -->

</div>

---

## How It Works

You load policies — either the built-in demo set or your own PDF exports — and ask questions in plain English. For each question M365Mind:

1. **Ingests** each policy: splits it into chunks (512 tokens, 50 overlap), embeds them, and indexes them in both a vector store and a keyword store
2. **Retrieves** candidates two ways at once — dense vector search *and* BM25 keyword search — then fuses the two ranked lists
3. **Reranks** the fused candidates with a cross-encoder that scores true question↔policy relevance
4. **Answers** — instantly from the exact policy text (no LLM), or, on request, with a local-LLM summary grounded in those same cited sources

**Two answer modes:**

- **Instant (default)** — an extractive answer built straight from the top-ranked policy chunks. No model generation, so it returns in well under a second once the models are warm. This is what every question uses first.
- **Explain with AI** — one click sends the same retrieved sources to a local Ollama model (`qwen2.5:1.5b`) for a natural-language summary, with every citation verified against the real sources before it's shown.

Nothing calls out to the cloud. Embeddings, reranking, and generation all run locally.

---

## The retrieval layer

Most "chat with your docs" tools embed a question, grab the nearest vectors, and hand them to an LLM. M365Mind treats retrieval as the product, not plumbing — because on governance questions the *right policy* matters more than fluent prose.

### Hybrid search + Reciprocal Rank Fusion

Policy language is templated and keyword-heavy ("require", "block", "grant", exact label names), which pure vector search can wash out, while pure keyword search misses paraphrases. So both run in parallel — dense vectors over ChromaDB (top-20) and BM25 over word tokens (top-20) — and their rankings are merged with **Reciprocal Rank Fusion**, which rewards policies that both methods rank highly without needing either score to be calibrated against the other. Implemented in `backend/retrieval.py` (`_rrf_merge`), with the sparse index in `backend/bm25_store.py`.

### Cross-encoder reranking

RRF gives a strong shortlist (top-8); a **cross-encoder** (`cross-encoder/ms-marco-MiniLM-L-6-v2`) then reads each `(question, policy)` pair jointly and scores real relevance, which a bi-encoder retrieving in isolation can't. The reranked top-k becomes the answer's sources. Implemented in `backend/reranker.py`.

### Citation enforcement

When the AI-summary mode is used, every `[filename, page N]` tag the model emits is checked against the actually-retrieved sources, and any citation that doesn't map to a real source is stripped (`_verify_citations`). The model is not allowed to invent a source.

---

## Confidence

Every answer carries a confidence score derived from the cross-encoder — and getting this honest took a real fix.

The cross-encoder emits an unbounded relevance **logit** per policy. The original code squashed it with an arbitrary linear map, `(logit + 10) / 20`, which pinned almost every genuine match near 0.5 — so even a perfect answer *looked* uncertain. That's now a **sigmoid**, the calibrated inverse of a logit, applied to the mean of the top-2 reranked logits (scoring the best-matching evidence, not diluting it with the deliberately-weaker tail):

```python
best_logit = mean(sorted(rerank_logits, reverse=True)[:2])
confidence = 1 / (1 + exp(-best_logit))
```

Illustrative effect on the same retrieved set:

| Evidence quality | Old (linear) | New (sigmoid) |
|------------------|--------------|---------------|
| Strong match     | 0.52         | **1.00**      |
| Decent match     | 0.41         | **0.78**      |
| Weak / off-topic | 0.21         | **0.02**      |

Strong answers now read as strong, and genuinely weak retrieval collapses toward zero instead of hovering at a misleading 0.5.

---

## Setup

**Requirements:** Python 3.10+. [Ollama](https://ollama.com) is needed only for the optional "Explain with AI" summary — instant answers and confidence work without it.

**1. Clone & install**

```bash
git clone https://github.com/aminabk99/M365Mind
cd M365Mind
pip install -r requirements.txt
```

**2. (Optional) Pull the local LLM** — only for AI summaries:

```bash
ollama pull qwen2.5:1.5b
```

The embedding model (`all-MiniLM-L6-v2`, ~80 MB) and the cross-encoder download automatically via sentence-transformers on first use — no manual step.

**3. Run the API + UI**

```bash
uvicorn backend.main:app --port 8000
```

Open **http://localhost:8000** for the web UI. On the home screen, click **Load demo policies** (17 sample policies, no tenant required) or **Upload your files** to index your own PDF exports, then open the chat and ask.

> The embedding and reranking models load in the background at startup, so the *first* user's question is already fast rather than paying the cold-load cost.

---

## Project Structure

```
M365Mind/
├── backend/
│   ├── main.py              # FastAPI routes + serves the web UI, warms models at startup
│   ├── retrieval.py         # Hybrid retrieval: vector + BM25 → RRF → rerank → confidence
│   ├── reranker.py          # Cross-encoder (ms-marco-MiniLM-L-6-v2) reranking
│   ├── embeddings.py        # sentence-transformers (all-MiniLM-L6-v2), lazy + cached
│   ├── bm25_store.py        # BM25 keyword index
│   ├── ingest.py            # PDF → chunk (512/50) → embed → index
│   ├── generation.py        # Local Ollama client (qwen2.5:1.5b), keep-alive + priming
│   ├── policy_formatter.py  # Turns raw policy JSON into readable, chunkable text
│   ├── graph_client.py      # Microsoft Graph client (real-tenant sync path)
│   └── auth.py              # Entra OAuth flow for tenant sync
├── frontend/
│   ├── index.html           # Single-page UI: home nav → chat, policy preview, confidence
│   └── bg.jpg               # Background image served at /bg.jpg
├── demo_data/
│   ├── sample_policies.json # 17 policies: 8 Conditional Access · 3 Named Locations · 6 Sensitivity Labels
│   └── load_demo.py         # Loads the demo set via the ingest pipeline
├── eval/
│   ├── test_cases.json      # M365 governance test cases grounded in the demo policies
│   ├── run_evals.py         # Quick heuristic + full LLM-as-judge scoring
│   ├── llm_judge.py         # Faithfulness / relevance / composite judge
│   └── generate_cases.py    # Case scaffolding
└── monitoring/
    ├── tracer.py            # Per-stage span timing (retrieve / rerank / generate)
    ├── metrics.py           # p50/p95/p99 latency + per-stage breakdown from traces
    └── traces.jsonl         # Request traces (generated)
```

---

## API

**POST `/query`** — ask a question

```json
{ "question": "Which policies require MFA?", "top_k": 5, "synthesize": false }
```

Returns `answer`, `sources` (with filenames + rerank scores), `confidence`, `mode` (`retrieval` \| `llm`), and `retrieval_stats` (candidates after RRF and after rerank). Set `synthesize: true` for the local-LLM summary.

**POST `/upload`** — index a policy PDF (≤ 50 MB) into the vector + keyword stores
**GET `/documents`** — list indexed policies (`doc_id`, `filename`, `chunk_count`) — this is what the UI's policy-preview dropdown reads
**DELETE `/documents/{doc_id}`** — remove an indexed document
**POST `/demo/load`** · **GET `/demo/status`** — load the 17 sample policies / check whether they're loaded
**GET `/metrics`** — p50/p95/p99 latency and per-stage timing from recent request traces
**GET `/auth-url`** · **GET `/callback`** · **GET `/auth-status`** · **POST `/sync`** — optional Microsoft Graph sync to pull policies from a real Entra tenant

---

## Evaluation

Answer quality is checked against `eval/test_cases.json` — governance questions grounded in the demo policies (MFA enforcement, legacy-auth blocking, sensitivity labels, named locations, and a deliberately out-of-scope question that should be refused rather than answered).

```bash
python -m eval.run_evals          # quick: citation + refusal heuristics, no LLM needed
python -m eval.run_evals --full   # full: real backend + LLM-as-judge (requires Ollama)
```

Full mode scores each answer on **faithfulness** (is it supported by the retrieved sources), **relevance** (does it answer the question), and a **composite**, appending every run to `eval/scores_history.jsonl` so quality is tracked over time rather than asserted once.

---

## Privacy

M365Mind is built to run entirely offline. Policy text is embedded, indexed, reranked, and (optionally) summarized by models running on your own machine — ChromaDB is a local store, and the LLM is a local Ollama model. No policy content is sent to any external API. The Microsoft Graph sync path is opt-in and read-only, using your own delegated permissions to pull policies *in*; it never writes back to the tenant.

---

<div align="center">
  <sub>Built by <a href="https://github.com/aminabk99">Amina Bilal</a> · <a href="https://linkedin.com/in/amina-bilal-926340382">LinkedIn</a></sub>
</div>
