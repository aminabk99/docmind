# M365Mind

**Local AI for Microsoft 365 Governance** — query your tenant's Conditional Access policies, Sensitivity Labels, and Named Locations using natural language. Everything runs on your machine. No data leaves your environment.

---

## Why local?

Governance policies contain regulated, confidential data — who can access what, from where, under which conditions. Sending that to a cloud AI service is often a compliance violation. M365Mind runs Phi-3.5-mini locally so your policies never leave the machine.

---

## Features

- **Two modes** — explore with realistic demo data, or connect your real Microsoft 365 tenant via OAuth2
- **Hybrid RAG pipeline** — BM25 sparse + ChromaDB vector search → Reciprocal Rank Fusion → cross-encoder reranking → Phi-3.5-mini
- **Microsoft Graph API** — pulls Conditional Access policies, Named Locations, and Sensitivity Labels directly from your tenant
- **Citation enforcement** — every answer is grounded in retrieved policy chunks; hallucinated citations are stripped
- **p50/p95/p99 latency monitoring** — per-stage metrics (embed, vector, BM25, rerank, LLM) via `/metrics`
- **No Ollama, no API keys** — Phi-3.5-mini (MIT licence) and nomic-embed-text load via HuggingFace on first run (~7.6 GB)

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/aminabk99/docmind
cd docmind
pip install -r requirements.txt
```

> First run downloads Phi-3.5-mini (~7.6 GB). GPU is used if available; CPU works but is slower.

### 2. Configure environment

```bash
cp .env.example .env
```

For **demo mode** you don't need to fill in anything. For **real-tenant mode**, register an app in [Azure Portal → Entra ID → App registrations](https://portal.azure.com) and add:

```
AZURE_CLIENT_ID=<your-app-client-id>
AZURE_TENANT_ID=<your-tenant-id>
AZURE_CLIENT_SECRET=<your-client-secret>
```

Required API permissions: `Policy.Read.All`, `InformationProtectionPolicy.Read.All`  
Redirect URI: `http://localhost:8000/callback`

### 3. Start the app

```bash
# Terminal 1 — backend
uvicorn backend.main:app --reload

# Terminal 2 — frontend
streamlit run frontend/app.py
```

Open [http://localhost:8501](http://localhost:8501).

---

## Try the demo

Click **Launch Demo** on the landing screen — no Microsoft account needed. Sample policies load instantly and cover:

- 8 Conditional Access policies (MFA, device compliance, legacy auth block, country restrictions, sign-in risk)
- 3 Named Locations (trusted office IPs, VPN, high-risk countries)
- 6 Sensitivity Labels (Public → Highly Confidential sublabels)

Try asking: *"Which policies require MFA?"* or *"Are legacy protocols blocked?"*

---

## Architecture

```
User question
      │
      ▼
 Embed (nomic-embed-text · sentence-transformers)
      │
      ├── Vector search (ChromaDB cosine, top-20)
      └── Sparse search (BM25Okapi, top-20)
                        │
                  RRF Fusion (k=60)
                        │
             Cross-encoder reranking
             (ms-marco-MiniLM-L-6-v2)
                        │
              Phi-3.5-mini (local)
                        │
            Citation enforcement
                        │
               Answer + Sources
```

Policy data path (real tenant):
```
Microsoft Graph API → graph_client.py → policy_formatter.py → ingest_text() → ChromaDB
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/demo/load` | Load sample policies |
| `GET` | `/demo/status` | Check if demo data is loaded |
| `GET` | `/auth-url` | Get Microsoft OAuth2 login URL |
| `GET` | `/callback` | OAuth2 redirect handler |
| `GET` | `/auth-status?sid=` | Check session connection |
| `POST` | `/sync` | Pull policies from tenant |
| `POST` | `/query` | Ask a question |
| `GET` | `/documents` | List loaded policies |
| `DELETE` | `/documents/{doc_id}` | Remove a policy |
| `GET` | `/metrics` | p50/p95/p99 latency stats |

---

## Tech stack

| Component | Technology |
|-----------|-----------|
| LLM | Phi-3.5-mini-instruct (Microsoft, MIT) |
| Embeddings | nomic-embed-text-v1.5 (HuggingFace) |
| Vector store | ChromaDB |
| Sparse retrieval | BM25Okapi (rank-bm25) |
| Reranker | MiniLM cross-encoder (sentence-transformers) |
| M365 auth | MSAL Python |
| Graph API | Microsoft Graph v1.0 |
| Backend | FastAPI + Uvicorn |
| Frontend | Streamlit |
