from __future__ import annotations

from pathlib import Path

from trojanbites_extract.parse.html import EvidenceBlock, EvidenceDoc


def parse_image_ocr(path: Path, source_url: str, content_hash: str | None) -> EvidenceDoc:
    """Optional OCR path. Requires optional deps: pytesseract + Pillow."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        return EvidenceDoc(
            source_url=source_url,
            content_hash=content_hash,
            blocks=[
                EvidenceBlock(
                    block_id="ocr_unavailable",
                    text="",
                    kind="ocr",
                    meta={"error": f"OCR dependencies missing: {exc}"},
                )
            ],
            ocr_confidence=0.0,
        )

    image = Image.open(path)
    text = pytesseract.image_to_string(image)
    # pytesseract does not always expose a single confidence; leave null-ish low if empty
    conf = 0.8 if text.strip() else 0.1
    return EvidenceDoc(
        source_url=source_url,
        content_hash=content_hash,
        blocks=[
            EvidenceBlock(
                block_id="ocr_1",
                text=text,
                kind="ocr",
                meta={"suspicious_ocr": conf < 0.5},
            )
        ],
        ocr_confidence=conf,
    )