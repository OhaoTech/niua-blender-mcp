from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).parent
_ITEMS = _ROOT / "items"
_RUBRICS = _ROOT / "rubrics"


def list_items() -> list[str]:
    if not _ITEMS.exists():
        return []
    return sorted(p.name for p in _ITEMS.iterdir() if (p / "item.json").is_file())


def load_item(item_id: str) -> dict:
    item_file = _ITEMS / item_id / "item.json"
    if not item_file.is_file():
        raise KeyError(item_id)
    item = json.loads(item_file.read_text(encoding="utf-8"))
    rubric_file = _RUBRICS / f"{item['rubric']}.md"
    if not rubric_file.is_file():
        raise KeyError(item["rubric"])
    item["rubric_text"] = rubric_file.read_text(encoding="utf-8")
    return item
