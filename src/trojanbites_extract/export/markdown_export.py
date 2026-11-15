from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_markdown(snapshot: dict[str, Any]) -> str:
    meta = snapshot["meta"]
    lines: list[str] = []
    lines.append(f"# {meta.get('product', 'Trojan Fork')} — USC Restaurant Extract")
    lines.append("")
    lines.append("## Scope and boundary")
    lines.append("")
    lines.append(f"- Campus: `{meta.get('campus_id')}`")
    lines.append(
        f"- Boundary: `{meta.get('boundary_id')}` @ `{meta.get('boundary_version')}`"
    )
    lines.append(f"- Boundary source: {meta.get('boundary_source_url')}")
    lines.append(f"- Generated at: `{meta.get('generated_at')}`")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append(meta.get("methodology") or "")
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for lim in meta.get("limitations") or []:
        lines.append(f"- {lim}")
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    cov = meta.get("coverage") or {}
    for k, v in cov.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")
    lines.append("## Macros tracked")
    lines.append("")
    lines.append(
        ", ".join(f"`{m}`" for m in meta.get("macros_fields") or [])
    )
    lines.append("")
    lines.append("## Restaurant directory")
    lines.append("")
    for r in snapshot.get("restaurants") or []:
        b = r.get("boundary") or {}
        lines.append(
            f"- **{r['name']}**"
            + (f" ({r['branch_name']})" if r.get("branch_name") else "")
            + f" — boundary `{b.get('status')}` — `{r['restaurant_id']}`"
        )
    lines.append("")

    nut_by_item: dict[str, list[dict[str, Any]]] = {}
    for n in snapshot.get("nutrition") or []:
        nut_by_item.setdefault(n["item_id"], []).append(n)

    lines.append("## Menus, prices, and nutrition")
    lines.append("")
    by_rest: dict[str, list[dict[str, Any]]] = {}
    for item in snapshot.get("menu_items") or []:
        by_rest.setdefault(item["restaurant_id"], []).append(item)
    name_by_id = {r["restaurant_id"]: r["name"] for r in snapshot.get("restaurants") or []}

    for rid, items in by_rest.items():
        lines.append(f"### {name_by_id.get(rid, rid)}")
        lines.append("")
        lines.append(
            "| Item | Size | Price | Status | Cal | Protein g | Carbs g | Fat g | Fiber g | Sugar g | Sodium mg |"
        )
        lines.append(
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
        )
        for item in items:
            nuts = nut_by_item.get(item["item_id"]) or []
            for variant in item.get("variants") or []:
                nut = next(
                    (n for n in nuts if n.get("variant_id") == variant.get("variant_id")),
                    nuts[0] if nuts else None,
                )
                pub = (nut or {}).get("published") or {}
                status = (nut or {}).get("evidence_status") or "unknown"
                price = variant.get("price") or {}
                amount = price.get("amount")
                price_s = (
                    f"{price.get('currency', 'USD')} {amount:.2f}"
                    if amount is not None
                    else "null"
                )

                def fmt(v: Any) -> str:
                    return "null" if v is None else str(v)

                lines.append(
                    "| "
                    + " | ".join(
                        [
                            item["name"].replace("|", "/"),
                            str(variant.get("size_label") or ""),
                            price_s,
                            status,
                            fmt(pub.get("calories_kcal")),
                            fmt(pub.get("protein_g")),
                            fmt(pub.get("carbohydrates_g")),
                            fmt(pub.get("fat_g")),
                            fmt(pub.get("fiber_g")),
                            fmt(pub.get("sugar_g")),
                            fmt(pub.get("sodium_mg")),
                        ]
                    )
                    + " |"
                )
        lines.append("")

    lines.append("## Sources")
    lines.append("")
    for s in snapshot.get("sources") or []:
        lines.append(
            f"- `{s.get('source_type')}` — {s.get('url')} (checked {s.get('retrieved_at')})"
        )
    lines.append("")
    lines.append(
        "_This Markdown contains no facts absent from `usc_restaurants.json`._"
    )
    lines.append("")
    return "\n".join(lines)


def write_markdown_export(snapshot: dict[str, Any] | Path, out_path: Path) -> Path:
    if isinstance(snapshot, Path):
        snapshot = json.loads(snapshot.read_text(encoding="utf-8"))
    out_path.write_text(render_markdown(snapshot), encoding="utf-8")  # type: ignore[arg-type]
    return out_path