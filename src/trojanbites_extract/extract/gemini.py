"""Gemini extraction + authorized Google Search grounding for menu discovery.

Uses the Generative Language REST API (no SDK required). Never invents menu
facts; missing values stay null. Search grounding is used only to locate
official website / menu / nutrition URLs — not to invent dishes.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from trojanbites_extract.extract.claude import EXTRACTION_JSON_SCHEMA_HINT, _ensure_ids, _strip_fences
from trojanbites_extract.ids import new_id
from trojanbites_extract.parse.html import EvidenceDoc
from trojanbites_extract.provider_records import record_response
from trojanbites_extract.settings import get_settings

logger = logging.getLogger(__name__)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def require_gemini_key() -> str:
    key = get_settings().gemini_api_key
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY missing. Copy .env.example to .env and add your key."
        )
    return key


class GeminiClient:
    # Process-wide circuit when quota is exhausted
    quota_exhausted: bool = False

    def __init__(self, api_key: str | None = None, model: str | None = None):
        settings = get_settings()
        self.api_key = api_key or require_gemini_key()
        self.model = model or settings.gemini_model
        self.timeout = float(settings.gemini_timeout_s)

    def _endpoint(self) -> str:
        return f"{GEMINI_BASE}/models/{self.model}:generateContent"

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        use_google_search: bool = False,
        temperature: float = 0.1,
        operation: str = "gemini_generate",
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Return (parsed_json_or_none, meta)."""
        meta: dict[str, Any] = {
            "provider": "gemini",
            "model": self.model,
            "operation": operation,
            "search_grounding": use_google_search,
        }
        if GeminiClient.quota_exhausted:
            meta["error"] = "gemini_quota_circuit_open"
            meta["http_status"] = 429
            return None, meta

        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
            },
        }
        if use_google_search:
            body["tools"] = [{"google_search": {}}]

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    self._endpoint(),
                    params={"key": self.api_key},
                    json=body,
                )
            try:
                record_response("gemini", operation, resp)
            except Exception:  # noqa: BLE001
                pass
            meta["http_status"] = resp.status_code
            if resp.status_code == 429:
                GeminiClient.quota_exhausted = True
                meta["error"] = "gemini_quota_exhausted"
                return None, meta
            if resp.status_code >= 400:
                meta["error"] = resp.text[:500]
                return None, meta
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            meta["error"] = str(exc)
            return None, meta

        text = _extract_text(data)
        meta["usage"] = data.get("usageMetadata") or {}
        grounding = data.get("candidates", [{}])[0].get("groundingMetadata")
        if grounding:
            meta["grounding"] = {
                "web_search_queries": grounding.get("webSearchQueries"),
                "grounding_chunks": [
                    (c.get("web") or {}).get("uri")
                    for c in (grounding.get("groundingChunks") or [])
                    if isinstance(c, dict)
                ],
            }
        if not text:
            meta["error"] = "empty_response"
            return None, meta
        try:
            return json.loads(_strip_fences(text)), meta
        except json.JSONDecodeError as exc:
            meta["error"] = f"json_parse:{exc}"
            meta["raw_text_preview"] = text[:400]
            return None, meta


def _extract_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for cand in data.get("candidates") or []:
        content = cand.get("content") or {}
        for part in content.get("parts") or []:
            if isinstance(part, dict) and part.get("text"):
                parts.append(part["text"])
    return "\n".join(parts).strip()


MENU_FIND_SYSTEM = """You locate official restaurant menu sources for a food-data pipeline.
Return JSON only. Rules:
1. Prefer the restaurant's own official website, PDF menus, and restaurant-published nutrition pages.
2. Do not invent URLs. Only return URLs you can support from search results or the provided website.
3. Prefer non-login, non-delivery-aggregator pages when an official site exists.
4. If nothing usable is found, return empty arrays and explain attempts in attempts[].
5. Never scrape or recommend bypassing Google Maps HTML pages.
Schema:
{
  "official_website": string|null,
  "menu_urls": [{"url": string, "kind": "html_menu"|"pdf_menu"|"ordering"|"nutrition"|"other", "confidence": "high"|"medium"|"low"}],
  "ordering_urls": [string],
  "nutrition_urls": [string],
  "attempts": [string],
  "notes": string|null
}
"""


