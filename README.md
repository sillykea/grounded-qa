# grounded-qa

[![ci](https://github.com/sillykea/grounded-qa/actions/workflows/ci.yml/badge.svg)](https://github.com/sillykea/grounded-qa/actions/workflows/ci.yml)

Ask questions about a set of engineering docs and get short answers with citations you can check. The docs are the READMEs, design decisions and runbooks of my other projects ([llm-gateway](https://github.com/sillykea/llm-gateway), its [platform](https://github.com/sillykea/llm-gateway-platform) and [console](https://github.com/sillykea/llm-gateway-console), [payments-ledger](https://github.com/sillykea/payments-ledger), [fraud-detection](https://github.com/sillykea/fraud-detection)): 39 documents, the kind of corpus an on-call engineer searches at 3 a.m.

The point is less the chatbot than the evals around it. Every change runs 42 labelled questions through retrieval and a real model, and CI fails if answers get worse.

```mermaid
flowchart LR
    Q[Question] --> R{Retrieve}
    R -->|BM25| C[(Chunks by<br/>section)]
    R -->|embeddings| O1[Ollama<br/>nomic-embed-text]
    R --> F[Reciprocal rank fusion<br/>top 4]
    F --> P[Prompt with<br/>numbered sources]
    P --> G[llm-gateway] --> O2[Ollama<br/>qwen2.5:1.5b]
    O2 --> A[Answer with [n] citations]
    A --> V{Check citations<br/>and refusals}
```

EXAMPLE_PLACEHOLDER

## How it works

**Chunking follows the document.** One chunk per section, carrying its heading path ("Runbook > Shared limits unavailable") so it reads on its own. Long sections split on paragraph breaks, code blocks stay whole, and Mermaid diagrams are dropped, since their node labels are noise to a retriever.

**Hybrid retrieval.** BM25 needs no model and is strong on the exact terms engineering docs are full of (`max_in_flight`, `FOR UPDATE`, `422`). Embeddings catch paraphrase ("charged twice" for idempotency). The two rankings are fused with reciprocal rank fusion, which needs no score calibration between them. Embeddings are cached on disk by content hash.

**Citations are checked, not trusted.** The model sees numbered sources and must cite them as `[n]`. Citations are parsed back: a number that doesn't match a source is reported as invalid, and the API returns each citation with its document, section and GitHub link.

**Saying "I don't know" is a feature.** The prompt gives the model one exact phrase for questions the sources don't cover. Six of the eval questions have no answer in the docs, and refusing them correctly is scored like any other answer.

**Through the gateway.** Chat requests go through llm-gateway, so its routing, personal-data rules, rate limits, budgets and tracing apply to this app like any other client. Swapping the model is a gateway config change.

## Evals

`evals/dataset.yaml` holds 36 answerable questions, each with the documents that answer it and the facts a correct answer must contain (as regexes), plus 6 the docs can't answer. They were written against the documents, not against the model's output.

| Check | What it measures | Needs a model |
|---|---|---|
| Right document in top 4 / ranked first, MRR | Retrieval | no |
| Citations all exist | No invented sources | yes |
| Cites a right document | The answer rests on the right source | yes |
| Required facts present | The answer is actually correct | yes |
| Unanswerable questions refused, answerable ones not | Knows its limits, without hiding behind them | yes |

An answer passes only if it isn't a refusal, every citation is valid, at least one points at a right document, and every required fact is there.

CI runs two jobs. `test` runs lint, unit tests and the retrieval evals on every push (no model, seconds). `answers` starts Ollama and llm-gateway, pulls the models, and runs all 42 questions through the full path. Each fails the build if a metric falls below `evals/thresholds.yaml`, which is set a little under the measured baseline. Both publish their report to the job summary.

These are checks a machine can make without another model's opinion. An LLM judge for groundedness would come next, scored against these checks before anyone trusts it, because a judge's mistakes are harder to see than a regex's.

### Results

Retrieval (BM25 only, top 4, 36 answerable questions):

| Metric | Value |
|---|---|
| Right document in top 4 | 100% |
| Right document ranked first | 89% |
| Mean reciprocal rank | 0.94 |

RESULTS_PLACEHOLDER

## Run it

```bash
make install && make test && make eval-retrieval   # no model needed
make up && make models                              # Ollama, llm-gateway, the API on :8000
make eval                                           # real answers, report in report.md
curl -s localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "Why does the console run as a single replica?"}'
```

| Variable | Default | |
|---|---|---|
| `LLM_URL`, `LLM_API_KEY`, `LLM_MODEL` | `http://localhost:8080`, none, `chat` | Any OpenAI-compatible chat endpoint; llm-gateway in the demo |
| `EMBED_URL`, `EMBED_MODEL` | none (BM25 only), `nomic-embed-text` | OpenAI-compatible embeddings endpoint |
| `CORPUS_DIR`, `TOP_K` | `corpus/`, 4 | |

## Layout

```
grounded_qa/chunking.py   markdown → section chunks
grounded_qa/retrieval.py  BM25, embeddings, reciprocal rank fusion
grounded_qa/answer.py     prompt, citation parsing, refusal detection
grounded_qa/evals.py      scoring, thresholds, report
grounded_qa/api.py        FastAPI: POST /ask
evals/                    labelled questions and thresholds
corpus/                   the documents
```

## License

MIT
