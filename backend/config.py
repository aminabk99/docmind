import os
from dotenv import load_dotenv

load_dotenv()

# ── Storage ───────────────────────────────────────────────────────────────────
CHROMA_DB_PATH:  str = os.getenv("CHROMA_DB_PATH", "./chroma_db")
BACKEND_URL:     str = os.getenv("BACKEND_URL",    "http://localhost:8000")
COLLECTION_NAME: str = "m365mind_chunks"

# ── Chunking ──────────────────────────────────────────────────────────────────
CHUNK_SIZE:    int = 512
CHUNK_OVERLAP: int = 50

# ── Demo mode ─────────────────────────────────────────────────────────────────
# Set DEMO_MODE=true in .env to pre-load sample M365 policies without
# requiring a real Microsoft 365 tenant.
DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() == "true"

# ── Microsoft / Azure app registration ───────────────────────────────────────
# Required only when DEMO_MODE=false.
# Register an app at https://portal.azure.com with read-only permissions:
#   Policy.Read.All, InformationProtectionPolicy.Read.All
AZURE_CLIENT_ID:     str = os.getenv("AZURE_CLIENT_ID",     "")
AZURE_TENANT_ID:     str = os.getenv("AZURE_TENANT_ID",     "")
AZURE_CLIENT_SECRET: str = os.getenv("AZURE_CLIENT_SECRET", "")
AZURE_REDIRECT_URI:  str = os.getenv("AZURE_REDIRECT_URI",  "http://localhost:8000/callback")

GRAPH_SCOPES: list[str] = [
    "Policy.Read.All",
    "InformationProtectionPolicy.Read.All",
]
