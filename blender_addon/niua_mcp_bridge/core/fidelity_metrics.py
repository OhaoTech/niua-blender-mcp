"""Pure-Python surface-fidelity metric: shaded-render luminance -> block-SSIM.

The do-no-harm SILHOUETTE metric (silhouette_metrics.py) measures the outline; this measures
the SURFACE. Two fixed-frame shaded renders (intake high-poly vs current) are compared with a
non-overlapping block SSIM over the masked (object) region -- structural, so lost surface detail
(facets, smeared normals) tanks the score while a global brightness shift barely moves it. Pure
stdlib, deterministic, fail-closed (too-small region -> None; no separable view -> unavailable).
"""

from __future__ import annotations

from .silhouette_metrics import decode_png_rgba

_C1 = (0.01 * 255) ** 2
_C2 = (0.03 * 255) ** 2


def png_b64_to_luma_mask(data_b64: str, threshold: int = 128) -> tuple[int, int, bytes, bytes]:
    import base64
    w, h, ch, px = decode_png_rgba(base64.b64decode(data_b64))
    luma = bytearray(w * h)
    mask = bytearray(w * h)
    has_alpha = ch in (2, 4)
    ai = ch - 1
    for i in range(w * h):
        base = i * ch
        if ch >= 3:
            luma[i] = (px[base] + px[base + 1] + px[base + 2]) // 3
        else:
            luma[i] = px[base]
        mask[i] = 1 if (has_alpha and px[base + ai] > threshold) else (0 if has_alpha else 1)
    return w, h, bytes(luma), bytes(mask)


def block_ssim(a: bytes, b: bytes, mask: bytes, w: int, h: int, block: int = 8, min_blocks: int = 4) -> float | None:
    scores: list[float] = []
    need = (block * block) // 2
    for by in range(0, h - block + 1, block):
        for bx in range(0, w - block + 1, block):
            av: list[int] = []
            bv: list[int] = []
            for yy in range(by, by + block):
                row = yy * w
                for xx in range(bx, bx + block):
                    if mask[row + xx]:
                        av.append(a[row + xx]); bv.append(b[row + xx])
            n = len(av)
            if n < need:
                continue
            ma = sum(av) / n
            mb = sum(bv) / n
            va = sum((x - ma) ** 2 for x in av) / n
            vb = sum((x - mb) ** 2 for x in bv) / n
            cov = sum((av[i] - ma) * (bv[i] - mb) for i in range(n)) / n
            s = ((2 * ma * mb + _C1) * (2 * cov + _C2)) / ((ma * ma + mb * mb + _C1) * (va + vb + _C2))
            scores.append(s)
    if len(scores) < min_blocks:
        return None
    return sum(scores) / len(scores)


def mean_fidelity(intake: dict, current: dict) -> dict:
    per_view: dict[str, float] = {}
    for view, (w, h, luma_i, mask_i) in intake.items():
        cur = current.get(view)
        if cur is None:
            continue
        w2, h2, luma_c, mask_c = cur
        if (w2, h2) != (w, h):
            continue
        combined = bytes(1 if (mask_i[i] and mask_c[i]) else 0 for i in range(w * h))
        s = block_ssim(luma_i, luma_c, combined, w, h)
        if s is not None:
            per_view[view] = s
    if not per_view:
        return {"available": False, "fidelity": None, "per_view": {}, "min_view": None}
    worst = min(per_view.items(), key=lambda kv: kv[1])
    return {"available": True, "fidelity": sum(per_view.values()) / len(per_view),
            "per_view": per_view, "min_view": {"view": worst[0], "ssim": worst[1]}}
