"""Answer a question from retrieved chunks, with citations that can be checked.

The model sees numbered sources and must cite them as [1], [2]. Citations are
parsed back and checked against what was actually retrieved, so an answer
citing a source that doesn't exist is caught rather than shown to a reader.
If the sources don't hold the answer, the model is told to say so in a fixed
phrase, which is how a refusal is recognised.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from .chunking import Chunk

REFUSAL = "I don't know based on these documents."

SYSTEM = f"""You answer questions about a set of engineering documents.
Use only the numbered sources below. Do not use anything else you know.
Cite the source of every statement with its number in square brackets, like [2].
Answer in at most four sentences.
If the sources do not contain the answer, reply exactly: {REFUSAL}"""

CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
REFUSED = re.compile(
    r"\bi (?:do not|don't|dont|cannot|can't) (?:know|find|answer)\b"
    r"|\b(?:sources|documents) (?:do not|don't|does not|doesn't) (?:contain|say|mention|cover)",
    re.IGNORECASE,
)

Chat = Callable[[Sequence[dict[str, str]]], str]


@dataclass
class Answer:
    question: str
    text: str
    sources: list[Chunk]  # what the model was shown, in order: [1] is sources[0]
    cited: list[int] = field(default_factory=list)  # valid citation numbers, 1-based
    invalid_citations: list[int] = field(default_factory=list)
    refused: bool = False

    @property
    def cited_chunks(self) -> list[Chunk]:
        return [self.sources[n - 1] for n in self.cited]

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.text,
            "refused": self.refused,
            "citations": [
                {"n": n, "doc": c.doc, "heading": c.heading, "url": c.url}
                for n, c in zip(self.cited, self.cited_chunks, strict=True)
            ],
            "invalid_citations": self.invalid_citations,
            "sources": [{"n": i + 1, "doc": c.doc, "heading": c.heading} for i, c in enumerate(self.sources)],
        }


def build_messages(question: str, sources: Sequence[Chunk]) -> list[dict[str, str]]:
    context = "\n\n".join(f"[{i + 1}] ({c.repo}: {c.heading})\n{c.text}" for i, c in enumerate(sources))
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Sources:\n\n{context}\n\nQuestion: {question}"},
    ]


def parse_citations(text: str, n_sources: int) -> tuple[list[int], list[int]]:
    valid: list[int] = []
    invalid: list[int] = []
    for group in CITE.findall(text):
        for part in group.split(","):
            n = int(part)
            target = valid if 1 <= n <= n_sources else invalid
            if n not in target:
                target.append(n)
    return valid, invalid


def is_refusal(text: str) -> bool:
    return bool(REFUSED.search(text))


def answer(question: str, sources: Sequence[Chunk], chat: Chat) -> Answer:
    if not sources:
        return Answer(question, REFUSAL, [], refused=True)
    text = chat(build_messages(question, sources)).strip()
    valid, invalid = parse_citations(text, len(sources))
    return Answer(
        question, text, list(sources), cited=valid, invalid_citations=invalid, refused=is_refusal(text)
    )
