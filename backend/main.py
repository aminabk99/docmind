from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from pydantic import BaseModel
from pathlib import Path

from backend.ingest import delete_document, get_chroma_collection, ingest_pdf
from backend.retrieval import answer_question
from monitoring.metrics import compute_metrics

app = FastAPI(title="M365Mind API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Startup warmup
# ---------------------------------------------------------------------------
# The embedding model, cross-encoder reranker, and Ollama LLM all load lazily
# on first use — tens of seconds cold. Without warmup, the *user's* first
# action (Launch Demo, or the first question) pays that entire cost, which is
# why the app felt like it "took forever". Warming them in a background thread
# at boot moves that cost off the request path: uvicorn starts immediately, the
# models load while the page is still rendering, and the first real request is
# fast. If a request arrives before warmup finishes it simply loads lazily as
# before — never worse than the old behaviour.

@app.on_event("startup")
async def _warmup_models() -> None:
    import threading, time

    def _warm() -> None:
        t0 = time.perf_counter()
        try:
            from backend.embeddings import embed
            embed("warmup")                       # loads the embedding model
        except Exception as exc:
            print(f"[warmup] embedding warm failed: {exc}")
        try:
            from backend.reranker import rerank
            rerank("warmup", [{"text": "warmup", "chunk_id": "w", "metadata": {}}], top_k=1)
        except Exception as exc:
            print(f"[warmup] reranker warm failed: {exc}")
        try:
            from backend.generation import prime
            prime()                               # loads the LLM into Ollama memory
        except Exception as exc:
            print(f"[warmup] llm prime failed: {exc}")
        print(f"[warmup] models warm in {time.perf_counter() - t0:.1f}s — first request will be fast.")

    threading.Thread(target=_warm, name="model-warmup", daemon=True).start()


# ---------------------------------------------------------------------------
# Frontend — the chat UI (replaces the Streamlit app)
# ---------------------------------------------------------------------------
_FRONTEND = Path(__file__).parent.parent / "frontend" / "index.html"


@app.get("/", response_class=HTMLResponse)
@app.get("/app", response_class=HTMLResponse)
async def serve_frontend():
    if not _FRONTEND.exists():
        raise HTTPException(status_code=404, detail="frontend/index.html not found")
    return FileResponse(_FRONTEND, media_type="text/html")


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    doc_ids: list[str] | None = None
    synthesize: bool = False   # False = instant retrieval; True = LLM summary


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    if file.size and file.size > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit.")
    try:
        contents = await file.read()
        result = ingest_pdf(contents, file.filename)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc


# ---------------------------------------------------------------------------
# POST /query
# ---------------------------------------------------------------------------

@app.post("/query")
async def query_documents(request: QueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if not (1 <= request.top_k <= 20):
        raise HTTPException(status_code=400, detail="top_k must be between 1 and 20.")
    try:
        return answer_question(request.question, request.top_k, request.doc_ids, request.synthesize)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}") from exc


# ---------------------------------------------------------------------------
# GET /documents
# ---------------------------------------------------------------------------

@app.get("/documents")
async def list_documents():
    try:
        collection = get_chroma_collection()
        results    = collection.get(include=["metadatas"], limit=10_000)
        if not results["metadatas"]:
            return []

        docs: dict[str, dict] = {}
        for meta in results["metadatas"]:
            did = meta["doc_id"]
            if did not in docs:
                docs[did] = {
                    "doc_id":      did,
                    "filename":    meta["filename"],
                    "chunk_count": 0,
                    "upload_time": meta.get("upload_time", ""),
                }
            docs[did]["chunk_count"] += 1

        return list(docs.values())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"List failed: {exc}") from exc


# ---------------------------------------------------------------------------
# DELETE /documents/{doc_id}
# ---------------------------------------------------------------------------

