import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
CHROMA_DB_PATH: str = os.getenv("CHROMA_DB_PATH", "./chroma_db")
BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")

COLLECTION_NAME: str = "docmind_chunks"
EMBEDDING_MODEL: str = "text-embedding-3-small"
LLM_MODEL: str = "gpt-4o-mini"
CHUNK_SIZE: int = 512
CHUNK_OVERLAP: int = 50

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set. Add it to your .env file.")