class GeminiMenuFinder:
    def __init__(self, client: GeminiClient | None = None):
        self.client = client or GeminiClient()

    def find_menu_links(
        self,
        *,
        name: str,
        address: str | None,
        website: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        user = (
            f"Restaurant: {name}\n"
            f"Branch address: {address or 'unknown'}\n"
            f"Known website hint: {website or 'none'}\n"
            "Find official website, menu, ordering, and nutrition pages. "
            "Search using the restaurant name, branch address, and terms menu / nutrition / order."
        )
        parsed, meta = self.client.generate_json(
            system=MENU_FIND_SYSTEM,
            user=user,
            use_google_search=True,
            operation="gemini_menu_find",
        )
        if not parsed:
            return {
                "official_website": website,
                "menu_urls": [],
                "ordering_urls": [],
                "nutrition_urls": [],
                "attempts": [meta.get("error") or "gemini_menu_find_failed"],
                "notes": None,
            }, meta
        # Keep website hint if model omitted it
        if not parsed.get("official_website") and website:
            parsed["official_website"] = website
        parsed.setdefault("menu_urls", [])
        parsed.setdefault("ordering_urls", [])
        parsed.setdefault("nutrition_urls", [])
        parsed.setdefault("attempts", [])
        return parsed, meta


EXTRACT_SYSTEM = """You are an extraction engine for TrojanPlate.
Extract restaurant menu and nutrition facts ONLY from the EVIDENCE blocks.
Hard rules:
1. Evidence-only. Missing values must be null. Never invent dishes, prices, calories, macros, allergens, or dietary claims.
2. Do not infer calories or allergens from food photographs or dish names alone.
3. Preserve sizes/variants and item-to-price relationships. Flag blurry/ambiguous text in ambiguities.
4. Nutrition macros only when restaurant-published in evidence. Keep estimates null unless evidence explicitly states estimation (default: no estimates).
5. Output JSON matching the provided schema only.
"""


class GeminiExtractor:
    def __init__(self, client: GeminiClient | None = None):
        self.client = client or GeminiClient()

    def extract(
        self,
        doc: EvidenceDoc,
        *,
        restaurant_id: str,
        restaurant_name: str,
        branch_name: str | None = None,
        address_formatted: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        evidence_blocks = []
        for i, block in enumerate(doc.blocks[:80]):
            text = getattr(block, "text", None) or str(block)
            if text and text.strip():
                evidence_blocks.append({"block_id": f"b{i}", "text": text[:4000]})
        for i, table in enumerate(doc.tables[:20]):
            evidence_blocks.append({"block_id": f"t{i}", "table": table})

        user = (
            f"RESTAURANT_CONTEXT:\n{restaurant_id} | {restaurant_name} | "
            f"{branch_name} | {address_formatted}\n\n"
            f"SCHEMA:\n{json.dumps(EXTRACTION_JSON_SCHEMA_HINT)}\n\n"
            f"SOURCE_URL: {doc.source_url}\nCONTENT_HASH: {doc.content_hash}\n\n"
            f"EVIDENCE_BLOCKS:\n{json.dumps(evidence_blocks)[:100000]}"
        )
        parsed, meta = self.client.generate_json(
            system=EXTRACT_SYSTEM,
            user=user,
            use_google_search=False,
            operation="gemini_menu_extract",
        )
        if not parsed:
            empty = {"menu_items": [], "conflicts": [], "ambiguities": [meta.get("error") or "gemini_failed"]}
            return empty, meta
        parsed.setdefault("menu_items", [])
        parsed.setdefault("conflicts", [])
        parsed.setdefault("ambiguities", [])
        return _ensure_ids(parsed, restaurant_id), meta


def extract_links_from_html(html: str, base_url: str) -> list[dict[str, str]]:
    """Heuristic nav/menu link discovery without inventing absolute paths beyond hrefs."""
    from urllib.parse import urljoin

    found: list[dict[str, str]] = []
    for match in re.finditer(
        r'href=["\']([^"\']+)["\'][^>]*>([^<]{0,80})',
        html,
        flags=re.I,
    ):
        href, label = match.group(1), match.group(2)
        blob = f"{href} {label}".lower()
        kind = None
        if href.lower().endswith(".pdf") and "menu" in blob:
            kind = "pdf_menu"
        elif "nutrition" in blob or "allergen" in blob:
            kind = "nutrition"
        elif any(k in blob for k in ("order", "online-ordering", "order-online")):
            kind = "ordering"
        elif any(k in blob for k in ("menu", "our-food", "food-menu")):
            kind = "html_menu"
        if kind:
            found.append({"url": urljoin(base_url, href), "kind": kind, "label": label.strip()})
    # de-dupe
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for row in found:
        if row["url"] in seen:
            continue
        seen.add(row["url"])
        out.append(row)
    return out


def new_attempt_id() -> str:
    return new_id("attempt")
