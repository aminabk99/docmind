import os
import uuid as _uuid

import httpx
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="DocMind",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Styles ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"], button, input, textarea, select {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

#MainMenu, footer, header { visibility: hidden; }

/* ── Dark sidebar ─────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] > div:first-child {
    background: #111827;
    border-right: none;
    padding-top: 1.25rem;
}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] small,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] .stCaption {
    color: #9ca3af !important;
}
section[data-testid="stSidebar"] h3 { color: #f9fafb !important; }
section[data-testid="stSidebar"] hr { border-color: #1f2937; }

/* Sidebar buttons — flat, left-aligned */
section[data-testid="stSidebar"] .stButton > button {
    background: transparent;
    border: none;
    color: #9ca3af;
    text-align: left;
    font-size: 0.875rem;
    font-weight: 400;
    padding: 7px 10px;
    border-radius: 7px;
    width: 100%;
    transition: background 0.12s, color 0.12s;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.07);
    color: #f3f4f6;
    border: none;
}

/* ── Main area ────────────────────────────────────────────────────────── */
.block-container {
    padding-top: 2.5rem !important;
    padding-bottom: 5rem !important;
    max-width: 800px;
}
h2 {
    font-size: 2rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.03em !important;
    color: #0f172a !important;
}

/* Doc chips */
.doc-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    color: #475569;
    padding: 3px 11px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 500;
}

