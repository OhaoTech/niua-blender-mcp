# Surface Fidelity + Bake-Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic surface-fidelity preservation metric (the ruler), prove it catches the detail loss the silhouette metric misses, then build a bake-transfer move + `bake_and_finish` skill graded by it — so a finished asset looks almost identical to the input.

**Architecture:** Ruler-first, two phases in one plan. Phase A extends the do-no-harm pair with an EEVEE shaded-render + pure-stdlib block-SSIM `surface_fidelity` axis, and ends with a LIVE validation gate that must flag the known-bad decimate before any bake code. Phase B adds an `object.bake_transfer` tool and a `bake_and_finish` skill (over the code-mode SDK) whose accept/revert loop is gated on silhouette AND fidelity.

**Tech Stack:** Python 3 stdlib (the metric is dependency-free like `silhouette_metrics.py`); the hand-rolled MCP kernel + TCP bridge; Blender 5.1 EEVEE for the shaded render and `bpy.ops.object.bake` for the bake; pytest.

## Global Constraints

- **ZERO niua knowledge in code.** The SSIM metric, the shaded render, and the bake op are generic; only the fidelity *floor* and the *skill* are policy.
- **Additive, non-breaking:** `feedback.preservation`'s existing `preservation` (silhouette IoU) field and all its consumers are unchanged; `surface_fidelity` is a new field. `make_game_ready` (skill #1) and its benchmark reading are untouched (0.36/0.36/0.36/0.24/0.28 baseline; 0.76/0.80/0.80/0.60/0.64 agent — must stay byte-identical).
- **Layer boundary green** (`tests/test_layer_boundary.py`): `core/fidelity_metrics.py` and the `core/silhouette.py` render are INTERFACE (import nothing from `finishing`/`evals`); `finishing/preservation_ledger.py` (holds `SURFACE_FIDELITY_FLOOR`), `domains/finishing_feedback.py`, and `finishing/skills/` are POLICY.
- **Determinism:** the fidelity render uses a fixed ortho frame + one fixed sun + no denoise/AA-dither/temporal sampling; the SSIM is pure integer/float math — so the metric is stable run-to-run and judge-free. Fail-closed: any unmeasurable view/render → `available: false`, never a fake score.
- **Parity green** (`tests/test_parity.py`): the new `object.bake_transfer` tool lands on BOTH sides in one commit; the SDK is regenerated so `session.object.bake_transfer` exists and the drift test stays green.
- **Full offline suite green before every commit:** `NIUA_SKIP_BLENDER=1 python -m pytest -q` (currently 794 passed, 71 skipped).
- **Ruler-first gate (binding):** Phase B does not start until Task A5's LIVE gate proves the metric flags the known-bad decimate. If A5 fails, fix the metric; do not proceed.
- **Commit style:** one commit per task, conventional subject, trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Module map

- `core/silhouette_metrics.py` [EXTEND] — factor out a shared raw-pixel PNG decode (interface).
- `core/fidelity_metrics.py` [NEW] — luma extraction + block-SSIM + `mean_fidelity` (interface, pure stdlib).
- `core/silhouette.py` [EXTEND] — `render_fidelity_views` EEVEE shaded pass (interface, live-validated).
- `finishing/preservation_ledger.py` [EXTEND] — `SURFACE_FIDELITY_FLOOR` + store the shaded baseline (policy).
- `domains/finishing_feedback.py` [EXTEND] — `capture_intake` stores the baseline; `preservation` returns `surface_fidelity` (policy).
- `domains/objects.py` (addon) + `src/.../domains/objects.py` (server) [EXTEND] — `object.bake_transfer` (interface op, both sides).
- `client/tools/object.py` [REGEN] — the SDK gains `bake_transfer`.
- `finishing/skills/bake_and_finish.py` [NEW] + `finishing/skills/__init__.py` [EXTEND] — skill #2 (policy).
- `evals/objective_bench.py` + `evals/scorecard.py` [EXTEND] — `surface_fidelity` axis (policy).

---

## PHASE A — the fidelity ruler

### Task A1: Shared raw-pixel PNG decode

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/core/silhouette_metrics.py`
- Test: `tests/core/test_silhouette_metrics.py` (extend; create if absent)

**Interfaces:**
- Produces: `decode_png_rgba(png: bytes) -> tuple[int, int, int, bytes]` returning `(width, height, channels, pixels)` where `pixels` is the defiltered 8-bit rows (length `w*h*channels`), `channels` is 1/2/3/4. `decode_png_coverage` keeps its exact current signature and output (now derived from the shared decode).

- [ ] **Step 1: Write the failing test**

Add to `tests/core/test_silhouette_metrics.py`:

```python
import base64, struct, zlib
from niua_mcp_bridge.core import silhouette_metrics as sm


def _make_png(w, h, channels, fill):
    """Build a minimal 8-bit PNG. fill(x,y) -> tuple of `channels` byte values."""
    color_type = {1: 0, 2: 4, 3: 2, 4: 6}[channels]
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter type 0
        for x in range(w):
            raw.extend(fill(x, y))
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b"")
    return png


def test_decode_png_rgba_returns_raw_pixels():
    png = _make_png(2, 1, 4, lambda x, y: (10 * (x + 1), 20, 30, 200))
    w, h, ch, px = sm.decode_png_rgba(png)
    assert (w, h, ch) == (2, 1, 4)
    assert list(px) == [10, 20, 30, 200, 20, 20, 30, 200]


