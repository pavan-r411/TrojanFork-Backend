from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Restaurant(Base):
    __tablename__ = "restaurants"

    restaurant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campus_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, default=None)
    university_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, default=None)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    branch_name: Mapped[Optional[str]] = mapped_column(String(512))
    address_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lng: Mapped[Optional[float]] = mapped_column(Float)
    geocode_provider: Mapped[Optional[str]] = mapped_column(String(128))
    geocoded_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    boundary_status: Mapped[str] = mapped_column(String(32), default="unknown")
    boundary_id: Mapped[Optional[str]] = mapped_column(String(64))
    boundary_version: Mapped[Optional[str]] = mapped_column(String(64))
    near_uncertain_edge: Mapped[bool] = mapped_column(Boolean, default=False)
    categories_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    cuisines_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    website: Mapped[Optional[str]] = mapped_column(String(1024))
    menu_links_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    business_status: Mapped[str] = mapped_column(String(64), default="unknown")
    hours_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    service_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_content_hash: Mapped[Optional[str]] = mapped_column(String(128))
    discontinued_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    provider_refs: Mapped[list[ProviderRef]] = relationship(back_populates="restaurant")
    menu_items: Mapped[list[MenuItem]] = relationship(back_populates="restaurant")
    sources: Mapped[list[Source]] = relationship(back_populates="restaurant")


class ProviderRef(Base):
    __tablename__ = "provider_refs"
    __table_args__ = (UniqueConstraint("provider", "place_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("restaurants.restaurant_id")
    )
    provider: Mapped[str] = mapped_column(String(64))
    place_id: Mapped[str] = mapped_column(String(256))
    refreshed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    restaurant: Mapped[Restaurant] = relationship(back_populates="provider_refs")


class Source(Base):
    __tablename__ = "sources"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    restaurant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("restaurants.restaurant_id")
    )
    url: Mapped[Optional[str]] = mapped_column(String(2048))
    publisher: Mapped[Optional[str]] = mapped_column(String(512))
    source_type: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    published_or_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    content_hash: Mapped[Optional[str]] = mapped_column(String(128))
    retention_class: Mapped[str] = mapped_column(String(64), default="retain_exportable")
    export_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    limitations: Mapped[Optional[str]] = mapped_column(Text)
    priority_tier: Mapped[int] = mapped_column(Integer, default=5)

    restaurant: Mapped[Restaurant] = relationship(back_populates="sources")


class MenuItem(Base):
    __tablename__ = "menu_items"

    item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    restaurant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("restaurants.restaurant_id")
    )
    name: Mapped[str] = mapped_column(String(512))
    raw_name: Mapped[Optional[str]] = mapped_column(String(512))
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(256))
    menu_section: Mapped[Optional[str]] = mapped_column(String(256))
    ingredients_json: Mapped[Optional[list[Any]]] = mapped_column(JSON)
    dietary_claims_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    allergen_claims_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    availability_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ambiguities_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    field_sources_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    discontinued_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    restaurant: Mapped[Restaurant] = relationship(back_populates="menu_items")
    variants: Mapped[list[MenuVariant]] = relationship(back_populates="item")


class MenuVariant(Base):
    __tablename__ = "menu_variants"

    variant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(64), ForeignKey("menu_items.item_id"))
    size_label: Mapped[Optional[str]] = mapped_column(String(128))
    serving_label: Mapped[Optional[str]] = mapped_column(String(128))
    price_amount: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    addons_json: Mapped[list[Any]] = mapped_column(JSON, default=list)

    item: Mapped[MenuItem] = relationship(back_populates="variants")
    nutrition: Mapped[Optional[Nutrition]] = relationship(
        back_populates="variant", uselist=False
    )


class Nutrition(Base):
    __tablename__ = "nutrition"

    nutrition_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(64), ForeignKey("menu_items.item_id"))
    variant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("menu_variants.variant_id"), unique=True
    )
    evidence_status: Mapped[str] = mapped_column(String(32), default="unknown")
    serving_basis: Mapped[Optional[str]] = mapped_column(String(256))
    # Published macros — null means unknown, never invent
    calories_kcal: Mapped[Optional[float]] = mapped_column(Float)
    protein_g: Mapped[Optional[float]] = mapped_column(Float)
    carbohydrates_g: Mapped[Optional[float]] = mapped_column(Float)
    fat_g: Mapped[Optional[float]] = mapped_column(Float)
    fiber_g: Mapped[Optional[float]] = mapped_column(Float)
    sugar_g: Mapped[Optional[float]] = mapped_column(Float)
    sodium_mg: Mapped[Optional[float]] = mapped_column(Float)
    estimated_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    field_sources_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    variant: Mapped[MenuVariant] = relationship(back_populates="nutrition")


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    restaurant_id: Mapped[Optional[str]] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    extraction_method: Mapped[Optional[str]] = mapped_column(String(32))
    model_id: Mapped[Optional[str]] = mapped_column(String(128))
    prompt_version: Mapped[Optional[str]] = mapped_column(String(64))
    validation_status: Mapped[Optional[str]] = mapped_column(String(32))
    conflicts_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    errors_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    cost_metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ReviewQueueItem(Base):
    __tablename__ = "review_queue"

    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    reason_codes_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    evidence_snapshot_ref: Mapped[Optional[str]] = mapped_column(String(512))
    model_review_signals_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="open")
    reviewer_action: Mapped[Optional[str]] = mapped_column(String(64))
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    audited_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    actor: Mapped[Optional[str]] = mapped_column(String(128))


class JobState(Base):
    __tablename__ = "job_state"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stage: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[Optional[str]] = mapped_column(String(64))
    cursor: Mapped[Optional[str]] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class IngestionJob(Base):
    """Campus-scoped collection job with resumable/idempotent semantics."""

    __tablename__ = "ingestion_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campus_id: Mapped[str] = mapped_column(String(64), index=True)
    job_type: Mapped[str] = mapped_column(String(64), default="campus_slice")
    # queued | running | partial | completed | failed
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    progress_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    errors_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )