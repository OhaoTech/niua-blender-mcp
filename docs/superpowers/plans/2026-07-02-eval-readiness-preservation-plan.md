# Eval Redesign — Readiness + Do-No-Harm Preservation (order-free, measure-and-flag)

> **For agentic workers:** REQUIRED SUB-SKILL — use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Do the failing test FIRST, watch it fail, implement
> minimally, watch it pass, run `pytest -q` green, commit. One commit per task.

**Date:** 2026-07-02 (rewritten 2026-07-03 — order-free, no pipeline FSM)
**Design:** `docs/superpowers/specs/2026-07-02-eval-readiness-preservation-design.md`, **binding correction §9
("measure-and-flag")** which supersedes §3.
**Architecture:** `docs/superpowers/specs/2026-07-03-architecture-audit.md` §4 (lean target) + the
PLANNED-redesign rows in §2 — **binding**.
**Supersedes:** the previous FSM-bound version of this plan (auto-revert guard, `pipeline.start`/`advance`
intake capture, per-stage-budget table) — all of that is **removed** here.

**Goal.** Build the objective **ruler** (the "DONE" tool, M3) for a lean rebuild of this technical
*finisher*: two deterministic, un-gameable axes —

- **Readiness** — fraction of objective game-ready gates passed, aggregated over **all** gate groups **in
  no order** (no FSM walk).
- **Preservation** — silhouette IoU of the current form vs a stored **intake** baseline, plus a GL-free
  bbox aspect/scale delta — the **do-no-harm** signal.

Do-no-harm is **measured and flagged, never auto-reverted.** Nothing in this plan touches
`pipeline.advance`, `current_stage`, `gate_check`, or any FSM control surface — that machine is being
deleted in a later wave, and this ruler must be built **before** it, order-free, so every later deletion
is validated by "the objective benchmark number is unchanged."

## Locked decisions (do not re-litigate)

1. **No FSM dependency.** The ruler reads gate *definitions* (`stage_gates`/`check_gates`/`gate_profile`)
   and `feedback.quality`, both of which are order-free and already FSM-free. It never calls
   `pipeline.start`/`advance`/`gate_check`/`status`, never reads `_STORE`/`current_stage`.
2. **Do-no-harm is a FLAG, not a revert.** Preservation below the floor is recorded as `harm_flagged` in
   the **scorecard**. There is **no** coded guard, **no** auto-revert, **no** per-stage-budget table. The
   agent's accept/revert loop lives in **prose** (the `refine_mesh` prompt), using generic
   `session.checkpoint`/`revert`.
3. **Preservation floor = 0.85 global** (per-class tuning deferred; one constant, one-line change later).
4. **Robust, fail-closed mask.** Render with `render.film_transparent = True`, threshold the **ALPHA**
   channel (object coverage — invariant to world/lighting/AgX). **Fixed** ortho camera framing derived
   **once** from the stored intake bbox (never per-render `view_selected`). **Ortho-only** views
   (`front`/`right`/`top`; **no** `persp`). Return `available:false` when object and background are not
   cleanly separable (coverage histogram check). Carry a GL-free **bbox aspect/scale delta** alongside IoU
   so a uniform-scale change is visible.
5. **Thin passive ledger, not the FSM.** Intake masks + the intake checkpoint label live in a new
   per-object `core/preservation_ledger.py` scratchpad — **not** in `pipeline._STORE`.
6. **Canonical tool names** (supersede the design §5 `feedback.silhouette_masks` and the maps'
   `evals/silhouette_mask.py`/`readiness.py`/`preservation_guard.py`): **`feedback.capture_intake`**,
   **`feedback.preservation`**, **`feedback.readiness`** (all `mutates=False`), plus pure modules
   `core/silhouette_metrics.py`, `core/preservation_ledger.py`, `evals/objective_bench.py`. Do NOT
   register any other name.
7. **Benchmark runner = pure-Python, no LLM judge.** Deterministic scoring. It is honestly scoped as an
   **input-quality / baseline probe by default** with a **pluggable real finisher** hook — it does **not**
   ship a no-op driver claiming "the pipeline preserves form." It distinguishes **unmeasured** (headless /
   non-separable) from **failed**.

## Architecture & the two package surfaces (already established in this repo)

- **Server** (`src/niua_blender_mcp/`) publishes `ToolSpec` manifests (`SPECS` lists in `domains/*.py`) and
  owns the offline eval harness (`evals/`). Server domains carry **no handlers** — just specs.
- **Add-on** (`blender_addon/niua_mcp_bridge/`) publishes matching `Command` handlers (`COMMANDS` lists in
  `domains/*.py`) that run inside Blender via `ctx.bpy`, plus pure logic in `core/`.
- **Parity** (`tests/test_parity.py`): `{spec.command} == registry.names()` and, for every spec,
  `command.mutates == spec.mutates` and `command.feedback == spec.feedback`. Every new tool needs BOTH a
  server `ToolSpec` and an add-on `Command` with identical `mutates`/`feedback`.
- **Undo contract:** `dispatch_on_main` pushes exactly one `ed.undo_push` after a successful handler **iff**
  `command.mutates` is `True`. All three new tools are **`mutates=False`** (read-only); they push no undo
  and must restore any transient state they touch. **No tool in this plan flips to `mutates=True`.**

## Tech & global constraints

- Python 3.14, `pytest`. `from __future__ import annotations` at the top of **every** new `.py`.
- **Pure metric helpers are `bpy`-free AND `PIL`-free.** Blender bundles `numpy` but **not** Pillow, so the
  in-Blender decode path uses only the stdlib (`zlib`, `struct`, `base64`) + plain Python. Tests may
  *encode* synthetic fixtures with Pillow (present in the dev venv, `PIL 12.2.0`); production code only ever
  *decodes* — proving the stdlib decoder against real PNG bytes.
- Preservation silhouettes are captured at **`res=256`** (compact, fast to decode/compare; the GL render is
  pure-Python-unfiltered on the main thread, so keep it small).
- Reuse `core/pipeline.py::{check_gates, stage_gates, gate_profile}` — gate **definitions** only, never the
  FSM control functions. **Do not** duplicate gate logic.
- The GL render path (`render_preservation_views`) cannot be unit-tested under fake-bpy (no GL); it is
  validated by the **live acceptance**. Everything else (pure metric, ledger, handler wiring with the render
  monkeypatched, readiness aggregation, bench scoring) is offline / fake-bpy tested.
- Run the whole suite (`pytest -q`) green before each commit that touches a shared module.

## File structure

**Create:**
- `blender_addon/niua_mcp_bridge/core/silhouette_metrics.py` — stdlib PNG(alpha/luma)→mask, coverage, IoU,
  separability-gated `mean_preservation`, `bbox_delta`, compact codec (bpy-free, PIL-free).
- `blender_addon/niua_mcp_bridge/core/preservation_ledger.py` — thin per-object intake store + `PRESERVATION_FLOOR`.
- `tests/core/test_silhouette_metrics.py` — pure offline metric tests (synthetic alpha PNGs).
- `tests/core/test_preservation_ledger.py` — ledger store tests.
- `tests/domains/test_preservation.py` — `feedback.capture_intake` + `feedback.preservation` (render monkeypatched).
- `tests/domains/test_readiness.py` — `feedback.readiness` scorecard tests.
- `src/niua_blender_mcp/evals/objective_bench.py` — pure scoring + aggregation (offline-testable).
- `tests/evals/test_objective_bench.py` — scoring/aggregation math tests.
- `scripts/run_objective_benchmark.py` — pure-Python live harness (drives bridge, no judge).
- `tests/evals/test_objective_runner.py` — offline registration guard + structural test for the runner.
- `tests/evals/test_primary_grade.py` — objective runner is primary; altimeter labelled non-primary.

**Modify:**
- `blender_addon/niua_mcp_bridge/core/silhouette.py` — add `render_preservation_views` (fixed-frame ortho,
  film_transparent, RGBA).
- `blender_addon/niua_mcp_bridge/domains/feedback.py` — `capture_intake`, `preservation`, `readiness`
  handlers + three `Command`s.
- `src/niua_blender_mcp/domains/feedback.py` — three new `ToolSpec`s.
- `src/niua_blender_mcp/prompts.py` — surface `feedback.readiness` (game-ready check) + `feedback.preservation`
  (do-no-harm check) + the checkpoint→act→re-measure→keep-iff-better-else-revert loop (prose only).
- `workflows/altimeter.mjs` — non-primary banner + `meta` relabel.

**Keep untouched:** the FSM (`core/pipeline.py` control surface, `domains/pipeline.py`) — deleted in a later
wave, not here. `core/silhouette.py::render_silhouette` (the existing `feedback.silhouette` path).
`feedback.quality`/`critique`, `core/session.py`, `core/capture.py` framing math.

---

## Task 1 — Pure-Python silhouette metric (alpha mask → IoU + bbox delta)

**Why first:** every later task depends on this. Fully offline-testable with synthetic PNGs — no bpy, no GL.
It fixes the red-team's mask defects at the math layer: **alpha** (not RGB-luma) coverage, **separability**
fail-closed (both-empty/both-full never scores a false 1.0), and an explicit **bbox delta** so uniform
scale is visible.

**Files:**
- Create: `blender_addon/niua_mcp_bridge/core/silhouette_metrics.py`
- Test: `tests/core/test_silhouette_metrics.py`

