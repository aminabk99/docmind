"""
Ingestion pipeline for M365Mind.

Changes from original
---------------------
- After every add OR delete, BM25Store.rebuild() is called so the sparse
  index stays in sync with ChromaDB.
- delete_document() is now defined here (moved from main.py) so both
  operations (ChromaDB delete + BM25 rebuild) are colocated.
"""

import os
import uuid
import tempfile
from datetime import datetime, timezone

import chromadb
from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter

from backend.config import (
    CHROMA_DB_PATH,
    COLLECTION_NAME,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
)
from backend.embeddings import embed, embed_batch


def get_chroma_collection() -> chromadb.Collection:
    """Return (or create) the persistent ChromaDB collection with cosine similarity."""
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def ingest_pdf(file_bytes: bytes, original_filename: str) -> dict:
    """
    Load a PDF, split into chunks, embed with sentence-transformers nomic-embed-text-v1.5,
    store in ChromaDB, then rebuild the BM25 index.

    Returns {doc_id, filename, chunk_count}.
    """
    doc_id      = str(uuid.uuid4())
    upload_time = datetime.now(timezone.utc).isoformat()

    # delete=False required on Windows — LlamaIndex needs to open the path
    # independently, and Windows locks the file while the handle is open.
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(file_bytes)
    tmp_path = tmp.name
    tmp.close()

    try:
        documents = SimpleDirectoryReader(input_files=[tmp_path]).load_data()

        splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
        nodes    = splitter.get_nodes_from_documents(documents)

        texts = [node.get_content() for node in nodes]
        if not texts:
            return {"doc_id": doc_id, "filename": original_filename, "chunk_count": 0}

        embeddings = embed_batch(texts)

        collection = get_chroma_collection()

        ids, metadatas = [], []
        for idx, node in enumerate(nodes):
            raw_page = (
                node.metadata.get("page_label")
                or node.metadata.get("page")
                or node.metadata.get("page_number")
                or 1
            )
            try:
                page_number = int(raw_page)
                if page_number == 0:
                    page_number = 1
            except (ValueError, TypeError):
                page_number = 1

            ids.append(f"{doc_id}_{idx}")
            metadatas.append(
                {
                    "doc_id":      doc_id,
                    "filename":    original_filename,
                    "page_number": page_number,
                    "chunk_index": idx,
                    "upload_time": upload_time,
                }
            )

        collection.add(
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )
    finally:
        os.unlink(tmp_path)

    # ------------------------------------------------------------------ #
    # Keep BM25 in sync — import here to avoid circular import at load    #
    # ------------------------------------------------------------------ #
    from backend.bm25_store import get_bm25_store
    get_bm25_store().rebuild()

    return {
        "doc_id":      doc_id,
        "filename":    original_filename,
        "chunk_count": len(nodes),
    }


def ingest_text(
    text: str,
    display_name: str,
    source_type: str = "graph_api",
    policy_type: str = "policy",
    doc_id: str | None = None,
) -> dict:
    """
    Ingest pre-formatted plain text (e.g. a Graph API policy) into ChromaDB.

    Used for Microsoft Graph API policy data which arrives as structured JSON
    and is pre-converted to readable text by backend/policy_formatter.py.

    Parameters
    ----------
    text         : the policy content as a readable string
    display_name : human-readable name (e.g. "Require MFA for External Users")
    source_type  : "graph_api" or "demo"
    policy_type  : "conditional_access" | "sensitivity_label" | "named_location"
    doc_id       : optional stable ID (e.g. the Graph API object id)

    Returns
    -------
    {doc_id, filename, chunk_count}
    """
    doc_id      = doc_id or str(uuid.uuid4())
    upload_time = datetime.now(timezone.utc).isoformat()

    from llama_index.core import Document as LIDocument
    splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    nodes    = splitter.get_nodes_from_documents([LIDocument(text=text)])

    texts = [node.get_content() for node in nodes]
    if not texts:
        return {"doc_id": doc_id, "filename": display_name, "chunk_count": 0}

    embeddings = embed_batch(texts)
    collection = get_chroma_collection()

    ids, metadatas = [], []
    for idx in range(len(texts)):
        ids.append(f"{doc_id}_{idx}")
        metadatas.append(
            {
                "doc_id":      doc_id,
                "filename":    display_name,
                "page_number": idx + 1,   # section number for policies
                "chunk_index": idx,
                "upload_time": upload_time,
                "source_type": source_type,
                "policy_type": policy_type,
            }
        )

    collection.add(
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
        ids=ids,
    )

    from backend.bm25_store import get_bm25_store
    get_bm25_store().rebuild()

    return {"doc_id": doc_id, "filename": display_name, "chunk_count": len(texts)}


def delete_document(doc_id: str) -> dict:
    """
    Remove all chunks for doc_id from ChromaDB and rebuild the BM25 index.

    Returns {"deleted_chunks": int}.
    Raises ValueError if doc_id is not found.
    """
    collection = get_chroma_collection()
    results    = collection.get(where={"doc_id": doc_id}, include=[])
    ids_to_delete = results["ids"]

    if not ids_to_delete:
        raise ValueError(f"Document '{doc_id}' not found.")

    collection.delete(ids=ids_to_delete)

    from backend.bm25_store import get_bm25_store
    get_bm25_store().rebuild()

    return {"deleted_chunks": len(ids_to_delete)}
