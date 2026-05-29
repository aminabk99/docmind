from llama_index.core.llms import ChatMessage
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama

from backend.config import (
    OLLAMA_BASE_URL,
    EMBEDDING_MODEL,
    LLM_MODEL,
)
from backend.ingest import get_chroma_collection

SYSTEM_PROMPT = """You are DocMind, a precise document analysis assistant.
Answer the user's question using ONLY the provided context chunks.
For every factual claim, cite the source using the format: [filename, page N].
If the context does not contain enough information, respond with:
"I could not find sufficient information in the uploaded documents to answer this question."
Do not fabricate information. Be concise but complete."""


def _doc_filter(doc_ids: list[str]) -> dict:
    """Build a ChromaDB where-filter for one or more doc_ids."""
    if len(doc_ids) == 1:
        return {"doc_id": doc_ids[0]}
    return {"doc_id": {"$in": doc_ids}}


def _embed(text: str) -> list[float]:
    embed_model = OllamaEmbedding(
        model_name=EMBEDDING_MODEL,
        base_url=OLLAMA_BASE_URL,
    )
    return embed_model.get_text_embedding(text)


def answer_question(
    question: str,
    top_k: int = 5,
    doc_ids: list[str] | None = None,
) -> dict:
    """
    Embed the question, retrieve top-k chunks (optionally scoped to doc_ids),
    call llama3.2:1b via Ollama, return {answer, sources, confidence}.
    """
    # Empty doc_ids means this chat has no documents yet
    if doc_ids is not None and len(doc_ids) == 0:
        return {
            "answer": "No documents in this chat yet. Upload a PDF using the input below.",
            "sources": [],
            "confidence": 0.0,
        }

    collection = get_chroma_collection()

    # Count how many chunks are in scope
    if doc_ids:
        scoped = collection.get(
            where=_doc_filter(doc_ids), include=[], limit=100_000
        )
        total = len(scoped["ids"])
    else:
        total = collection.count()

    if total == 0:
        return {
            "answer": "No documents have been uploaded yet. Upload a PDF to get started.",
            "sources": [],
            "confidence": 0.0,
        }

    actual_k = min(top_k, total)
    query_embedding = _embed(question)

    query_kwargs: dict = dict(
        query_embeddings=[query_embedding],
        n_results=actual_k,
        include=["documents", "metadatas", "distances"],
    )
    if doc_ids:
        query_kwargs["where"] = _doc_filter(doc_ids)

    results = collection.query(**query_kwargs)

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    # ChromaDB cosine distance ∈ [0, 2] → similarity ∈ [0, 1]
    similarities = [round(1.0 - d / 2.0, 4) for d in results["distances"][0]]

    context_parts = []
    for i, (doc, meta) in enumerate(zip(docs, metas)):
        context_parts.append(
            f"[Source {i + 1}: {meta['filename']}, page {meta['page_number']}]\n{doc}"
        )
    context_str = "\n\n---\n\n".join(context_parts)
    user_message = f"Context:\n{context_str}\n\nQuestion: {question}"

    llm = Ollama(
        model=LLM_MODEL,
        base_url=OLLAMA_BASE_URL,
        request_timeout=120.0,
    )
    response = llm.chat([
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_message),
    ])
    answer = response.message.content

    confidence = round(sum(similarities) / len(similarities), 4)

    sources = [
        {"filename": meta["filename"], "page_number": meta["page_number"], "chunk_text": doc}
        for doc, meta in zip(docs, metas)
    ]

    return {"answer": answer, "sources": sources, "confidence": confidence}