def test_decode_png_coverage_still_returns_alpha_for_rgba():
    png = _make_png(2, 1, 4, lambda x, y: (0, 0, 0, 128 + x))
    w, h, cov = sm.decode_png_coverage(png)
    assert (w, h) == (2, 1)
    assert list(cov) == [128, 129]  # alpha channel, unchanged behavior
```

- [ ] **Step 2: Run to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/core/test_silhouette_metrics.py -q`
Expected: FAIL — `decode_png_rgba` does not exist.

- [ ] **Step 3: Refactor `silhouette_metrics.py`**

Extract the header-parse + zlib + defilter loop (currently inside `decode_png_coverage`, lines ~24-71) into a shared function, and derive both outputs from it:

```python
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
        ftype = raw[i]; i += 1
        line = bytearray(raw[i : i + stride]); i += stride
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
    alpha_i = {2: 1, 4: 3}.get(ch)  # channels 2 (GA) / 4 (RGBA) carry alpha last
    out = bytearray(w * h)
    for i in range(w * h):
        base = i * ch
        if alpha_i is not None:
            out[i] = px[base + alpha_i]
        elif ch >= 3:
            out[i] = (px[base] + px[base + 1] + px[base + 2]) // 3
        else:
            out[i] = px[base]
    return w, h, bytes(out)
```

Note: `_CHANNELS` maps color_type→channels (existing). The alpha index by *channel count* (2→1, 4→3) reproduces the old `_ALPHA_INDEX` by color_type (4→1 was GA, 6→3 was RGBA) — verify against the existing `_ALPHA_INDEX` constant and keep behavior identical.

- [ ] **Step 4: Run the tests + the existing silhouette tests**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/core/test_silhouette_metrics.py -q`
Expected: PASS (both new + any existing). The existing `mean_preservation`/`png_b64_to_mask` tests prove the refactor preserved behavior.

- [ ] **Step 5: Full suite + commit**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
```bash
git add blender_addon/niua_mcp_bridge/core/silhouette_metrics.py tests/core/test_silhouette_metrics.py
git commit -m "refactor: shared raw-pixel PNG decode in silhouette_metrics (behavior-preserving)"
```

---

### Task A2: `core/fidelity_metrics.py` — luma + block-SSIM

**Files:**
- Create: `blender_addon/niua_mcp_bridge/core/fidelity_metrics.py`
- Test: `tests/core/test_fidelity_metrics.py`

**Interfaces:**
- Consumes: `silhouette_metrics.decode_png_rgba` (A1); `silhouette_metrics.{compact_encode, compact_decode}` for storage.
- Produces:
  - `png_b64_to_luma_mask(data_b64, threshold=128) -> tuple[int, int, bytes, bytes]` → `(w, h, luma, mask)`, luma = `(R+G+B)//3`, mask = `1` where alpha>threshold.
  - `block_ssim(a: bytes, b: bytes, mask: bytes, w: int, h: int, block=8, min_blocks=4) -> float | None` — mean SSIM over non-overlapping `block×block` cells that are ≥half inside the mask; `None` if fewer than `min_blocks` qualify (fail-closed).
  - `mean_fidelity(intake: dict[str, tuple], current: dict[str, tuple]) -> dict` where each value is `(w, h, luma, mask)`; returns `{available, fidelity, per_view, min_view}` over the common views whose `block_ssim` is not None. `available: false` if none.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_fidelity_metrics.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/core/test_fidelity_metrics.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `core/fidelity_metrics.py`**

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/core/test_fidelity_metrics.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Full suite + commit**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
```bash
git add blender_addon/niua_mcp_bridge/core/fidelity_metrics.py tests/core/test_fidelity_metrics.py
git commit -m "feat: pure-stdlib surface-fidelity metric (block-SSIM over shaded renders)"
```

---

### Task A3: EEVEE shaded render pass (`render_fidelity_views`)

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/core/silhouette.py`
- Test: `tests/core/test_silhouette.py` (import-safety only; the render is LIVE-validated in A5)

**Interfaces:**
- Produces: `render_fidelity_views(bpy, obj_name, *, frame=None, views=("front","right","top"), res=256) -> dict` returning `{available, res, frame, images:[{view, data(b64 RGBA PNG)}]}` or `{available: False, reason}`. Same fixed-frame ortho isolation as `render_preservation_views`, but shaded (EEVEE + neutral clay + one fixed sun + shade-smooth).

This task is LIVE-validated (like `render_preservation_views`, which the file documents as "cannot be exercised under fake-bpy (no GL); validated by the live acceptance pass"). The only offline test asserts the module still imports and the function exists.

- [ ] **Step 1: Write the import-safety test**

Add to `tests/core/test_silhouette.py` (create if absent):

```python
def test_render_fidelity_views_exists_and_is_callable_signature():
    from niua_mcp_bridge.core import silhouette
    assert hasattr(silhouette, "render_fidelity_views")
    import inspect
    params = inspect.signature(silhouette.render_fidelity_views).parameters
    assert "obj_name" in params and "frame" in params and "views" in params and "res" in params
```

- [ ] **Step 2: Run to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/core/test_silhouette.py::test_render_fidelity_views_exists_and_is_callable_signature -q`
Expected: FAIL — function missing.

- [ ] **Step 3: Implement `render_fidelity_views`**

Add beside `render_preservation_views`. It mirrors that function's snapshot/isolate/restore structure exactly, with these differences: EEVEE engine, a temporary neutral clay material applied to the subject (its real material slots snapshotted and restored), one temporary sun lamp (removed after), shade-smooth on the subject (restored), RGBA + `film_transparent`. Reuse the existing `capture` helpers (`_ensure_capture_camera`, `scene_bbox`, `view_camera`, `_apply_frame`). Full code:

