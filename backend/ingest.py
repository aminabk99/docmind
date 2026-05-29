import os
import uuid
import tempfile
from datetime import datetime, timezone

import chromadb
from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter
from openai import OpenAI

from backend.config import (
    OPENAI_API_KEY,
    CHROMA_DB_PATH,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
)


def get_chroma_collection() -> chromadb.Collection:
    """Return (or create) the persistent ChromaDB collection with cosine similarity."""
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def ingest_pdf(file_bytes: bytes, original_filename: str) -> dict:
    """
    Load a PDF, split into chunks, embed with OpenAI, and store in ChromaDB.
    Returns {doc_id, filename, chunk_count}.
    """
    doc_id = str(uuid.uuid4())
    upload_time = datetime.now(timezone.utc).isoformat()

    # Write to a temp file with delete=False — required on Windows to avoid
    # file-locking conflicts when LlamaIndex opens the path independently.
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(file_bytes)
    tmp_path = tmp.name
    tmp.close()

    try:
        documents = SimpleDirectoryReader(input_files=[tmp_path]).load_data()

        splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
        nodes = splitter.get_nodes_from_documents(documents)

        texts = [node.get_content() for node in nodes]
        if not texts:
            return {"doc_id": doc_id, "filename": original_filename, "chunk_count": 0}

        # Single batched embedding call — OpenAI allows up to 2048 inputs.
        # For very large documents, split into batches of 500 to be safe.
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        embeddings = []
        batch_size = 500
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = openai_client.embeddings.create(
                model=EMBEDDING_MODEL, input=batch
            )
            embeddings.extend([item.embedding for item in response.data])

        collection = get_chroma_collection()

        ids, metadatas = [], []
        for idx, node in enumerate(nodes):
            # page_label is a 1-based string in llama-index>=0.10 with pypdf;
            # older versions used 'page' (0-based int). Cascade handles both.
            raw_page = (
                node.metadata.get("page_label")
                or node.metadata.get("page")
                or node.metadata.get("page_number")
                or 1
            )
            try:
                page_number = int(raw_page)
                # If the value was 0-indexed (older LlamaIndex), convert to 1-based
                if page_number == 0:
                    page_number = 1
            except (ValueError, TypeError):
                page_number = 1

            ids.append(f"{doc_id}_{idx}")
            metadatas.append(
                {
                    "doc_id": doc_id,
                    "filename": original_filename,
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

    return {
        "doc_id": doc_id,
        "filename": original_filename,
        "chunk_count": len(nodes),
    }
