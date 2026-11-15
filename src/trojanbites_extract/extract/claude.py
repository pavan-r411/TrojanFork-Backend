from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import anthropic

from trojanbites_extract.extract.chunking import chunk_evidence
from trojanbites_extract.extract.merge import merge_extractions
from trojanbites_extract.ids import new_id
from trojanbites_extract.parse.html import EvidenceDoc
from trojanbites_extract.settings import get_settings, load_extraction_config, require_anthropic_key

EXTRACTION_JSON_SCHEMA_HINT = {
    "type": "object",
    "required": ["menu_items", "conflicts", "ambiguities"],
    "properties": {
        "menu_items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "variants"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": ["string", "null"]},
                    "category": {"type": ["string", "null"]},
                    "menu_section": {"type": ["string", "null"]},
                    "variants": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "size_label": {"type": ["string", "null"]},
                                "serving_label": {"type": ["string", "null"]},
                                "price": {
                                    "type": "object",
                                    "properties": {
                                        "amount": {"type": ["number", "null"]},
                                        "currency": {"type": ["string", "null"]},
                                    },
                                },
                                "addons": {"type": "array"},
                            },
                        },
                    },
                    "ingredients_published": {"type": ["array", "null"]},
                    "dietary_claims": {"type": "array"},
                    "allergen_claims": {"type": "array"},
                    "availability": {"type": "object"},
                    "nutrition": {
                        "type": ["object", "null"],
                        "properties": {
                            "evidence_status": {
                                "enum": ["restaurant_published", "estimated", "unknown"]
                            },
                            "serving_basis": {"type": ["string", "null"]},
                            "published": {
                                "type": "object",
                                "properties": {
                                    "calories_kcal": {"type": ["number", "null"]},
                                    "protein_g": {"type": ["number", "null"]},
                                    "carbohydrates_g": {"type": ["number", "null"]},
                                    "fat_g": {"type": ["number", "null"]},
                                    "fiber_g": {"type": ["number", "null"]},
                                    "sugar_g": {"type": ["number", "null"]},
                                    "sodium_mg": {"type": ["number", "null"]},
                                },
                            },
                            "estimated": {"type": ["object", "null"]},
                        },
                    },
                    "ambiguities": {"type": "array"},
                },
            },
        },
        "conflicts": {"type": "array"},
        "ambiguities": {"type": "array"},
        "_review_signals": {"type": "object"},
    },
}


def _load_system_prompt() -> str:
    path = get_settings().prompts_dir / "extract_menu_v1.md"
    text = path.read_text(encoding="utf-8")
    if "# System" in text:
        return text.split("# User template")[0].replace("# System", "").strip()
    return text


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _ensure_ids(result: dict[str, Any], restaurant_id: str) -> dict[str, Any]:
    for item in result.get("menu_items") or []:
        item.setdefault("item_id", new_id("item"))
        item["restaurant_id"] = restaurant_id
        item.setdefault("dietary_claims", [])
        item.setdefault("allergen_claims", [])
        item.setdefault(
            "availability",
            {"status": "unknown", "meal_periods": [], "days": None},
        )
        item.setdefault("ambiguities", [])
        for variant in item.get("variants") or []:
            variant.setdefault("variant_id", new_id("var"))
            variant.setdefault("addons", [])
            price = variant.setdefault("price", {"amount": None, "currency": "USD"})
            price.setdefault("currency", "USD")
        nut = item.get("nutrition")
        if nut:
            nut.setdefault("nutrition_id", new_id("nut"))
            nut["item_id"] = item["item_id"]
            if item.get("variants"):
                nut["variant_id"] = item["variants"][0]["variant_id"]
            nut.setdefault("evidence_status", "unknown")
            published = nut.setdefault("published", {})
            for field in (
                "calories_kcal",
                "protein_g",
                "carbohydrates_g",
                "fat_g",
                "fiber_g",
                "sugar_g",
                "sodium_mg",
            ):
                published.setdefault(field, None)
            # Never promote estimates into published
            if nut.get("evidence_status") != "restaurant_published":
                # keep published nulls if not published
                pass
            nut.setdefault("estimated", None)
    result.setdefault("conflicts", [])
    result.setdefault("ambiguities", [])
    return result