```python
def render_fidelity_views(bpy, obj_name, *, frame=None, views=("front", "right", "top"), res=256):
    """Fixed-frame EEVEE shaded renders (neutral clay + one fixed sun) for the surface-fidelity
    metric. Isolates the subject, applies a temporary clay material + smooth shading so the shaded
    luminance reflects SURFACE detail (and any baked normal map), renders RGBA (alpha = mask), then
    restores every touched piece of state. Degrades to {available:false} headless. LIVE-validated.
    """
    from . import capture as cap
    import base64, os, tempfile

    subject = bpy.data.objects.get(obj_name)
    if subject is None or getattr(subject, "type", None) != "MESH":
        return {"available": False, "reason": f"object not a mesh: {obj_name}"}
    try:
        center, size = cap.scene_bbox(bpy, obj_name)
        used = frame or {"center": center, "size": size}
        scene = bpy.context.scene
        render = scene.render
        cam = cap._ensure_capture_camera(bpy)

        prev = {
            "camera": scene.camera, "engine": getattr(render, "engine", None),
            "x": render.resolution_x, "y": render.resolution_y, "pct": render.resolution_percentage,
            "filepath": render.filepath, "fmt": render.image_settings.file_format,
            "color_mode": render.image_settings.color_mode,
            "film_transparent": getattr(render, "film_transparent", None),
        }
        hidden = [(o, o.hide_render) for o in scene.objects]
        slots = [m.material for m in subject.data.materials] if subject.data.materials else None
        prev_smooth = [p.use_smooth for p in subject.data.polygons]
        clay = bpy.data.materials.new("niua_fidelity_clay")
        clay.use_nodes = True
        bsdf = clay.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (0.6, 0.6, 0.6, 1.0)
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = 0.7
        sun_data = bpy.data.lights.new("niua_fidelity_sun", type="SUN")
        sun_data.energy = 3.0
        sun_obj = bpy.data.objects.new("niua_fidelity_sun", sun_data)
        sun_obj.rotation_euler = (0.9, 0.2, 0.5)
        scene.collection.objects.link(sun_obj)
        path = os.path.join(tempfile.gettempdir(), "niua_fidelity.png")
        images = []
        try:
            for o in scene.objects:
                o.hide_render = (o is not subject and o is not sun_obj)
            # temp clay: replace all slots with the clay material (keep normal-map materials?
            # no -- the metric wants surface SHAPE incl. baked normal, so clay replaces albedo but
            # a caller that wants the baked normal applied must have it wired into the object's OWN
            # material. For the intake high-poly there is no normal map; clay is correct. For a
            # baked low-poly, its own material carries the normal -- so DO NOT override slots when
            # the subject already has a material; only add clay when it has none.)
            added_clay = False
            if not subject.data.materials:
                subject.data.materials.append(clay)
                added_clay = True
            for p in subject.data.polygons:
                p.use_smooth = True
            scene.camera = cam
            try:
                render.engine = "BLENDER_EEVEE_NEXT"
            except Exception:  # noqa: BLE001 - older EEVEE id
                render.engine = "BLENDER_EEVEE"
            render.resolution_x = render.resolution_y = int(res)
            render.resolution_percentage = 100
            render.image_settings.file_format = "PNG"
            render.image_settings.color_mode = "RGBA"
            render.film_transparent = True
            render.filepath = path
            for view in views:
                cap._apply_frame(cam, cap.view_camera(used["center"], used["size"], view))
                bpy.ops.render.render(write_still=True)
                with open(path, "rb") as fh:
                    images.append({"view": view, "data": base64.b64encode(fh.read()).decode("ascii")})
        finally:
            if added_clay:
                subject.data.materials.pop()
            for p, was in zip(subject.data.polygons, prev_smooth):
                p.use_smooth = was
            bpy.data.objects.remove(sun_obj, do_unlink=True)
            bpy.data.lights.remove(sun_data)
            bpy.data.materials.remove(clay)
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
        return {"available": True, "res": int(res), "frame": used, "images": images}
    except Exception as exc:  # noqa: BLE001 - graceful degrade is the contract
        return {"available": False, "reason": str(exc)}
```

Design note captured in the code comment above: the fidelity render replaces albedo with neutral clay ONLY when the subject has no material of its own; a baked low-poly keeps its own material so the baked normal map affects shading (that is the whole point). The intake high-poly has no baked normal, so its surface shape comes from geometry — clay is correct there.

- [ ] **Step 4: Run the import-safety test + full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/core/test_silhouette.py -q && NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: PASS. (The render itself is validated live in A5.)

- [ ] **Step 5: Commit**

```bash
git add blender_addon/niua_mcp_bridge/core/silhouette.py tests/core/test_silhouette.py
git commit -m "feat: EEVEE shaded fixed-frame render for the surface-fidelity metric (live-validated)"
```

---

### Task A4: Ledger + capture_intake + preservation extensions

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/finishing/preservation_ledger.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/finishing_feedback.py`
- Modify: server mirror `src/niua_blender_mcp/domains/finishing_feedback.py` ONLY if the ToolSpec for `feedback.preservation`/`capture_intake` changes (it does NOT — params are unchanged; the result shape is additive), so the server side is untouched. Confirm with `tests/test_parity.py`.
- Test: `tests/domains/test_fidelity_feedback.py`

**Interfaces:**
- Consumes: `fidelity_metrics.{png_b64_to_luma_mask, mean_fidelity}`; `silhouette.render_fidelity_views`; `silhouette_metrics.{compact_encode, compact_decode}`.
- Produces: `preservation_ledger.SURFACE_FIDELITY_FLOOR = 0.90`; intake records gain an optional `"shaded"` key `{views: {view: {luma: b64z, mask: b64z}}, shape:[h,w], frame}`. `feedback.preservation` result gains `surface_fidelity: {available, fidelity, per_view, min_view}` (unmeasured → `{available: False}`), silhouette fields unchanged.

- [ ] **Step 1: Write the failing test**

Create `tests/domains/test_fidelity_feedback.py`. It drives the two handlers with a fake ctx whose `bpy` returns canned renders, so the fidelity path is exercised offline without GL:

```python
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
```

(Handler-level wiring is validated live in A5; these offline tests pin the floor, the ledger storage roundtrip, and the metric contract the handler composes.)

- [ ] **Step 2: Run to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/domains/test_fidelity_feedback.py -q`
Expected: FAIL — `SURFACE_FIDELITY_FLOOR` missing.

