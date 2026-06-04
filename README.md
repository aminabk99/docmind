# DocMind

A RAG-powered document intelligence web app that runs **fully locally** — no API keys, no cloud, no cost. Upload PDFs, ask natural-language questions, and get cited answers with confidence scores.

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
│                        ChromaDB .add()                          │
│                                                                 │
│  POST /query       ──► retrieval.py                             │
│                        Ollama nomic-embed-text (embed question) │
│                        ChromaDB cosine search (top-5)           │
│                        Ollama llama3.2 (cited-answer prompt)    │
│                        confidence = mean(cosine similarities)   │
│                                                                 │
│  GET  /documents   ──► list all uploaded docs                   │
│  DELETE /documents/{id} ──► remove doc + chunks                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────┐
              │   ChromaDB (./chroma_db) │
              │   Ollama (localhost:11434)│
              └──────────────────────────┘
```

---

## Setup

### 1. Install Ollama

Download from [ollama.com](https://ollama.com) and install it, then pull the required models:

```bash
ollama pull llama3.2
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
    {"filename": "report.pdf", "page_number": 3, "chunk_text": "…"}
  ],
  "confidence": 0.847
}
```

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
| 🟢 High Confidence | ≥ 0.80 | Retrieved chunks are highly relevant |
| 🟡 Medium Confidence | 0.50 – 0.79 | Partial match; review sources |
| 🔴 Low Confidence | < 0.50 | Weak match; answer may be unreliable |

---

## Note: Migrating from a previous version

If you ran the OpenAI version and have an existing `chroma_db/` folder, delete it before starting — the embedding dimensions changed (OpenAI: 1536-dim → nomic-embed-text: 768-dim) and ChromaDB will reject the mismatch:

```bash
rm -rf chroma_db/
```

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
| LLM | Ollama llama3.2 |
| Vector DB | ChromaDB (persistent) |
| HTTP client | httpx |
| Containerization | Docker + docker-compose |
