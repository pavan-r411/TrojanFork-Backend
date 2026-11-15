from __future__ import annotations

from pathlib import Path

from trojanbites_extract.parse.html import EvidenceDoc, parse_html_file
from trojanbites_extract.parse.ocr import parse_image_ocr
from trojanbites_extract.parse.pdf import parse_pdf_file
from trojanbites_extract.retrieve.fetcher import RawArtifact


def artifact_to_evidence(artifact: RawArtifact) -> EvidenceDoc:
    if not artifact.ok or not artifact.bytes_path:
        return EvidenceDoc(
            source_url=artifact.url,
            content_hash=None,
            blocks=[],
        )
    path = Path(artifact.bytes_path)
    ctype = (artifact.content_type or "").lower()
    if "pdf" in ctype or path.suffix.lower() == ".pdf":
        return parse_pdf_file(path, artifact.url, artifact.content_hash)
    if ctype.startswith("image/"):
        return parse_image_ocr(path, artifact.url, artifact.content_hash)
    return parse_html_file(path, artifact.url, artifact.content_hash)