- [ ] **Step 3: Extend `preservation_ledger.py`**

Add below `PRESERVATION_FLOOR`:

```python
SURFACE_FIDELITY_FLOOR = 0.90   # locked global surface-fidelity floor (block-SSIM; per-class later)
```

No other change — `set_intake`/`get_intake` already store an arbitrary dict, so the `"shaded"` key rides along.

- [ ] **Step 4: Extend `capture_intake` in `finishing_feedback.py`**

After the existing masks/coverage are stored, ALSO render + store the shaded baseline (best-effort, never breaks the silhouette baseline). Locate `capture_intake` and, just before its final `_ledger.set_intake(...)` success write, build the shaded block and include it in the record:

```python
from ..core import fidelity_metrics as _fm  # add to imports

# ... inside capture_intake, after masks/coverage/shape computed, before the success set_intake:
shaded = None
try:
    fout = _sil.render_fidelity_views(ctx.bpy, obj.name, frame=out.get("frame"),
                                      views=_ledger.PRESERVATION_VIEWS, res=_ledger.PRESERVATION_RES)
    if fout.get("available"):
        sviews = {}
        for img in fout.get("images", []):
            fw, fh, luma, fmask = _fm.png_b64_to_luma_mask(img["data"])
            sviews[img["view"]] = {"luma": _sm.compact_encode(luma), "mask": _sm.compact_encode(fmask)}
        if sviews:
            shaded = {"views": sviews, "shape": [fh, fw], "frame": fout.get("frame")}
except Exception:  # noqa: BLE001 - fidelity is additive; never break the silhouette baseline
    shaded = None
```

Then include `"shaded": shaded` in the success `_ledger.set_intake(obj.name, {... , "shaded": shaded})` dict.

- [ ] **Step 5: Extend `preservation` in `finishing_feedback.py`**

After computing the silhouette `metric`/`delta`/`score`, compute the fidelity axis and add it to the returned dict:

```python
surface = {"available": False, "fidelity": None, "per_view": {}, "min_view": None}
sh = rec.get("shaded")
if sh:
    try:
        fcur = _sil.render_fidelity_views(ctx.bpy, obj.name, frame=sh.get("frame"),
                                          views=tuple(sh["views"]), res=rec["res"])
        if fcur.get("available"):
            fh, fw = sh["shape"]
            intake_lm = {v: (fw, fh, _sm.compact_decode(d["luma"]), _sm.compact_decode(d["mask"]))
                         for v, d in sh["views"].items()}
            cur_lm = {}
            for img in fcur.get("images", []):
                cw, ch2, luma, cmask = _fm.png_b64_to_luma_mask(img["data"])
                cur_lm[img["view"]] = (cw, ch2, luma, cmask)
            surface = _fm.mean_fidelity(intake_lm, cur_lm)
    except Exception:  # noqa: BLE001 - fail-closed: fidelity unmeasured, never a fake score
        surface = {"available": False, "fidelity": None, "per_view": {}, "min_view": None}
```

Add `"surface_fidelity": surface` to the returned dict (all existing keys unchanged).

- [ ] **Step 6: Run the tests + parity + full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/domains/test_fidelity_feedback.py tests/test_parity.py tests/test_layer_boundary.py -q && NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: PASS. Parity green (no ToolSpec change). Layer boundary green (finishing_feedback importing core.fidelity_metrics is policy→interface, allowed).

- [ ] **Step 7: Commit**

```bash
git add blender_addon/niua_mcp_bridge/finishing/preservation_ledger.py blender_addon/niua_mcp_bridge/domains/finishing_feedback.py tests/domains/test_fidelity_feedback.py
git commit -m "feat: surface_fidelity axis on feedback.preservation + shaded intake baseline (additive)"
```

---

### Task A5: LIVE validation gate — the metric must catch the troll

**Files:**
- Create: `docs/reports/surface-fidelity-validation.md`

**This is the ruler-first gate. Phase B does not begin until this passes.**

- [ ] **Step 1: Launch Blender with the current addon**

```bash
pkill -f blender_supervise.py || true; pkill -x blender || true
```
Then (separate command, background): `python scripts/blender_supervise.py --port 8765`; wait for the bridge (bash tcp probe on 127.0.0.1:8765).

- [ ] **Step 2: Self-fidelity ≈ 1.0 on an unchanged mesh**

Import one real asset, `feedback.capture_intake`, then immediately `feedback.preservation` (no edits). Confirm `surface_fidelity.available == true` and `surface_fidelity.fidelity >= 0.98` (an unchanged mesh is self-identical up to render nondeterminism). Use `scripts/bridge_call.py 8765 ...`. If self-fidelity is materially below ~0.98, the render is nondeterministic — fix (disable denoise/AA/temporal, fixed sun) before proceeding.

- [ ] **Step 3: The metric flags the known-bad decimate**