**Interfaces (produced):**
- `decode_png_coverage(png: bytes) -> tuple[int, int, bytes]` — `(width, height, coverage)`; `coverage` is
  `width*height` bytes 0..255 = the **alpha** channel for color types 4/6, else luma for 0/2. Stdlib only;
  raises `ValueError` on unsupported (palette/16-bit) or malformed PNG.
- `png_b64_to_mask(data_b64: str, threshold: int = 128) -> tuple[int, int, bytes]` — decode → threshold
  coverage → flat `uint8` mask (1 = object).
- `mask_coverage(mask: bytes) -> float` — fraction of set pixels.
- `is_separable(mask: bytes, lo: float = 0.005, hi: float = 0.995) -> bool` — object is a plausible fraction
  of frame (not all-empty, not all-full).
- `compute_iou(a: bytes, b: bytes) -> float | None` — IoU of equal-length 0/1 buffers; length mismatch ⇒
  `None`; both-empty ⇒ `1.0` (a math primitive — separability gating in `mean_preservation` prevents it
  masking a double-capture failure).
- `mean_preservation(intake, current, *, lo=0.005, hi=0.995) -> dict` — over the common views, keep only
  views where **both** masks are separable, compute IoU; return
  `{available, preservation, per_view, min_view, n_views}`; `available=False` with `reason` when no separable
  comparable view survives (**fail-closed**).
- `bbox_delta(intake_size, current_size) -> dict` — GL-free
  `{scale_ratio, aspect_delta, per_axis_ratio, changed}`; `changed` when any axis ratio leaves `1 ± tol` or
  the aspect ratio moves beyond `tol` (default `tol=0.02`). Pure tuples in, plain floats out.
- `compact_encode(mask: bytes) -> str` / `compact_decode(data: str) -> bytes` — `base64(zlib(mask))`.

- [ ] **Step 1 — Write the failing test**

```python
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
```

- [ ] **Step 2 — Run to verify it fails**

Run: `pytest tests/core/test_silhouette_metrics.py -q` → FAIL (module not importable).

- [ ] **Step 3 — Implement the metric (stdlib only; runs inside Blender)**

```python
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
_ALPHA_INDEX = {4: 1, 6: 3}           # coverage = alpha channel for these color types


def decode_png_coverage(png: bytes) -> tuple[int, int, bytes]:
    """Decode an 8-bit PNG to (width, height, coverage-bytes). Alpha for 4/6, luma for 0/2."""
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
    alpha_i = _ALPHA_INDEX.get(color_type)
    raw = zlib.decompress(bytes(idat))
    stride = width * ch
    out = bytearray(width * height)
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
        row = y * width
        if alpha_i is not None:               # coverage = alpha (film_transparent path)
            for px in range(width):
                out[row + px] = line[px * ch + alpha_i]
        elif ch >= 3:                          # opaque RGB -> luma fallback
            for px in range(width):
                base = px * ch
                out[row + px] = (line[base] + line[base + 1] + line[base + 2]) // 3
        else:                                  # opaque grayscale
            for px in range(width):
                out[row + px] = line[px * ch]
        prev = line
    return int(width), int(height), bytes(out)


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
```

- [ ] **Step 4 — Run to verify pass**

Run: `pytest tests/core/test_silhouette_metrics.py -q` → PASS.

- [ ] **Step 5 — Full suite + commit**

```bash
pytest -q
git add blender_addon/niua_mcp_bridge/core/silhouette_metrics.py tests/core/test_silhouette_metrics.py
git commit -m "feat: pure-python alpha silhouette IoU + bbox-delta metric (fail-closed)"
```

---

## Task 2 — Thin ledger + fixed-frame ortho render + `feedback.capture_intake`

**Why:** the ruler needs an intake baseline captured **once**, stored **outside** the FSM. This task adds
the passive per-object ledger, the robust fixed-frame/ortho/alpha render, and the tool that writes the
baseline (masks + intake bbox + a generic `session` checkpoint label). `mutates=False` — rendering, a
datablock copy, and an in-memory ledger write do not change the visible scene.

**Files:**
- Create: `blender_addon/niua_mcp_bridge/core/preservation_ledger.py`
- Modify: `blender_addon/niua_mcp_bridge/core/silhouette.py` (add `render_preservation_views`)
- Modify: `blender_addon/niua_mcp_bridge/domains/feedback.py` (`capture_intake` handler + Command)
- Modify: `src/niua_blender_mcp/domains/feedback.py` (`feedback.capture_intake` ToolSpec)
- Test: `tests/core/test_preservation_ledger.py`, `tests/domains/test_preservation.py`

**Interfaces:**
- `preservation_ledger.py`: `PRESERVATION_FLOOR = 0.85`; `PRESERVATION_VIEWS = ("front", "right", "top")`;
  `PRESERVATION_RES = 256`; `set_intake(obj_name, record)`, `get_intake(obj_name) -> dict | None`,
  `reset()`. Plain module-level dict `_LEDGER`, no bpy, no FSM.
- `silhouette.render_preservation_views(bpy, obj_name, *, frame=None, views=PRESERVATION_VIEWS, res=256) -> dict`
  — the **fixed-frame, ortho-only, alpha** render. Uses the hidden capture camera (`_ensure_capture_camera`
  + `_apply_frame(view_camera(center, size, view))`), sets `render.film_transparent=True` +
  `image_settings.color_mode='RGBA'`, isolates the subject (snapshot every other object's `hide_render`,
  hide them, restore in `finally`), renders `view_context=False`, returns
  `{available, res, frame:{center,size}, measured:{center,size}, images:[{view, data}]}`. `frame` (if given)
  fixes the camera to the stored **intake** framing; else it is derived from the object's current bbox
  (`scene_bbox`). Degrades to `{available:False, reason}` on any failure (headless / no GL). **Not
  fake-bpy-testable — validated live (A2/A3).**
- `feedback.capture_intake(ctx, payload) -> dict` — `_resolve_mesh`; render ortho3 alpha views; decode to
  masks; require **every** view separable else `available:False` (fail-closed); `session.checkpoint(obj,
  label="niua:intake")`; write `{available, res, frame, size, masks:{view:compact}, shape, coverage,
  checkpoint_label}` to the ledger. Returns `{object, available, views, coverage, checkpoint_label}`.

- [ ] **Step 1 — Write the failing tests**

```python
# tests/core/test_preservation_ledger.py
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
```

```python
# tests/domains/test_preservation.py
from __future__ import annotations

import base64
import io

import pytest

from niua_mcp_bridge.core import preservation_ledger as ledger
from niua_mcp_bridge.core import silhouette as sil
from niua_mcp_bridge.domains import build_default_registry, feedback as fb

# Reuse the fake-bpy env + cube fixtures from the existing pipeline domain tests.
from tests.domains.test_pipeline import _CUBE_QUADS, _CUBE_VERTS, FakeMesh, FakeObj, env  # noqa: F401


@pytest.fixture(autouse=True)
def _reset_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _rgba(rows):
    from PIL import Image

    h, w = len(rows), len(rows[0])
    img = Image.new("RGBA", (w, h))
    img.putdata([(200, 200, 210, 255) if v else (240, 240, 240, 0) for r in rows for v in r])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _render_stub(rows, size=(2.0, 2.0, 2.0)):
    data = _rgba(rows)
    frame = {"center": (0.0, 0.0, 0.0), "size": size}

    def _fn(bpy, obj_name, *, frame=None, views=ledger.PRESERVATION_VIEWS, res=256):
        used = frame or {"center": (0.0, 0.0, 0.0), "size": size}
        return {
            "available": True,
            "res": res,
            "frame": used,
            "measured": {"center": (0.0, 0.0, 0.0), "size": size},
            "images": [{"view": v, "data": data} for v in views],
        }

    return _fn


def test_capture_intake_writes_ledger(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(sil, "render_preservation_views", _render_stub([[1, 1], [1, 0]]))
    out = fb.capture_intake(ctx, {"object": "Cube"})
    assert out["available"] is True
    rec = ledger.get_intake("Cube")
    assert set(rec["masks"]) == {"front", "right", "top"}
    assert rec["checkpoint_label"] == "niua:intake"
    assert rec["size"] == (2.0, 2.0, 2.0)


def test_capture_intake_fails_closed_on_nonseparable(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(sil, "render_preservation_views", _render_stub([[1, 1], [1, 1]]))  # all-full
    out = fb.capture_intake(ctx, {"object": "Cube"})
    assert out["available"] is False
    assert ledger.get_intake("Cube")["available"] is False


def test_capture_intake_headless_degrades(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(
        sil, "render_preservation_views",
        lambda bpy, name, **kw: {"available": False, "reason": "headless"},
    )
    out = fb.capture_intake(ctx, {"object": "Cube"})
    assert out["available"] is False


def test_capture_intake_command_registered_readonly() -> None:
    cmd = build_default_registry().get("feedback.capture_intake")
    assert cmd is not None and cmd.mutates is False and cmd.feedback is None
```

- [ ] **Step 2 — Run to verify it fails**

Run: `pytest tests/core/test_preservation_ledger.py tests/domains/test_preservation.py -q` → FAIL.

- [ ] **Step 3 — Implement the ledger** (`core/preservation_ledger.py`)

