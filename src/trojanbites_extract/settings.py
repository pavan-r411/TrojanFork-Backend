from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider_records_enabled: bool = False
    provider_records_dir: Path = Path('data/provider_records')

    gemini_api_key: str | None = None
    gemini_model: str = 'gemini-3.5-flash'
    gemini_timeout_s: float = Field(35, gt=0, le=60)

    recommendation_provider: str = 'openai'
    openai_api_key: str | None = None
    openai_model: str = 'gpt-4.1-mini'
    openai_timeout_s: float = Field(8.0, gt=0, le=30)
    recommendation_candidate_limit: int = Field(30, ge=1, le=100)

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    google_maps_api_key: str | None = None
    web_search_api_key: str | None = None
    web_search_provider: str = "none"
    database_url: str = "sqlite:///./data/trojanbites.db"
    log_level: str = "INFO"
    max_llm_usd_per_day: float = 25.0
    max_places_requests_per_day: int = 500

    config_path: Path = Field(default=ROOT / "config" / "extraction.yaml")

    @property
    def root(self) -> Path:
        return ROOT

    @property
    def schemas_dir(self) -> Path:
        return ROOT / "schemas"

    @property
    def prompts_dir(self) -> Path:
        return ROOT / "prompts"

    @property
    def boundaries_dir(self) -> Path:
        return ROOT / "boundaries"

    @property
    def artifacts_dir(self) -> Path:
        path = ROOT / "data" / "artifacts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def exports_dir(self) -> Path:
        path = ROOT / "exports"
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def load_extraction_config() -> dict[str, Any]:
    settings = get_settings()
    with settings.config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def require_anthropic_key() -> str:
    key = (
        get_settings().anthropic_api_key
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("CLAUDE_API_KEY")
    )
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY missing. Copy .env.example to .env and add your key "
            "(CLAUDE_API_KEY is also accepted)."
        )
    return key


def require_google_key() -> str:
    key = get_settings().google_maps_api_key or os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY missing. Copy .env.example to .env and add your key."
        )
    return key