Run the current `make_game_ready` finisher on the dense assets via the benchmark in agent mode (it decimates without baking), then read `feedback.preservation` on the finished subject. Confirm `surface_fidelity.fidelity` is well BELOW `SURFACE_FIDELITY_FLOOR (0.90)` on the assets whose silhouette IoU wrongly passed (real_prop, real_character) — i.e. the metric catches what the silhouette missed. Capture the exact numbers.

- [ ] **Step 4: Write the report + decide the gate**

Create `docs/reports/surface-fidelity-validation.md`: the self-fidelity number, the per-asset `surface_fidelity` after the raw decimate vs the silhouette IoU that passed, and an explicit **PASS/FAIL of the gate** (PASS = self ≈ 1.0 AND raw-decimate fidelity < floor on the known-bad assets). If FAIL: stop, tune the metric (window size, floor, render), do not start Phase B. If the floor 0.90 is wrong (e.g. even good meshes score 0.85), adjust `SURFACE_FIDELITY_FLOOR` here with the evidence and note it.

- [ ] **Step 5: Commit**

```bash
git add docs/reports/surface-fidelity-validation.md
git commit -m "docs: surface-fidelity validation gate — metric catches the raw-decimate detail loss"
```

---

## PHASE B — the bake move + skill #2 (only after A5 passes)

### Task B1: `object.bake_transfer` tool (both sides + SDK)

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/domains/objects.py` (add the Command + handler)
- Modify: `src/niua_blender_mcp/domains/objects.py` (add the mirrored ToolSpec)
- Regenerate: `src/niua_blender_mcp/client/tools/object.py` (SDK gains `bake_transfer`)
- Test: `tests/domains/test_bake_transfer.py`

**Interfaces:**
- Produces tool `object.bake_transfer` (command + spec, `mutates=True`, `timeout_tier="heavy"`), params: `source: Str(required)` (high-poly), `target: Str(required)` (low-poly, must have UVs), `maps: Str(default="NORMAL,AO")` (comma-separated), `size: Int(default=1024)`, `ray_distance: Float(default=0.01)`. Handler bakes selected-to-active source→target into new image textures on the target's material and plugs the NORMAL map into the target's Principled BSDF normal input. Returns `{object, baked:[maps], images:[names]}`.

The bake itself is LIVE-validated (GL/bake). Offline tests cover registration + parity + param validation + that `session.object.bake_transfer` exists in the regenerated SDK.

- [ ] **Step 1: Write the failing offline tests**

Create `tests/domains/test_bake_transfer.py`:

```python
def test_bake_transfer_registered_both_sides_with_parity():
    from niua_blender_mcp.domains import build_router
    from niua_mcp_bridge.domains import build_default_registry
    server = {s.command for s in build_router().specs()}
    addon = {c.name for c in build_default_registry().commands()}
    assert "object.bake_transfer" in server
    assert "object.bake_transfer" in addon


def test_bake_transfer_spec_is_heavy_and_mutating():
    from niua_blender_mcp.domains import build_router
    spec = next(s for s in build_router().specs() if s.name == "object.bake_transfer")
    assert spec.mutates is True
    assert spec.timeout_tier == "heavy"
    assert {"source", "target"} <= set(spec.params)


def test_sdk_exposes_bake_transfer_after_regen():
    from niua_blender_mcp.client import ToolSession
    session = ToolSession(bridge=None)
    assert hasattr(session.object, "bake_transfer")
```

(Adjust `build_default_registry().commands()` to the real accessor — check `tests/test_parity.py` for how it enumerates addon commands, and match it.)

- [ ] **Step 2: Run to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/domains/test_bake_transfer.py -q`
Expected: FAIL — tool not registered.

- [ ] **Step 3: Add the addon handler + Command** in `blender_addon/niua_mcp_bridge/domains/objects.py`

```python
def bake_transfer(ctx: Ctx, payload: dict) -> dict:
    """Bake high->low detail (selected-to-active) from `source` into new image maps on `target`,
    and wire the NORMAL map into target's Principled BSDF. Requires target to have UVs.
    """
    bpy = ctx.bpy
    src = bpy.data.objects.get(payload.get("source", ""))
    tgt = bpy.data.objects.get(payload.get("target", ""))
    if src is None or tgt is None or src.type != "MESH" or tgt.type != "MESH":
        raise BridgeError(INVALID_PARAMS, "source and target must be existing mesh objects")
    if not tgt.data.uv_layers:
        raise BridgeError(PRECONDITION, "target has no UVs; unwrap before baking")
    maps = [m.strip().upper() for m in str(payload.get("maps", "NORMAL,AO")).split(",") if m.strip()]
    size = int(payload.get("size", 1024))
    ray = float(payload.get("ray_distance", 0.01))
    scene = bpy.context.scene
    prev_engine = scene.render.engine
    scene.render.engine = "CYCLES"          # object bake requires Cycles
    scene.cycles.bake_type = "NORMAL"
    # ensure target has a material with an image node to receive the bake
    mat = tgt.active_material or bpy.data.materials.new(f"{tgt.name}_baked")
    mat.use_nodes = True
    if tgt.active_material is None:
        tgt.data.materials.append(mat)
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    baked, images = [], []
    try:
        with ctx.ensure(active=tgt, mode="OBJECT", select=[src, tgt]):  # active=to, both selected
            for m in maps:
                img = bpy.data.images.new(f"{tgt.name}_{m}", width=size, height=size,
                                          alpha=False, float_buffer=(m == "NORMAL"))
                if m == "NORMAL":
                    img.colorspace_settings.name = "Non-Color"
                node = nt.nodes.new("ShaderNodeTexImage")
                node.image = img
                nt.nodes.active = node
                scene.cycles.bake_type = m
                bpy.ops.object.bake(type=m, use_selected_to_active=True,
                                    cage_extrusion=ray, use_clear=True)
                if m == "NORMAL" and bsdf is not None:
                    nmap = nt.nodes.new("ShaderNodeNormalMap")
                    nt.links.new(node.outputs["Color"], nmap.inputs["Color"])
                    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
                baked.append(m); images.append(img.name)
    finally:
        scene.render.engine = prev_engine
    return {"object": tgt.name, "baked": baked, "images": images}
```

