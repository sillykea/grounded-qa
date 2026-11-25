"""Clients for OpenAI-compatible chat and embedding endpoints.

Chat goes through llm-gateway in the demo and CI, so the gateway's routing,
personal-data rules, budgets and tracing apply to this app like any other.
Embeddings go straight to the model server: the gateway has no embeddings
endpoint yet.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

import httpx


class LLMError(RuntimeError):
    pass


class Chat:
    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 180.0):
        self.url = base_url.rstrip("/") + "/v1/chat/completions"
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.http = httpx.Client(timeout=timeout, headers=headers)

    def __call__(self, messages: Sequence[dict[str, str]], max_tokens: int = 300) -> str:
        body = {"model": self.model, "messages": list(messages), "temperature": 0, "max_tokens": max_tokens}
        for attempt in range(3):
            try:
                r = self.http.post(self.url, json=body)
            except httpx.TransportError as e:
                err: Exception = e
            else:
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"] or ""
                if r.status_code < 500 and r.status_code != 429:
                    raise LLMError(f"chat: {r.status_code} {r.text[:300]}")
                err = LLMError(f"chat: {r.status_code} {r.text[:300]}")
            time.sleep(2**attempt)
        raise LLMError(f"chat failed after 3 attempts: {err}")


class Embeddings:
    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 120.0):
        self.url = base_url.rstrip("/") + "/v1/embeddings"
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.http = httpx.Client(timeout=timeout, headers=headers)

    def __call__(self, texts: list[str]) -> list[list[float]]:
        r = self.http.post(self.url, json={"model": self.model, "input": texts})
        if r.status_code != 200:
            raise LLMError(f"embeddings: {r.status_code} {r.text[:300]}")
        data = sorted(r.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]
