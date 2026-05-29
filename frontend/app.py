import os

import httpx
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="DocMind", page_icon="📄", layout="wide")

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "documents" not in st.session_state:
    st.session_state.documents = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch_documents():
    try:
        r = httpx.get(f"{BACKEND_URL}/documents", timeout=10)
        r.raise_for_status()
        st.session_state.documents = r.json()
    except Exception as exc:
        st.sidebar.error(f"Could not load document list: {exc}")


def confidence_badge(score: float) -> str:
    pct = f"{score:.0%}"
    if score >= 0.8:
        return f":green[**High confidence** — {pct}]"
    elif score >= 0.5:
        return f":orange[**Medium confidence** — {pct}]"
    else:
        return f":red[**Low confidence** — {pct}]"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📄 DocMind")
    st.caption("RAG-powered document intelligence")
    st.divider()

    # --- Upload ---
    st.subheader("Upload Document")
    uploaded_file = st.file_uploader(
        "Choose a PDF file", type=["pdf"], key="pdf_uploader"
    )
    if uploaded_file is not None:
        if st.button("Upload", use_container_width=True):
            with st.spinner("Ingesting document…"):
                try:
                    r = httpx.post(
                        f"{BACKEND_URL}/upload",
                        files={
                            "file": (
                                uploaded_file.name,
                                uploaded_file.getvalue(),
                                "application/pdf",
                            )
                        },
                        timeout=120,
                    )
                    r.raise_for_status()
                    data = r.json()
                    st.success(
                        f"✅ **{data['filename']}** ingested — {data['chunk_count']} chunks"
                    )
                    fetch_documents()
                except httpx.HTTPStatusError as exc:
                    st.error(f"Upload failed: {exc.response.text}")
                except Exception as exc:
                    st.error(f"Upload error: {exc}")

    st.divider()

    # --- Document list ---
    st.subheader("Uploaded Documents")
    fetch_documents()

    if not st.session_state.documents:
        st.caption("No documents uploaded yet.")
    else:
        for doc in st.session_state.documents:
            col1, col2 = st.columns([3, 1])
            col1.markdown(f"**{doc['filename']}**")
            col1.caption(f"{doc['chunk_count']} chunks")
            if col2.button("🗑", key=f"del_{doc['doc_id']}", help="Delete document"):
                try:
                    r = httpx.delete(
                        f"{BACKEND_URL}/documents/{doc['doc_id']}", timeout=10
                    )
                    r.raise_for_status()
                    st.success("Deleted.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Delete failed: {exc}")

# ---------------------------------------------------------------------------
# Main — Q&A
# ---------------------------------------------------------------------------

st.title("Ask Your Documents")
st.caption("Upload PDFs in the sidebar, then ask questions below.")

col_input, col_topk = st.columns([5, 1])
question = col_input.text_input(
    "Your question",
    placeholder="What does the document say about…?",
    label_visibility="collapsed",
)
top_k = col_topk.number_input("Top K", min_value=1, max_value=20, value=5)

if st.button("Ask", type="primary", use_container_width=False):
    if not question.strip():
        st.warning("Please enter a question.")
    else:
        with st.spinner("Thinking…"):
            try:
                r = httpx.post(
                    f"{BACKEND_URL}/query",
                    json={"question": question, "top_k": int(top_k)},
                    timeout=60,
                )
                r.raise_for_status()
                result = r.json()
                st.session_state.chat_history.append(
                    {"question": question, **result}
                )
            except httpx.HTTPStatusError as exc:
                st.error(f"Query failed: {exc.response.text}")
            except Exception as exc:
                st.error(f"Query error: {exc}")

# ---------------------------------------------------------------------------
# Chat history (most recent first)
# ---------------------------------------------------------------------------

for item in reversed(st.session_state.chat_history):
    st.divider()
    st.markdown(f"**Q:** {item['question']}")
    st.markdown(f"**A:** {item['answer']}")
    st.markdown(confidence_badge(item["confidence"]))

    sources = item.get("sources", [])
    if sources:
        with st.expander(f"Sources — {len(sources)} chunk(s)"):
            for src in sources:
                st.markdown(f"**{src['filename']}** — Page {src['page_number']}")
                preview = src["chunk_text"]
                if len(preview) > 500:
                    preview = preview[:500] + "…"
                st.caption(preview)
                st.divider()
