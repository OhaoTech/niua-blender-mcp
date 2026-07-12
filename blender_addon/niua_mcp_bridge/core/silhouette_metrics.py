# blender_addon/niua_mcp_bridge/core/silhouette_metrics.py
"""Pure-Python silhouette preservation metrics: PNG -> binary alpha mask -> IoU + bbox delta.

bpy-free AND PIL-free: runs inside Blender (numpy bundled, Pillow not) and offline in tests.
Decoding uses only the stdlib. The mask is the ALPHA channel (film_transparent coverage) for
RGBA/gray+alpha PNGs, so it is invariant to world/lighting/AgX; luma is a fallback for opaque
PNGs only. Separability gating (mean_preservation) keeps a double-capture failure from scoring
a false 1.0. bbox_delta is a GL-free scale/aspect signal so uniform scaling is still visible.
"""

from __future__ import annotations

import base64
import struct
import zlib

_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}  # gray, RGB, gray+alpha, RGBA (8-bit)


def decode_png_rgba(png: bytes) -> tuple[int, int, int, bytes]:
    """Decode an 8-bit PNG to (width, height, channels, defiltered-pixel-bytes)."""
    if png[:8] != _PNG_SIG:
        raise ValueError("not a PNG")
    pos = 8
    width = height = bit_depth = color_type = None
    idat = bytearray()
    while pos + 8 <= len(png):
        (length,) = struct.unpack(">I", png[pos : pos + 4])
        ctype = png[pos + 4 : pos + 8]
        data = png[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
        elif ctype == b"IDAT":
            idat += data
        elif ctype == b"IEND":
            break
    if width is None or bit_depth != 8 or color_type not in _CHANNELS:
        raise ValueError(f"unsupported PNG (depth={bit_depth}, color_type={color_type})")
    ch = _CHANNELS[color_type]
    raw = zlib.decompress(bytes(idat))
    stride = width * ch
    pixels = bytearray(width * height * ch)
    prev = bytearray(stride)
    i = 0
    for y in range(height):
        ftype = raw[i]
        i += 1
        line = bytearray(raw[i : i + stride])
        i += stride
        if ftype:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                b = prev[x]
                c = prev[x - ch] if x >= ch else 0
                if ftype == 1:
                    line[x] = (line[x] + a) & 0xFF
                elif ftype == 2:
                    line[x] = (line[x] + b) & 0xFF
                elif ftype == 3:
                    line[x] = (line[x] + ((a + b) >> 1)) & 0xFF
                elif ftype == 4:
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                    line[x] = (line[x] + pr) & 0xFF
                else:
                    raise ValueError(f"bad PNG filter {ftype}")
        pixels[y * stride : (y + 1) * stride] = line
        prev = line
    return int(width), int(height), int(ch), bytes(pixels)


def decode_png_coverage(png: bytes) -> tuple[int, int, bytes]:
    """Decode an 8-bit PNG to (width, height, coverage-bytes). Alpha for 4/6, luma for 0/2."""
    w, h, ch, px = decode_png_rgba(png)
    # coverage = alpha channel for alpha-bearing pixel layouts: GA (2 channels) / RGBA (4
    # channels) carry alpha last. Equivalent to the old color_type-keyed _ALPHA_INDEX
    # {4: 1, 6: 3} because _CHANNELS is a bijection {0:1, 2:3, 4:2, 6:4} between color_type
    # and channel count in this 8-bit-only decoder.
    alpha_i = {2: 1, 4: 3}.get(ch)
    out = bytearray(w * h)
    for i in range(w * h):
        base = i * ch
        if alpha_i is not None:                # coverage = alpha (film_transparent path)
            out[i] = px[base + alpha_i]
        elif ch >= 3:                          # opaque RGB -> luma fallback
            out[i] = (px[base] + px[base + 1] + px[base + 2]) // 3
        else:                                  # opaque grayscale
            out[i] = px[base]
    return w, h, bytes(out)


def png_b64_to_mask(data_b64: str, threshold: int = 128) -> tuple[int, int, bytes]:
    """base64 PNG -> (width, height, binary mask) where 1 = object (coverage > threshold)."""
    w, h, cov = decode_png_coverage(base64.b64decode(data_b64))
    return w, h, bytes(1 if px > threshold else 0 for px in cov)


def mask_coverage(mask: bytes) -> float:
    return (sum(mask) / len(mask)) if mask else 0.0


def is_separable(mask: bytes, lo: float = 0.005, hi: float = 0.995) -> bool:
    cov = mask_coverage(mask)
    return lo <= cov <= hi


def compute_iou(a: bytes, b: bytes) -> float | None:
    if len(a) != len(b):
        return None
    inter = union = 0
    for x, y in zip(a, b):
        if x or y:
            union += 1
            if x and y:
                inter += 1
    if union == 0:
        return 1.0
    return inter / union


def mean_preservation(
    intake: dict[str, bytes], current: dict[str, bytes], *, lo: float = 0.005, hi: float = 0.995
) -> dict:
    """Mean IoU over the SEPARABLE common views (fail-closed do-no-harm detector, no judge)."""
    per_view: dict[str, float] = {}
    for view in sorted(set(intake) & set(current)):
        mi, mc = intake[view], current[view]
        if not (is_separable(mi, lo, hi) and is_separable(mc, lo, hi)):
            continue  # a degenerate capture is excluded, never scored a false 1.0
        iou = compute_iou(mi, mc)
        if iou is not None:
            per_view[view] = iou
    if not per_view:
        return {"available": False, "preservation": None, "reason": "no separable comparable views"}
    worst = min(per_view.items(), key=lambda kv: kv[1])
    return {
        "available": True,
        "preservation": sum(per_view.values()) / len(per_view),
        "per_view": per_view,
        "min_view": {"view": worst[0], "iou": worst[1]},
        "n_views": len(per_view),
    }


def bbox_delta(intake_size, current_size, *, tol: float = 0.02) -> dict:
    """GL-free scale/aspect change between two (x, y, z) bbox sizes.

    scale_ratio  = geometric-mean of per-axis current/intake (a uniform resize is visible here
                   even though a fixed-frame IoU already reflects it).
    aspect_delta = max relative change of the pairwise axis ratios (shape/proportion change).
    """
    ins = [max(float(v), 1e-9) for v in intake_size]
    cur = [max(float(v), 1e-9) for v in current_size]
    per_axis = [c / i for c, i in zip(cur, ins)]
    scale_ratio = (per_axis[0] * per_axis[1] * per_axis[2]) ** (1.0 / 3.0)
    # normalize out uniform scale, then measure how the proportions moved
    norm_in = [v / (ins[0] * ins[1] * ins[2]) ** (1.0 / 3.0) for v in ins]
    norm_cur = [v / (cur[0] * cur[1] * cur[2]) ** (1.0 / 3.0) for v in cur]
    aspect_delta = max(abs(nc - ni) / ni for ni, nc in zip(norm_in, norm_cur))
    changed = abs(scale_ratio - 1.0) > tol or aspect_delta > tol
    return {
        "scale_ratio": scale_ratio,
        "aspect_delta": aspect_delta,
        "per_axis_ratio": per_axis,
        "changed": bool(changed),
    }


def compact_encode(mask: bytes) -> str:
    return base64.b64encode(zlib.compress(mask)).decode("ascii")


def compact_decode(data: str) -> bytes:
    return zlib.decompress(base64.b64decode(data))
