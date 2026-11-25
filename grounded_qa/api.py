"""HTTP API: POST /ask with a question, get an answer with citations.

uvicorn grounded_qa.api:app
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import app as build
from .answer import answer
from .config import Settings
from .llm import LLMError

state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = Settings()
    state["settings"] = settings
    state.setdefault("retriever", build.retriever(settings))
    state.setdefault("chat", build.chat(settings))
    yield


app = FastAPI(title="grounded-qa", lifespan=lifespan)


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    k: int = Field(default=4, ge=1, le=10)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask")
def ask(q: Question) -> dict:
    sources = state["retriever"].search(q.question, q.k)
    try:
        return answer(q.question, sources, state["chat"]).to_dict()
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"model unavailable: {e}") from e
