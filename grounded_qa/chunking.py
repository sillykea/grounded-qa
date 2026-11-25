"""Split markdown documents into chunks that each answer one kind of question.

Chunks follow the document's own structure: one per section, carrying the
heading path ("Runbook > Shared limits unavailable") so a chunk makes sense on
its own. Long sections are split on paragraph breaks, never mid-paragraph,
and code blocks are kept whole. Mermaid diagrams are dropped: they are
pictures, and their node labels only add noise to retrieval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


@dataclass(frozen=True)
class Chunk:
    id: str  # "<doc>#<n>", stable for a given document
    doc: str  # path relative to the corpus root, e.g. "payments-ledger/README.md"
    heading: str  # "Title > Section > Subsection"
    text: str

    @property
    def repo(self) -> str:
        return self.doc.split("/", 1)[0]

    @property
    def url(self) -> str:
        repo, _, path = self.doc.partition("/")
        return f"https://github.com/sillykea/{repo}/blob/main/{path}"


@dataclass
class _Section:
    path: list[str]
    lines: list[str] = field(default_factory=list)


def _sections(markdown: str) -> list[_Section]:
    sections = [_Section(path=[])]
    stack: list[tuple[int, str]] = []
    fence: str | None = None  # the opening fence while inside a code block
    skipping = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if fence is None and stripped.startswith(("```", "~~~")):
            fence = stripped[:3]
            skipping = stripped[3:].strip().lower().startswith("mermaid")
            if not skipping:
                sections[-1].lines.append(line)
            continue
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
                if not skipping:
                    sections[-1].lines.append(line)
                skipping = False
            elif not skipping:
                sections[-1].lines.append(line)
            continue
        m = HEADING.match(line)
        if m:
            level, title = len(m.group(1)), m.group(2)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            sections.append(_Section(path=[t for _, t in stack]))
            continue
        sections[-1].lines.append(line)
    return sections


def _paragraphs(lines: list[str]) -> list[str]:
    """Blank-line separated blocks, treating a code block as one block."""
    blocks, cur, in_code = [], [], False
    for line in lines:
        if line.strip().startswith(("```", "~~~")):
            in_code = not in_code
        if not line.strip() and not in_code:
            if cur:
                blocks.append("\n".join(cur))
                cur = []
            continue
        cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return blocks


def chunk_markdown(doc: str, markdown: str, max_chars: int = 900) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in _sections(markdown):
        heading = " > ".join(section.path)
        pieces: list[str] = []
        cur = ""
        for block in _paragraphs(section.lines):
            if cur and len(cur) + len(block) + 2 > max_chars:
                pieces.append(cur)
                cur = block
            else:
                cur = f"{cur}\n\n{block}" if cur else block
        if cur:
            pieces.append(cur)
        for piece in pieces:
            # A heading with no body of its own (just a parent of subsections)
            # makes no useful chunk.
            if len(piece.strip()) < 20:
                continue
            chunks.append(Chunk(id=f"{doc}#{len(chunks)}", doc=doc, heading=heading, text=piece.strip()))
    return chunks


def load_corpus(root: str | Path, max_chars: int = 900) -> list[Chunk]:
    root = Path(root)
    chunks: list[Chunk] = []
    for path in sorted(root.rglob("*.md")):
        doc = path.relative_to(root).as_posix()
        chunks.extend(chunk_markdown(doc, path.read_text(encoding="utf-8"), max_chars))
    return chunks
