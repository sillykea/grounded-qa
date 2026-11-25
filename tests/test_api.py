from fastapi.testclient import TestClient

from grounded_qa import api
from grounded_qa.chunking import load_corpus
from grounded_qa.config import ROOT
from grounded_qa.llm import LLMError
from grounded_qa.retrieval import Retriever


def client(chat):
    api.state.clear()
    api.state["retriever"] = Retriever(load_corpus(ROOT / "corpus"))
    api.state["chat"] = chat
    return TestClient(api.app)


def test_ask():
    with client(lambda m: "The outbox is written in the same transaction [1].") as c:
        r = c.post("/ask", json={"question": "How does the ledger publish events?"})
        assert r.status_code == 200
        body = r.json()
        assert body["citations"][0]["doc"].startswith("payments-ledger/")
        assert len(body["sources"]) == 4
        assert c.post("/ask", json={"question": "x"}).status_code == 422
        assert c.get("/healthz").json() == {"status": "ok"}


def test_model_down_is_a_502():
    def down(_):
        raise LLMError("connection refused")

    with client(down) as c:
        assert c.post("/ask", json={"question": "How does the ledger publish events?"}).status_code == 502
