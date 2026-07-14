# DocMind

A RAG-powered document intelligence web app that runs **fully locally** — no API keys, no cloud, no cost. Upload PDFs, ask natural-language questions, and get cited answers with confidence scores.

Retrieval uses a **hybrid BM25 + vector search pipeline** with cross-encoder reranking and enforced source citations. A CI-gated eval suite runs on every push.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Streamlit UI                             │
│  Sidebar: upload PDF, list/delete docs                          │
│  Main:    question input → answer cards + citations + confidence│
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP (httpx)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                            │
│                                                                 │
│  POST /upload      ──► ingest.py                                │
│                        LlamaIndex SimpleDirectoryReader         │
│                        SentenceSplitter (512 tokens, 50 overlap)│
│                        Ollama nomic-embed-text (embeddings)     │
│                        ChromaDB .add() + BM25 index rebuild     │
│                                                                 │
│  POST /query       ──► retrieval.py                             │
│                        ① Vector search  (ChromaDB, top-20)     │
│                        ② BM25 search    (rank-bm25, top-20)    │
│                        ③ RRF fusion     (k=60, top-15)         │
│                        ④ Cross-encoder rerank (MiniLM, top-k)  │
│                        ⑤ Ollama tinyllama (cited-answer prompt) │
│                        ⑥ Citation enforcement (strip halluc.)  │
│                        confidence = normalised mean rerank score│
│                                                                 │
│  GET  /documents   ──► list all uploaded docs                   │
│  DELETE /documents/{id} ──► remove doc + chunks + BM25 rebuild  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────────────┐
              │   ChromaDB      (./chroma_db)    │
              │   BM25 index    (./chroma_db/    │
              │                  bm25_index.pkl) │
              │   Ollama        (localhost:11434) │
              └──────────────────────────────────┘
```

---

## Setup

### 1. Install Ollama

Download from [ollama.com](https://ollama.com) and install it, then pull the required models:

```bash
ollama pull tinyllama
ollama pull nomic-embed-text
ollama serve
```

> Ollama must be running (`ollama serve`) before starting the backend.

### 2. Clone and install

```bash
git clone https://github.com/aminabk99/docmind.git
cd docmind
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# No API keys needed — defaults work out of the box
```

### 4. Run the backend

```bash
uvicorn backend.main:app --reload
# API at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### 5. Run the frontend (new terminal)

```bash
streamlit run frontend/app.py
# UI at http://localhost:8501
```

---

## Setup (Docker)

> Make sure Ollama is running on the host before starting containers.

```bash
cp .env.example .env
# Edit .env and set: OLLAMA_BASE_URL=http://host.docker.internal:11434
docker-compose up --build
```

| Service  | URL                        |
|----------|----------------------------|
| Frontend | http://localhost:8501      |
| Backend  | http://localhost:8000      |
| API docs | http://localhost:8000/docs |

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/upload` | Upload a PDF (multipart/form-data, field: `file`) |
| `POST` | `/query` | Ask a question `{"question": "...", "top_k": 5}` |
| `GET` | `/documents` | List all ingested documents |
| `DELETE` | `/documents/{doc_id}` | Delete a document and all its chunks |

**POST /query response:**
```json
{
  "answer": "The report concludes… [report.pdf, page 3]",
  "sources": [
    {
      "filename": "report.pdf",
      "page_number": 3,
      "chunk_text": "…",
      "rerank_score": 4.821
    }
  ],
  "confidence": 0.847,
  "retrieval_stats": {
    "vector_hits": 20,
    "bm25_hits": 14,
    "after_rrf": 15,
    "after_rerank": 5
  }
}
```

---

## Retrieval Pipeline

| Stage | What happens |
|-------|-------------|
| ① Vector search | Question embedded with `nomic-embed-text`; top-20 chunks retrieved from ChromaDB by cosine similarity |
| ② BM25 search | Same question searched against a persisted BM25Okapi index; top-20 chunks returned |
| ③ RRF fusion | Both ranked lists merged with Reciprocal Rank Fusion (k=60); top-15 candidates selected |
| ④ Cross-encoder rerank | `cross-encoder/ms-marco-MiniLM-L-6-v2` scores each candidate against the query; reranked to top-k |
| ⑤ Generation | Cited-answer prompt sent to Ollama tinyllama with the reranked context |
| ⑥ Citation enforcement | Any `[filename, page N]` tag not matching a retrieved source is stripped from the answer |

---

## Example Queries

- *"What are the key findings of this report?"*
- *"Summarize the methodology section."*
- *"What dates or deadlines are mentioned?"*
- *"Who are the authors or contributors?"*

---

## Confidence Score

| Badge | Range | Meaning |
|-------|-------|---------|
| 🟢 High Confidence | ≥ 0.80 | Cross-encoder scored retrieved chunks as highly relevant |
| 🟡 Medium Confidence | 0.50 – 0.79 | Partial match; review sources |
| 🔴 Low Confidence | < 0.50 | Weak match; answer may be unreliable |

---

## Eval Pipeline

No manual labelling needed — the pipeline evaluates itself.

```bash
# Step 1: auto-generate Q&A pairs from whatever is currently ingested
python -m eval.generate_cases --max-cases 20

# Step 2a: quick mode — mocked LLM, safe for CI (no GPU required)
python -m eval.run_evals --quick

# Step 2b: full mode — LLM-as-judge scores every answer on faithfulness + relevance
python -m eval.run_evals --full --backend-url http://localhost:8000
```

**How it works:**
- `generate_cases.py` pulls chunks from ChromaDB and calls the local LLM to write a question and ground-truth answer for each chunk automatically
- `llm_judge.py` scores the pipeline's answers against those ground-truth answers on two axes: **Faithfulness** (does the answer stick to the sources?) and **Relevance** (does it actually answer the question?)
- Scores are appended to `eval/scores_history.jsonl` on every run so quality regressions are visible across commits
- CI runs case generation + full eval on every push to main via `.github/workflows/eval.yml` and fails the build if thresholds are not met

---

## Note: Migrating from a previous version

If you have an existing `chroma_db/` folder from a previous version, delete it before starting:

```bash
rm -rf chroma_db/
```

The BM25 index (`chroma_db/bm25_index.pkl`) is rebuilt automatically on first ingest.

---

## Demo
<img width="561" height="427" alt="DocMind Demo" src="https://github.com/user-attachments/assets/3853cdee-17ce-4b77-beb4-639db9bfce68" />

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Streamlit |
| Backend | FastAPI + uvicorn |
| Orchestration | LlamaIndex (load + chunk) |
| Embeddings | Ollama nomic-embed-text |
| Sparse retrieval | rank-bm25 (BM25Okapi) |
| Reranking | sentence-transformers (MiniLM cross-encoder) |
| LLM | Ollama tinyllama |
| Vector DB | ChromaDB (persistent) |
| HTTP client | httpx |
| Containerization | Docker + docker-compose |
| CI / Eval | GitHub Actions + custom eval pipeline |
