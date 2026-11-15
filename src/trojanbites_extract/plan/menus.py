from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from trojanbites_extract.settings import ROOT

USC_DINING_DIR = ROOT / "data" / "menus" / "usc_dining"
OFF_CAMPUS_PATH = ROOT / "data" / "menus" / "off_campus" / "curated_upc_0_3mi.json"


def _latest_usc_dining_path() -> Path:
    dates = sorted(
        [p for p in USC_DINING_DIR.iterdir() if p.is_dir()],
        reverse=True,
    )
    if not dates:
        raise FileNotFoundError("No USC dining snapshots under data/menus/usc_dining/")
    snap = dates[0] / "snapshot.json"
    if not snap.exists():
        raise FileNotFoundError(f"Missing snapshot: {snap}")
    return snap


@lru_cache
def load_usc_dining_menu(menu_date: str | None = None) -> dict[str, Any]:
    if menu_date:
        path = USC_DINING_DIR / menu_date / "snapshot.json"
    else:
        path = _latest_usc_dining_path()
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    data["_path"] = str(path.relative_to(ROOT))
    return data


@lru_cache
def load_off_campus_menu() -> dict[str, Any]:
    with OFF_CAMPUS_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    data["_path"] = str(OFF_CAMPUS_PATH.relative_to(ROOT))
    return data


def clear_menu_cache() -> None:
    load_usc_dining_menu.cache_clear()
    load_off_campus_menu.cache_clear()
