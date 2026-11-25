"""Command line: ask a question, or run the evals.

grounded-qa ask "How does the ledger handle retries?"
grounded-qa eval --retrieval-only
grounded-qa eval --report report.md
"""

from __future__ import annotations

import argparse
import sys

import yaml

from . import app as build
from .answer import answer
from .config import ROOT, Settings
from .evals import check, load_cases, markdown, run, save, summarise


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="grounded-qa")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask", help="answer one question")
    a.add_argument("question")
    e = sub.add_parser("eval", help="score retrieval and answers on the labelled questions")
    e.add_argument("--dataset", default=str(ROOT / "evals" / "dataset.yaml"))
    e.add_argument("--thresholds", default=str(ROOT / "evals" / "thresholds.yaml"))
    e.add_argument("--retrieval-only", action="store_true", help="no model needed")
    e.add_argument("--report", help="write the markdown report here")
    e.add_argument("--results", default="results.json")
    args = p.parse_args(argv)

    s = Settings()
    retriever = build.retriever(s)

    if args.cmd == "ask":
        res = answer(args.question, retriever.search(args.question, s.top_k), build.chat(s))
        print(res.text)
        for n, c in zip(res.cited, res.cited_chunks, strict=True):
            print(f"  [{n}] {c.doc} > {c.heading}")
        return 0

    cases = load_cases(args.dataset)
    chat = None if args.retrieval_only else build.chat(s)
    results = run(cases, retriever, s.top_k, chat, progress=lambda m: print(m, flush=True))
    summary = summarise(results, s.top_k)
    limits = yaml.safe_load(open(args.thresholds))  # noqa: SIM115
    limits = limits["retrieval"] | ({} if args.retrieval_only else limits["answers"])
    mode = "BM25 + embeddings" if s.embed_url else "BM25"
    header = (
        f"Retrieval: {mode}, top {s.top_k}. "
        + ("" if args.retrieval_only else f"Model: {s.llm_model} via {s.llm_url}. ")
        + f"{len(cases)} questions.\n"
    )
    report = markdown(summary, results, s.top_k, limits, header)
    print(report)
    save(results, summary, args.results)
    if args.report:
        with open(args.report, "w") as f:
            f.write(report)
    failures = check(summary, limits)
    for f in failures:
        print("FAIL:", f, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
