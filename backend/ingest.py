import os
import uuid
import tempfile
from datetime import datetime, timezone

import chromadb
from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.ollama import OllamaEmbedding

from backend.config import (
    OLLAMA_BASE_URL,
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
    Load a PDF, split into chunks, embed with Ollama nomic-embed-text, store in ChromaDB.
    Returns {doc_id, filename, chunk_count}.
    """
    doc_id = str(uuid.uuid4())
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
        nodes = splitter.get_nodes_from_documents(documents)

        texts = [node.get_content() for node in nodes]
        if not texts:
            return {"doc_id": doc_id, "filename": original_filename, "chunk_count": 0}

        embed_model = OllamaEmbedding(
            model_name=EMBEDDING_MODEL,
            base_url=OLLAMA_BASE_URL,
        )
        embeddings = embed_model.get_text_embedding_batch(texts, show_progress=False)

        collection = get_chroma_collection()

        ids, metadatas = [], []
        for idx, node in enumerate(nodes):
            # page_label is 1-based string in llama-index>=0.10; 'page' is
            # 0-based int in older versions. Cascade handles both.
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
