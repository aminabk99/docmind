from openai import OpenAI

from backend.config import (
    OPENAI_API_KEY,
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


def _embed(text: str) -> list[float]:
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
    return response.data[0].embedding


def answer_question(question: str, top_k: int = 5) -> dict:
    """
    Embed the question, retrieve top-k chunks from ChromaDB, call GPT-4o-mini,
    and return {answer, sources, confidence}.
    """
    collection = get_chroma_collection()
    total = collection.count()

    if total == 0:
        return {
            "answer": "No documents have been uploaded yet. Please upload a PDF first.",
            "sources": [],
            "confidence": 0.0,
        }

    # Guard: ChromaDB raises if n_results > number of stored embeddings.
    actual_k = min(top_k, total)

    query_embedding = _embed(question)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=actual_k,
        include=["documents", "metadatas", "distances"],
    )

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    # ChromaDB cosine distance is in [0, 2]; convert to similarity in [0, 1].
    similarities = [round(1.0 - d / 2.0, 4) for d in results["distances"][0]]

    # Build numbered context for the LLM prompt.
    context_parts = []
    for i, (doc, meta) in enumerate(zip(docs, metas)):
        context_parts.append(
            f"[Source {i + 1}: {meta['filename']}, page {meta['page_number']}]\n{doc}"
        )
    context_str = "\n\n---\n\n".join(context_parts)

    user_message = f"Context:\n{context_str}\n\nQuestion: {question}"

    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    completion = openai_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
        max_tokens=1024,
    )
    answer = completion.choices[0].message.content

    confidence = round(sum(similarities) / len(similarities), 4)

    sources = [
        {
            "filename": meta["filename"],
            "page_number": meta["page_number"],
            "chunk_text": doc,
        }
        for doc, meta in zip(docs, metas)
    ]

    return {"answer": answer, "sources": sources, "confidence": confidence}
