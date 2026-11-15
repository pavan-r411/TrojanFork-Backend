from __future__ import annotations

from pathlib import Path

import pdfplumber

from trojanbites_extract.parse.html import EvidenceBlock, EvidenceDoc


def parse_pdf_file(path: Path, source_url: str, content_hash: str | None) -> EvidenceDoc:
    blocks: list[EvidenceBlock] = []
    tables: list[list[list[str]]] = []
    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                blocks.append(
                    EvidenceBlock(
                        block_id=f"pdf_p{page_num}",
                        text=text,
                        kind="pdf_text",
                        page=page_num,
                    )
                )
            for t in page.extract_tables() or []:
                cleaned = [
                    [("" if c is None else str(c).strip()) for c in row] for row in t
                ]
                tables.append(cleaned)
                blocks.append(
                    EvidenceBlock(
                        block_id=f"pdf_table_p{page_num}_{len(tables)}",
                        text="\n".join([" | ".join(r) for r in cleaned]),
                        kind="table",
                        page=page_num,
                    )
                )
    return EvidenceDoc(
        source_url=source_url,
        content_hash=content_hash,
        blocks=blocks,
        tables=tables,
        ocr_confidence=None,
    )