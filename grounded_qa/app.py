"""Build the retriever and chat client from settings."""

from __future__ import annotations

from .chunking import load_corpus
from .config import Settings
from .llm import Chat, Embeddings
from .retrieval import Retriever


def retriever(s: Settings) -> Retriever:
    embed = Embeddings(s.embed_url, s.embed_model) if s.embed_url else None
    return Retriever(load_corpus(s.corpus), embed=embed, cache_dir=s.cache_dir, model_name=s.embed_model)


def chat(s: Settings) -> Chat:
    return Chat(s.llm_url, s.llm_model, s.llm_key)
