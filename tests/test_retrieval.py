from grounded_qa.chunking import Chunk, load_corpus
from grounded_qa.config import ROOT
from grounded_qa.retrieval import BM25, Retriever, rrf, stem, tokenize


def test_tokenize():
    assert tokenize("The max_in_flight replicas") == [
        "max_in_flight",
        "max",
        "flight",
        "replica",
    ]  # "in" is a stop word
    assert stem("policies") == "policy" and stem("gas") == "gas"


def test_bm25_prefers_rare_matching_terms():
    chunks = [
        Chunk(f"d#{i}", "repo/d.md", "H", t)
        for i, t in enumerate(
            ["the gateway routes requests", "idempotency keys stop double charges", "requests and requests"]
        )
    ]
    assert BM25(chunks).rank("idempotency key")[0] == 1


def test_rrf_rewards_agreement():
    assert rrf([[1, 2, 3], [3, 1, 2]])[0] == 1


def test_dense_retrieval_is_fused():
    chunks = load_corpus(ROOT / "corpus")

    def embed(texts):  # a fake embedder that only "understands" one concept
        return [[1.0, 0.0] if ("PBKDF2" in t or "zorp" in t) else [0.0, 1.0] for t in texts]

    # No word in the question appears in the corpus, so BM25 finds nothing
    # and only the dense side can.
    assert Retriever(chunks).search("zorp blarg", k=3) == []
    found = Retriever(chunks, embed=embed).search("zorp blarg", k=3)
    assert found and all("PBKDF2" in c.text for c in found)


def test_embedding_cache(tmp_path):
    chunks = load_corpus(ROOT / "corpus")[:5]
    calls = []

    def embed(texts):
        calls.append(len(texts))
        return [[float(len(t)), 1.0] for t in texts]

    Retriever(chunks, embed=embed, cache_dir=str(tmp_path), model_name="m")
    Retriever(chunks, embed=embed, cache_dir=str(tmp_path), model_name="m")
    assert calls == [5]  # second build read the cache
