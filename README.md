# DocMind

A RAG-powered document intelligence web app. Upload PDFs, ask natural-language questions, and get cited answers with confidence scores — all backed by OpenAI embeddings, ChromaDB, and GPT-4o-mini.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Streamlit UI                             │
│  Sidebar: upload PDF, list/delete docs                          │
│  Main:    question input → answer + cited sources + confidence  │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP (httpx)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                            │
│                                                                 │
│  POST /upload      ──► ingest.py                                │
│                        LlamaIndex SimpleDirectoryReader         │
│                        SentenceSplitter (512 tokens, 50 overlap)│
│                        OpenAI text-embedding-3-small            │
│                        ChromaDB .add()                          │
│                                                                 │
│  POST /query       ──► retrieval.py                             │
│                        OpenAI embed question                    │
│                        ChromaDB cosine search (top-K)           │
│                        GPT-4o-mini with cited-answer prompt     │
│                        confidence = mean(cosine similarities)   │
│                                                                 │
│  GET  /documents   ──► list all uploaded docs                   │
│  DELETE /documents/{id} ──► remove doc + chunks                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   ChromaDB      │
                    │  (./chroma_db)  │
                    │  cosine index   │
                    └─────────────────┘
```

---

## Setup (local)

**1. Clone and configure**

```bash
git clone <your-repo-url>
cd docmind
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Run the backend**

```bash
uvicorn backend.main:app --reload
# API available at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

**4. Run the frontend** (new terminal)

```bash
streamlit run frontend/app.py
# UI available at http://localhost:8501
```

---

## Setup (Docker)

```bash
cp .env.example .env   # add your OPENAI_API_KEY
docker-compose up --build
```

| Service  | URL                    |
|----------|------------------------|
| Frontend | http://localhost:8501  |
| Backend  | http://localhost:8000  |
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
  "answer": "The policy states… [report.pdf, page 3]",
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
| 🟢 High | ≥ 0.80 | Retrieved chunks are highly relevant |
| 🟡 Medium | 0.50 – 0.79 | Partial match; review sources |
| 🔴 Low | < 0.50 | Weak match; answer may be unreliable |

The score is the average cosine similarity between the query embedding and the retrieved chunk embeddings.

---

## Demo

<!-- Replace with your actual GIF -->
![DocMind Demo](demo.gif)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Streamlit |
| Backend | FastAPI + uvicorn |
| Orchestration | LlamaIndex (load + chunk) |
| Embeddings | OpenAI text-embedding-3-small |
| LLM | GPT-4o-mini |
| Vector DB | ChromaDB (persistent) |
| HTTP client | httpx |
| Containerization | Docker + docker-compose |
