from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from trojanbites_extract.ids import new_id
from trojanbites_extract.store.models import ReviewQueueItem


def enqueue_review(
    session: Session,
    *,
    entity_type: str,
    entity_id: str,
    reason_codes: list[str],
    evidence_snapshot_ref: str | None = None,
    model_review_signals: dict[str, Any] | None = None,
) -> ReviewQueueItem:
    item = ReviewQueueItem(
        review_id=new_id("rev"),
        entity_type=entity_type,
        entity_id=entity_id,
        reason_codes_json=reason_codes,
        evidence_snapshot_ref=evidence_snapshot_ref,
        model_review_signals_json=model_review_signals or {},
        status="open",
        created_at=datetime.utcnow(),
    )
    session.add(item)
    return item