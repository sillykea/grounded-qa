from grounded_qa.chunking import chunk_markdown, load_corpus
from grounded_qa.config import ROOT

DOC = """# Runbook

Intro paragraph that says what this is for.

## Slow responses

Check the provider first.

```mermaid
flowchart LR
  A --> B
```

```bash
kubectl get pods
# not a heading
```

### On Ollama

Check GPU memory: a model that does not fit falls back to the CPU.
"""


def test_sections_carry_heading_path_and_drop_diagrams():
    chunks = chunk_markdown("gw/docs/runbook.md", DOC)
    by_heading = {c.heading: c.text for c in chunks}
    assert set(by_heading) == {"Runbook", "Runbook > Slow responses", "Runbook > Slow responses > On Ollama"}
    slow = by_heading["Runbook > Slow responses"]
    assert "kubectl get pods" in slow and "# not a heading" in slow  # code kept whole
    assert "flowchart" not in slow  # mermaid dropped
    assert chunks[0].id == "gw/docs/runbook.md#0" and chunks[0].repo == "gw"
    assert chunks[0].url == "https://github.com/sillykea/gw/blob/main/docs/runbook.md"


def test_long_sections_split_on_paragraphs():
    body = "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(10))
    chunks = chunk_markdown("d.md", "# T\n\n" + body, max_chars=500)
    assert len(chunks) > 3
    assert all(len(c.text) <= 500 for c in chunks)
    assert all(c.text.startswith("Paragraph") for c in chunks)  # never cut mid-paragraph


def test_corpus_loads():
    chunks = load_corpus(ROOT / "corpus")
    assert len({c.doc for c in chunks}) >= 30
    assert len({c.id for c in chunks}) == len(chunks)
