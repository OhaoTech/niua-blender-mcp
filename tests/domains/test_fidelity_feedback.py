import base64

from niua_mcp_bridge.core import fidelity_metrics as fm
from niua_mcp_bridge.core import silhouette_metrics as sm
from niua_mcp_bridge.finishing import preservation_ledger as ledger


def test_surface_fidelity_floor_exists():
    assert isinstance(ledger.SURFACE_FIDELITY_FLOOR, float)
    assert 0.5 < ledger.SURFACE_FIDELITY_FLOOR <= 1.0


def test_ledger_roundtrips_shaded_baseline():
    # store a compact luma+mask and read it back through the compact codec
    luma = bytes(range(16)) * 16  # 256 bytes -> 16x16
    mask = bytes([1]) * 256
    rec = {"available": True, "shaded": {"views": {
        "front": {"luma": sm.compact_encode(luma), "mask": sm.compact_encode(mask)}},
        "shape": [16, 16]}}
    ledger.set_intake("Obj", rec)
    got = ledger.get_intake("Obj")
    dec_luma = sm.compact_decode(got["shaded"]["views"]["front"]["luma"])
    assert dec_luma == luma
    ledger.reset()


def test_mean_fidelity_wired_end_to_end_on_decoded_views():
    # sanity: the metric the handler will call behaves on real luma+mask tuples
    w = h = 16
    a = bytes(((x // 8) * 30) % 256 for _ in range(h) for x in range(w))
    m = bytes([1]) * (w * h)
    out = fm.mean_fidelity({"front": (w, h, a, m)}, {"front": (w, h, a, m)})
    assert out["available"] and out["fidelity"] > 0.99
