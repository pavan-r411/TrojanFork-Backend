from __future__ import annotations

from trojanbites_extract.parse.html import EvidenceDoc


def chunk_evidence(doc: EvidenceDoc, max_chars: int = 12000) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for block in doc.blocks:
        payload = {
            "block_id": block.block_id,
            "text": block.text,
            "kind": block.kind,
            "page": block.page,
            "meta": block.meta,
        }
        add = len(block.text) + 32
        if current and size + add > max_chars:
            chunks.append(current)
            current = []
            size = 0
        current.append(payload)
        size += add
    if current:
        chunks.append(current)
    return chunks or [[]]