/* Empty state */
.empty-state { text-align: center; padding: 5rem 1rem; }
.empty-state-icon  { font-size: 2.75rem; margin-bottom: 0.75rem; line-height: 1; }
.empty-state-title { font-size: 1.05rem; font-weight: 600; color: #1e293b; margin-bottom: 0.35rem; }
.empty-state-sub   { font-size: 0.875rem; color: #94a3b8; }

/* Answer card tweaks */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px !important;
    border-color: #e2e8f0 !important;
}

/* ── Sidebar toggle buttons ─────────────────────────────────────────────
   Fixed to screen so they're always visible no matter the scroll position.
   Targets both the "expand" button (sidebar closed) and "collapse" button
   (sidebar open). ──────────────────────────────────────────────────────── */

/* EXPAND button — shown when sidebar is collapsed */
[data-testid="collapsedControl"] {
    position: fixed !important;
    top: 50vh !important;
    left: 0 !important;
    transform: translateY(-50%) !important;
    z-index: 9999999 !important;
    background: #ff1493 !important;
    border-radius: 0 16px 16px 0 !important;
    width: 48px !important;
    height: 96px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-shadow: 4px 0 20px rgba(255,20,147,0.6) !important;
    cursor: pointer !important;
    border: none !important;
    padding: 0 !important;
}
[data-testid="collapsedControl"] button {
    background: transparent !important;
    border: none !important;
    width: 100% !important;
    height: 100% !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
[data-testid="collapsedControl"] svg {
    width: 26px !important;
    height: 26px !important;
    fill: white !important;
    stroke: white !important;
}
[data-testid="collapsedControl"] svg * {
    fill: white !important;
    stroke: white !important;
}

/* COLLAPSE button — shown inside the open sidebar */
button[data-testid="baseButton-headerNoPadding"] {
    background: #ff1493 !important;
    border-radius: 10px !important;
    width: 44px !important;
    height: 44px !important;
    border: none !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-shadow: 0 2px 10px rgba(255,20,147,0.5) !important;
}
button[data-testid="baseButton-headerNoPadding"] svg {
    width: 22px !important;
    height: 22px !important;
    fill: white !important;
    stroke: white !important;
}
button[data-testid="baseButton-headerNoPadding"] svg * {
    fill: white !important;
    stroke: white !important;
}
</style>
""", unsafe_allow_html=True)

# ─── Session state ────────────────────────────────────────────────────────────

def _new_chat(name: str = "New Chat") -> dict:
    return {
        "id": str(_uuid.uuid4()),
        "name": name,
        "messages": [],   # [{question, answer, sources, confidence}]
        "doc_ids": [],    # doc UUIDs uploaded to this chat
        "docs": {},       # {doc_id: {filename, chunk_count}}
    }

if "chats" not in st.session_state:
    first = _new_chat()
    st.session_state.chats = [first]
    st.session_state.current_chat_id = first["id"]

if "upload_key" not in st.session_state:
    st.session_state.upload_key = 0
if "last_file_id" not in st.session_state:
    st.session_state.last_file_id = None


def _current_chat() -> dict:
    for c in st.session_state.chats:
        if c["id"] == st.session_state.current_chat_id:
            return c
    # Fallback: return first chat
    return st.session_state.chats[0]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def do_upload(file) -> dict | None:
    """Upload PDF to backend; returns {doc_id, filename, chunk_count} or None."""
    try:
        r = httpx.post(
            f"{BACKEND_URL}/upload",
            files={"file": (file.name, file.getvalue(), "application/pdf")},
            timeout=180,
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        if any(k in detail.lower() for k in ("connection", "refused", "ollama")):
            st.error("Ollama is not running. Start it with `ollama serve`.")
        else:
            st.error(detail)
        return None
    except Exception as exc:
        st.error(str(exc))
        return None


def do_delete(doc_id: str) -> bool:
    try:
        r = httpx.delete(f"{BACKEND_URL}/documents/{doc_id}", timeout=15)
        r.raise_for_status()
        return True
    except Exception as exc:
        st.error(str(exc))
        return False


def confidence_label(score: float) -> tuple[str, str]:
    if score >= 0.8:
        return "High Confidence", "green"
    elif score >= 0.5:
        return "Medium Confidence", "orange"
    else:
        return "Low Confidence", "red"


# ─── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 📄 DocMind")
    st.caption("Local AI · No API keys needed")
    st.divider()

    # New chat
    if st.button("＋  New Chat", use_container_width=True, key="new_chat_btn"):
        nc = _new_chat()
        st.session_state.chats.insert(0, nc)
        st.session_state.current_chat_id = nc["id"]
        st.session_state.last_file_id = None
        st.session_state.upload_key += 1
        st.rerun()

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # Chat list
    for chat in st.session_state.chats:
        is_active = chat["id"] == st.session_state.current_chat_id
        icon = "▸ " if is_active else "   "
        label = f"{icon}{chat['name']}"
        if st.button(label, key=f"chat_{chat['id']}", use_container_width=True):
            if not is_active:
                st.session_state.current_chat_id = chat["id"]
                st.session_state.last_file_id = None
                st.session_state.upload_key += 1
                st.rerun()

    # Files in current chat
    chat = _current_chat()
    if chat["docs"]:
        st.divider()
        st.caption("Files in this chat")
        for doc_id, info in list(chat["docs"].items()):
            c1, c2 = st.columns([5, 1])
            c1.caption(f"📄 {info['filename']}")
            if c2.button("✕", key=f"del_{doc_id}", help="Remove"):
                if do_delete(doc_id):
                    chat["doc_ids"].remove(doc_id)
                    del chat["docs"][doc_id]
                    st.rerun()

# ─── Main ────────────────────────────────────────────────────────────────────

chat = _current_chat()

st.markdown("## Learn about your documents")
st.caption(
    "Upload a PDF and ask questions — answers are cited directly from your files "
    "and everything runs locally on your machine."
)

# ─── Chat history ─────────────────────────────────────────────────────────────

if not chat["messages"]:
    if not chat["docs"]:
        st.markdown("""
<div class="empty-state">
  <div class="empty-state-icon">📂</div>
  <div class="empty-state-title">Attach a PDF to get started</div>
  <div class="empty-state-sub">Use the upload area below — files stay on your machine.</div>
</div>""", unsafe_allow_html=True)
    else:
        # Show loaded files as chips, then prompt
        chips = "".join(
            f'<span class="doc-chip">📄 {i["filename"]}</span> '
            for i in chat["docs"].values()
        )
        st.markdown(
            f"<div style='margin-bottom:1rem'>{chips}</div>",
            unsafe_allow_html=True,
        )
        st.markdown("""
<div class="empty-state" style="padding:2rem 1rem">
  <div class="empty-state-icon">💬</div>
  <div class="empty-state-title">Ready — ask your first question</div>
  <div class="empty-state-sub">Type in the box below.</div>
</div>""", unsafe_allow_html=True)

else:
    # Show loaded files as small chips above the conversation
    if chat["docs"]:
        chips = "".join(
            f'<span class="doc-chip">📄 {i["filename"]}</span> '
            for i in chat["docs"].values()
        )
        st.markdown(
            f"<div style='margin-bottom:1.25rem'>{chips}</div>",
            unsafe_allow_html=True,
        )

    for item in chat["messages"]:
        label, color = confidence_label(item["confidence"])

        seen: set = set()
        unique_sources = []
        for src in item.get("sources", []):
            key = (src["filename"], src["page_number"])
            if key not in seen:
                seen.add(key)
                unique_sources.append(src)

        with st.container(border=True):
            st.markdown(f"**{item['question']}**")
            st.markdown(item["answer"])
            bl, br = st.columns([3, 1])
            if unique_sources:
                parts = [f"`{s['filename']}` p. {s['page_number']}" for s in unique_sources]
                bl.markdown("**Sources:** " + " · ".join(parts))
            br.markdown(f":{color}[**{label}**]")

# ─── Input area ──────────────────────────────────────────────────────────────

st.markdown("---")

# File uploader — auto-uploads when a new file is detected
attached = st.file_uploader(
    "📎 Attach a PDF to this chat",
    type=["pdf"],
    key=f"uploader_{st.session_state.upload_key}",
)

if attached is not None:
    file_id = f"{attached.name}_{attached.size}"
    if file_id != st.session_state.last_file_id:
        st.session_state.last_file_id = file_id
        with st.spinner("Indexing PDF…"):
            result = do_upload(attached)
        if result:
            chat["doc_ids"].append(result["doc_id"])
            chat["docs"][result["doc_id"]] = {
                "filename": result["filename"],
                "chunk_count": result["chunk_count"],
            }
            # Auto-name the chat from the first document
            if chat["name"] == "New Chat":
                name = result["filename"].rsplit(".", 1)[0][:36]
                chat["name"] = name
            st.toast(f"✓ {result['filename']} — {result['chunk_count']} chunks", icon="📄")
            st.session_state.upload_key += 1
            st.rerun()

# Question form — st.form stops keystroke reruns
with st.form("question_form", clear_on_submit=True):
    qc, bc = st.columns([5, 1])
    question = qc.text_input(
        "question",
        placeholder="Ask a question about your documents…",
        label_visibility="collapsed",
    )
    submitted = bc.form_submit_button("Ask →", type="primary", use_container_width=True)

if submitted:
    if not question.strip():
        st.warning("Please enter a question.")
    elif not chat["doc_ids"]:
        st.warning("Attach a PDF first using the upload area above.")
    else:
        with st.spinner("Thinking…"):
            try:
                r = httpx.post(
                    f"{BACKEND_URL}/query",
                    json={"question": question, "top_k": 5, "doc_ids": chat["doc_ids"]},
                    timeout=120,
                )
                r.raise_for_status()
                result = r.json()
                chat["messages"].append({"question": question, **result})
                st.rerun()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text
                if any(k in detail.lower() for k in ("connection", "refused", "ollama")):
                    st.error("Ollama is not running. Start it with `ollama serve`.")
                else:
                    st.error(f"Error: {detail}")
            except Exception as exc:
                st.error(f"Error: {exc}")