```python
# blender_addon/niua_mcp_bridge/core/preservation_ledger.py
"""Thin passive per-object preservation ledger (NOT the pipeline FSM).

A plain per-object scratchpad the ruler reads/writes: intake silhouette masks + the intake
bbox + a generic session-checkpoint label. It holds no stage/order/progress state and is
independent of core/pipeline._STORE, so the FSM can be deleted around it without touching this.
"""

from __future__ import annotations

from typing import Any

PRESERVATION_FLOOR = 0.85                       # locked global do-no-harm floor (per-class later)
PRESERVATION_VIEWS = ("front", "right", "top")  # ortho-only; persp excluded
PRESERVATION_RES = 256

_LEDGER: dict[str, dict[str, Any]] = {}


def reset() -> None:
    _LEDGER.clear()


def set_intake(object_name: str, record: dict[str, Any]) -> None:
    _LEDGER[object_name] = record


def get_intake(object_name: str) -> dict[str, Any] | None:
    return _LEDGER.get(object_name)
```

- [ ] **Step 4 — Implement `render_preservation_views`** (`core/silhouette.py`)

Add the fixed-frame, ortho-only, alpha render. Reuses `capture.py` internals already verified present
(`_ensure_capture_camera`, `_apply_frame`, `view_camera`, `scene_bbox`, `_configure_engine`). Contract is
above; skeleton:

```python
def render_preservation_views(
    bpy, obj_name, *, frame=None, views=("front", "right", "top"), res=256
) -> dict:
    """Fixed-frame ORTHO alpha silhouettes for the preservation metric (validated live).

    Robust + fail-closed vs the RGB-luma/view_selected `render_silhouette`:
      * film_transparent=True + RGBA -> threshold ALPHA (world/lighting/AgX invariant),
      * hidden ortho camera framed ONCE from `frame` (the stored intake bbox), never view_selected,
      * ortho-only views, so no perspective foreshortening noise,
      * isolates the subject by snapshotting+hiding every other object's hide_render (restored).
    Returns {available, res, frame:{center,size}, measured:{center,size}, images:[{view,data}]}
    or {available:False, reason} on any failure (headless / no GL). No exception escapes.
    """
    from . import capture as cap
    import base64, os, tempfile

    try:
        center, size = cap.scene_bbox(bpy, obj_name)
        used = frame or {"center": center, "size": size}
        scene = bpy.context.scene
        render = scene.render
        cam = cap._ensure_capture_camera(bpy)
        subject = bpy.data.objects.get(obj_name)
        if subject is None:
            return {"available": False, "reason": f"object not found: {obj_name}"}

        prev = {
            "camera": scene.camera,
            "engine": getattr(render, "engine", None),
            "x": render.resolution_x, "y": render.resolution_y, "pct": render.resolution_percentage,
            "filepath": render.filepath, "fmt": render.image_settings.file_format,
            "color_mode": render.image_settings.color_mode,
            "film_transparent": getattr(render, "film_transparent", None),
        }
        hidden = [(o, o.hide_render) for o in scene.objects]
        path = os.path.join(tempfile.gettempdir(), "niua_preservation.png")
        images = []
        try:
            for o in scene.objects:
                o.hide_render = (o is not subject)
            scene.camera = cam
            render.resolution_x = render.resolution_y = int(res)
            render.resolution_percentage = 100
            render.image_settings.file_format = "PNG"
            render.image_settings.color_mode = "RGBA"
            render.film_transparent = True
            render.filepath = path
            cap._configure_engine(bpy, scene, "MATERIAL")
            for view in views:
                cap._apply_frame(cam, cap.view_camera(used["center"], used["size"], view))
                bpy.ops.render.opengl(write_still=True, view_context=False)
                with open(path, "rb") as fh:
                    images.append({"view": view, "data": base64.b64encode(fh.read()).decode("ascii")})
        finally:
            for o, was in hidden:
                o.hide_render = was
            scene.camera = prev["camera"]
            if prev["engine"] is not None:
                try:
                    render.engine = prev["engine"]
                except Exception:  # noqa: BLE001
                    pass
            render.resolution_x, render.resolution_y = prev["x"], prev["y"]
            render.resolution_percentage = prev["pct"]
            render.filepath, render.image_settings.file_format = prev["filepath"], prev["fmt"]
            render.image_settings.color_mode = prev["color_mode"]
            if prev["film_transparent"] is not None:
                render.film_transparent = prev["film_transparent"]
        return {"available": True, "res": int(res), "frame": used,
                "measured": {"center": center, "size": size}, "images": images}
    except Exception as exc:  # noqa: BLE001 - graceful degrade is the contract
        return {"available": False, "reason": str(exc)}
```

- [ ] **Step 5 — Implement `capture_intake`** (`blender_addon/niua_mcp_bridge/domains/feedback.py`)

```python
from ..core import preservation_ledger as _ledger
from ..core import session as _session
from ..core import silhouette as _sil
from ..core import silhouette_metrics as _sm


def capture_intake(ctx: Ctx, payload: dict) -> dict:
    """Record the intake do-no-harm baseline: fixed-frame ortho alpha masks + bbox + checkpoint.

    Read-only (mutates=False): renders, copies a datablock (session.checkpoint), and writes the
    passive ledger — none of which changes the visible scene. Fail-closed: if any view is not
    cleanly separable, the baseline is stored unavailable so preservation reports 'unmeasured'
    rather than trusting a degenerate capture.
    """
    obj = _resolve_mesh(ctx, payload)
    out = _sil.render_preservation_views(
        ctx.bpy, obj.name, views=_ledger.PRESERVATION_VIEWS, res=_ledger.PRESERVATION_RES
    )
    if not out.get("available"):
        _ledger.set_intake(obj.name, {"available": False, "reason": out.get("reason", "unavailable")})
        return {"object": obj.name, "available": False, "reason": out.get("reason", "unavailable")}

    masks: dict[str, str] = {}
    coverage: dict[str, float] = {}
    shape = None
    for img in out.get("images", []):
        try:
            w, h, mask = _sm.png_b64_to_mask(img["data"])
        except Exception:  # noqa: BLE001 - a bad view fails the whole baseline (fail-closed)
            _ledger.set_intake(obj.name, {"available": False, "reason": "decode failed"})
            return {"object": obj.name, "available": False, "reason": "decode failed"}
        if not _sm.is_separable(mask):
            _ledger.set_intake(obj.name, {"available": False, "reason": f"{img['view']} not separable"})
            return {"object": obj.name, "available": False, "reason": f"{img['view']} not separable"}
        masks[img["view"]] = _sm.compact_encode(mask)
        coverage[img["view"]] = _sm.mask_coverage(mask)
        shape = [h, w]

    _session.checkpoint(obj, label="niua:intake")
    _ledger.set_intake(obj.name, {
        "available": True, "res": out["res"], "frame": out["frame"],
        "size": out["measured"]["size"], "masks": masks, "shape": shape,
        "coverage": coverage, "checkpoint_label": "niua:intake",
    })
    return {"object": obj.name, "available": True, "views": sorted(masks),
            "coverage": coverage, "checkpoint_label": "niua:intake"}
```

Add to `COMMANDS`: `Command("feedback.capture_intake", capture_intake, mutates=False)`.

- [ ] **Step 6 — Add the server ToolSpec** (`src/niua_blender_mcp/domains/feedback.py`)

```python
ToolSpec(
    name="feedback.capture_intake",
    category="feedback",
    summary="Record the do-no-harm baseline: fixed-frame ortho alpha silhouettes + bbox + a session checkpoint",
    command="feedback.capture_intake",
    params={"object": Str(summary="Mesh object to baseline (defaults to active)")},
),
```

- [ ] **Step 7 — Run tests + full suite + commit**

```bash
pytest tests/core/test_preservation_ledger.py tests/domains/test_preservation.py tests/test_parity.py -q
pytest -q
git add blender_addon/niua_mcp_bridge/core/preservation_ledger.py \
        blender_addon/niua_mcp_bridge/core/silhouette.py \
        blender_addon/niua_mcp_bridge/domains/feedback.py \
        src/niua_blender_mcp/domains/feedback.py \
        tests/core/test_preservation_ledger.py tests/domains/test_preservation.py
git commit -m "feat: thin preservation ledger + fixed-frame ortho alpha render + feedback.capture_intake"
```

---

## Task 3 — Read-only `feedback.preservation` (measure-and-flag, no guard)

**Why:** the do-no-harm **metric**. It reads the intake baseline from the ledger, re-renders the current
form with the **same fixed frame**, and reports mean/min silhouette IoU + the GL-free bbox delta. It
**measures and flags** — there is no auto-revert, no FSM, no `advance` mutation. `mutates=False`.

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/domains/feedback.py` (`preservation` handler + Command)
- Modify: `src/niua_blender_mcp/domains/feedback.py` (ToolSpec)
- Modify: `src/niua_blender_mcp/prompts.py` (name the do-no-harm check)
- Test: extend `tests/domains/test_preservation.py`

**Interface:** `preservation(ctx, payload) -> dict`:
- `_resolve_mesh`; `rec = ledger.get_intake(obj.name)`.
- No baseline at all → `BridgeError(PRECONDITION, "call feedback.capture_intake first")`.
- Baseline stored `available:False` (headless intake) → return `available:False` (unmeasured), no raise.
- Else re-render current with `frame=rec["frame"]` (fixed); if unavailable → `available:False`.
- Decode current masks; `mean_preservation(intake_masks, current_masks)` (separability-gated);
  `delta = bbox_delta(rec["size"], current_measured_size)`.
- Return `{object, available, preservation, preservation_pass, threshold, min_view, per_view, bbox_delta}`
  where `preservation_pass = available and preservation >= PRESERVATION_FLOOR`. **`harm_flagged` is set by
  the scorecard, not here** — this tool only reports the number.

- [ ] **Step 1 — Write the failing test** (append to `tests/domains/test_preservation.py`)

```python
def test_preservation_requires_intake_baseline(env) -> None:
    from niua_mcp_bridge.errors import BridgeError
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    with pytest.raises(BridgeError):
        fb.preservation(ctx, {"object": "Cube"})