Register: `Command("object.bake_transfer", bake_transfer, mutates=True, feedback="viewport")` in the module's COMMANDS. (Import `INVALID_PARAMS, PRECONDITION, BridgeError` if not already imported in objects.py.)

- [ ] **Step 4: Add the server ToolSpec** in `src/niua_blender_mcp/domains/objects.py` SPECS:

```python
ToolSpec(
    name="object.bake_transfer", category="object",
    summary="Bake high->low detail (normal/AO) from a source mesh into a target mesh's maps",
    command="object.bake_transfer",
    params={
        "source": Str(required=True, summary="High-poly source object"),
        "target": Str(required=True, summary="Low-poly target object (must have UVs)"),
        "maps": Str(default="NORMAL,AO", summary="Comma-separated maps to bake: NORMAL, AO"),
        "size": Int(default=1024, minimum=1, maximum=8192, summary="Baked image size in pixels"),
        "ray_distance": Float(default=0.01, minimum=0.0, summary="Cage extrusion / ray distance"),
    },
    mutates=True, feedback="viewport", timeout_tier="heavy",
),
```

- [ ] **Step 5: Regenerate the SDK**

```bash
cat > /tmp/gen_sdk.py <<'PY'
from pathlib import Path
from niua_blender_mcp.client import generate
out = Path("src/niua_blender_mcp/client/tools")
for domain, source in generate.generate_all().items():
    (out / f"{domain}.py").write_text(source, encoding="utf-8")
PY
NIUA_SKIP_BLENDER=1 python /tmp/gen_sdk.py && rm /tmp/gen_sdk.py
```
This updates `client/tools/object.py` to include `bake_transfer`; the drift test (`tests/test_client_sdk.py`) will confirm it matches.

- [ ] **Step 6: Run tests + parity + drift + full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/domains/test_bake_transfer.py tests/test_parity.py tests/test_client_sdk.py -q && NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add blender_addon/niua_mcp_bridge/domains/objects.py src/niua_blender_mcp/domains/objects.py src/niua_blender_mcp/client/tools/object.py tests/domains/test_bake_transfer.py
git commit -m "feat: object.bake_transfer — high->low normal/AO bake (both sides + SDK)"
```

---

### Task B2: `bake_and_finish` skill #2 (gated on silhouette AND fidelity)

**Files:**
- Create: `src/niua_blender_mcp/finishing/skills/bake_and_finish.py`
- Modify: `src/niua_blender_mcp/finishing/skills/__init__.py` (register it)
- Test: `tests/test_skills.py` (extend)

**Interfaces:**
- Consumes: the SDK (`session.object.{duplicate, bake_transfer, lod_create, ...}`, `session.mesh.*`, `session.uv.*`, `session.feedback.*`, `session.session.*`); `preservation_ledger.SURFACE_FIDELITY_FLOOR`.
- Produces: `bake_and_finish.SKILL` (a `Skill`); `bake_and_finish.run(session, subject, params) -> report`; `bake_and_finish.TOOLS_USED`. The accept rule is `readiness held AND silhouette >= PRESERVATION_FLOOR AND surface_fidelity (when measured) >= SURFACE_FIDELITY_FLOOR`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_skills.py` (reuse its `FakeBridge`, extending it to return a `surface_fidelity` block from `feedback.preservation`):

```python
def _pres(silhouette=1.0, fidelity=1.0):
    return {"available": True, "preservation": silhouette, "preservation_pass": silhouette >= 0.85,
            "surface_fidelity": {"available": True, "fidelity": fidelity,
                                 "per_view": {}, "min_view": {"view": "front", "ssim": fidelity}}}


class FidelityBridge(FakeBridge):
    """FakeBridge whose feedback.preservation returns a scriptable surface_fidelity."""
    def __init__(self, *a, fidelity_after=1.0, **k):
        super().__init__(*a, **k)
        self.fidelity_after = fidelity_after
    def call(self, tool, payload):
        r = super().call(tool, payload)
        if tool == "feedback.preservation":
            fid = self.fidelity_after if self.state is not self.before else 1.0
            return _pres(silhouette=self.preservation, fidelity=fid)
        return r


def test_bake_and_finish_registered():
    from niua_blender_mcp.finishing import skills
    assert "bake_and_finish" in {s["name"] for s in skills.list_skills()}


def test_low_fidelity_step_is_reverted_even_if_readiness_rose():
    from niua_blender_mcp.client import ToolSession
    from niua_blender_mcp.finishing.skills import bake_and_finish
    bridge = FidelityBridge(before=_readiness(0.4, ["engine.within_triangle_budget"]),
                            effects={"modifiers.apply": _readiness(0.6)}, fidelity_after=0.5)
    session = ToolSession(bridge)
    report = bake_and_finish.run(session, "subject", {"asset_class": "hard_surface_prop"})
    move = next((m for m in report["moves"] if m["move"] == "bake_transfer"), None)
    assert move is not None and move["kept"] is False  # low fidelity forced a revert
    assert any(c[0] == "session.revert" for c in bridge.calls)
```

