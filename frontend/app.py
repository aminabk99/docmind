"""
M365Mind — Microsoft 365 Governance Intelligence
Streamlit frontend.

Two entry paths:
  1. "Try Demo"               — loads sample M365 policies, no account needed
  2. "Connect to Microsoft 365" — real tenant via MSAL OAuth2
"""

import os
import time
import uuid as _uuid

import httpx
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="M365Mind",
    page_icon="🔷",
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
    background: #0f172a;
    border-right: none;
    padding-top: 1.25rem;
}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] small,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] .stCaption {
    color: #94a3b8 !important;
}
section[data-testid="stSidebar"] h3 { color: #f1f5f9 !important; }
section[data-testid="stSidebar"] hr { border-color: #1e293b; }

/* Sidebar buttons — flat, left-aligned */
section[data-testid="stSidebar"] .stButton > button {
    background: transparent;
    border: none;
    color: #94a3b8;
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
    color: #f1f5f9;
    border: none;
}

/* ── Main area ────────────────────────────────────────────────────────── */
.block-container {
    padding-top: 2.5rem !important;
    padding-bottom: 5rem !important;
    max-width: 820px;
}
h2 {
    font-size: 1.85rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.03em !important;
    color: #0f172a !important;
}

/* Policy chips */
.policy-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    color: #1d4ed8;
    padding: 3px 11px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 500;
    margin-right: 4px;
    margin-bottom: 4px;
}

/* Connection badge */
.badge-connected {
    display: inline-flex; align-items: center; gap: 5px;
    background: #dcfce7; border: 1px solid #bbf7d0;
    color: #15803d; padding: 4px 12px; border-radius: 999px;
    font-size: 0.8rem; font-weight: 600;
}
.badge-demo {
    display: inline-flex; align-items: center; gap: 5px;
    background: #fef3c7; border: 1px solid #fde68a;
    color: #92400e; padding: 4px 12px; border-radius: 999px;
    font-size: 0.8rem; font-weight: 600;
}

/* Empty state */
.empty-state { text-align: center; padding: 4rem 1rem; }
.empty-state-icon  { font-size: 2.75rem; margin-bottom: 0.75rem; line-height: 1; }
.empty-state-title { font-size: 1.05rem; font-weight: 600; color: #1e293b; margin-bottom: 0.35rem; }
.empty-state-sub   { font-size: 0.875rem; color: #94a3b8; }

/* Landing cards */
.landing-card {
    border: 1.5px solid #e2e8f0;
    border-radius: 14px;
    padding: 1.5rem;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.15s, box-shadow 0.15s;
}
.landing-card:hover {
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59,130,246,0.1);
}

/* Answer card */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px !important;
    border-color: #e2e8f0 !important;
}

/* Sidebar toggle */
[data-testid="collapsedControl"] {
    position: fixed !important;
    top: 50vh !important;
    left: 0 !important;
    transform: translateY(-50%) !important;
    z-index: 9999999 !important;
    background: #2563eb !important;
    border-radius: 0 16px 16px 0 !important;
    width: 48px !important;
    height: 96px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-shadow: 4px 0 20px rgba(37,99,235,0.5) !important;
    cursor: pointer !important;
    border: none !important;
    padding: 0 !important;
}
[data-testid="collapsedControl"] button {
    background: transparent !important;
    border: none !important;
    width: 100% !important;
    height: 100% !important;
}
[data-testid="collapsedControl"] svg {
    width: 26px !important; height: 26px !important;
    fill: white !important; stroke: white !important;
}
[data-testid="collapsedControl"] svg * { fill: white !important; stroke: white !important; }

button[data-testid="baseButton-headerNoPadding"] {
    background: #2563eb !important;
    border-radius: 10px !important;
    width: 44px !important; height: 44px !important;
    border: none !important;
    box-shadow: 0 2px 10px rgba(37,99,235,0.4) !important;
}
button[data-testid="baseButton-headerNoPadding"] svg {
    width: 22px !important; height: 22px !important;
    fill: white !important; stroke: white !important;
}
button[data-testid="baseButton-headerNoPadding"] svg * { fill: white !important; stroke: white !important; }
</style>
""", unsafe_allow_html=True)


# ─── Session state ────────────────────────────────────────────────────────────

def _init_state():
    defaults = {
        "mode":          None,    # "demo" | "connected" | None (landing)
        "sid":           None,    # Microsoft 365 session ID
        "messages":      [],      # [{question, answer, sources, confidence}]
        "policies_info": [],      # [{filename, policy_type}] from last sync
        "demo_loaded":   False,
        "upload_key":    0,
        "last_file_id":  None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# Handle OAuth redirect query params
qp = st.query_params
if qp.get("m365_connected") == "true" and qp.get("sid") and st.session_state.mode is None:
    st.session_state.mode = "connected"
    st.session_state.sid  = qp.get("sid")
    st.query_params.clear()
if qp.get("m365_error"):
    st.error(f"Microsoft login failed: {qp.get('m365_error')}")
    st.query_params.clear()


# ─── API helpers ──────────────────────────────────────────────────────────────

def api_get(path: str, **kwargs):
    return httpx.get(f"{BACKEND_URL}{path}", timeout=30, **kwargs)

def api_post(path: str, **kwargs):
    return httpx.post(f"{BACKEND_URL}{path}", timeout=30, **kwargs)


def get_auth_url() -> str | None:
    try:
        r = api_get("/auth-url")
        if r.status_code == 400:
            st.error("Azure credentials not configured. Add AZURE_CLIENT_ID, AZURE_TENANT_ID, and AZURE_CLIENT_SECRET to your .env file first.")
            return None
        r.raise_for_status()
        return r.json()["url"]
    except Exception as exc:
        st.error(f"Could not generate Microsoft login URL: {exc}")
        return None


def load_demo_data() -> dict | None:
    try:
        r = httpx.post(f"{BACKEND_URL}/demo/load", timeout=300)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        st.error(f"Demo load failed: {exc}")
        return None


def demo_already_loaded() -> bool:
    try:
        r = api_get("/demo/status")
        return r.json().get("demo_loaded", False)
    except Exception:
        return False


def sync_tenant(sid: str) -> dict | None:
    try:
        r = httpx.post(f"{BACKEND_URL}/sync", json={"sid": sid}, timeout=120)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            st.error("Session expired. Please reconnect to Microsoft 365.")
            st.session_state.mode = None
            st.session_state.sid  = None
        else:
            st.error(f"Sync failed: {exc.response.text}")
        return None
    except Exception as exc:
        st.error(f"Sync failed: {exc}")
        return None


def do_query(question: str) -> dict | None:
    try:
        r = httpx.post(
            f"{BACKEND_URL}/query",
            json={"question": question, "top_k": 5},
            timeout=180,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        st.error(f"Query failed: {exc}")
        return None


def confidence_label(score: float) -> tuple[str, str]:
    if score >= 0.75:
        return "High Confidence", "green"
    elif score >= 0.45:
        return "Medium Confidence", "orange"
    else:
        return "Low Confidence", "red"


# ─── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🔷 M365Mind")
    st.caption("Local governance intelligence\nNo data leaves your machine")
    st.divider()

    if st.session_state.mode == "demo":
        st.markdown('<span class="badge-demo">🧪 Demo mode</span>', unsafe_allow_html=True)
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        if st.button("↩ Back to start", use_container_width=True):
            st.session_state.mode       = None
            st.session_state.messages   = []
            st.session_state.demo_loaded = False
            st.rerun()

    elif st.session_state.mode == "connected":
        st.markdown('<span class="badge-connected">✓ Connected to M365</span>', unsafe_allow_html=True)
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        if st.button("🔄 Sync Policies", use_container_width=True):
            with st.spinner("Pulling policies from tenant…"):
                result = sync_tenant(st.session_state.sid)
            if result:
                st.session_state.policies_info = [
                    {"filename": p} for p in result.get("policies", [])
                ]
                st.toast(
                    f"✓ {result['synced']} policies synced ({result['chunks']} chunks)",
                    icon="🔷",
                )
                st.rerun()

        if st.button("↩ Disconnect", use_container_width=True):
            st.session_state.mode          = None
            st.session_state.sid           = None
            st.session_state.messages      = []
            st.session_state.policies_info = []
            st.rerun()

    else:
        st.caption("Not connected — choose a mode on the right")

    if st.session_state.policies_info:
        st.divider()
        st.caption(f"Loaded policies ({len(st.session_state.policies_info)})")
        for p in st.session_state.policies_info[:20]:
            st.caption(f"🔹 {p['filename']}")
        if len(st.session_state.policies_info) > 20:
            st.caption(f"… and {len(st.session_state.policies_info) - 20} more")

    st.divider()
    st.caption("Query templates")
    templates = [
        "Which policies require MFA?",
        "What happens when a high-risk sign-in is detected?",
        "Which sensitivity labels encrypt content?",
        "Are legacy authentication protocols blocked?",
        "Which policies apply to guest or external users?",
        "What trusted locations are defined?",
    ]
    for t in templates:
        if st.button(t, key=f"tpl_{t[:20]}", use_container_width=True):
            st.session_state["_prefill"] = t
            st.rerun()


# ─── Landing screen ───────────────────────────────────────────────────────────

if st.session_state.mode is None:
    st.markdown("## 🔷 M365Mind")
    st.markdown(
        "Query your Microsoft 365 governance policies using AI — "
        "**everything runs locally, nothing leaves your machine.**"
    )
    st.markdown("---")
    st.markdown("#### Choose how to get started")

    col_demo, col_connect = st.columns(2, gap="large")

    with col_demo:
        st.markdown("##### ⚡ Try it in 2 minutes")
        st.markdown(
            "Jump straight in with realistic sample M365 policies — "
            "Conditional Access, Sensitivity Labels, Named Locations. "
            "No account, no setup, no waiting."
        )
        if st.button("Launch Demo", type="primary", use_container_width=True):
            if demo_already_loaded():
                st.session_state.mode = "demo"
                st.session_state.demo_loaded = True
                st.session_state.policies_info = [{"filename": "Demo policies (17 loaded)"}]
                st.rerun()
            else:
                with st.spinner("Loading sample policies… (first run downloads embedding model, ~1 min)"):
                    result = load_demo_data()
                if result:
                    st.session_state.mode = "demo"
                    st.session_state.demo_loaded = True
                    st.session_state.policies_info = [
                        {"filename": f"Demo policies ({result['loaded']} loaded)"}
                    ]
                    st.rerun()

    with col_connect:
        st.markdown("##### 🏢 Connect your own tenant")
        st.markdown(
            "Sign in with your Microsoft 365 work account to query your "
            "**real tenant's** policies — Conditional Access, Sensitivity Labels, Named Locations."
        )
        if st.button("Sign in with Microsoft", type="secondary", use_container_width=True):
            url = get_auth_url()
            if url:
                st.markdown(
                    f'<meta http-equiv="refresh" content="0; url={url}">',
                    unsafe_allow_html=True,
                )
                st.info("Redirecting to Microsoft login…")

    st.markdown("---")

    # ── Model download section ────────────────────────────────────────────────
    try:
        status = api_get("/model/status").json()
        model_ready   = status.get("ready", False)
        model_warming = status.get("warming", False)
    except Exception:
        model_ready   = False
        model_warming = False

    if model_ready:
        st.success("AI model ready — first query will be fast.")
    elif model_warming:
        st.info("Downloading AI model… this takes a few minutes. You can launch the demo while you wait.")
        time.sleep(3)
        st.rerun()
    else:
        st.warning(
            "**AI model not downloaded yet.** Download it now so your first question "
            "answers instantly (~3 GB, 3-5 min on a typical connection)."
        )
        if st.button("Download AI model now", type="secondary"):
            httpx.post(f"{BACKEND_URL}/model/warm", timeout=10)
            st.rerun()

    st.markdown(
        "<small>Powered by Qwen2.5-1.5B (local) · nomic-embed-text · Hybrid RAG · "
        "No telemetry · No cloud calls</small>",
        unsafe_allow_html=True,
    )
    st.stop()


# ─── Main query interface ─────────────────────────────────────────────────────

mode_label = "Demo" if st.session_state.mode == "demo" else "Your Tenant"

# ── Back button ───────────────────────────────────────────────────────────────
if st.button("← Home", key="back_home"):
    st.session_state.mode          = None
    st.session_state.sid           = None
    st.session_state.messages      = []
    st.session_state.policies_info = []
    st.session_state.demo_loaded   = False
    st.rerun()

st.markdown(f"## M365Mind — {mode_label}")

if st.session_state.mode == "demo":
    st.caption("You're exploring sample M365 policies. No account needed.")
elif st.session_state.mode == "connected" and not st.session_state.policies_info:
    st.info("Click **Sync Policies** in the sidebar to pull your tenant's policies.")

# ── Loaded policies expander ──────────────────────────────────────────────────
if st.session_state.policies_info:
    try:
        docs_resp = httpx.get(f"{BACKEND_URL}/documents", timeout=10)
        docs = docs_resp.json() if docs_resp.status_code == 200 else []
    except Exception:
        docs = []

    with st.expander(f"📋 View loaded policies ({len(docs)})"):
        if docs:
            ca     = [d for d in docs if "conditional" in d.get("filename","").lower() or "policy" in d.get("filename","").lower() or "mfa" in d.get("filename","").lower() or "block" in d.get("filename","").lower() or "compliant" in d.get("filename","").lower() or "risk" in d.get("filename","").lower() or "admin" in d.get("filename","").lower() or "mobile" in d.get("filename","").lower() or "external" in d.get("filename","").lower() or "country" in d.get("filename","").lower() or "restrict" in d.get("filename","").lower() or "legacy" in d.get("filename","").lower() or "frequency" in d.get("filename","").lower() or "require" in d.get("filename","").lower()]
            labels = [d for d in docs if "confidential" in d.get("filename","").lower() or "label" in d.get("filename","").lower() or "public" in d.get("filename","").lower() or "general" in d.get("filename","").lower() or "highly" in d.get("filename","").lower() or "sensitivity" in d.get("filename","").lower()]
            locs   = [d for d in docs if "location" in d.get("filename","").lower() or "office" in d.get("filename","").lower() or "vpn" in d.get("filename","").lower() or "country" in d.get("filename","").lower() or "trusted" in d.get("filename","").lower()]

            # Simple grouping — show all docs in clean list
            st.markdown("**Conditional Access Policies**")
            for d in docs:
                name = d.get("filename", "")
                if any(k in name.lower() for k in ["require", "block", "compliant", "risk", "admin", "mobile", "external", "legacy", "frequency", "restrict"]):
                    st.markdown(f"&nbsp;&nbsp;— {name}")

            st.markdown("**Named Locations**")
            for d in docs:
                name = d.get("filename", "")
                if any(k in name.lower() for k in ["office", "vpn", "location", "countries", "trusted", "high-risk"]):
                    st.markdown(f"&nbsp;&nbsp;— {name}")

            st.markdown("**Sensitivity Labels**")
            for d in docs:
                name = d.get("filename", "")
                if any(k in name.lower() for k in ["public", "general", "confidential", "highly"]):
                    st.markdown(f"&nbsp;&nbsp;— {name}")

            st.markdown("---")
            st.caption("Try asking about any of these policies below.")

# ─── Conversation history ─────────────────────────────────────────────────────

if not st.session_state.messages:
    if not st.session_state.policies_info:
        st.markdown("""
<div class="empty-state">
  <div class="empty-state-icon">🔷</div>
  <div class="empty-state-title">No policies loaded yet</div>
  <div class="empty-state-sub">Go back home and launch the demo or connect your tenant.</div>
</div>""", unsafe_allow_html=True)
    else:
        st.markdown("""
<div class="empty-state" style="padding:2.5rem 1rem">
  <div class="empty-state-icon">💬</div>
  <div class="empty-state-title">Ask about your governance policies</div>
  <div class="empty-state-sub">Type a question below, or expand "View loaded policies" above to see what's available.</div>
</div>""", unsafe_allow_html=True)
else:
    for item in st.session_state.messages:
        label, color = confidence_label(item["confidence"])

        seen: set = set()
        unique_sources = []
        for src in item.get("sources", []):
            key = (src["filename"], src["page_number"])
            if key not in seen:
                seen.add(key)
                unique_sources.append(src)

        # User bubble
        with st.chat_message("user"):
            st.markdown(item["question"])

        # Assistant bubble
        with st.chat_message("assistant", avatar="🔷"):
            st.markdown(item["answer"])
            if unique_sources:
                parts = [f"`{s['filename']}` §{s['page_number']}" for s in unique_sources]
                st.caption("**Sources:** " + " · ".join(parts))
            st.caption(f":{color}[{label}]")

    if st.button("Clear conversation", key="clear_conv"):
        st.session_state.messages = []
        st.rerun()

# ─── Input ────────────────────────────────────────────────────────────────────

has_policies = bool(st.session_state.policies_info)

# Handle template prefill
prefill = st.session_state.pop("_prefill", "")

if not has_policies:
    st.chat_input("Load policies first to start asking questions…", disabled=True)
else:
    question = st.chat_input(prefill or "Ask about your M365 governance policies…")
    if question:
        # Show user bubble immediately
        with st.chat_message("user"):
            st.markdown(question)
        # Stream spinner in assistant bubble
        with st.chat_message("assistant", avatar="🔷"):
            with st.spinner("Analysing policies… (first query loads the AI model, ~30 s)"):
                result = do_query(question)
            if result:
                st.markdown(result["answer"])
                unique_sources = []
                seen: set = set()
                for src in result.get("sources", []):
                    key = (src["filename"], src["page_number"])
                    if key not in seen:
                        seen.add(key)
                        unique_sources.append(src)
                if unique_sources:
                    parts = [f"`{s['filename']}` §{s['page_number']}" for s in unique_sources]
                    st.caption("**Sources:** " + " · ".join(parts))
                label, color = confidence_label(result["confidence"])
                st.caption(f":{color}[{label}]")
        if result:
            st.session_state.messages.append({"question": question, **result})
            st.rerun()