@app.delete("/documents/{doc_id}")
async def delete_document_endpoint(doc_id: str):
    try:
        return delete_document(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Delete failed: {exc}") from exc


# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------

@app.get("/metrics")
async def get_metrics(last_n: int = 1000):
    """
    Returns p50/p95/p99 latency, per-stage breakdown, token stats,
    and quality metrics computed from the last N requests in traces.jsonl.
    """
    try:
        return compute_metrics(last_n=last_n)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Metrics computation failed: {exc}") from exc


# ---------------------------------------------------------------------------
# M365 AUTH  —  GET /auth-url
# ---------------------------------------------------------------------------

@app.get("/auth-url")
async def get_auth_url():
    """Return the Microsoft OAuth2 login URL."""
    from backend.config import AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_SECRET
    if not AZURE_CLIENT_ID or not AZURE_TENANT_ID or not AZURE_CLIENT_SECRET:
        raise HTTPException(
            status_code=400,
            detail="Azure credentials not configured. Add AZURE_CLIENT_ID, AZURE_TENANT_ID, and AZURE_CLIENT_SECRET to your .env file."
        )
    try:
        from backend.auth import get_auth_url as _get_auth_url
        url = _get_auth_url()
        return {"url": url}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auth URL generation failed: {exc}") from exc


# ---------------------------------------------------------------------------
# M365 AUTH  —  GET /callback  (Microsoft redirects here after login)
# ---------------------------------------------------------------------------

@app.get("/callback")
async def oauth_callback(code: str = Query(...), state: str = Query(default="")):
    """
    Exchange the authorisation code for an access token.
    Redirects to the Streamlit frontend with the session ID as a query param.
    """
    try:
        from backend.auth import exchange_code
        session_id = exchange_code(code)
        redirect_url = f"http://localhost:8501?m365_connected=true&sid={session_id}"
        return RedirectResponse(url=redirect_url)
    except Exception as exc:
        error_url = f"http://localhost:8501?m365_error={str(exc)[:200]}"
        return RedirectResponse(url=error_url)


# ---------------------------------------------------------------------------
# M365 AUTH  —  GET /auth-status
# ---------------------------------------------------------------------------

@app.get("/auth-status")
async def auth_status(sid: str = Query(...)):
    """Return whether a session has a valid token."""
    try:
        from backend.auth import is_connected
        return {"connected": is_connected(sid)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# M365 SYNC  —  POST /sync
# ---------------------------------------------------------------------------

class SyncRequest(BaseModel):
    sid: str   # session ID returned by /callback

@app.post("/sync")
async def sync_policies(request: SyncRequest):
    """
    Pull all governance policies from the tenant and ingest them.
    Requires a valid session (user must have completed OAuth login first).
    """
    try:
        from backend.auth import get_token
        from backend.graph_client import pull_all
        from backend.policy_formatter import format_policy
        from backend.ingest import ingest_text, get_chroma_collection, delete_document

        token = get_token(request.sid)
        if not token:
            raise HTTPException(status_code=401, detail="Session not found or expired. Please reconnect.")

        # Remove previously synced real-tenant data before re-syncing
        collection = get_chroma_collection()
        existing = collection.get(where={"source_type": "graph_api"}, include=[], limit=10_000)
        for doc_id_chunk in existing["ids"]:
            # ids are in format "doc_id_chunkindex" — extract base doc_id
            pass
        # Cleaner approach: delete all graph_api chunks directly
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
            from backend.bm25_store import get_bm25_store
            get_bm25_store().rebuild()

        raw = pull_all(token)

        _TYPE_MAP = {
            "conditional_access": "conditional_access",
            "named_locations":    "named_location",
            "sensitivity_labels": "sensitivity_label",
        }

        results: list[dict] = []
        for section_key, policy_type in _TYPE_MAP.items():
            for item in raw.get(section_key, []):
                display_name, text = format_policy(policy_type, item)
                if not text.strip():
                    continue
                doc_id = f"graph_{policy_type}_{item.get('id', '')}"
                res = ingest_text(
                    text=text,
                    display_name=display_name,
                    source_type="graph_api",
                    policy_type=policy_type,
                    doc_id=doc_id,
                )
                results.append(res)

        total_chunks = sum(r["chunk_count"] for r in results)
        return {
            "synced": len(results),
            "chunks": total_chunks,
            "policies": [r["filename"] for r in results],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Sync failed: {exc}") from exc


# ---------------------------------------------------------------------------
# DEMO  —  POST /demo/load
# ---------------------------------------------------------------------------

@app.post("/demo/load")
async def load_demo():
    """Load pre-built sample M365 policies for the demo mode."""
    try:
        from demo_data.load_demo import load_demo as _load_demo
        result = _load_demo()
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Demo load failed: {exc}") from exc


# ---------------------------------------------------------------------------
# DEMO  —  GET /demo/status
# ---------------------------------------------------------------------------

@app.get("/demo/status")
async def demo_status():
    """Check whether demo data is currently loaded."""
    try:
        collection = get_chroma_collection()
        results = collection.get(where={"source_type": "demo"}, include=[], limit=1)
        loaded = len(results["ids"]) > 0
        return {"demo_loaded": loaded}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