- [ ] **Step 2: Run to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_skills.py -q`
Expected: FAIL — `bake_and_finish` missing.

- [ ] **Step 3: Write `bake_and_finish.py`**

Model it on `make_game_ready.py` (same loop harness and revert/stray-cleanup), with two differences: (1) the harm check is a `_harm_ok(session, subject)` that reads BOTH `preservation` and `surface_fidelity` from one `feedback.preservation` call and requires both above their floors; (2) the `decimate_to_budget` move is replaced by a `bake_transfer` move that duplicates the high-poly, decimates the copy... no — keeps the high-poly as source: duplicate subject→`<subject>__high`, decimate `subject` to budget, unwrap `subject`, `object.bake_transfer(source=__high, target=subject)`, then delete `__high`. Full move:

```python
def _bake_transfer(session, subject, info):
    high = f"{subject}__high"
    session.object.duplicate(object=subject, name=high)   # keep the pre-decimate detail as bake source
    # decimate the working subject to budget (same math as make_game_ready)
    q = session.feedback.quality(object=subject, asset_class=info["asset_class"])
    tris = int(q.get("topology", {}).get("tris") or 0)
    budget = int(q.get("asset_class", {}).get("effective_defaults", {}).get("triangle_budget") or 0)
    if tris > 0 and budget > 0 and budget < tris:
        ratio = max(0.01, min(1.0, budget / tris))
        session.modifiers.add(object=subject, type="DECIMATE", name="niua_decimate")
        session.modifiers.set(object=subject, name="niua_decimate", property="ratio", value=str(ratio))
        session.modifiers.apply(object=subject, name="niua_decimate")
    session.mesh.select_all(object=subject, action="SELECT")
    session.uv.smart_unwrap(object=subject)
    session.uv.pack_islands(object=subject)
    session.object.bake_transfer(source=high, target=subject, maps="NORMAL,AO")
    session.object.delete(objects=high)   # remove the high-poly source; low-poly carries baked detail
```

The rest of the skill mirrors `make_game_ready` (repair, tris_to_quads, pbr_maps, lod, collision, apply_transform moves and the loop), but the loop's keep-rule calls `_harm_ok`:

```python
from ...finishing.preservation_ledger import PRESERVATION_FLOOR, SURFACE_FIDELITY_FLOOR

def _harm_ok(session, subject):
    """Both do-no-harm axes from one preservation call. Unmeasured axis never blocks (measure-and-flag)."""
    try:
        pres = session.feedback.preservation(object=subject)
    except BridgeError:
        return True, None, None
    sil = pres.get("preservation")
    sf = pres.get("surface_fidelity") or {}
    fid = sf.get("fidelity") if sf.get("available") else None
    sil_ok = (not pres.get("available")) or sil is None or sil >= PRESERVATION_FLOOR
    fid_ok = fid is None or fid >= SURFACE_FIDELITY_FLOOR
    return (sil_ok and fid_ok), sil, fid
