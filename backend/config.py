import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CHROMA_DB_PATH: str = os.getenv("CHROMA_DB_PATH", "./chroma_db")
BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")

COLLECTION_NAME: str = "docmind_chunks"
EMBEDDING_MODEL: str = "nomic-embed-text"
LLM_MODEL: str = "tinyllama"
CHUNK_SIZE: int = 512
CHUNK_OVERLAP: int = 50
