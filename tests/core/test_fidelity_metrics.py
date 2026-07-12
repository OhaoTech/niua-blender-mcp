from niua_mcp_bridge.core import fidelity_metrics as fm


def _solid(w, h, val):
    return bytes([val]) * (w * h)


def _full_mask(w, h):
    return bytes([1]) * (w * h)


def test_identical_images_score_one():
    w = h = 16
    a = _solid(w, h, 120)
    assert fm.block_ssim(a, a, _full_mask(w, h), w, h) == 1.0 or abs(fm.block_ssim(a, a, _full_mask(w, h), w, h) - 1.0) < 1e-9


def test_structural_difference_drops_score():
    w = h = 16
    # a: smooth gradient; b: block-flattened (detail lost) -> lower SSIM
    a = bytes((x * 8) % 256 for y in range(h) for x in range(w))
    b = bytes(((x // 8) * 64) % 256 for y in range(h) for x in range(w))
    s = fm.block_ssim(a, b, _full_mask(w, h), w, h)
    assert s is not None and s < 0.9


def test_too_small_masked_region_is_none():
    w = h = 16
    mask = bytearray(w * h)  # all background
    mask[0] = 1
    assert fm.block_ssim(_solid(w, h, 100), _solid(w, h, 100), bytes(mask), w, h) is None


def test_mean_fidelity_aggregates_common_views_min_reported():
    w = h = 16
    a = _solid(w, h, 100); m = _full_mask(w, h)
    intake = {"front": (w, h, a, m), "right": (w, h, a, m)}
    b_diff = bytes(((x // 8) * 80) % 256 for y in range(h) for x in range(w))
    current = {"front": (w, h, a, m), "right": (w, h, b_diff, m)}
    out = fm.mean_fidelity(intake, current)
    assert out["available"] is True
    assert set(out["per_view"]) == {"front", "right"}
    assert out["min_view"]["view"] == "right"
    assert out["fidelity"] <= out["per_view"]["front"]


def test_mean_fidelity_unavailable_when_no_separable_view():
    w = h = 16
    tiny = bytearray(w * h); tiny[0] = 1
    a = _solid(w, h, 100)
    out = fm.mean_fidelity({"front": (w, h, a, bytes(tiny))}, {"front": (w, h, a, bytes(tiny))})
    assert out["available"] is False