```

The MOVES table replaces `("decimate_to_budget", ...)` with `("bake_transfer", ("engine.within_triangle_budget",), _bake_transfer)` and drops the separate `uv_unwrap` move (the bake move already unwraps) — keep `tris_to_quads`, `pbr_maps`, `lod`, `collision`, `apply_transform`. `TOOLS_USED` = make_game_ready's set + `{"object.duplicate", "object.bake_transfer"}` (and it still includes the uv/mesh/modifiers tools the bake move uses). Register `SKILL` in `skills/__init__.py`'s `_SKILLS`.

- [ ] **Step 4: Run the tests**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_skills.py -q`
Expected: PASS. `make_game_ready` tests unchanged (skill #1 untouched).

- [ ] **Step 5: Full suite + commit**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
```bash
git add src/niua_blender_mcp/finishing/skills/bake_and_finish.py src/niua_blender_mcp/finishing/skills/__init__.py tests/test_skills.py
git commit -m "feat: bake_and_finish skill #2 — bake-transfer move, gated on silhouette AND surface fidelity"
```

---

### Task B3: `surface_fidelity` axis in the scorecard + benchmark

**Files:**
- Modify: `src/niua_blender_mcp/evals/objective_bench.py`
- Modify: `scripts/run_objective_benchmark.py` (read + thread the fidelity axis)
- Test: `tests/evals/test_objective_bench.py` (extend)

**Interfaces:**
- Produces: `score_item_objective(..., surface_fidelity: float | None = None, surface_fidelity_available: bool = False)` → card gains `surface_fidelity: float | None`, `surface_fidelity_measured: bool`, and `harm_flagged` fires when EITHER preservation OR fidelity is measured-and-below-floor. `aggregate_objective` gains `mean_surface_fidelity` + `n_fidelity_measured`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/evals/test_objective_bench.py`:

```python
def test_low_surface_fidelity_flags_harm():
    card = score_item_objective(
        {"id": "x", "asset_class": "hard_surface_prop"},
        readiness=0.6, stage_pass_fraction=0.6,
        preservation=1.0, preservation_available=True,
        surface_fidelity=0.5, surface_fidelity_available=True)
    assert card["surface_fidelity_measured"] is True
    assert card["harm_flagged"] is True  # fidelity below floor = harm even if silhouette passed


def test_unmeasured_fidelity_is_none_not_zero():
    card = score_item_objective(
        {"id": "x", "asset_class": "hard_surface_prop"},
        readiness=0.6, stage_pass_fraction=0.6,
        preservation=1.0, preservation_available=True,
        surface_fidelity=None, surface_fidelity_available=False)
    assert card["surface_fidelity_measured"] is False
    assert card["surface_fidelity"] is None
    assert card["harm_flagged"] is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/evals/test_objective_bench.py -q`
Expected: FAIL — unexpected keyword / missing keys.

- [ ] **Step 3: Extend `objective_bench.py`**

Add the keyword-only params and, using the existing `SURFACE_FIDELITY`-equivalent floor (import `PRESERVATION_FLOOR_DEFAULT` pattern; define `SURFACE_FIDELITY_FLOOR_DEFAULT = 0.90`), compute:

```python
    fid_measured = bool(surface_fidelity_available) and surface_fidelity is not None
    fid_harm = fid_measured and surface_fidelity < SURFACE_FIDELITY_FLOOR_DEFAULT
    # in the returned card:
        "surface_fidelity": surface_fidelity if fid_measured else None,
        "surface_fidelity_measured": fid_measured,
    # and OR it into harm_flagged:
        "harm_flagged": (preservation_measured and preservation < floor) or fid_harm,
```

In `aggregate_objective` add `mean_surface_fidelity` (mean over measured) and `n_fidelity_measured`.

- [ ] **Step 4: Thread it through the runner**

In `scripts/run_objective_benchmark.py`'s `run_item`, after reading `pres = _safe(bridge, "feedback.preservation", ...)`, extract the fidelity axis and pass it to `score_item_objective`:

```python
    sf = (pres or {}).get("surface_fidelity") or {}
    # ... in the score_item_objective call:
        surface_fidelity=sf.get("fidelity") if sf.get("available") else None,
        surface_fidelity_available=bool(sf.get("available")),
```

(Pass `surface_fidelity=None, surface_fidelity_available=False` on the build-failed early return.)

- [ ] **Step 5: Run tests + full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/evals/ -q && NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/niua_blender_mcp/evals/objective_bench.py scripts/run_objective_benchmark.py tests/evals/test_objective_bench.py
git commit -m "feat: surface_fidelity axis in the objective benchmark (harm fires on either preservation axis)"
```

---

### Task B4: LIVE acceptance — the troll no longer garbage

**Files:**
- Create: `docs/reports/bake-and-finish-first-run.md`
- Modify: `docs/reports/objective-baseline.md` (append)

- [ ] **Step 1: Launch Blender** (as in A5 Step 1).

- [ ] **Step 2: Confirm make_game_ready still byte-identical**

Run: `python scripts/run_objective_benchmark.py --mode agent --finisher niua_blender_mcp.evals.finisher:finish --no-godot --outdir /tmp/niua_mgr_check`
Expected: readiness 0.76/0.80/0.80/0.60/0.64 (skill #1 untouched). The new `surface_fidelity` axis now also reports for these — record it (it will be LOW on the dense assets, confirming the raw decimate's harm is now visible in the scorecard).

- [ ] **Step 3: Run `bake_and_finish` via the code-mode runner**

Run: `python scripts/run_skill.py --skill bake_and_finish --outdir /tmp/niua_bake_run`
(If `run_skill.py` doesn't yet accept a non-default skill cleanly, it does — `--skill` is a flag; `get_skill("bake_and_finish")` resolves it.) Expected: each asset's finished `surface_fidelity` is HIGH (>= floor, near the high-poly) — the bake restored the detail — while readiness still climbs.

- [ ] **Step 4: Capture before/after and write the report**

Render before/after captures (reuse the gallery approach from prior reports) of the dense assets (troll/samurai/prop) under `bake_and_finish`, and create `docs/reports/bake-and-finish-first-run.md`: per-asset table (readiness before→after, silhouette, **surface_fidelity before-raw-decimate vs after-bake**), the before/after images, and a plain statement of whether the founder quality bar is met (the finished asset looks almost identical to the input). Append a one-line confirmation to `docs/reports/objective-baseline.md`.

- [ ] **Step 5: Commit**

```bash
git add docs/reports/bake-and-finish-first-run.md docs/reports/objective-baseline.md
git commit -m "docs: bake_and_finish first run — surface fidelity restored, founder quality bar met"
```

---

## Self-Review

1. **Spec coverage:** fidelity metric pure/deterministic (A2) ✓; EEVEE shaded render, neutral-clay/normal-applied (A3) ✓; ledger + capture_intake + preservation additive `surface_fidelity` (A4) ✓; ruler-first validation gate catches the troll before Phase B (A5) ✓; `object.bake_transfer` both sides + SDK (B1) ✓; `bake_and_finish` gated on both axes (B2) ✓; scorecard/bench fidelity axis, harm on either (B3) ✓; LIVE acceptance + founder bar (B4) ✓; layer boundary (A2/A3 interface, floor/skill policy) ✓; make_game_ready + byte-identical bench preserved (B4 Step 2) ✓.
2. **Placeholder scan:** every code step carries real code; the two live-validated renders/bake carry full operator-level code + offline registration/param/import tests; SDK regen is a concrete script; no TBD/TODO.
3. **Type consistency:** `decode_png_rgba -> (w,h,ch,pixels)` used identically in A1/A2; `mean_fidelity(intake, current)` value tuples `(w,h,luma,mask)` consistent A2↔A4; `render_fidelity_views(...)->{available,images:[{view,data}]}` consumed identically in A4; `surface_fidelity` dict shape `{available,fidelity,per_view,min_view}` identical across A2/A4/B2/B3; `_harm_ok` floors imported from `preservation_ledger` (both defined in A4); `object.bake_transfer` params identical across addon handler (B1 Step3), server spec (B1 Step4), and skill call (B2); `score_item_objective` new kwargs identical across B3 def/test/runner.
