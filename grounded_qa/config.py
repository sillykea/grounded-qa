"""Settings from the environment, shared by the CLI and the API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    corpus: str = os.environ.get("CORPUS_DIR", str(ROOT / "corpus"))
    llm_url: str = os.environ.get("LLM_URL", "http://localhost:8080")  # llm-gateway
    llm_key: str = os.environ.get("LLM_API_KEY", "")
    llm_model: str = os.environ.get("LLM_MODEL", "chat")
    embed_url: str = os.environ.get("EMBED_URL", "")  # empty: BM25 only
    embed_model: str = os.environ.get("EMBED_MODEL", "nomic-embed-text")
    cache_dir: str = os.environ.get("CACHE_DIR", str(ROOT / ".cache"))
    top_k: int = int(os.environ.get("TOP_K", "4"))
