from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.ingest import get_chroma_collection, ingest_pdf
from backend.retrieval import answer_question

app = FastAPI(title="DocMind API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    doc_ids: list[str] | None = None  # scoped to this chat's documents when provided


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
        return answer_question(request.question, request.top_k, request.doc_ids)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}") from exc


# ---------------------------------------------------------------------------
# GET /documents
# ---------------------------------------------------------------------------

@app.get("/documents")
async def list_documents():
    try:
        collection = get_chroma_collection()
        results = collection.get(include=["metadatas"], limit=10_000)
        if not results["metadatas"]:
            return []

        docs: dict[str, dict] = {}
        for meta in results["metadatas"]:
            did = meta["doc_id"]
            if did not in docs:
                docs[did] = {
                    "doc_id": did,
                    "filename": meta["filename"],
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
async def delete_document(doc_id: str):
    try:
        collection = get_chroma_collection()
        results = collection.get(where={"doc_id": doc_id}, include=[])
        ids_to_delete = results["ids"]
        if not ids_to_delete:
            raise HTTPException(status_code=404, detail="Document not found.")
        collection.delete(ids=ids_to_delete)
        return {"deleted_chunks": len(ids_to_delete)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Delete failed: {exc}") from exc
