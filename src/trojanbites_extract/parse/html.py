from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup


@dataclass
class EvidenceBlock:
    block_id: str
    text: str
    kind: str = "html"
    page: int | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class EvidenceDoc:
    source_url: str
    content_hash: str | None
    blocks: list[EvidenceBlock]
    tables: list[list[list[str]]] = field(default_factory=list)
    ocr_confidence: float | None = None


_INSTRUCTION_PATTERNS = re.compile(
    r"(ignore (all )?(previous|prior) instructions|system prompt|exfiltrate|api[_-]?key)",
    re.I,
)


def parse_html_file(path: Path, source_url: str, content_hash: str | None) -> EvidenceDoc:
    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    blocks: list[EvidenceBlock] = []
    tables: list[list[list[str]]] = []

    # Prefer menu-ish sections
    candidates = soup.find_all(["h1", "h2", "h3", "h4", "section", "article", "li", "tr", "p"])
    for i, el in enumerate(candidates):
        text = " ".join(el.get_text(" ", strip=True).split())
        if not text or len(text) < 2:
            continue
        meta = {}
        if _INSTRUCTION_PATTERNS.search(text):
            meta["untrusted_instruction_pattern"] = True
        blocks.append(
            EvidenceBlock(
                block_id=f"html_{i}",
                text=text,
                kind="html",
                meta=meta,
            )
        )

    for table in soup.find_all("table"):
        rows: list[list[str]] = []
        for tr in table.find_all("tr"):
            cells = [
                " ".join(td.get_text(" ", strip=True).split())
                for td in tr.find_all(["th", "td"])
            ]
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(rows)
            blocks.append(
                EvidenceBlock(
                    block_id=f"table_{len(tables)}",
                    text="\n".join([" | ".join(r) for r in rows]),
                    kind="table",
                )
            )

    if not blocks:
        text = " ".join(soup.get_text(" ", strip=True).split())
        blocks.append(EvidenceBlock(block_id="html_full", text=text[:50000], kind="html"))

    return EvidenceDoc(
        source_url=source_url,
        content_hash=content_hash,
        blocks=blocks,
        tables=tables,
    )