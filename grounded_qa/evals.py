"""Measure retrieval and answers against the labelled question set.

Retrieval is scored without any model, so it runs everywhere and gates every
pull request. Answers need a model; they are scored with checks a machine
can make without another model's opinion:

  citations valid   every [n] in the answer points at a source it was shown
  cites a right doc  at least one citation is a document that holds the answer
  facts             every required fact (a regex) appears in the answer
  refusals          unanswerable questions get "I don't know"; answerable
                    ones don't

An LLM judge would add a groundedness score, but a judge's mistakes are
harder to see than a regex's. These checks come first; a judge is a later
layer, scored against these.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from .answer import Answer, answer
from .retrieval import Retriever


@dataclass
class Case:
    id: str
    question: str
    sources: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    answerable: bool = True


def load_cases(path: str | Path) -> list[Case]:
    raw = yaml.safe_load(Path(path).read_text())
    cases = [Case(**item) for item in raw]
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids in dataset")
    for c in cases:
        if c.answerable and not c.sources:
            raise ValueError(f"{c.id}: an answerable case needs sources")
        for f in c.facts:
            re.compile(f)
    return cases


@dataclass
class CaseResult:
    id: str
    answerable: bool
    rank: int | None  # 1-based rank of the first chunk from a right document; None if not retrieved
    retrieved: list[str]
    answer: str | None = None
    refused: bool | None = None
    citations_valid: bool | None = None
    cites_right_doc: bool | None = None
    facts_found: int = 0
    facts_total: int = 0
    seconds: float = 0.0

    @property
    def passed(self) -> bool | None:
        if self.answer is None:
            return None
        if not self.answerable:
            return bool(self.refused)
        return (
            not self.refused
            and bool(self.citations_valid)
            and bool(self.cites_right_doc)
            and self.facts_found == self.facts_total
        )


def first_relevant(retrieved: list[str], sources: list[str]) -> int | None:
    for i, doc in enumerate(retrieved):
        if doc in sources:
            return i + 1
    return None


def run(
    cases: list[Case],
    retriever: Retriever,
    k: int = 4,
    chat: Callable | None = None,
    progress: Callable[[str], None] | None = None,
) -> list[CaseResult]:
    results = []
    for case in cases:
        chunks = retriever.search(case.question, k)
        docs = [c.doc for c in chunks]
        r = CaseResult(
            case.id, case.answerable, first_relevant(docs, case.sources) if case.answerable else None, docs
        )
        if chat is not None:
            start = time.monotonic()
            a: Answer = answer(case.question, chunks, chat)
            r.seconds = round(time.monotonic() - start, 2)
            r.answer, r.refused = a.text, a.refused
            r.citations_valid = not a.invalid_citations
            r.cites_right_doc = any(c.doc in case.sources for c in a.cited_chunks)
            r.facts_total = len(case.facts)
            r.facts_found = sum(bool(re.search(f, a.text, re.IGNORECASE)) for f in case.facts)
            if progress:
                progress(f"{'PASS' if r.passed else 'FAIL'} {case.id} ({r.seconds}s)")
        results.append(r)
    return results


def summarise(results: list[CaseResult], k: int) -> dict[str, float]:
    answerable = [r for r in results if r.answerable]
    s: dict[str, float] = {
        f"recall_at_{k}": sum(r.rank is not None for r in answerable) / len(answerable),
        "recall_at_1": sum(r.rank == 1 for r in answerable) / len(answerable),
        "mrr": sum(1 / r.rank for r in answerable if r.rank) / len(answerable),
    }
    scored = [r for r in results if r.answer is not None]
    if scored:
        a = [r for r in scored if r.answerable]
        u = [r for r in scored if not r.answerable]
        s["answer_pass_rate"] = sum(bool(r.passed) for r in a) / len(a)
        s["citations_valid"] = sum(bool(r.citations_valid) for r in scored) / len(scored)
        s["cites_right_doc"] = sum(bool(r.cites_right_doc) for r in a) / len(a)
        s["facts_found"] = sum(r.facts_found for r in a) / max(sum(r.facts_total for r in a), 1)
        s["false_refusals"] = sum(bool(r.refused) for r in a) / len(a)
        s["correct_refusals"] = sum(bool(r.refused) for r in u) / len(u) if u else 1.0
        s["median_seconds"] = sorted(r.seconds for r in scored)[len(scored) // 2]
    return s


# For each metric, whether higher is better. Thresholds are minimums for
# those, maximums for the rest.
HIGHER_IS_BETTER = {"false_refusals": False, "median_seconds": False}


def check(summary: dict[str, float], thresholds: dict[str, float]) -> list[str]:
    failures = []
    for name, limit in thresholds.items():
        if name not in summary:
            continue
        value = summary[name]
        if HIGHER_IS_BETTER.get(name, True) and value < limit:
            failures.append(f"{name} {value:.3f} is below {limit}")
        elif not HIGHER_IS_BETTER.get(name, True) and value > limit:
            failures.append(f"{name} {value:.3f} is above {limit}")
    return failures


LABELS = {
    "recall_at_1": "Right document ranked first",
    "mrr": "Mean reciprocal rank",
    "answer_pass_rate": "Answers passing every check",
    "citations_valid": "Answers whose citations all exist",
    "cites_right_doc": "Answers citing a right document",
    "facts_found": "Required facts present",
    "false_refusals": "Answerable questions refused",
    "correct_refusals": "Unanswerable questions refused",
    "median_seconds": "Median seconds per answer",
}


def markdown(
    summary: dict[str, float],
    results: list[CaseResult],
    k: int,
    thresholds: dict[str, float],
    header: str = "",
) -> str:
    out = [header] if header else []
    out += ["| Metric | Value | Threshold |", "|---|---|---|"]
    for name, value in summary.items():
        label = LABELS.get(name, f"Right document in top {k}" if name == f"recall_at_{k}" else name)
        shown = (
            f"{value:.1f}"
            if name == "median_seconds"
            else f"{value:.0%}"
            if name != "mrr"
            else f"{value:.2f}"
        )
        limit = thresholds.get(name)
        lim = (
            "" if limit is None else (f"≤ {limit}" if not HIGHER_IS_BETTER.get(name, True) else f"≥ {limit}")
        )
        out.append(f"| {label} | {shown} | {lim} |")
    missed = [r for r in results if r.answerable and r.rank is None]
    if missed:
        out.append("\nNot retrieved: " + ", ".join(r.id for r in missed))
    failed = [r for r in results if r.passed is False]
    if failed:
        out.append("\n| Failed case | Why | Answer |\n|---|---|---|")
        for r in failed:
            why = []
            if r.answerable:
                if r.refused:
                    why.append("refused")
                if not r.citations_valid:
                    why.append("invalid citation")
                if not r.cites_right_doc:
                    why.append("didn't cite a right document")
                if r.facts_found < r.facts_total:
                    why.append(f"{r.facts_found}/{r.facts_total} facts")
            else:
                why.append("answered an unanswerable question")
            text = (r.answer or "").replace("\n", " ").replace("|", "\\|")
            out.append(f"| {r.id} | {', '.join(why)} | {text[:160]} |")
    passed = [r for r in results if r.passed]
    if passed:
        out.append("\n<details><summary>Answers that passed</summary>\n")
        out.append("| Case | Answer |\n|---|---|")
        for r in passed:
            text = (r.answer or "").replace("\n", " ").replace("|", "\\|")
            out.append(f"| {r.id} | {text[:300]} |")
        out.append("\n</details>")
    return "\n".join(out) + "\n"


def save(results: list[CaseResult], summary: dict[str, float], path: str | Path) -> None:
    Path(path).write_text(json.dumps({"summary": summary, "cases": [asdict(r) for r in results]}, indent=2))
