# tests/core/test_silhouette_metrics.py
from __future__ import annotations

import base64
import io

from niua_mcp_bridge.core import silhouette_metrics as sm


def _rgba(rows: list[list[int]]) -> str:
    """Encode a 0/1 mask as a base64 RGBA PNG: object alpha=255, background alpha=0.

    Background RGB is deliberately BRIGHT so a luma threshold would wrongly include it —
    proving the alpha path is background/lighting invariant. (test-only, uses Pillow)
    """
    from PIL import Image

    h, w = len(rows), len(rows[0])
    img = Image.new("RGBA", (w, h))
    img.putdata([(200, 200, 210, 255) if v else (240, 240, 240, 0) for r in rows for v in r])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _solid(w: int, h: int, val: int) -> str:
    return _rgba([[val] * w for _ in range(h)])


def test_decode_uses_alpha_not_luma() -> None:
    # Bright bg (luma high) but alpha 0 -> mask must be empty (alpha-driven).
    w, h, mask = sm.png_b64_to_mask(_solid(4, 4, 0))
    assert (w, h) == (4, 4)
    assert set(mask) == {0}
    _, _, full = sm.png_b64_to_mask(_solid(4, 4, 1))
    assert set(full) == {1}


def test_iou_identical_is_one() -> None:
    _, _, m = sm.png_b64_to_mask(_solid(16, 16, 1))
    assert sm.compute_iou(m, m) == 1.0


def test_iou_disjoint_is_zero() -> None:
    top = sm.png_b64_to_mask(_rgba([[1, 1], [0, 0]]))[2]
    bot = sm.png_b64_to_mask(_rgba([[0, 0], [1, 1]]))[2]
    assert sm.compute_iou(top, bot) == 0.0


def test_iou_half_overlap_is_one_third() -> None:
    a = sm.png_b64_to_mask(_rgba([[1, 1], [0, 0]]))[2]
    b = sm.png_b64_to_mask(_rgba([[1, 0], [1, 0]]))[2]
    assert abs(sm.compute_iou(a, b) - 1 / 3) < 1e-9


def test_iou_length_mismatch_is_none() -> None:
    assert sm.compute_iou(b"\x01\x01", b"\x01") is None


def test_separability_flags_empty_and_full() -> None:
    empty = sm.png_b64_to_mask(_solid(8, 8, 0))[2]
    full = sm.png_b64_to_mask(_solid(8, 8, 1))[2]
    half = sm.png_b64_to_mask(_rgba([[1, 1], [0, 0]]))[2]
    assert sm.is_separable(empty) is False
    assert sm.is_separable(full) is False
    assert sm.is_separable(half) is True


def test_mean_preservation_identical_separable() -> None:
    views = {v: sm.png_b64_to_mask(_rgba([[1, 1], [1, 0]]))[2] for v in ("front", "right", "top")}
    out = sm.mean_preservation(views, dict(views))
    assert out["available"] is True
    assert out["preservation"] == 1.0
    assert set(out["per_view"]) == {"front", "right", "top"}


def test_mean_preservation_detects_damage_and_min_view() -> None:
    full = sm.png_b64_to_mask(_rgba([[1, 1], [1, 1]]))[2]     # not separable alone
    half = sm.png_b64_to_mask(_rgba([[1, 1], [0, 0]]))[2]
    quarter = sm.png_b64_to_mask(_rgba([[1, 0], [0, 0]]))[2]
    intake = {"front": half, "right": half}
    current = {"front": half, "right": quarter}
    out = sm.mean_preservation(intake, current)
    assert out["available"] is True
    assert 0.0 < out["preservation"] < 1.0
    assert out["min_view"]["view"] == "right"  # the collapsed view surfaces, not diluted
    # A fully-collapsed (empty) or fully-full mask is not separable -> excluded, not scored 1.0.
    assert sm.mean_preservation({"front": half}, {"front": full})["available"] is False


def test_mean_preservation_no_separable_views_is_unavailable() -> None:
    empty = sm.png_b64_to_mask(_solid(4, 4, 0))[2]
    out = sm.mean_preservation({"front": empty}, {"front": empty})
    assert out["available"] is False
    assert "reason" in out


def test_bbox_delta_uniform_scale_is_visible() -> None:
    same = sm.bbox_delta((2.0, 1.0, 3.0), (2.0, 1.0, 3.0))
    assert same["changed"] is False
    scaled = sm.bbox_delta((2.0, 1.0, 3.0), (1.0, 0.5, 1.5))  # uniform 0.5x
    assert scaled["changed"] is True
    assert abs(scaled["scale_ratio"] - 0.5) < 1e-9
    assert scaled["aspect_delta"] < 1e-9  # aspect unchanged, but scale flagged
    squashed = sm.bbox_delta((2.0, 2.0, 2.0), (2.0, 1.0, 2.0))
    assert squashed["changed"] is True
    assert squashed["aspect_delta"] > 0.0


def test_compact_codec_roundtrip() -> None:
    _, _, m = sm.png_b64_to_mask(_rgba([[1, 0], [0, 1]]))
    assert sm.compact_decode(sm.compact_encode(m)) == m
