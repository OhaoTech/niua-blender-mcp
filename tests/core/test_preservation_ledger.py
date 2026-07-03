from __future__ import annotations

from niua_mcp_bridge.core import preservation_ledger as ledger


def test_floor_and_views_constants() -> None:
    assert ledger.PRESERVATION_FLOOR == 0.85
    assert ledger.PRESERVATION_VIEWS == ("front", "right", "top")  # ortho-only, no persp


def test_set_get_reset_roundtrip() -> None:
    ledger.reset()
    assert ledger.get_intake("Cube") is None
    ledger.set_intake("Cube", {"available": True, "masks": {"front": "x"}})
    assert ledger.get_intake("Cube")["masks"]["front"] == "x"
    ledger.reset()
    assert ledger.get_intake("Cube") is None