class ClaudeExtractor:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=require_anthropic_key())
        self.settings = get_settings()
        cfg = load_extraction_config().get("claude", {})
        self.max_repair = int(cfg.get("max_repair_retries", 2))
        self.max_chars = int(cfg.get("max_evidence_chars_per_chunk", 12000))
        self.prompt_version = cfg.get("prompt_version", "extract_menu_v1")
        self.system = _load_system_prompt()

    def extract(
        self,
        doc: EvidenceDoc,
        restaurant_id: str,
        restaurant_name: str,
        branch_name: str | None = None,
        address_formatted: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        chunks = chunk_evidence(doc, max_chars=self.max_chars)
        partials: list[dict[str, Any]] = []
        costs = {
            "llm_input_tokens": 0,
            "llm_output_tokens": 0,
            "llm_usd": 0.0,
            "chunks": len(chunks),
        }
        prior_keys: list[str] = []

        for idx, chunk in enumerate(chunks, start=1):
            user = self._user_message(
                restaurant_id=restaurant_id,
                name=restaurant_name,
                branch_name=branch_name,
                address_formatted=address_formatted,
                chunk_index=idx,
                chunk_total=len(chunks),
                prior_keys=prior_keys,
                evidence_blocks=chunk,
            )
            parsed, usage = self._call_with_repairs(user)
            costs["llm_input_tokens"] += usage.get("input_tokens", 0)
            costs["llm_output_tokens"] += usage.get("output_tokens", 0)
            parsed = _ensure_ids(parsed, restaurant_id)
            for item in parsed.get("menu_items") or []:
                prior_keys.append(item.get("name") or "")
            partials.append(parsed)

        merged = merge_extractions(*partials) if partials else {
            "menu_items": [],
            "conflicts": [],
            "ambiguities": ["no_chunks"],
        }
        # Rough cost placeholder — update with current Anthropic pricing if needed
        costs["llm_usd"] = (
            costs["llm_input_tokens"] * 3e-6 + costs["llm_output_tokens"] * 15e-6
        )
        return merged, costs

    def _user_message(self, **kwargs: Any) -> str:
        return (
            f"RESTAURANT_CONTEXT:\n"
            f"{kwargs['restaurant_id']} | {kwargs['name']} | "
            f"{kwargs.get('branch_name')} | {kwargs.get('address_formatted')}\n\n"
            f"SCHEMA:\n{json.dumps(EXTRACTION_JSON_SCHEMA_HINT)}\n\n"
            f"PROMPT_VERSION: {self.prompt_version}\n"
            f"CHUNK: {kwargs['chunk_index']} / {kwargs['chunk_total']}\n"
            f"PRIOR_ITEM_KEYS_FROM_EARLIER_CHUNKS: {json.dumps(kwargs['prior_keys'])}\n\n"
            f"EVIDENCE_BLOCKS:\n{json.dumps(kwargs['evidence_blocks'])}\n\n"
            "TASK:\nExtract menu items, variants, prices, published ingredients, "
            "dietary/allergen claims, and published nutrition macros "
            "(calories_kcal, protein_g, carbohydrates_g, fat_g, fiber_g, sugar_g, sodium_mg). "
            "Use null for unknowns. Do not invent values. Estimation is disabled."
        )

    def _call_with_repairs(self, user: str) -> tuple[dict[str, Any], dict[str, int]]:
        usage_total = {"input_tokens": 0, "output_tokens": 0}
        last_error = None
        messages = [{"role": "user", "content": user}]
        for attempt in range(self.max_repair + 1):
            resp = self.client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=4096,
                system=self.system,
                messages=messages,
            )
            usage_total["input_tokens"] += getattr(resp.usage, "input_tokens", 0) or 0
            usage_total["output_tokens"] += getattr(resp.usage, "output_tokens", 0) or 0
            text = "".join(
                block.text for block in resp.content if getattr(block, "type", None) == "text"
            )
            try:
                data = json.loads(_strip_fences(text))
                if not isinstance(data, dict) or "menu_items" not in data:
                    raise ValueError("JSON missing menu_items")
                return data, usage_total
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                messages.append({"role": "assistant", "content": text})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your previous output was invalid ({exc}). "
                            "Return corrected JSON only matching the schema. "
                            "Do not invent facts."
                        ),
                    }
                )
        raise RuntimeError(f"Claude extraction failed after repairs: {last_error}")