def test_preservation_identical_is_one(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(sil, "render_preservation_views", _render_stub([[1, 1], [1, 0]]))
    fb.capture_intake(ctx, {"object": "Cube"})
    out = fb.preservation(ctx, {"object": "Cube"})
    assert out["available"] is True
    assert out["preservation"] == 1.0
    assert out["preservation_pass"] is True
    assert out["threshold"] == 0.85
    assert out["bbox_delta"]["changed"] is False


def test_preservation_flags_damage_below_floor(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(sil, "render_preservation_views", _render_stub([[1, 1], [1, 0]]))
    fb.capture_intake(ctx, {"object": "Cube"})
    # Current form collapses to a quarter of the frame -> IoU well below floor.
    monkeypatch.setattr(sil, "render_preservation_views", _render_stub([[1, 0], [0, 0]]))
    out = fb.preservation(ctx, {"object": "Cube"})
    assert out["available"] is True
    assert out["preservation"] < 0.85
    assert out["preservation_pass"] is False


def test_preservation_uniform_scale_visible_in_bbox_delta(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(sil, "render_preservation_views", _render_stub([[1, 1], [1, 0]], size=(2.0, 2.0, 2.0)))
    fb.capture_intake(ctx, {"object": "Cube"})
    # Same silhouette shape, but the object is half the size -> bbox_delta flags it.
    monkeypatch.setattr(sil, "render_preservation_views", _render_stub([[1, 1], [1, 0]], size=(1.0, 1.0, 1.0)))
    out = fb.preservation(ctx, {"object": "Cube"})
    assert out["bbox_delta"]["changed"] is True
    assert abs(out["bbox_delta"]["scale_ratio"] - 0.5) < 1e-9


def test_preservation_unmeasured_when_intake_headless(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(sil, "render_preservation_views",
                        lambda bpy, name, **kw: {"available": False, "reason": "headless"})
    fb.capture_intake(ctx, {"object": "Cube"})
    out = fb.preservation(ctx, {"object": "Cube"})
    assert out["available"] is False  # unmeasured, not a false failure


def test_preservation_command_registered_readonly() -> None:
    cmd = build_default_registry().get("feedback.preservation")
    assert cmd is not None and cmd.mutates is False and cmd.feedback is None
```

- [ ] **Step 2 — Run to verify it fails**

Run: `pytest tests/domains/test_preservation.py -q` → FAIL (`preservation` missing).

- [ ] **Step 3 — Implement the handler** (`blender_addon/niua_mcp_bridge/domains/feedback.py`)

```python
from ..errors import PRECONDITION  # already imported? add if missing


def preservation(ctx: Ctx, payload: dict) -> dict:
    """Do-no-harm METRIC (read-only): mean/min silhouette IoU of current form vs stored intake,
    plus a GL-free bbox scale/aspect delta. Measures and reports; it never reverts anything and
    touches no pipeline state. `harm_flagged` is applied downstream by the scorecard.
    """
    obj = _resolve_mesh(ctx, payload)
    rec = _ledger.get_intake(obj.name)
    if rec is None:
        raise BridgeError(PRECONDITION, f"no intake baseline; call feedback.capture_intake for {obj.name}")
    floor = _ledger.PRESERVATION_FLOOR
    if not rec.get("available"):
        return {"object": obj.name, "available": False, "preservation": None,
                "preservation_pass": False, "threshold": floor,
                "reason": rec.get("reason", "intake baseline unavailable")}

    cur = _sil.render_preservation_views(
        ctx.bpy, obj.name, frame=rec["frame"], views=tuple(rec["masks"]), res=rec["res"]
    )
    if not cur.get("available"):
        return {"object": obj.name, "available": False, "preservation": None,
                "preservation_pass": False, "threshold": floor,
                "reason": cur.get("reason", "current silhouette unavailable")}

    intake_masks = {v: _sm.compact_decode(d) for v, d in rec["masks"].items()}
    current_masks: dict[str, bytes] = {}
    for img in cur.get("images", []):
        try:
            current_masks[img["view"]] = _sm.png_b64_to_mask(img["data"])[2]
        except Exception:  # noqa: BLE001
            continue
    metric = _sm.mean_preservation(intake_masks, current_masks)
    delta = _sm.bbox_delta(rec["size"], cur["measured"]["size"])
    score = metric.get("preservation") if metric.get("available") else None
    return {
        "object": obj.name,
        "available": bool(metric.get("available")),
        "preservation": score,
        "preservation_pass": bool(metric.get("available")) and score is not None and score >= floor,
        "threshold": floor,
        "per_view": metric.get("per_view", {}),
        "min_view": metric.get("min_view"),
        "bbox_delta": delta,
    }
```

Add to `COMMANDS`: `Command("feedback.preservation", preservation, mutates=False)`.

- [ ] **Step 4 — Add the server ToolSpec** (`src/niua_blender_mcp/domains/feedback.py`)

```python
ToolSpec(
    name="feedback.preservation",
    category="feedback",
    summary="Do-no-harm metric: mean/min silhouette IoU of current form vs the stored intake baseline + bbox delta (read-only, no revert)",
    command="feedback.preservation",
    params={"object": Str(summary="Object with a stored intake baseline (defaults to active)")},
),
```

- [ ] **Step 5 — Surface the do-no-harm check in the prompt** (`src/niua_blender_mcp/prompts.py`)

In `_refine_mesh`, extend the JUDGE step (5th bullet cluster) so the agent consults preservation. Add after
the topology bullet in step 4:

```
   - Do-no-harm: after establishing a baseline with `feedback.capture_intake` (once, at intake),
     call `feedback.preservation` to check the silhouette IoU vs that baseline. A drop below ~0.85
     (or `bbox_delta.changed == true`) means the form itself was altered — that is HARM on a finisher,
     even if the topology numbers improved.
```

- [ ] **Step 6 — Run tests + full suite + commit**

```bash
pytest tests/domains/test_preservation.py tests/test_parity.py -q
pytest -q
git add blender_addon/niua_mcp_bridge/domains/feedback.py \
        src/niua_blender_mcp/domains/feedback.py src/niua_blender_mcp/prompts.py \
        tests/domains/test_preservation.py
git commit -m "feat: read-only feedback.preservation (measure-and-flag, no auto-revert)"
```

---

## Task 4 — Read-only `feedback.readiness` (order-free gate aggregate, deduped)

**Why:** the un-gameable "did we make it game-ready?" half. It aggregates **all** objective gate groups **in
no order** (no FSM walk) and reports **both** the mean per-group pass-fraction **and** the deduplicated-gate
fraction (so `topology.non_manifold_edges`, which appears in two groups, is counted once). `mutates=False`,
no images, no judge. It stays FSM-free by passing `asset_class` explicitly to `feedback.quality` (which
already resolves the class from the payload only — verified at `feedback.py:236`).

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/domains/feedback.py` (`readiness` handler + Command)
- Modify: `src/niua_blender_mcp/domains/feedback.py` (ToolSpec)
- Modify: `src/niua_blender_mcp/prompts.py` (name the game-ready check + the accept/revert loop)
- Test: `tests/domains/test_readiness.py`

**Interface:** `readiness(ctx, payload) -> dict` computes `feedback.quality` ONCE (with `asset_class`
threaded through the payload), then for each gate group in
`["repair","retopo","uv","bake","material","optimize","export_preflight"]` runs
`stage_gates(group, asset_class)` + `check_gates(metrics, gates)` and aggregates:

```
{object, asset_class,
 readiness,                    # DEDUPED gate fraction = deduped_pass / deduped_total  (headline)
 stage_pass_fraction_mean,     # mean over groups of (pass/count), equal weight per group/axis
 total_gates_deduped, total_gates_pass_deduped,
 per_group: [{group, gate_profile, gates_pass, gates_count, gates_pass_count, pass_fraction}],
 per_gate: [{path, op, value, actual, pass}]}      # deduped by (path, op, value)
```

Dedup by the full `(path, op, value)` signature — identical gates (non_manifold_edges `== 0` in both retopo
and export_preflight) collapse to one; a genuinely different threshold (an overridden `quad_ratio`) stays
distinct. Reuses `core/pipeline.{stage_gates, check_gates, gate_profile}` (gate **definitions**, not FSM
control) — no gate logic duplicated.

- [ ] **Step 1 — Write the failing test**

```python
# tests/domains/test_readiness.py
from __future__ import annotations

from niua_mcp_bridge.domains import build_default_registry, feedback as fb

from tests.domains.test_pipeline import _CUBE_QUADS, _CUBE_VERTS, FakeMesh, FakeObj, env  # noqa: F401

_PASS_TOPO = {"quad_ratio": 1.0, "ngons": 0, "non_manifold_edges": 0}
_PASS_UV = {"has_uvs": True, "out_of_bounds_loops": 0, "overlap_detected": False, "stretch_ratio": 1.0}
_PASS_ORI = {"degenerate_faces": 0, "inward_facing_faces": 0}


def _metrics(engine_all: bool, material_all: bool):
    return {
        "object": "Cube",
        "asset_class": {"id": "hard_surface_prop", "profile_version": 1},
        "topology": dict(_PASS_TOPO),
        "uv": dict(_PASS_UV),
        "orientation": dict(_PASS_ORI),
        "material": {"bake_maps_present": material_all, "data_maps_non_color": material_all,
                     "pbr_maps_present": material_all, "textures_within_size": True,
                     "atlas_ready": material_all},
        "engine": {k: engine_all for k in (
            "within_triangle_budget", "within_material_budget", "within_texture_budget",
            "has_lods", "has_collision_proxy", "lod_triangle_reduction_ok",
            "lod_silhouette_preserved", "has_collision_hulls", "collision_bounds_valid")},
        "scale": {"transform_applied": True},
        "export_profile": {"profile_pass": True},
    }


def test_readiness_reports_both_fractions_and_dedup(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(fb, "quality", lambda ctx, payload: _metrics(engine_all=False, material_all=False))
    out = fb.readiness(ctx, {"object": "Cube", "asset_class": "hard_surface_prop"})
    assert set(out) >= {"object", "readiness", "stage_pass_fraction_mean",
                        "total_gates_deduped", "per_group", "per_gate"}
    assert 0.0 <= out["readiness"] <= 1.0
    # non_manifold_edges==0 appears in retopo AND export_preflight; deduped it is counted once.
    paths = [g["path"] for g in out["per_gate"]]
    assert paths.count("topology.non_manifold_edges") == 1
    # deduped total < raw sum over groups (2+3+4+2+3+9+3 = 26 raw; >=1 duplicate removed).
    raw = sum(s["gates_count"] for s in out["per_group"])
    assert out["total_gates_deduped"] < raw
    # the two fractions are distinct notions and both present
    assert isinstance(out["stage_pass_fraction_mean"], float)


def test_readiness_all_pass_is_one_on_both(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(fb, "quality", lambda ctx, payload: _metrics(engine_all=True, material_all=True))
    out = fb.readiness(ctx, {"object": "Cube", "asset_class": "hard_surface_prop"})
    assert out["readiness"] == 1.0
    assert out["stage_pass_fraction_mean"] == 1.0


def test_readiness_command_registered_readonly() -> None:
    cmd = build_default_registry().get("feedback.readiness")
    assert cmd is not None and cmd.mutates is False and cmd.feedback is None
```

- [ ] **Step 2 — Run to verify it fails**

Run: `pytest tests/domains/test_readiness.py -q` → FAIL.

- [ ] **Step 3 — Implement the handler** (`blender_addon/niua_mcp_bridge/domains/feedback.py`)

```python
from ..core.pipeline import check_gates, gate_profile, stage_gates  # gate DEFINITIONS, not FSM control

# All objective gate groups, aggregated in NO ORDER (this is a set to check, not a walk).
_GATE_GROUPS = ["repair", "retopo", "uv", "bake", "material", "optimize", "export_preflight"]


def readiness(ctx: Ctx, payload: dict) -> dict:
    """Objective game-readiness scorecard (read-only): fraction of gates passed across every gate
    group, aggregated with no order. Reports BOTH the deduped-gate fraction (headline) and the
    mean per-group pass-fraction, so a group with many gates (optimize=9) can't skew the reading
    and a path shared by two groups isn't double-counted. Reuses feedback.quality + the objective
    gate definitions — no judge, no images, no pipeline state.
    """
    obj = _resolve_mesh(ctx, payload)
    asset_class = payload.get("asset_class")
    metrics = quality(ctx, {"object": obj.name, "asset_class": asset_class} if asset_class
                      else {"object": obj.name})
    asset_meta = metrics.get("asset_class", {})
    ac_id = asset_meta.get("id") if isinstance(asset_meta, dict) else asset_class

    per_group: list[dict] = []
    deduped: dict[tuple, bool] = {}          # (path, op, value) -> pass (kept once)
    stage_fractions: list[float] = []
    for group in _GATE_GROUPS:
        gates, _applied = stage_gates(group, asset_class=ac_id)
        if not gates:
            continue
        checked = check_gates(metrics, gates)
        count = len(gates)
        passed = sum(1 for g in checked["gates"] if g["pass"])
        stage_fractions.append(passed / count)
        per_group.append({"group": group, "gate_profile": gate_profile(group),
                          "gates_pass": checked["gates_pass"], "gates_count": count,
                          "gates_pass_count": passed, "pass_fraction": passed / count})
        for g in checked["gates"]:
            deduped[(g["path"], g["op"], _hashable(g["value"]))] = g["pass"]

    total = len(deduped)
    total_pass = sum(1 for ok in deduped.values() if ok)
    per_gate = [{"path": p, "op": o, "value": v, "pass": ok} for (p, o, v), ok in deduped.items()]
    return {
        "object": obj.name, "asset_class": asset_meta,
        "readiness": (total_pass / total) if total else None,
        "stage_pass_fraction_mean": (sum(stage_fractions) / len(stage_fractions)) if stage_fractions else None,
        "total_gates_deduped": total, "total_gates_pass_deduped": total_pass,
        "per_group": per_group, "per_gate": per_gate,
    }


def _hashable(v):
    return tuple(v) if isinstance(v, (list, dict, set)) else v
```

Add to `COMMANDS`: `Command("feedback.readiness", readiness, mutates=False)`.

- [ ] **Step 4 — Add the server ToolSpec** (`src/niua_blender_mcp/domains/feedback.py`)

```python
ToolSpec(
    name="feedback.readiness",
    category="feedback",
    summary="Objective game-ready scorecard: fraction of all objective gates passed, order-free + deduped (no judge, no images)",
    command="feedback.readiness",
    params={
        "object": Str(summary="Mesh object to score (defaults to active)"),
        "asset_class": Enum(ASSET_CLASS_IDS, summary="Layer 2 asset-class profile"),
    },
),
```
(`ASSET_CLASS_IDS` and `Enum` are already imported in this server module.)

- [ ] **Step 5 — Surface the game-ready check + accept/revert loop in the prompt** (`src/niua_blender_mcp/prompts.py`)

In `_refine_mesh`, name readiness in step 4 and document the loop in step 5:

```
   - Game-ready: call `feedback.readiness` for the objective definition-of-done — the fraction of
     all game-ready gates passed (topology / UV / material / engine / export), aggregated in no
     order. Read `per_group` to see which axis is blocking.
```
and, in step 5 (KEEP OR REVERT), add the do-no-harm hill-climb explicitly:

```
   THE CORE LOOP (do no harm while making it game-ready): once per subject, `feedback.capture_intake`
   to set the baseline. Then, each iteration: `session.checkpoint` -> make ONE edit -> re-measure
   `feedback.readiness` AND `feedback.preservation` -> KEEP the edit only if readiness went up (or
   held) AND preservation stayed >= 0.85; otherwise `session.revert`. This keeps the pass a monotone
   hill-climb that cannot score below where it started — the machine does not revert for you.
```

- [ ] **Step 6 — Run tests + full suite + commit**

```bash
pytest tests/domains/test_readiness.py tests/test_parity.py -q
pytest -q
git add blender_addon/niua_mcp_bridge/domains/feedback.py \
        src/niua_blender_mcp/domains/feedback.py src/niua_blender_mcp/prompts.py \
        tests/domains/test_readiness.py
git commit -m "feat: order-free deduped feedback.readiness scorecard + agent-loop prompt"
```

---

## Task 5 — Objective benchmark runner (pure Python, no judge, honestly scoped)

**Why:** replace the judged altimeter's grade with a deterministic reading. Scoring/aggregation is pure
Python (offline-testable). The live harness drives the bridge, reads `feedback.readiness` +
`feedback.preservation`, and scores — **no LLM judge**. It is honestly scoped as an **input-quality /
baseline probe by default**, with a **pluggable real finisher**, so it never claims "the pipeline preserves
form" from a no-op driver. It **distinguishes unmeasured from failed**, adds a **startup registration guard**,
and uses **correct tool names**.

**Files:**
- Create: `src/niua_blender_mcp/evals/objective_bench.py` (pure scoring + aggregation)
- Create: `scripts/run_objective_benchmark.py` (live harness)
- Test: `tests/evals/test_objective_bench.py`, `tests/evals/test_objective_runner.py`

**Interface (pure, tested):**
- `score_item_objective(item, *, readiness, stage_pass_fraction, preservation, preservation_available, floor=0.85) -> dict`
  → `{id, asset_class, readiness, stage_pass_fraction, preservation, preservation_measured,
  preservation_pass, harm_flagged, fully_ready}` where
  `preservation_measured = bool(preservation_available)`,
  `preservation_pass = preservation_measured and preservation >= floor`,
  `harm_flagged = preservation_measured and preservation < floor` (the do-no-harm FLAG),
  `fully_ready = readiness == 1.0`. **No all-26-gate `success` boolean** — the two continuous axes are the
  headline.
- `aggregate_objective(cards, floor=0.85) -> dict` → `{n_items, n_measured, n_unmeasured, n_harm_flagged,
  n_preservation_pass, n_fully_ready, mean_readiness, mean_stage_pass_fraction, mean_preservation, per_class,
  valid}`. `mean_readiness`/`mean_stage_pass_fraction` are over **all** items (readiness is always
  measurable — pure geometry). `mean_preservation` is over **measured** items only (`n_unmeasured` excluded);
  `None` when nothing was measured. `valid = n_unmeasured == 0` so a headless run cannot masquerade as a
  clean primary reading.

- [ ] **Step 1 — Write the failing test**

```python
# tests/evals/test_objective_bench.py
from __future__ import annotations

from niua_blender_mcp.evals.objective_bench import aggregate_objective, score_item_objective

ITEM = {"id": "barrel", "asset_class": "from_scratch_prop"}


def test_harm_flagged_below_floor() -> None:
    card = score_item_objective(ITEM, readiness=1.0, stage_pass_fraction=1.0,
                                preservation=0.80, preservation_available=True)
    assert card["preservation_measured"] is True
    assert card["preservation_pass"] is False
    assert card["harm_flagged"] is True


def test_floor_boundary_passes_at_085() -> None:
    card = score_item_objective(ITEM, readiness=0.9, stage_pass_fraction=0.9,
                                preservation=0.85, preservation_available=True)
    assert card["preservation_pass"] is True
    assert card["harm_flagged"] is False


def test_unmeasured_is_not_failed() -> None:
    card = score_item_objective(ITEM, readiness=0.5, stage_pass_fraction=0.4,
                                preservation=None, preservation_available=False)
    assert card["preservation_measured"] is False
    assert card["harm_flagged"] is False       # unmeasured != harm
    assert card["preservation_pass"] is False


def test_aggregate_excludes_unmeasured_from_preservation_mean() -> None:
    cards = [
        score_item_objective({"id": "a", "asset_class": "hard_surface_prop"},
                             readiness=1.0, stage_pass_fraction=1.0, preservation=0.95, preservation_available=True),
        score_item_objective({"id": "b", "asset_class": "hard_surface_prop"},
                             readiness=0.5, stage_pass_fraction=0.4, preservation=None, preservation_available=False),
    ]
    agg = aggregate_objective(cards)
    assert agg["n_items"] == 2
    assert agg["n_measured"] == 1
    assert agg["n_unmeasured"] == 1
    assert abs(agg["mean_readiness"] - 0.75) < 1e-9       # readiness always measurable
    assert abs(agg["mean_preservation"] - 0.95) < 1e-9    # only the measured item
    assert agg["valid"] is False                          # a headless item present


def test_aggregate_empty_and_all_unmeasured() -> None:
    assert aggregate_objective([])["mean_preservation"] is None
    card = score_item_objective({"id": "c", "asset_class": "organic_prop"},
                                readiness=0.0, stage_pass_fraction=0.0, preservation=None, preservation_available=False)
    agg = aggregate_objective([card])
    assert agg["mean_preservation"] is None
    assert agg["valid"] is False
```

- [ ] **Step 2 — Run to verify it fails**

Run: `pytest tests/evals/test_objective_bench.py -q` → FAIL (module missing).

- [ ] **Step 3 — Implement the pure scoring/aggregation** (`src/niua_blender_mcp/evals/objective_bench.py`)

```python
# src/niua_blender_mcp/evals/objective_bench.py
"""Deterministic objective benchmark scoring — no LLM judge.

readiness (order-free deduped gate fraction) and preservation (mean silhouette IoU vs intake)
are computed by the tools; this module only scores + aggregates. Do-no-harm is a FLAG
(harm_flagged), never a revert. 'unmeasured' (headless / non-separable preservation) is kept
distinct from 'failed' so a headless run reports honestly and is marked invalid.
"""

from __future__ import annotations

from typing import Any

PRESERVATION_FLOOR_DEFAULT = 0.85


def _num(x: Any) -> float:
    return float(x) if isinstance(x, (int, float)) else 0.0


def score_item_objective(item: dict, *, readiness: float | None, stage_pass_fraction: float | None,
                         preservation: float | None, preservation_available: bool,
                         floor: float = PRESERVATION_FLOOR_DEFAULT) -> dict:
    measured = bool(preservation_available) and preservation is not None
    return {
        "id": item.get("id"),
        "asset_class": item.get("asset_class"),
        "readiness": readiness,
        "stage_pass_fraction": stage_pass_fraction,
        "preservation": preservation if measured else None,
        "preservation_measured": measured,
        "preservation_pass": measured and preservation >= floor,
        "harm_flagged": measured and preservation < floor,
        "fully_ready": readiness == 1.0,
    }


def aggregate_objective(cards: list[dict], floor: float = PRESERVATION_FLOOR_DEFAULT) -> dict:
    n = len(cards)
    measured = [c for c in cards if c.get("preservation_measured")]
    mean_r = (sum(_num(c.get("readiness")) for c in cards) / n) if n else None
    mean_s = (sum(_num(c.get("stage_pass_fraction")) for c in cards) / n) if n else None
    mean_p = (sum(c["preservation"] for c in measured) / len(measured)) if measured else None
    per_class: dict[str, dict] = {}
    for c in cards:
        b = per_class.setdefault(c["asset_class"], {"n": 0, "_r": 0.0, "_pm": [], "n_harm": 0})
        b["n"] += 1
        b["_r"] += _num(c.get("readiness"))
        b["n_harm"] += 1 if c.get("harm_flagged") else 0
        if c.get("preservation_measured"):
            b["_pm"].append(c["preservation"])
    for b in per_class.values():
        b["mean_readiness"] = b.pop("_r") / b["n"]
        pm = b.pop("_pm")
        b["mean_preservation"] = (sum(pm) / len(pm)) if pm else None
    return {
        "n_items": n, "n_measured": len(measured), "n_unmeasured": n - len(measured),
        "n_harm_flagged": sum(1 for c in cards if c.get("harm_flagged")),
        "n_preservation_pass": sum(1 for c in cards if c.get("preservation_pass")),
        "n_fully_ready": sum(1 for c in cards if c.get("fully_ready")),
        "mean_readiness": mean_r, "mean_stage_pass_fraction": mean_s, "mean_preservation": mean_p,
        "floor": floor, "per_class": per_class, "valid": n > 0 and (n - len(measured)) == 0,
    }
```

- [ ] **Step 4 — Run tests to verify pass**

Run: `pytest tests/evals/test_objective_bench.py -q` → PASS.

- [ ] **Step 5 — Write the live harness** (`scripts/run_objective_benchmark.py`)

Pure-Python CLI. It builds each item's input from `item.input.recipe`, names the subject via the create
step (or `object.rename`), captures the intake baseline, runs a **finisher** (default = baseline probe;
a real agent finisher is pluggable), then reads readiness + preservation and scores. **No LLM judge.**

```python
#!/usr/bin/env python3
"""Objective benchmark runner (deterministic, no LLM judge). PRIMARY grade for this ruler.

Per item: build the input mesh from item.input.recipe as subject 'bench_<id>',
feedback.capture_intake (do-no-harm baseline), run a FINISHER, then read feedback.readiness
+ feedback.preservation and score. Aggregate + write {outdir}/objective-reading.json.

MODES (honest scoping — see --mode):
  baseline : the finisher is a no-op; the reading is the INPUT-QUALITY of each benchmark mesh
             (readiness + preservation of the untouched intake). This does NOT claim the
             pipeline preserves form — it is a baseline probe. (default)
  agent    : a real finisher callable is wired in (--finisher module:function); it does the
             actual finishing work before scoring, so the reading is of the FINISHED asset.
Scoring is deterministic in both modes. The forced-damage acceptance (A3) proves the
preservation metric detects harm regardless of mode.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from niua_blender_mcp.bridge import BlenderBridge, BridgeError
from niua_blender_mcp.domains import build_router
from niua_blender_mcp.evals.benchmark import list_items, load_item
from niua_blender_mcp.evals.objective_bench import aggregate_objective, score_item_objective

# Fixed tools the runner itself calls (recipe tools are added dynamically in the guard).
_RUNNER_TOOLS = {"object.rename", "feedback.capture_intake", "feedback.readiness", "feedback.preservation"}


def known_tools() -> set[str]:
    return {("capabilities.invoke" if s.tier == "generated" else s.command) for s in build_router().specs()}


def assert_tools_registered(items: list[dict]) -> None:
    """Startup registration guard: fail LOUD + OFFLINE if the runner would call a missing tool."""
    needed = set(_RUNNER_TOOLS)
    for it in items:
        for step in it["input"]["recipe"]:
            needed.add(step["tool"])
    missing = sorted(needed - known_tools())
    if missing:
        raise SystemExit(f"registration guard: tools not in build_router().specs(): {missing}")


def _build_input(bridge, item, subject) -> None:
    steps = item["input"]["recipe"]
    for i, step in enumerate(steps):
        args = dict(step.get("args", {}))
        if i == 0 and step["tool"] == "scene.create_object" and "name" not in args:
            args["name"] = subject                      # name the created object deterministically
        bridge.call(step["tool"], args)
    # Ensure the subject carries the unique name even if the recipe did not create it first.
    if not (steps and steps[0]["tool"] == "scene.create_object"):
        created = bridge.call("scene.create_object", {"type": "CUBE", "name": subject})
        bridge.call("object.rename", {"object": created.get("name", subject), "name": subject})


def _no_op_finisher(bridge, subject, item) -> None:
    """Baseline mode: do nothing. The reading is the untouched intake's quality."""
    return None


def run_item(bridge, item, finisher) -> dict:
    subject = f"bench_{item['id']}"
    _build_input(bridge, item, subject)
    intake = bridge.call("feedback.capture_intake", {"object": subject})
    finisher(bridge, subject, item)                      # real work in agent mode; no-op in baseline
    readiness = bridge.call("feedback.readiness", {"object": subject, "asset_class": item["asset_class"]})
    pres = bridge.call("feedback.preservation", {"object": subject})
    pres_available = bool(intake.get("available")) and bool(pres.get("available"))
    return score_item_objective(
        item,
        readiness=readiness.get("readiness"),
        stage_pass_fraction=readiness.get("stage_pass_fraction"),
        preservation=pres.get("preservation"),
        preservation_available=pres_available,
    )


def _load_finisher(spec: str):
    module_name, _, func = spec.partition(":")
    return getattr(importlib.import_module(module_name), func)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Objective benchmark runner (no LLM judge)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--outdir", default="/tmp/niua_objective_run")
    ap.add_argument("--items", default="", help="comma-separated ids (all if empty)")
    ap.add_argument("--mode", choices=["baseline", "agent"], default="baseline")
    ap.add_argument("--finisher", default="", help="agent mode: 'module:function(bridge, subject, item)'")
    args = ap.parse_args(argv)

    ids = list_items()
    if args.items:
        wanted = set(args.items.split(","))
        ids = [i for i in ids if i in wanted]
    items = [load_item(i) for i in ids]

    assert_tools_registered(items)                       # loud, offline, before any bridge call
    finisher = _no_op_finisher if args.mode == "baseline" else _load_finisher(args.finisher)

    bridge = BlenderBridge(port=args.port, timeout=120.0)
    cards = [run_item(bridge, it, finisher) for it in items]
    reading = aggregate_objective(cards)
    grade = "PRIMARY" if reading["valid"] else "INVALID"  # headless / unmeasured -> INVALID
    out = {"meta": {"grade": grade, "runner": "objective", "judge": None, "mode": args.mode,
                    "finisher": args.finisher or None,
                    "timestamp": datetime.now(timezone.utc).isoformat()},
           "items": cards, "reading": reading}
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "objective-reading.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6 — Offline registration + structural test** (`tests/evals/test_objective_runner.py`)

```python
# tests/evals/test_objective_runner.py
from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_RUNNER = _REPO / "scripts" / "run_objective_benchmark.py"


def test_runner_parses() -> None:
    ast.parse(_RUNNER.read_text(encoding="utf-8"))


def test_every_runner_and_recipe_tool_is_registered() -> None:
    # The heart of red-team CRITICAL #1: no bad tool names reach the live path.
    import sys
    sys.path.insert(0, str(_REPO / "scripts"))
    import run_objective_benchmark as runner  # noqa: E402
    from niua_blender_mcp.evals.benchmark import list_items, load_item

    known = runner.known_tools()
    assert runner._RUNNER_TOOLS <= known, sorted(runner._RUNNER_TOOLS - known)
    # object.rename is the correct singular tool; objects.rename must NOT exist.
    assert "object.rename" in known and "objects.rename" not in known
    for item_id in list_items():
        for step in load_item(item_id)["input"]["recipe"]:
            assert step["tool"] in known, step["tool"]
```

- [ ] **Step 7 — Run tests + full suite + commit**

```bash
pytest tests/evals/test_objective_bench.py tests/evals/test_objective_runner.py -q
pytest -q
git add src/niua_blender_mcp/evals/objective_bench.py \
        scripts/run_objective_benchmark.py \
        tests/evals/test_objective_bench.py tests/evals/test_objective_runner.py
git commit -m "feat: pure-python objective benchmark runner (readiness+preservation, no judge, honest scoping)"
```

---

## Task 6 — Retire the judged altimeter as the PRIMARY grade

**Why:** the objective runner is now the grade. The judged altimeter stays only as an optional perceptual
spot-check, unmistakably labelled non-primary so no later wave targets its number.

**Files:**
- Modify: `workflows/altimeter.mjs` (banner + `meta` relabel)
- Test: `tests/evals/test_primary_grade.py`

- [ ] **Step 1 — Write the failing test**

```python
# tests/evals/test_primary_grade.py
from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def test_objective_runner_is_the_primary_grade() -> None:
    from niua_blender_mcp.evals.objective_bench import aggregate_objective, score_item_objective  # noqa: F401
    assert (_REPO / "scripts" / "run_objective_benchmark.py").is_file()


def test_altimeter_marked_non_primary() -> None:
    text = (_REPO / "workflows" / "altimeter.mjs").read_text(encoding="utf-8")
    assert "NON-PRIMARY" in text
    assert "run_objective_benchmark" in text
```

- [ ] **Step 2 — Run to verify it fails** → `pytest tests/evals/test_primary_grade.py -q` FAIL.

- [ ] **Step 3 — Relabel the altimeter** (`workflows/altimeter.mjs`)

Prepend the banner and edit `meta`:

```javascript
// ============================================================================
// NON-PRIMARY. This judged 5-lens panel is an OPTIONAL perceptual spot-check only.
// The PRIMARY, deterministic grade for this tool is the objective runner:
//   python scripts/run_objective_benchmark.py --port <p>
// (readiness = objective gates passed, order-free; preservation = silhouette IoU vs intake;
//  do-no-harm is a scorecard FLAG, never a revert; no LLM judge). Do NOT treat this workflow's
//  number as the target — SEM ~0.7 — it is retained solely for occasional perceptual review.
// ============================================================================

export const meta = {
  name: 'altimeter',
  grade: 'non-primary',
  description: 'NON-PRIMARY perceptual spot-check (judged). Primary grade is scripts/run_objective_benchmark.py.',
  // ...
}
```

- [ ] **Step 4 — Run tests to verify pass** → `pytest tests/evals/test_primary_grade.py -q` then `node --check workflows/altimeter.mjs`.

- [ ] **Step 5 — Full suite + commit**

```bash
pytest -q
git add workflows/altimeter.mjs tests/evals/test_primary_grade.py
git commit -m "chore: demote judged altimeter to non-primary; objective runner is primary"
```

---

## Final live-acceptance (LIVE — deliberately triggered, not in the TDD loop)

The eyes need a GL context, so run against a **visible** Blender bridge (pure `--background` returns
`available:false`, so preservation is `unmeasured` and the runner stamps `meta.grade == "INVALID"` — by
design).

**Prerequisite:** launch the visible bridge on 8765:
`blender --python scripts/blender_gui.py -- <repo>/blender_addon 8765 0`
Confirm it answers: `python scripts/bridge_call.py 8765 scene.info '{}'`.

- [ ] **A1 — The mask is real and separable (do FIRST).** On one live intake mesh, call
  `feedback.capture_intake`, then decode one stored view and assert `0.02 < coverage < 0.98` (object is a
  plausible fraction of frame; not all-empty, not all-full). Confirms the alpha/film_transparent separation
  works before trusting any IoU.

- [ ] **A2 — Preservation matches the eye + fixed frame holds.** On an untouched subject, `capture_intake`
  then `feedback.preservation` → `preservation ≈ 1.0`, `bbox_delta.changed == false`. Re-render twice with
  no edit and confirm the IoU **noise floor** (fixed ortho frame + alpha should sit ≈ 0.99, well above
  0.85). Then apply a real uniform **resize** and confirm `bbox_delta.changed == true` even if IoU stays
  high — proving uniform scale is visible.

- [ ] **A3 — The metric flags a forced damaging op.** On a subject with a stored baseline, deliberately
  collapse the form (e.g. heavy `mesh.subdivide` + smooth/shrink), then `feedback.preservation` →
  `available == true`, `preservation < 0.85`, `preservation_pass == false`, `min_view` names the worst
  angle. Confirm **nothing auto-reverts** (the mesh stays damaged; `pipeline.advance` is never called) and
  that the agent-loop remedy is `session.revert` to `niua:intake`. Record `docs/reports/objective/harm-proof.md`.

- [ ] **A4 — Run the objective runner (baseline mode) on the 7 items.**
  `python scripts/run_objective_benchmark.py --port 8765 --mode baseline --outdir docs/reports/objective`
  Confirm `meta.grade == "PRIMARY"` (all preservation measured — else INVALID and investigate headless),
  `meta.judge == null`, `reading.valid == true`, and read the honest input-quality baseline:
  `mean_readiness` (order-free deduped gate fraction), `mean_stage_pass_fraction`, and `mean_preservation`
  (≈ 1.0 — the intake meshes are untouched, so this run is a BASELINE PROBE, **not** a claim that a
  pipeline preserves form). Save `objective-reading.json` as the baseline every later wave must beat.

- [ ] **A5 — Calibrate the floor.** Using A2's noise floor and A3's damage number (and, per class, a couple
  of known-benign edits vs known-harmful edits), confirm 0.85 cleanly separates AA/render noise from real
  harm. If a class needs a different floor, note it — `PRESERVATION_FLOOR` is a one-line per-class change.

**Done when:** metric + ledger + render + three read-only tools + runner are parity-green and committed
(Tasks 1–6); `feedback.readiness` and `feedback.preservation` are computable offline (synthetic) and live;
the objective runner produces `{mean_readiness, mean_stage_pass_fraction, mean_preservation}` deterministically
with unmeasured excluded and headless stamped INVALID; the preservation metric demonstrably flags a forced
damaging op (with nothing auto-reverting); and no LLM judge sits in the primary grade.

---

## Self-review notes

- **Order-free, no FSM.** Nothing calls `pipeline.start`/`advance`/`gate_check`/`status`, reads `_STORE`/
  `current_stage`, or flips a tool to `mutates=True`. `readiness` aggregates gate **groups** as a set;
  `preservation` reads the thin ledger; the ruler is buildable **before** the FSM is deleted and validates
  every later deletion.
- **Measure-and-flag.** Do-no-harm is `harm_flagged` in the scorecard; the accept/revert hill-climb lives in
  the `refine_mesh` prompt as prose using generic `session.checkpoint`/`revert`. No coded guard, no
  auto-revert, no per-stage-budget table.
- **Robust mask.** film_transparent + alpha threshold (world/lighting/AgX invariant); fixed ortho camera
  framed once from the intake bbox (never `view_selected`); ortho-only (front/right/top, no persp);
  separability fail-closed (both-empty/both-full → `available:false`, never a false 1.0); GL-free bbox delta
  makes uniform scale visible; `min_view` surfaces a single collapsed angle.
- **Parity everywhere.** Three new read-only tools each ship a server `ToolSpec` + add-on `Command`
  (`mutates=False`, `feedback=None`); `tests/test_parity.py` guards them. Consistent `object` contract
  (optional, defaults to active) across all three.
- **Honest runner.** `object.rename` (not `objects.rename`); subject named via the create step / rename (no
  `scene.info["active"]`); startup registration guard (offline, loud); unmeasured vs failed distinguished
  (`n_unmeasured` excluded, `meta.grade == INVALID` on headless); no no-op driver claiming "preserves form"
  — baseline probe by default, real finisher pluggable; no LLM judge.
- **Runs inside Blender.** Decode path is stdlib-only (Pillow only encodes test fixtures); `res=256` keeps
  the pure-Python unfilter fast; every GL path degrades to `available:false` without raising.
- **Floor is one constant.** `PRESERVATION_FLOOR = 0.85` in `core/preservation_ledger.py` and
  `PRESERVATION_FLOOR_DEFAULT` in `objective_bench.py`; per-class tuning is a later one-line map.

---

## Red-team resolution ledger

Mapping every finding on the first (FSM-bound) plan to its resolution here. "Obviated" = the order-free /
measure-and-flag / no-FSM design removes the failure mode entirely.

### CRITICAL

1. **Runner calls `objects.rename` + `scene.info["active"]` (nonexistent).** → **Task 5.** Uses
   `object.rename` (singular, verified `objects.py:121`); derives the subject name from the create step's
   `name` param (falls back to `object.rename` on the create result); startup **registration guard** +
   `tests/evals/test_objective_runner.py` assert every runner/recipe tool ∈ `build_router().specs()`
   **offline**, and that `objects.rename` does not exist.
2. **RGB-luma threshold scene-dependent → guard silently fails open.** → **Tasks 1 + 2.** Mask is the
   **alpha** channel under `render.film_transparent=True` (invariant to world/lighting/AgX); `is_separable`
   returns `available:false` when object/background aren't separable.
3. **Cumulative-vs-intake auto-revert deadlocks retopo/LOD.** → **Obviated (Tasks 3 + 5).** No guard, no
   auto-revert; `pipeline.advance` untouched; preservation is a measured metric flagged in the scorecard;
   the per-stage-budget table is dropped per the architecture verdict.
4. **Guard fails open; snapshot-`data`-None divergence.** → **Obviated.** No guard. Preservation is
   fail-closed (`available:false` on ambiguity); the metric never reverts, so there is no
   reported-vs-actual divergence.
5. **`view_selected` reframing + AA false-reverts legitimate stages.** → **Tasks 2 + 3.** Fixed ortho camera
   framed once from the stored intake bbox (never `view_selected`); no reverts at all; `min_view` +
   live noise-floor calibration (A2/A5).
6. **No-op driver vacuously "proves the pipeline preserves form".** → **Task 5.** Runner is honestly scoped
   as a **baseline / input-quality probe** by default (`meta.mode`), with a pluggable real finisher; the
   forced-damage acceptance (A3) proves harm detection; unmeasured items can't inflate the reading.
7. **Live fg/bg separation unvalidated; both-degenerate → IoU 1.0.** → **Tasks 1 + 2 + A1.** Alpha mask +
   `is_separable` (both-empty/both-full excluded); `capture_intake` fail-closes on non-separable views; A1
   asserts `0.02 < coverage < 0.98` on a real render.
8. **Task-3 red test contradicts impl (`from_stage=="intake"` skip).** → **Obviated.** No guard, no `advance`
   change; the preservation tests drive `capture_intake` → `preservation` directly with a monkeypatched
   render.

### IMPORTANT

1. **Tools registered but not discoverable.** → **Tasks 3 + 4.** `prompts.py` `_refine_mesh` names
   `feedback.readiness` (game-ready) and `feedback.preservation` (do-no-harm) and documents the
   capture_intake baseline + accept/revert loop — shipped in the same tasks that add each tool.
2. **`advance` → `mutates=True` violates the mutation contract on the happy path.** → **Obviated.** `advance`
   is never touched; all three new tools stay `mutates=False`.
3. **Uniform-scale invisibility.** → **Tasks 1 + 2.** Fixed intake frame makes a uniform resize reduce IoU,
   and `bbox_delta` reports an explicit `scale_ratio`/`changed` flag (verified in
   `test_preservation_uniform_scale_visible_in_bbox_delta`).
4. **Framing not reproducible across the intake/current gap.** → **Task 2.** Hidden ortho camera fitted to
   the **stored** intake frame (center/size in the ledger); square `res=256` output — region/aspect
   independent.
5. **0.85 floor unvalidated; report min not just mean.** → **Task 1 (`min_view`) + A2/A5.** Live noise-floor
   calibration vs benign/harmful edits before trusting 0.85; floor is one constant.
6. **No loop-breaker for an agentic caller.** → **Obviated.** No guard/loop; the agent's bounded hill-climb
   is prose (prompt), keep-iff-better else `session.revert`.
7. **PRIMARY runner never exercises the guard / does no finishing.** → **Task 5.** Explicitly scoped as a
   baseline probe with a pluggable finisher; guard obviated; harm detection proven by A3.
8. **Headless yields a misleading catastrophic grade.** → **Task 5.** `preservation_measured` distinguishes
   unmeasured from failed; `aggregate` excludes unmeasured from `mean_preservation`; `meta.grade == INVALID`
   and `reading.valid == false` when `n_unmeasured > 0`.
9. **Spurious undo on every `advance` (duplicate of IMPORTANT #2).** → **Obviated.**
10. **Readiness is a gate-count artifact; `non_manifold_edges` double-weighted; optimize dominates.** →
    **Task 4.** Reports the **deduped** gate fraction (headline) **and** the equal-weight
    `stage_pass_fraction_mean`; dedup by `(path, op, value)` collapses the shared `non_manifold_edges` gate
    (asserted in `test_readiness_reports_both_fractions_and_dedup`).
11. **Preservation uses `ortho4` = includes `persp` (design said `ortho3`, which doesn't exist).** →
    **Task 2.** `PRESERVATION_VIEWS = ("front","right","top")` — ortho-only, persp excluded.
12. **Phantom undo on `advance` (duplicate of #2/#9).** → **Obviated.**
13. **Runner non-existent symbols (duplicate of CRITICAL #1).** → **Task 5** + offline registration test.

### MINOR

- **`object` required vs optional inconsistency across the two tools.** → All three read-only tools use
  `object` **optional** (defaults to active via `_resolve_mesh`) — consistent.
- **Name drift (`feedback.silhouette_masks` / `feedback.preservation` / separate `evals/*` modules).** →
  Locked canonical names (decision 6): `feedback.capture_intake` / `feedback.preservation` /
  `feedback.readiness` + `core/silhouette_metrics.py` + `core/preservation_ledger.py` +
  `evals/objective_bench.py`. Design §5 / maps' alternate names are explicitly superseded.
- **Persp in the mean adds noise.** → Ortho-only (Task 2).
- **`compute_iou` both-empty → 1.0 silent pass.** → `mean_preservation` separability-gates it out; both-empty
  → `available:false` (Task 1, `test_mean_preservation_detects_damage_and_min_view`).
- **Guard state inconsistency / res=768 vs 256 stall.** → **Obviated** (no guard); `res=256` pinned in the
  ledger constant.
- **`gates_pass`/`fully_ready` conflation; all-26 hard `AND` degenerate `success`.** → **Tasks 4 + 5.** The
  headline is the two continuous fractions; there is no all-gate `success` boolean — only
  `preservation_pass`/`harm_flagged` (do-no-harm) and an informational `fully_ready`.
- **Alpha-vs-luma version-dependence.** → **Task 1.** Alpha for color types 4/6; luma only as an opaque
  fallback.
- **Checkpoint of damaged geometry retained.** → **Obviated** (no per-stage checkpointing; the only
  checkpoint is the intake baseline `niua:intake`).
- **`success` near-degenerate.** → **Task 5.** Continuous fractions are primary; per-class means reported.
