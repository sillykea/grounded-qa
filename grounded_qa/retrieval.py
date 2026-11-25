"""Retrieval: BM25 over chunks, optionally fused with embedding similarity.

BM25 needs no model, is deterministic and is strong on the exact terms
engineering docs are full of (`max_in_flight`, `FOR UPDATE`, `422`). Dense
embeddings help with paraphrase ("charged twice" for "idempotency"). With an
embedding endpoint configured, both rankings are combined with reciprocal
rank fusion, which needs no score calibration between the two.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

from .chunking import Chunk

TOKEN = re.compile(r"[a-z0-9]+(?:[_.][a-z0-9]+)*")
STOP = frozenset(
    (
        "a an and are as at be by can do does for from has have how i if in into is it its of on or so "
        "that the their them then there these they this to was what when where which who why will with "
        "would you your"
    ).split()
)


def stem(word: str) -> str:
    """A light suffix stripper: enough to match "replicas" with "replica"."""
    if len(word) <= 4 or not word.isalpha():
        return word
    for suffix, repl in (("ies", "y"), ("sses", "ss"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: len(word) - len(suffix)] + repl
    return word


def tokenize(text: str) -> list[str]:
    out = []
    for tok in TOKEN.findall(text.lower()):
        if tok in STOP:
            continue
        out.append(stem(tok))
        if "_" in tok or "." in tok:  # also index the parts of max_in_flight, v1.2
            out.extend(stem(p) for p in re.split(r"[_.]", tok) if p and p not in STOP)
    return out


def _doc_terms(chunk: Chunk) -> list[str]:
    # The repo name and heading say what a chunk is about; count them twice.
    title = chunk.repo.replace("-", " ") + " " + chunk.heading
    return tokenize(title) * 2 + tokenize(chunk.text)


class BM25:
    def __init__(self, chunks: Sequence[Chunk], k1: float = 1.2, b: float = 0.75):
        self.chunks = list(chunks)
        self.k1, self.b = k1, b
        self.tf = [Counter(_doc_terms(c)) for c in self.chunks]
        self.len = [sum(tf.values()) for tf in self.tf]
        self.avg = sum(self.len) / max(len(self.len), 1)
        df: Counter[str] = Counter()
        for tf in self.tf:
            df.update(tf.keys())
        n = len(self.chunks)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = tokenize(query)
        out = []
        for tf, length in zip(self.tf, self.len, strict=True):
            s = 0.0
            for t in terms:
                f = tf.get(t)
                if f:
                    s += (
                        self.idf[t]
                        * f
                        * (self.k1 + 1)
                        / (f + self.k1 * (1 - self.b + self.b * length / self.avg))
                    )
            out.append(s)
        return out

    def rank(self, query: str) -> list[int]:
        s = self.scores(query)
        return [i for i in sorted(range(len(s)), key=lambda i: -s[i]) if s[i] > 0]


Embed = Callable[[list[str]], list[list[float]]]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class Retriever:
    """Ranks chunks for a question. Pass embed to add dense retrieval."""

    def __init__(
        self,
        chunks: Sequence[Chunk],
        embed: Embed | None = None,
        cache_dir: str | None = None,
        model_name: str = "",
    ):
        self.chunks = list(chunks)
        self.bm25 = BM25(self.chunks)
        self.embed = embed
        self.vectors: list[list[float]] | None = None
        if embed is not None:
            self.vectors = self._embed_corpus(embed, cache_dir, model_name)

    def _embed_corpus(self, embed: Embed, cache_dir: str | None, model_name: str) -> list[list[float]]:
        texts = [f"{c.heading}\n{c.text}" for c in self.chunks]
        key = hashlib.sha256(("\0".join(texts) + model_name).encode()).hexdigest()[:16]
        path = Path(cache_dir) / f"embeddings-{key}.json" if cache_dir else None
        if path and path.exists():
            return json.loads(path.read_text())
        vectors: list[list[float]] = []
        for i in range(0, len(texts), 32):
            vectors.extend(embed(texts[i : i + 32]))
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(vectors))
        return vectors

    def search(self, question: str, k: int = 4) -> list[Chunk]:
        lexical = self.bm25.rank(question)
        if self.vectors is None or self.embed is None:
            return [self.chunks[i] for i in lexical[:k]]
        q = self.embed([question])[0]
        sims = [_cosine(q, v) for v in self.vectors]
        dense = sorted(range(len(sims)), key=lambda i: -sims[i])
        return [self.chunks[i] for i in rrf([lexical, dense])[:k]]


def rrf(rankings: list[list[int]], k: int = 60) -> list[int]:
    """Reciprocal rank fusion: each list adds 1/(k + rank) to an item's score."""
    score: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            score[item] = score.get(item, 0.0) + 1.0 / (k + rank + 1)
    return sorted(score, key=lambda i: -score[i])
