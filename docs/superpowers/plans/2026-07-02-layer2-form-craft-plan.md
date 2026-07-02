# Layer 2 — Form-Craft Wave Implementation Plan (red-team-hardened)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise the pipeline's weakest axis — **FORM** (silhouette 3.79 / proportion 3.86 / design 3.86,
all below topology 4.21 at the altimeter baseline) — by giving the agent (a) a reusable, **structured
form self-critique** eye (`feedback.form_critique`) grounded in per-subject **target+tolerance** reference
proportions, (b) a **blockout-first stage** whose objective gate is a **degenerate guard** (real
mesh-fill floor + extreme-aspect guard) plus an **enforced, recorded observation** (the agent must have
*looked* via `feedback.form_critique` before advancing), and (c) **form-craft verbs/workflows**
(proportion adjust, silhouette-aware refine, checkpoint-safe reblock) recommended by
`craft_workflow.recommend`. Believable form is **agent-carried and measured by the altimeter's
silhouette/proportion/design lenses** — it is NOT hard-gated. Success is measured live by re-running the
altimeter and comparing **per-lens deltas** against a recorded baseline.

**This plan supersedes the first (flawed) plan.** The design's `## 9. Revision — red-team-driven
corrections` is binding and overrides the conflicting parts of design §3/§6. An adversarial 6-lens review
found a design-level flaw (a bounding-box gate cannot capture "believable form"): `boxiness =
bbox_volume/longest³` is pure bbox cubeness (a spindly cross, a hollow shell, and a solid cube all ≈1.0),
so the old gate was blind to the bad-form cases it targeted *and* wrongly blocked a legitimate elongated
input (`hard_surface_bracket`, aspect 6.29). Every CRITICAL [1..10] and IMPORTANT [1..20] finding is
resolved; see the **Red-team resolution ledger** at the end.

**Architecture:** Three TDD sub-waves that preserve the repo's dual-surface contract at every step —
every server `ToolSpec` in `src/niua_blender_mcp/domains/<d>.py` (`SPECS`) is mirrored by an add-on
`Command` in `blender_addon/niua_mcp_bridge/domains/<d>.py` (`COMMANDS`), and `tests/test_parity.py`
enforces name + `mutates`/`feedback` parity. Data registries (`_PROFILES`, `_PACKS`, `_WORKFLOWS`,
`_GATES`) are duplicated server↔add-on and kept identical by **dedicated equality tests** (now including
`_GATES`). The new `blockout` stage's objective gate is a **degenerate guard only** — `form.fill_ratio_ok`
(real solid-volume fill ≥ a low collapse floor, degrades-to-pass when unmeasurable) and
`form.aspect_within_degenerate_guard` (aspect ≤ ~20). The believable-proportion read is **not gated**: it
is enforced only as a *recorded* `feedback.form_critique` observation (a state flag proving the agent
looked) and judged by the altimeter lenses.

**Tech Stack:** Python 3.14, pytest, fake-bpy unit tests (offline) + a real-Blender `--background`
headless smoke; GL renders degrade to `available: false` headless. `fill_ratio` is computed in **pure
Python** from `mesh.polygons`+`mesh.vertices` (signed-tetrahedra / divergence theorem) so it is
fully fake-bpy testable and needs no `bmesh`. The Workflow tool (`.mjs`) drives the live judged altimeter
re-measure against a **visible** Blender bridge.

## Global Constraints

- **Standalone Blender-MCP — ZERO niua/Godot references in code.** All new tools, packs, verbs,
  workflows, and reference targets are generic Blender/game-asset craft.
- `from __future__ import annotations` at the top of every new/edited `.py`.
- **Parity is law.** Every new server `ToolSpec` gets a mirrored add-on `Command` in the same-named
  domain module, with matching `mutates`/`feedback`. Run `pytest tests/test_parity.py -q` green before
  every commit that adds/removes a tool.
- **`bpy` only via `ctx.bpy`** inside add-on handlers; never import `bpy` at module top. Pure framing
  math / metric helpers (`_proportion`, `_symmetry`, `_form`, `_solid_volume`) stay bpy-free and
  fake-bpy-testable.
- **Mutating verbs push exactly one undo after success** — automatic in `dispatch_on_main`
  (`dispatch.py:62-74`) when `Command(..., mutates=True)`; handlers must not push undo themselves.
  `dispatch_on_main` raises *before* the undo push on any handler exception, so a failed verb pushes NO
  undo. **`ctx.ensure.__exit__` restores mode/selection/active but NEVER mesh data and never swallows the
  exception** (`core/context.py:148-164`) — therefore any multi-op destructive verb that must be
  recoverable manages its OWN mesh transaction via `session_store` (see `model.reblock_form`).
- **Read-only feedback tools set `mutates=False` and restore all state.** `feedback.form_critique`
  composes only read-only sub-calls (`core.silhouette.render_silhouette` swaps in a fill material and
  restores the originals in a `finally`; `_proportion`/`_symmetry`/`_form` are pure) and mutates no mesh.
  It DOES record a lightweight pipeline **metadata** flag (the "agent looked" observation) — that is
  pipeline state, not mesh geometry, needs no undo, and mirrors how `pipeline.gate_check` (also
  `mutates=False`) records gate results.
- **Server↔add-on data registries stay byte-identical**, asserted by dedicated equality tests:
  `_PROFILES` (`test_form_targets_registry_matches...`), `_PACKS` (`test_server_and_addon_packs_identical`),
  `_WORKFLOWS` (`test_server_and_addon_craft_workflow_registries_match`), and **NEW** `_GATES`
  (`test_server_and_addon_gate_profiles_identical`).
- **The objective gate is a degenerate floor, not a taste gate.** It must NOT block any of the 7 benchmark
  items at intake (a test asserts each item's intake bbox clears its class degenerate guard). Believable
  proportion is agent-carried (enforced observation) and judge-measured, never machine-gated.
- TDD: write the failing test, watch it fail, implement minimally, watch it pass, commit.
- Run `pytest -q` green before each commit that touches a shared module.

---

## File Structure

**Create:** (none — every change extends an existing module or test file, except one tiny new test file
`tests/evals/test_altimeter_wiring.py` in Task C3.)

**Modify — server (`src/niua_blender_mcp/`):**
- `asset_classes.py` — replace/extend `form_targets` on all 4 `_PROFILES` with **target+tolerance +
  degenerate-guard params**; add `form_targets_for_class()`.
- `domains/feedback.py` — add `feedback.form_critique` `ToolSpec` (default `preset=ortho3`; optional
  per-subject `target_aspect`/`aspect_tolerance`).
- `domains/modeling_verbs.py` — add `model.proportion_adjust`, `model.silhouette_refine`,
  `model.reblock_form` `ToolSpec`s.
- `knowledge/__init__.py` — add the `blockout` pack to `_PACKS`.
- `craft_workflows.py` — add 4 form-craft workflow records to `_WORKFLOWS`.
- `evals/stage_gates.py` — add the `blockout` gate profile to `_GATES`.
- `evals/benchmark/items/*/item.json` — insert `"blockout"` into each item's `stages` (7 files).
- `evals/scorecard.py` — `aggregate()` gains a `per_lens_means` field (surfaces the per-lens mean it
  already computes internally to pick `weakest_lens`, so the FINAL exit gate has a real data source).

**Modify — add-on (`blender_addon/niua_mcp_bridge/`):**
- `core/asset_classes.py` — mirror `form_targets` + `form_targets_for_class()`.
- `core/capture.py` — add an `ortho3` preset (`["front", "right", "top"]`) to `PRESETS`.
- `domains/feedback.py` — add `_solid_volume()` + `_form()` helpers, extend `quality()` with a `form`
  block, add the `form_critique()` handler (records the observation) + `Command`.
- `domains/modeling_verbs.py` — add the 3 verb handlers + `Command`s (reblock is a self-managed
  `session_store` transaction; refine is feature-angle-aware; proportion is non-uniform resize).
- `core/knowledge.py` — mirror the `blockout` pack.
- `core/craft_workflows.py` — mirror the 4 workflow records.
- `core/pipeline.py` — insert the `blockout` stage into `_STAGES` (after `repair`, before `retopo`) + the
  `blockout` profile in `_GATES`; add `observations` to the run state + `record_observation()`; enforce
  the recorded observation when advancing OUT of `blockout`.

**Modify — workflow + tests:**
- `workflows/altimeter.mjs` — finish prompt OBSERVES form via `feedback.form_critique` at `blockout` and
  iterates before advancing; returns a per-item `form_critique_calls` count (instrumentation), which
  Stage-2 assemble must copy from `fin` into the raw card or it never reaches `raw_cards.json`/the report.
- `tests/core/test_pipeline_core.py` — stage registry + gate-profile map + bake/material flow +
  blockout-order + **enforced-observation** + `_GATES` server↔addon equality.
- `tests/core/test_knowledge.py`, `tests/domains/test_knowledge.py` — `list_packs()` includes `blockout`.
- `tests/test_smoke_headless.py` — thread `repair → blockout → (form_critique) → retopo` through **ALL
  FIVE** real-Blender walks + live reblock recoverability.
- `tests/evals/test_benchmark.py` — items carry `blockout`; **all 7 intake bboxes clear the degenerate
  guard**.
- `tests/domains/test_pipeline.py` — offline `gate_check(stage="blockout")` **pass AND reject**.
- `tests/test_craft_workflows.py`, `tests/domains/test_craft_workflow.py` — new ids + from-scratch
  fallback + **repair-order lock** for `generated_cleanup`.
- new assertion blocks in `tests/domains/test_quality.py`, `tests/domains/test_feedback.py`,
  `tests/domains/test_asset_class.py`, `tests/test_asset_classes.py`, `tests/domains/test_modeling_verbs.py`,
  `tests/evals/test_scorecard.py` (`per_lens_means`), and new `tests/evals/test_altimeter_wiring.py`.

**Keep untouched:** the `feedback` render engine core (`core/capture.py` except the additive `ortho3`
preset, `core/silhouette.py`), `dispatch.py`, the objective gate evaluator
(`evals/gates.py::check_gates`), and every existing tool's behavior.

---
---

# SUB-WAVE A — Form perception + grounding (`W-form-a`)

*Adds per-subject target+tolerance reference targets, the objective `form` metric block (real fill ratio +
degenerate guard, boxiness kept but correctly documented), the structured `feedback.form_critique` tool
(ortho-only, records the observation), and the `blockout` knowledge pack. Additive only — the pipeline
stage list is NOT touched yet, so all existing stage-order tests stay green. Parity green at every commit.*

## Task A1: Asset-class reference targets — target+tolerance + degenerate-guard params

**Resolves:** IMPORTANT [7] (wide bands mislead), design §9 decision 3b. Drops the dead aspect lower bound
and the permissive `[min,max]` believable-range bands.

**Files:**
- Modify: `src/niua_blender_mcp/asset_classes.py`
- Modify: `blender_addon/niua_mcp_bridge/core/asset_classes.py`
- Test: `tests/test_asset_classes.py`, `tests/domains/test_asset_class.py`

**Interfaces:**
- Each of the 4 `_PROFILES` gains a `"form_targets"` dict — **NOT** min/max class bands:
  `{"target_aspect": float, "aspect_tolerance": float, "fill_floor": float,
    "aspect_degenerate_max": float, "note": str}`.
  - `target_aspect` — the representative believable aspect (`longest/shortest`, always ≥ 1) for the
    class's canonical subject; the **advisory** proportion read compares measured aspect to this ± tolerance.
  - `fill_floor` — the collapse floor for the objective gate: real solid fill (`solid_volume/bbox_volume`)
    below this ⇒ degenerate. LOW by design (catches collapse, not "believable range").
  - `aspect_degenerate_max` — the extreme-aspect degenerate guard for the objective gate (≈ 20; must be
    well above every benchmark item's intake aspect so it never blocks a legitimate elongated input).
- New helper on both sides: `form_targets_for_class(name: str | None) -> dict[str, Any]` returns
  `get_asset_class(name)["form_targets"]` (deepcopy-safe via `get_asset_class`).

**v1 values (curated, target+tolerance — locked decision #4 keeps it to the 4 existing classes):**

| class | target_aspect | aspect_tolerance | fill_floor | aspect_degenerate_max | note |
|---|---|---|---|---|---|
| `hard_surface_prop` | `1.0` | `0.6` | `0.05` | `20.0` | Crates read near-cubic (~1:1:1); brackets/panels elongate. Judge believable proportion by eye against the brief. |
| `organic_prop` | `1.1` | `0.7` | `0.05` | `20.0` | Rounded masses; softer proportions, lower fill acceptable. |
| `generated_cleanup` | `1.0` | `0.9` | `0.04` | `20.0` | Unknown subject; guard degeneracy only, judge the rest. |
| `from_scratch_prop` | `1.2` | `0.6` | `0.05` | `20.0` | Authored prop (barrel ≈1:1:1.2), moderate proportions. |

Note: `target_aspect`/`aspect_tolerance` drive only the **advisory** proportion readout in
`form_critique`; `fill_floor`/`aspect_degenerate_max` drive the **objective gate**. Neither is a
believable-range advance-blocker.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_asset_classes.py
from niua_blender_mcp import asset_classes as server_asset_classes
from niua_mcp_bridge.core import asset_classes as addon_asset_classes


def test_form_targets_present_and_well_formed_for_all_classes() -> None:
    for module in (server_asset_classes, addon_asset_classes):
        for profile in module.list_asset_classes():
            ft = profile["form_targets"]
            assert ft["target_aspect"] >= 1.0            # aspect is longest/shortest; no dead lower band
            assert ft["aspect_tolerance"] > 0.0
            assert 0.0 < ft["fill_floor"] < 0.5          # a LOW collapse floor, not a believable range
            assert ft["aspect_degenerate_max"] >= 10.0   # generous guard; never blocks a real prop


def test_form_targets_registry_matches_server_and_addon() -> None:
    server = {p["id"]: p["form_targets"] for p in server_asset_classes.list_asset_classes()}
    addon = {p["id"]: p["form_targets"] for p in addon_asset_classes.list_asset_classes()}
    assert server == addon


def test_form_targets_for_class_helper_returns_targets() -> None:
    ft = addon_asset_classes.form_targets_for_class("hard_surface_prop")
    assert ft["target_aspect"] == 1.0
    assert ft["aspect_degenerate_max"] == 20.0
    # defaults to hard_surface_prop when name is missing
    assert addon_asset_classes.form_targets_for_class(None)["fill_floor"] == 0.05
```

```python
# add to tests/domains/test_asset_class.py (dispatches inline via Ctx(FakeBpy()))
def test_describe_includes_form_targets() -> None:
    ctx = Ctx(FakeBpy())
    reg = build_default_registry()
    out = dispatch_on_main(reg, "asset_class.describe", {"asset_class": "from_scratch_prop"}, ctx)
    ft = out["asset_class"]["form_targets"]
    assert ft["target_aspect"] == 1.2
    assert "aspect_degenerate_max" in ft
```
(`asset_class.describe` returns the full profile dict, so `form_targets` rides along with no
domain-handler change.)

- [ ] **Step 2: Run tests to verify they fail** — `pytest tests/test_asset_classes.py tests/domains/test_asset_class.py -q` → FAIL (`KeyError: 'form_targets'`).

- [ ] **Step 3: Add `form_targets` to both `_PROFILES`** — insert the dict from the table into EACH of the
  4 profiles in BOTH `src/niua_blender_mcp/asset_classes.py` and
  `blender_addon/niua_mcp_bridge/core/asset_classes.py`. Example for `hard_surface_prop`:

```python
        "form_targets": {
            "target_aspect": 1.0,
            "aspect_tolerance": 0.6,
            "fill_floor": 0.05,
            "aspect_degenerate_max": 20.0,
            "note": "Crates read near-cubic (~1:1:1); brackets/panels elongate. Judge believable proportion by eye against the brief.",
        },
```

- [ ] **Step 4: Add the helper to both files** (identical body):

```python
def form_targets_for_class(name: str | None) -> dict[str, Any]:
    """Reference proportion targets (target+tolerance + degenerate-guard params) for one class."""
    return get_asset_class(name)["form_targets"]
```

- [ ] **Step 5: Run tests to verify pass** — `pytest tests/test_asset_classes.py tests/domains/test_asset_class.py -q` → PASS. Then `pytest -q` (the existing server==addon registry-equality test still passes because both copies changed identically).

- [ ] **Step 6: Commit**

```bash
git add src/niua_blender_mcp/asset_classes.py blender_addon/niua_mcp_bridge/core/asset_classes.py \
  tests/test_asset_classes.py tests/domains/test_asset_class.py
git commit -m "feat: reference form targets as per-class target+tolerance + degenerate guards"
```

---

## Task A2: Objective `form` block — real fill ratio + degenerate guard (boxiness kept, documented correctly)

**Resolves:** CRITICAL [2][8][11], IMPORTANT [11], design §9 decisions 1 (objective half) & 2. Adds a
**real** solid-fill metric that discriminates a thin cross (LOW fill) from a solid cube (~1) while
boxiness stays ~1 for both; keeps `boxiness` but documents it as bbox cubeness, not fill.

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/domains/feedback.py`
- Test: `tests/domains/test_quality.py`

**Interfaces:**
- New pure helper `_solid_volume(mesh) -> float | None` — signed-tetrahedra (divergence-theorem) volume of
  the closed mesh, fan-triangulating each polygon from its first vertex; `abs()` of the sum. Returns
  `None` when the mesh has no polygons/vertices (open/point-cloud → unmeasurable). No `bmesh`, so it runs
  under fake-bpy exactly as under Blender.
- **Winding assumption (explicit dependency):** `_solid_volume` assumes the mesh has **consistent
  outward-facing** polygon winding — with mixed winding the signed-tetrahedra sum under/over-counts and
  `fill_ratio` is silently wrong (it does not raise; it returns a plausible-looking but incorrect number).
  Real pipeline meshes are safe by construction: `repair` always runs BEFORE `blockout` in the stage order
  (Sub-wave B), and `model.reblock_form`'s op sequence explicitly calls `ops.mesh.normals_make_consistent()`
  before remeshing (Task C1) — so by the time `feedback.quality`'s `form` block is evaluated at the
  `blockout` gate, winding has already been normalized upstream. Test fixtures must therefore be
  hand-wound consistently too, for the same reason (see `_CUBE_QUADS` below).
- New pure helper `_form(obj, form_targets, *, target_aspect=None, aspect_tolerance=None) -> dict`
  returning:
  ```
  {"aspect_ratio", "boxiness",              # boxiness = bbox cubeness (kept, NOT fill)
   "fill_ratio",                            # solid_volume / bbox_volume, or None
   "fill_ratio_ok": bool,                   # True when fill is None (degrade-to-pass) OR >= fill_floor
   "aspect_within_degenerate_guard": bool,  # True when aspect is None OR <= aspect_degenerate_max
   "reference": {"target_aspect", "aspect_tolerance", "aspect_delta", "proportion_ok", "note"}}  # advisory only
  ```
  `fill_ratio_ok` / `aspect_within_degenerate_guard` are the ONLY gate paths (Sub-wave B). The `reference`
  block is advisory (not gated); `target_aspect`/`aspect_tolerance` default to the class `form_targets`
  but may be overridden per-subject by `form_critique`.
- `quality()` gains a top-level `"form"` key: `_form(obj, form_targets)` where
  `form_targets = asset_classes.get_asset_class(effective_payload.get("asset_class")).get("form_targets", {})`.
  Adding a key is backward-compatible (no existing test asserts an exact key-set on `quality()`).

- [ ] **Step 1: Write the failing tests** (add closed-mesh fixtures + assertions to `tests/domains/test_quality.py`)

```python
# closed unit cube (6 quads) — solid, fills its cubic bbox.
# NOTE: every face must be wound OUTWARD for _solid_volume's signed-tetrahedra sum to equal +8 (2x2x2).
# The bottom face is [0,3,2,1] (not the more "obvious" [0,1,2,3], which is wound INWARD here and would
# make the signed volume sum to 16/3 -> fill_ratio 0.667, failing the pytest.approx(1.0, abs=0.05) below).
_CUBE_VERTS = [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
_CUBE_QUADS = [[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
# octahedron inscribed in the SAME 2x2x2 bbox — spindly, encloses little of it
_OCTA_VERTS = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
_OCTA_TRIS = [[0,2,4],[2,1,4],[1,3,4],[3,0,4],[2,0,5],[1,2,5],[3,1,5],[0,3,5]]


def test_quality_form_reports_fill_and_cubeness_distinctly(env) -> None:
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS),
                    dimensions=(2.0, 2.0, 2.0)))
    form = _quality(env, "Cube", asset_class="hard_surface_prop")["form"]
    assert form["boxiness"] == pytest.approx(1.0)         # bbox cubeness ~1
    assert form["fill_ratio"] == pytest.approx(1.0, abs=0.05)  # solid cube fills its bbox
    assert form["fill_ratio_ok"] is True
    assert form["aspect_within_degenerate_guard"] is True


def test_quality_form_fill_discriminates_spindly_from_solid(env) -> None:
    _ctx, bpy = env
    bpy.add(FakeObj("Octa", data=FakeMesh(verts=_OCTA_VERTS, polys=_OCTA_TRIS),
                    dimensions=(2.0, 2.0, 2.0)))
    form = _quality(env, "Octa", asset_class="hard_surface_prop")["form"]
    # boxiness is BLIND to fill (bbox is still cubic) ...
    assert form["boxiness"] == pytest.approx(1.0)
    # ... but fill_ratio SEES that the octahedron barely fills the box: THIS is the real signal.
    assert form["fill_ratio"] < 0.35
    assert form["fill_ratio"] < form["boxiness"]


def test_quality_form_fill_degrades_to_pass_when_unmeasurable(env) -> None:
    _ctx, bpy = env
    # open mesh (two disconnected quads) => no enclosed volume => None => never blocks
    bpy.add(FakeObj("Open", data=FakeMesh(verts=_SYMMETRIC_VERTS, polys=_SYMMETRIC_POLYS),
                    dimensions=(2.0, 2.0, 1.0)))
    form = _quality(env, "Open", asset_class="generated_cleanup")["form"]
    assert form["fill_ratio"] is None
    assert form["fill_ratio_ok"] is True


def test_quality_form_degenerate_guard_flags_extreme_aspect(env) -> None:
    _ctx, bpy = env
    bpy.add(FakeObj("Needle", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS),
                    dimensions=(40.0, 1.0, 1.0)))
    form = _quality(env, "Needle", asset_class="hard_surface_prop")["form"]
    assert form["aspect_ratio"] == pytest.approx(40.0)
    assert form["aspect_within_degenerate_guard"] is False   # 40 > aspect_degenerate_max (20)
```
(Reuse the file's `env`, `_quality`, `FakeObj`, `FakeMesh`, `_SYMMETRIC_VERTS`, `_SYMMETRIC_POLYS`. The
`env` fixture deletes `bmesh` from `sys.modules`, confirming the pure-Python fill path is what runs.)

- [ ] **Step 2: Run tests to verify they fail** — `pytest tests/domains/test_quality.py -k form -q` → FAIL (`KeyError: 'form'`).

- [ ] **Step 3: Add the helpers + wire into `quality()`** in `blender_addon/niua_mcp_bridge/domains/feedback.py`:

```python
def _solid_volume(mesh: Any) -> float | None:
    """Enclosed solid volume via signed tetrahedra (divergence theorem); None if unmeasurable.

    Pure geometry — no bmesh, so it runs identically under fake-bpy and Blender. A closed cube
    returns its true volume; a spindly/cross form encloses little; an open mesh returns None.

    ASSUMES consistent outward-facing winding (see the Interfaces note above) — the `repair` stage
    runs before `blockout` and `model.reblock_form` calls `normals_make_consistent()`, so real
    pipeline meshes satisfy this by the time this is evaluated at the gate.
    """
    verts = list(getattr(mesh, "vertices", []) or [])
    polys = list(getattr(mesh, "polygons", []) or [])
    if not verts or not polys:
        return None
    co = [tuple(v.co) for v in verts]
    total = 0.0
    for poly in polys:
        idx = list(poly.vertices)
        if len(idx) < 3:
            continue
        a = co[idx[0]]
        for k in range(1, len(idx) - 1):
            b, c = co[idx[k]], co[idx[k + 1]]
            total += (
                a[0] * (b[1] * c[2] - b[2] * c[1])
                - a[1] * (b[0] * c[2] - b[2] * c[0])
                + a[2] * (b[0] * c[1] - b[1] * c[0])
            ) / 6.0
    return abs(total)


def _form(obj: Any, form_targets: dict, *, target_aspect: float | None = None,
          aspect_tolerance: float | None = None) -> dict:
    """Objective degenerate-guard signals + an advisory proportion read (pure geometry)."""
    prop = _proportion(obj)
    aspect = prop.get("aspect_ratio")
    boxiness = prop.get("boxiness")  # bbox cubeness — kept, NOT a fill signal
    dims = prop.get("bbox_dimensions") or (0.0, 0.0, 0.0)
    bbox_volume = dims[0] * dims[1] * dims[2] if len(dims) == 3 else 0.0
    solid = _solid_volume(getattr(obj, "data", None))
    fill_ratio = (solid / bbox_volume) if (solid is not None and bbox_volume > 0) else None

    fill_floor = form_targets.get("fill_floor")
    aspect_max = form_targets.get("aspect_degenerate_max")
    fill_ratio_ok = True if fill_ratio is None or fill_floor is None else bool(fill_ratio >= fill_floor)
    aspect_ok = True if aspect is None or aspect_max is None else bool(aspect <= aspect_max)

    tgt = target_aspect if target_aspect is not None else form_targets.get("target_aspect")
    tol = aspect_tolerance if aspect_tolerance is not None else form_targets.get("aspect_tolerance")
    delta = (aspect - tgt) if (aspect is not None and tgt is not None) else None
    proportion_ok = (abs(delta) <= tol) if (delta is not None and tol is not None) else None

    return {
        "aspect_ratio": aspect,
        "boxiness": boxiness,
        "fill_ratio": fill_ratio,
        "fill_ratio_ok": fill_ratio_ok,
        "aspect_within_degenerate_guard": aspect_ok,
        "reference": {
            "target_aspect": tgt,
            "aspect_tolerance": tol,
            "aspect_delta": delta,
            "proportion_ok": proportion_ok,
            "note": form_targets.get("note"),
        },
    }
```

In `quality()`, resolve the targets and add the block to the returned dict (after
`effective_payload, asset_meta = asset_classes.apply_asset_class_defaults(...)`):

```python
    form_targets = asset_classes.get_asset_class(effective_payload.get("asset_class")).get("form_targets", {})
    return {
        "object": obj.name,
        "asset_class": asset_meta,
        "topology": _topology_quality(obj, counts),
        "uv": uv_report(ctx, {"object": obj.name}),
        "orientation": orientation_quality(obj),
        "symmetry": _symmetry(mesh),
        "proportion": _proportion(obj),
        "form": _form(obj, form_targets),
        "scale": _scale(obj),
        "engine": engine_quality(ctx, obj, counts, effective_payload),
        "material": material_quality(obj, effective_payload),
        "export_profile": export_profile_quality(ctx, obj, counts, effective_payload),
    }
```

- [ ] **Step 4: Run tests to verify pass** — `pytest tests/domains/test_quality.py -q` → PASS. Then `pytest -q`.

- [ ] **Step 5: Commit**

```bash
git add blender_addon/niua_mcp_bridge/domains/feedback.py tests/domains/test_quality.py
git commit -m "feat: add real fill_ratio + degenerate-guard form block to feedback.quality (boxiness = bbox cubeness)"
```

---

## Task A3: `feedback.form_critique` — structured, ortho-only, records the observation

**Resolves:** design §9 decision 3, IMPORTANT [5][8][9], and the enforced-observation half of decision 1
(recording). Structured checklist object; default preset **ortho3 (front/right/top)**, no persp;
`mutates=False` with materials/state restored (proven byte-identical); records the `form_critique`
observation into the object's pipeline run so Sub-wave B can require it before advancing out of blockout.

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/core/capture.py` (add `ortho3` preset)
- Modify: `src/niua_blender_mcp/domains/feedback.py` (ToolSpec)
- Modify: `blender_addon/niua_mcp_bridge/domains/feedback.py` (handler + Command)
- Test: `tests/domains/test_feedback.py`, `tests/test_parity.py` (auto — no edit)

**Interfaces:**
- `core/capture.py` `PRESETS` gains `"ortho3": ["front", "right", "top"]` (additive; `render_silhouette`
  already resolves any preset via `cap.PRESETS.get(preset, ...)`).
- `feedback.form_critique(object?, asset_class?, brief?, target_aspect?, aspect_tolerance?, preset=ortho3, res=768)`
  — **read-only** (`mutates=False`). Returns:
  ```
  {available, images:[flat silhouette PNGs], reason?, preset,
   proportion:{bbox_dimensions, aspect_ratio, boxiness},
   symmetry:{symmetry_x, symmetry_y, symmetry_z},
   form:{fill_ratio, fill_ratio_ok, aspect_within_degenerate_guard, reference:{target_aspect, aspect_tolerance, aspect_delta, proportion_ok, note}, ...},
   reference:{asset_class, target_aspect, aspect_tolerance, note},
   brief,
   checklist:{reads_all_angles:null, proportion_ok:<measured seed>, primary_masses_ok:null, fixes:[]}}
  ```
  The `checklist` is a STRUCTURED object the multimodal agent fills in (`reads_all_angles`,
  `primary_masses_ok`, `fixes`); `proportion_ok` is seeded from the measured aspect-vs-target delta so the
  reference discriminates instead of echoing a wide band. Default preset is **ortho-only** (persp distorts
  proportion). Resolves the asset class + per-subject target from the payload, else the object's pipeline
  run, else the class default. When the object is in a pipeline run, records the observation via
  `pipeline_store.record_observation(obj_name, state["current_stage"], "form_critique")`.

- [ ] **Step 1: Write the failing tests.** First extend `tests/domains/test_feedback.py`'s fake `bpy.data`
  and give the Cube a mesh with materials so `render_silhouette`'s swap+restore actually EXECUTES (the
  file's `bpy.data` currently has only `objects`/`cameras` and `FakeObj.data = None`). Add near the top:

```python
class _MatStub:
    def __init__(self, name="m"):
        self.name = name
        self.use_nodes = False
        self.diffuse_color = (0, 0, 0, 1)
        self.node_tree = types.SimpleNamespace(
            nodes=_Nodes(), links=types.SimpleNamespace(new=lambda *a, **k: None),
        )


class _Nodes(list):
    def clear(self):
        del self[:]
    def new(self, _type):
        n = types.SimpleNamespace(
            inputs=_SocketMap(), outputs=_SocketMap(),
        )
        self.append(n)
        return n


class _SocketMap(dict):
    def __missing__(self, key):
        s = types.SimpleNamespace(default_value=None)
        self[key] = s
        return s


class _DataMaterials:
    def __init__(self):
        self._by_name = {}
    def get(self, name):
        return self._by_name.get(name)
    def new(self, name):
        m = _MatStub(name)
        self._by_name[name] = m
        return m


class _MeshWithMats:
    """A minimal mesh datablock exercising silhouette's material swap+restore."""
    def __init__(self, mats):
        self.materials = list(mats)          # supports clear()/append via list methods
        self.polygons = [types.SimpleNamespace(material_index=0)]
        self.vertices = []


class _Slot:
    def __init__(self, material):
        self.material = material
```

```python
def test_form_critique_is_structured_ortho_only_and_records_observation(ctx_env) -> None:
    ctx, bpy = ctx_env
    bpy.data.materials = _DataMaterials()                 # extend fake bpy.data (was objects/cameras only)
    reg = build_default_registry()
    cube = bpy._objects["Cube"]
    original_mat = _MatStub("orig")
    cube.data = _MeshWithMats([original_mat])
    cube.material_slots = [_Slot(original_mat)]
    dispatch_on_main(reg, "pipeline.start",
                     {"object": "Cube", "asset_class": "hard_surface_prop"}, ctx)

    before_mats = list(cube.data.materials)
    before_slots = [s.material for s in cube.material_slots]
    renders_before = len(getattr(bpy, "_render_calls", []))

    out = dispatch_on_main(
        reg, "feedback.form_critique",
        {"object": "Cube", "asset_class": "hard_surface_prop", "brief": "a wooden crate"}, ctx,
    )

    # structured + grounded
    assert out["preset"] == "ortho3"
    assert set(out["checklist"]) == {"reads_all_angles", "proportion_ok", "primary_masses_ok", "fixes"}
    assert out["checklist"]["fixes"] == []
    assert out["reference"]["asset_class"] == "hard_surface_prop"
    assert out["reference"]["target_aspect"] == 1.0
    assert out["brief"] == "a wooden crate"
    assert "fill_ratio_ok" in out["form"]
    # render actually ran (swap path executed), and materials are byte-identical afterwards
    assert len(bpy._render_calls) > renders_before
    assert list(cube.data.materials) == before_mats
    assert [s.material for s in cube.material_slots] == before_slots
    # the observation was recorded on the run (enforced-observation flag for Sub-wave B)
    from niua_mcp_bridge.core import pipeline as pstore
    assert pstore.get_state("Cube")["observations"]["intake"]["form_critique"] is True


def test_form_critique_preset_resolves_to_three_orthographic_views() -> None:
    from niua_mcp_bridge.core import capture as cap
    assert cap.PRESETS["ortho3"] == ["front", "right", "top"]
    assert "persp" not in cap.PRESETS["ortho3"]


def test_form_critique_is_read_only_in_parity() -> None:
    from niua_blender_mcp.domains import build_router
    spec = next(s for s in build_router().specs() if s.name == "feedback.form_critique")
    assert spec.mutates is False
    reg = build_default_registry()
    assert reg.get("feedback.form_critique").mutates is False
```
(The observation is recorded under `"intake"` because `pipeline.start` leaves the run at `intake`; in the
live pipeline the agent calls `form_critique` while the run is at `blockout`, so it records under
`"blockout"` — which is exactly what Sub-wave B enforces.)

- [ ] **Step 2: Run tests to verify they fail** — `pytest tests/domains/test_feedback.py -k form_critique -q` → FAIL (tool not registered) and `pytest tests/test_parity.py -q` → FAIL (server spec has no add-on handler).

- [ ] **Step 3: Add the `ortho3` preset** to `blender_addon/niua_mcp_bridge/core/capture.py` `PRESETS`:

```python
    "ortho3": ["front", "right", "top"],  # ortho-only proportion read (no persp distortion)
```

- [ ] **Step 4: Add the server `ToolSpec`** in `src/niua_blender_mcp/domains/feedback.py` (`SPECS` list):

```python
    ToolSpec(
        name="feedback.form_critique",
        category="feedback",
        summary="Structured form self-critique: ortho silhouettes + proportion/symmetry + per-subject reference target (read-only; records the observation)",
        command="feedback.form_critique",
        params={
            "object": Str(summary="Mesh object to critique; defaults to the active mesh"),
            "asset_class": Enum(ASSET_CLASS_IDS, summary="Reference class; defaults to the object's pipeline class"),
            "brief": Str(default="", summary="Task brief echoed back to anchor the critique"),
            "target_aspect": Float(minimum=1.0, summary="Per-subject believable aspect (longest/shortest); defaults to the class target"),
            "aspect_tolerance": Float(minimum=0.0, summary="Per-subject aspect tolerance; defaults to the class tolerance"),
            "preset": Enum(["ortho3", "ortho4", "ortho6", "orbit4"], default="ortho3", summary="Silhouette angle preset (ortho-only by default)"),
            "res": Int(default=768, minimum=64, maximum=2048, summary="Square render resolution (px)"),
        },
    ),
```

- [ ] **Step 5: Add the add-on handler + `Command`** in `blender_addon/niua_mcp_bridge/domains/feedback.py`
  (`asset_classes` and `pipeline_store` are already imported at module top):

```python
def form_critique(ctx: Ctx, payload: dict) -> dict:
    """Read-only OBSERVE bundle for FORM self-critique; records the observation on the run."""
    from ..core import silhouette as sil

    obj_name = payload.get("object")
    preset = str(payload.get("preset", "ortho3"))
    res = int(payload.get("res", 768))
    brief = payload.get("brief")
    raw_class = payload.get("asset_class")
    state = pipeline_store.get_state(obj_name) if obj_name else None
    asset_class = raw_class if isinstance(raw_class, str) and raw_class else (state.get("asset_class") if state else None)
    profile = asset_classes.get_asset_class(asset_class)
    form_targets = profile.get("form_targets", {})
    tgt = payload.get("target_aspect")
    tol = payload.get("aspect_tolerance")

    rendered = sil.render_silhouette(ctx.bpy, obj_name, preset=preset, res=res)
    obj = ctx.bpy.data.objects.get(obj_name) if obj_name else sil._active_mesh(ctx.bpy)
    proportion = symmetry = form = None
    if obj is not None and getattr(obj, "type", None) == "MESH":
        proportion = _proportion(obj)
        symmetry = _symmetry(obj.data)
        form = _form(obj, form_targets,
                     target_aspect=tgt if isinstance(tgt, (int, float)) else None,
                     aspect_tolerance=tol if isinstance(tol, (int, float)) else None)

    # record the observation (metadata, not mesh) so the pipeline can require the agent looked
    if state is not None and obj_name:
        pipeline_store.record_observation(obj_name, state.get("current_stage"), "form_critique")

    ref = form["reference"] if form else {}
    return {
        "available": rendered.get("available", False),
        "images": rendered.get("images", []),
        "reason": rendered.get("reason"),
        "preset": preset,
        "proportion": proportion,
        "symmetry": symmetry,
        "form": form,
        "reference": {
            "asset_class": profile["id"],
            "target_aspect": ref.get("target_aspect"),
            "aspect_tolerance": ref.get("aspect_tolerance"),
            "note": form_targets.get("note"),
        },
        "brief": brief if isinstance(brief, str) and brief else None,
        "checklist": {
            "reads_all_angles": None,                       # agent fills after LOOKING at the ortho silhouettes
            "proportion_ok": ref.get("proportion_ok"),      # seeded from measured aspect vs target
            "primary_masses_ok": None,                      # agent fills
            "fixes": [],                                    # agent fills with concrete verbs
        },
    }
```

Add to the `COMMANDS` list:

```python
    Command("feedback.form_critique", form_critique, mutates=False),
```

- [ ] **Step 6: Run tests to verify pass** — `pytest tests/domains/test_feedback.py tests/test_parity.py -q` → PASS. Then `pytest -q`. (Task B1 adds `record_observation` to `core/pipeline.py`; if you implement A3 before B1, add a tiny `record_observation` stub now and flesh it out in B1, OR reorder so B1's `record_observation` lands first — the enforced-observation assertion in this test needs it.)

- [ ] **Step 7: Commit**

```bash
git add blender_addon/niua_mcp_bridge/core/capture.py src/niua_blender_mcp/domains/feedback.py \
  blender_addon/niua_mcp_bridge/domains/feedback.py tests/domains/test_feedback.py
git commit -m "feat: add structured ortho-only feedback.form_critique that records the observation"
```

---

## Task A4: `blockout` form knowledge pack

**Resolves:** grounding for `pipeline.self_critique` at blockout; keys recommendations to the NEW gate
paths (`form.fill_ratio_ok`, `form.aspect_within_degenerate_guard`) so failed-gate guidance points at the
real form-craft verbs.

**Files:**
- Modify: `src/niua_blender_mcp/knowledge/__init__.py`
- Modify: `blender_addon/niua_mcp_bridge/core/knowledge.py`
- Test: `tests/core/test_knowledge.py`, `tests/domains/test_knowledge.py`

- [ ] **Step 1: Update the failing tests**

```python
# tests/core/test_knowledge.py — replace the list_packs assertion
def test_list_packs_includes_blockout():
    assert list_packs() == [
        "bake", "blockout", "export_preflight", "material", "optimize", "repair", "retopo", "uv"
    ]


def test_blockout_pack_targets_form_guard_and_observation():
    pack = stage_pack("blockout")
    assert pack["stage"] == "blockout"
    assert "silhouette" in pack["standards"].lower()
    assert pack["targets"]["fill_ratio_ok"] is True
    assert pack["targets"]["form_critique_observed"] is True
    assert "form.fill_ratio_ok" in pack["recommendations"]
    assert "model.reblock_form" in pack["recommendations"]["form.fill_ratio_ok"]
    assert pack["sources"]


def test_server_and_addon_packs_identical():
    from niua_blender_mcp.knowledge import _PACKS as server_packs
    from niua_mcp_bridge.core.knowledge import _PACKS as addon_packs
    assert server_packs == addon_packs
```

```python
# add to tests/domains/test_knowledge.py
def test_blockout_pack_with_asset_class_guidance() -> None:
    ctx = Ctx(FakeBpy())
    reg = build_default_registry()
    out = dispatch_on_main(reg, "knowledge.load", {"name": "blockout", "asset_class": "from_scratch_prop"}, ctx)
    pack = out["pack"]
    assert pack["stage"] == "blockout"
    assert pack["asset_class"]["id"] == "from_scratch_prop"
```

- [ ] **Step 2: Run tests to verify they fail** — `pytest tests/core/test_knowledge.py tests/domains/test_knowledge.py -q` → FAIL.

- [ ] **Step 3: Add the pack to BOTH `_PACKS`** (identical entry):

```python
    "blockout": {
        "stage": "blockout",
        "standards": "Blockout establishes believable primary masses and a silhouette that reads from every angle before any detailing. The objective gate only rejects degenerate geometry (collapsed/spindly via fill_ratio, extreme aspect via the degenerate guard); believable proportion is judged perceptually with feedback.form_critique (which you MUST record before advancing) and by the render lenses, not machine-gated.",
        "targets": {
            "fill_ratio_ok": True,
            "aspect_within_degenerate_guard": True,
            "form_critique_observed": True,
            "silhouette_reads_all_angles": True,
        },
        "sources": [
            {"title": "Blender Manual - Modeling Introduction", "locator": "manual/modeling/introduction"},
            {"title": "Primary-form-first blockout practice", "locator": "blockout: establish major volumes and silhouette before detail"},
        ],
        "recommendations": {
            "form.fill_ratio_ok": "The form reads as collapsed or spindly. Rebuild primary masses; for noisy/generated input use model.reblock_form (auto-checkpointed, bbox-relative merge).",
            "form.aspect_within_degenerate_guard": "Extreme aspect ratio. Reproportion the primary masses toward the brief's believable proportion with model.proportion_adjust, then re-observe with feedback.form_critique.",
        },
    },
```

- [ ] **Step 4: Run tests to verify pass** — `pytest tests/core/test_knowledge.py tests/domains/test_knowledge.py -q` → PASS. Then `pytest -q`.

- [ ] **Step 5: Commit**

```bash
git add src/niua_blender_mcp/knowledge/__init__.py blender_addon/niua_mcp_bridge/core/knowledge.py \
  tests/core/test_knowledge.py tests/domains/test_knowledge.py
git commit -m "feat: add blockout form knowledge pack keyed to the degenerate-guard gate paths"
```


---
---

# SUB-WAVE B — Blockout stage: degenerate guard + enforced observation (`W-form-b`)

*Inserts the `blockout` stage (after `repair`, before `retopo`). Its gate is a **degenerate guard only**
(`form.fill_ratio_ok` + `form.aspect_within_degenerate_guard`) — it must NOT block any of the 7 benchmark
items. Advancing OUT of blockout additionally requires a **recorded `feedback.form_critique` observation**
(a state flag, not a taste bar). This changes the canonical stage order, so EVERY stage-list assertion is
updated in lockstep, and — critically — ALL FIVE real-Blender smoke walks. Parity green (no new tools).*

## Task B1: Insert `blockout` stage + degenerate-guard gate + enforced observation

**Resolves:** CRITICAL [3][4][5][9] (gate is a degenerate guard, believable form moved to the enforced
observation + judge), IMPORTANT [1][2][3][4][15][20], design §9 decisions 1 & 7 (offline `_GATES`
equality + `gate_check(blockout)` pass AND reject).

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/core/pipeline.py` (`_STAGES`, `_GATES`, run state
  `observations`, `record_observation()`, `advance()` enforcement)
- Modify: `src/niua_blender_mcp/evals/stage_gates.py` (`_GATES`)
- Test: `tests/core/test_pipeline_core.py`, `tests/domains/test_pipeline.py`

**Interfaces:** new stage `{"name": "blockout", "gate_profile": "blockout", "terminal": False}` between
`repair` and `retopo`. New gate profile `"blockout"` (in BOTH `_GATES` dicts) — a **degenerate guard**,
NOT a believable-range gate:
```python
    "blockout": [
        {"path": "form.fill_ratio_ok", "op": "==", "value": True},
        {"path": "form.aspect_within_degenerate_guard", "op": "==", "value": True},
    ],
```
The per-class floor/guard values are baked into `feedback.quality`'s `form` block (A2), so the gate paths
are plain booleans (no gate-override collision). `start()`'s state dict gains `"observations": {}`. New
`record_observation(object_name, stage, kind)` sets `state["observations"].setdefault(stage, {})[kind] = True`.
`advance()` gains: when leaving `blockout`, after the normal gate-pass check, require
`state["observations"].get("blockout", {}).get("form_critique")` — else `raise ValueError("blockout requires
a recorded feedback.form_critique observation before advancing")` (the domain layer converts `ValueError`
→ `BridgeError(PRECONDITION)`).

- [ ] **Step 1: Update the failing tests** in `tests/core/test_pipeline_core.py`:

```python
# replace the body of test_stage_registry_declares_game_asset_flow
def test_stage_registry_declares_game_asset_flow():
    registry = pipeline.stage_registry()
    assert [stage["name"] for stage in registry] == [
        "intake", "repair", "blockout", "retopo", "uv", "bake", "material",
        "optimize", "export_preflight", "exported",
    ]
    assert {stage["name"]: stage["gate_profile"] for stage in registry} == {
        "intake": None, "repair": "orientation", "blockout": "blockout", "retopo": "retopo",
        "uv": "uv", "bake": "bake", "material": "material", "optimize": "optimize",
        "export_preflight": "export_preflight", "exported": None,
    }
    assert registry[-1]["terminal"] is True


# blockout sits between repair and retopo AND requires a recorded form_critique observation
def test_advance_out_of_blockout_requires_form_critique_observation():
    pipeline.start("Hero")
    pipeline.advance("Hero")                                   # intake -> repair
    pipeline.record_gate("Hero", "repair", _gate("repair", True))
    out = pipeline.advance("Hero")                             # repair -> blockout
    assert out["state"]["current_stage"] == "blockout"
    pipeline.record_gate("Hero", "blockout", _gate("blockout", True))

    # gate passes but the agent has not observed form yet -> blocked
    with pytest.raises(ValueError, match="form_critique"):
        pipeline.advance("Hero")

    pipeline.record_observation("Hero", "blockout", "form_critique")
    out = pipeline.advance("Hero")                             # blockout -> retopo
    assert out["state"]["current_stage"] == "retopo"
    assert out["state"]["completed"] == ["intake", "repair", "blockout"]


# server<->addon _GATES equality (mirrors _PACKS/_WORKFLOWS identity tests)
def test_server_and_addon_gate_profiles_identical():
    from niua_blender_mcp.evals.stage_gates import _GATES as server_gates
    from niua_mcp_bridge.core.pipeline import _GATES as addon_gates
    assert server_gates == addon_gates
    assert server_gates["blockout"] == [
        {"path": "form.fill_ratio_ok", "op": "==", "value": True},
        {"path": "form.aspect_within_degenerate_guard", "op": "==", "value": True},
    ]
```

```python
# update test_bake_and_material_stages_require_gates_before_optimize:
# thread a blockout gate + recorded observation + advance after repair, before retopo.
def test_bake_and_material_stages_require_gates_before_optimize():
    pipeline.start("Hero")
    pipeline.advance("Hero")
    pipeline.record_gate("Hero", "repair", _gate("repair", True))
    pipeline.advance("Hero")
    pipeline.record_gate("Hero", "blockout", _gate("blockout", True))
    pipeline.record_observation("Hero", "blockout", "form_critique")
    pipeline.advance("Hero")
    pipeline.record_gate("Hero", "retopo", _gate("retopo", True))
    pipeline.advance("Hero")
    pipeline.record_gate("Hero", "uv", _gate("uv", True))
    out = pipeline.advance("Hero")
    assert out["state"]["current_stage"] == "bake"
    with pytest.raises(ValueError, match="bake"):
        pipeline.advance("Hero")
    pipeline.record_gate("Hero", "bake", _gate("bake", True))
    pipeline.advance("Hero")
    with pytest.raises(ValueError, match="material"):
        pipeline.advance("Hero")
    pipeline.record_gate("Hero", "material", _gate("material", True))
    out = pipeline.advance("Hero")
    assert out["state"]["current_stage"] == "optimize"
    with pytest.raises(ValueError, match="optimize"):
        pipeline.advance("Hero")
    pipeline.record_gate("Hero", "optimize", _gate("optimize", True))
    out = pipeline.advance("Hero")
    assert out["state"]["current_stage"] == "export_preflight"
    assert out["state"]["completed"] == [
        "intake", "repair", "blockout", "retopo", "uv", "bake", "material", "optimize",
    ]
```

And the offline `gate_check(stage="blockout")` **pass AND reject** in `tests/domains/test_pipeline.py`
(mirrors the existing `retopo` gate_check test at ~L287; `FakeMesh` has `.copy()`, `FakeObj` accepts
`dimensions=`, `_CUBE_VERTS`/`_CUBE_QUADS` already defined in the file):

```python
def test_gate_check_blockout_passes_in_guard_cube(env):
    _ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS),
                    dimensions=(2.0, 2.0, 2.0)))
    _dispatch(env, "pipeline.start", {"object": "Cube", "asset_class": "hard_surface_prop"})
    out = _dispatch(env, "pipeline.gate_check", {"object": "Cube", "stage": "blockout"})
    assert out["stage"] == "blockout"
    assert out["metrics"]["form"]["aspect_within_degenerate_guard"] is True
    assert out["metrics"]["form"]["fill_ratio_ok"] is True
    assert out["gates_pass"] is True


def test_gate_check_blockout_rejects_degenerate_needle(env):
    _ctx, bpy = env
    # aspect 40 > aspect_degenerate_max(20): a genuinely degenerate needle, NOT a legit 6:1 bracket.
    bpy.add(FakeObj("Needle", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS),
                    dimensions=(40.0, 1.0, 1.0)))
    _dispatch(env, "pipeline.start", {"object": "Needle", "asset_class": "hard_surface_prop"})
    out = _dispatch(env, "pipeline.gate_check", {"object": "Needle", "stage": "blockout"})
    assert out["metrics"]["form"]["aspect_within_degenerate_guard"] is False
    assert out["gates_pass"] is False
```

- [ ] **Step 2: Run tests to verify they fail** — `pytest tests/core/test_pipeline_core.py tests/domains/test_pipeline.py -q` → FAIL (blockout not in registry; `record_observation` missing; advance goes straight to retopo).

- [ ] **Step 3: Implement.** In `blender_addon/niua_mcp_bridge/core/pipeline.py`:
  - Insert the stage in `_STAGES` between `repair` and `retopo`:
    ```python
        {"name": "repair", "gate_profile": "orientation", "terminal": False},
        {"name": "blockout", "gate_profile": "blockout", "terminal": False},
        {"name": "retopo", "gate_profile": "retopo", "terminal": False},
    ```
  - Add the profile to `_GATES` (the degenerate-guard pair above).
  - In `start()`'s state dict, add `"observations": {}`.
  - Add the recorder:
    ```python
    def record_observation(object_name: str, stage: str, kind: str) -> dict[str, Any]:
        state = _require_state(object_name)
        state.setdefault("observations", {}).setdefault(stage, {})[kind] = True
        return status(object_name)
    ```
  - In `advance()`, after the existing gate-pass check and before appending to `completed`:
    ```python
        if current_stage == "blockout":
            observed = state.get("observations", {}).get("blockout", {}).get("form_critique")
            if not observed:
                raise ValueError(
                    "blockout requires a recorded feedback.form_critique observation before advancing"
                )
    ```
  Add the identical `"blockout"` profile to `_GATES` in `src/niua_blender_mcp/evals/stage_gates.py`.

- [ ] **Step 4: Run tests to verify pass** — `pytest tests/core/test_pipeline_core.py tests/domains/test_pipeline.py -q` → PASS. Then `pytest -q` (domain-pipeline tests that advance intake→repair or block at a failed repair gate are unaffected — they never reach blockout).

- [ ] **Step 5: Commit**

```bash
git add blender_addon/niua_mcp_bridge/core/pipeline.py src/niua_blender_mcp/evals/stage_gates.py \
  tests/core/test_pipeline_core.py tests/domains/test_pipeline.py
git commit -m "feat: add blockout stage with degenerate-guard gate + enforced form_critique observation"
```

---

## Task B2: Thread blockout through ALL FIVE smoke walks + benchmark items (+ intake-guard proof)

**Resolves:** CRITICAL [1] (FIVE walks, not one), design §9 decision 1 (each of the 7 items clears its
class degenerate guard at intake), IMPORTANT [20] (no new gate-fail regression path for any item).

**Files:**
- Modify: `tests/test_smoke_headless.py` (five real-Blender pipeline walks)
- Modify: `src/niua_blender_mcp/evals/benchmark/items/*/item.json` (7 files)
- Test: `tests/evals/test_benchmark.py`

**Interfaces:** the canonical walk now advances `repair → blockout → (feedback.form_critique observe) →
retopo`; benchmark item metadata carries `blockout` right after `repair`. All five smoke seed meshes are
plain 2×2×2 cubes (verified): aspect 1.0 ≤ 20 and a closed cube fills its bbox (fill ≈ 1.0 ≥ floor), so
each blockout gate passes; the walk then calls `feedback.form_critique` to record the observation before
advancing.

- [ ] **Step 1: Write the failing tests** in `tests/evals/test_benchmark.py`:

```python
# base primitive default dims (Blender): CUBE/CYLINDER/SPHERE/ICO_SPHERE all ~2x2x2, then recipe scale.
# aspect = longest/shortest of the intake bbox. All must clear aspect_degenerate_max (20).
_INTAKE_DIMS = {
    "from_scratch_barrel":   (2.0, 2.0, 2.0),   # CYLINDER default
    "generated_blob":        (2.0, 2.0, 2.0),   # CUBE subdivided
    "generated_shell":       (2.0, 2.0, 2.0),   # CYLINDER
    "hard_surface_bracket":  (4.4, 0.7, 2.2),   # CUBE * [2.2,0.35,1.1] -> aspect 6.29
    "hard_surface_crate":    (2.0, 2.0, 2.0),   # CUBE subdivided
    "organic_pumpkin":       (2.6, 2.6, 1.7),   # SPHERE * [1.3,1.3,0.85] -> aspect 1.53
    "organic_rock":          (2.0, 2.0, 2.0),   # icosphere + jitter (~1.x)
}


def test_items_include_blockout_stage_after_repair():
    for item in (load_item(i) for i in list_items()):
        stages = item["stages"]
        assert stages[0] == "repair"
        assert stages[1] == "blockout"


def test_every_benchmark_item_intake_clears_its_class_degenerate_guard():
    from niua_blender_mcp.asset_classes import form_targets_for_class
    for item in (load_item(i) for i in list_items()):
        dims = _INTAKE_DIMS[item["id"]]
        aspect = max(dims) / min(d for d in dims if d > 0)
        guard = form_targets_for_class(item["asset_class"])["aspect_degenerate_max"]
        assert aspect <= guard, f"{item['id']} intake aspect {aspect:.2f} would wrongly block at blockout"
```
(**Scope note — this only proves the ASPECT half of the gate.** `fill_ratio_ok` is the other
`blockout` gate path, and it is NOT offline-testable here: it depends on `_solid_volume` over the
ACTUAL recipe-built mesh, which only exists once the recipe runs on a live Blender (`_INTAKE_DIMS` above
is bbox dimensions, not mesh topology). `generated_shell`'s recipe in particular
(`scene.create_object CYLINDER` → `mesh.quads_to_tris` → `mesh.delete type:"EDGE"`) is deliberately an
OPEN mesh at intake — its brief says "needs manifold repair" — so it is not obvious a priori whether its
`fill_ratio` degrades-to-pass via `None` (only guaranteed when the mesh has zero remaining
polygons/vertices, per A2) or computes a real, possibly-low number over the punctured geometry. **FINAL
Step 2b** closes this gap with a live per-item `pipeline.gate_check(stage="blockout")` assertion that
`fill_ratio_ok` holds for all 7 items, so "no legitimate item is blocked at blockout" is proven for BOTH
gate paths, not just aspect.)

- [ ] **Step 2: Run tests to verify they fail** — `pytest tests/evals/test_benchmark.py -k "blockout or degenerate" -q` → FAIL (`stages[1]` is `retopo`).

- [ ] **Step 3: Edit each `item.json`** — insert `"blockout"` into `stages` between `"repair"` and
  `"retopo"` in all 7 files (`from_scratch_barrel`, `generated_blob`, `generated_shell`,
  `hard_surface_bracket`, `hard_surface_crate`, `organic_pumpkin`, `organic_rock`), e.g.
  `["repair", "blockout", "retopo", "uv", "bake", "material", "optimize", "export_preflight"]`.

- [ ] **Step 4: Update ALL FIVE real-Blender smoke walks** in `tests/test_smoke_headless.py`. For each
  walk, replace the single `repair → retopo` advance with `repair → blockout → form_critique → retopo`.

  Walk 1 — `test_layer2_wave2_pipeline_spine_acceptance` (PipeHero, ~L749-758), which does explicit
  gate_check/advance:
```python
    assert bridge.call("pipeline.advance", {"object": "PipeHero"})["to_stage"] == "blockout"
    blockout = bridge.call("pipeline.gate_check", {"object": "PipeHero"})
    assert blockout["stage"] == "blockout"
    # 2x2x2 cube: aspect 1.0 <= 20, solid fill ~1.0 >= floor -> degenerate guard passes.
    assert blockout["metrics"]["form"]["aspect_within_degenerate_guard"] is True
    assert blockout["metrics"]["form"]["fill_ratio_ok"] is True
    assert blockout["gates_pass"] is True
    # enforced observation: must record a form_critique before advancing out of blockout
    fc = bridge.call("feedback.form_critique", {"object": "PipeHero", "asset_class": "hard_surface_prop"})
    assert "form" in fc
    assert bridge.call("pipeline.advance", {"object": "PipeHero"})["to_stage"] == "retopo"
    retopo = bridge.call("pipeline.gate_check", {"object": "PipeHero"})
    assert retopo["stage"] == "retopo"
```
  Also add, near the existing `stage_gates("retopo")` check, a blockout-profile smoke assert:
```python
    assert check_gates(quality, stage_gates("blockout"))["gates_pass"] is True
```
  Walks 2-5 — the "double advance" walks (`WorkflowHero` L936-937, `GeneratedWorkflowHero` L989-990,
  `OrganicWorkflowHero` L1009-1010, `CritPipeHero` L1036-1037) call `pipeline.advance` twice and rely on
  the domain `advance`'s internal `gate_check`. For EACH, replace the second advance with:
```python
    assert bridge.call("pipeline.advance", {"object": "<Hero>"})["to_stage"] == "blockout"
    bridge.call("feedback.form_critique", {"object": "<Hero>"})   # record the enforced observation
    assert bridge.call("pipeline.advance", {"object": "<Hero>"})["to_stage"] == "retopo"
```
  (Substitute the correct object name per walk. Without the `form_critique` call the second advance now
  raises `PRECONDITION` at blockout — that is the enforcement working.)

- [ ] **Step 5: Run tests to verify pass** — `pytest tests/evals/test_benchmark.py -q` → PASS.
  `pytest tests/test_smoke_headless.py -q` runs the five walks when a Blender binary is present (skipped
  otherwise; exercised for real in FINAL Step 2). Then `pytest -q`.

- [ ] **Step 6: Commit**

```bash
git add tests/test_smoke_headless.py src/niua_blender_mcp/evals/benchmark tests/evals/test_benchmark.py
git commit -m "test: thread blockout+observation through all five smoke walks and benchmark items"
```


---
---

# SUB-WAVE C — Form-craft verbs + workflows + altimeter wiring (`W-form-c`)

*Adds the MOVES the agent uses to fix form — a non-uniform `proportion_adjust`, a **silhouette-aware**
`silhouette_refine` (preserves hard-surface corners), and a **checkpoint-safe-by-mechanism**
`reblock_form` (auto-checkpoint, revert-on-failure, bbox-relative merge) — plus the workflows
`craft_workflow.recommend` surfaces at `blockout`, and the wiring that makes the altimeter finish agent
actually USE `feedback.form_critique`. Parity re-checked after the verbs land.*

## Task C1: Form-craft verbs — proportion_adjust, silhouette-aware refine, checkpoint-safe reblock

**Resolves:** CRITICAL [6][7] (reblock is a real transaction: auto-checkpoint before the first mutating op,
`session.restore` on ANY exception then re-raise, no partial destructive mutation), IMPORTANT [13]
(recoverability tested), [14] (bbox-relative merge, never absolute), [19] (silhouette_refine is
feature-angle-aware, does not round hard-surface corners), design §9 decisions 4 & 5.

**Files:**
- Modify: `src/niua_blender_mcp/domains/modeling_verbs.py` (3 `ToolSpec`s)
- Modify: `blender_addon/niua_mcp_bridge/domains/modeling_verbs.py` (3 handlers + `Command`s)
- Test: `tests/domains/test_modeling_verbs.py`, `tests/test_parity.py` (auto)

**Interfaces (all `mutates=True, feedback="viewport", tier="curated"`):**
- `model.proportion_adjust(object, scale_x=1, scale_y=1, scale_z=1)` — OBJECT-mode non-uniform
  `ops.transform.resize` toward reference proportions (the only bbox-changing move).
- `model.silhouette_refine(object, factor=0.5, iterations=3, feature_angle=30.0)` — EDIT-mode
  `ops.mesh.vertices_smooth`, but **feature-angle-aware**: when `feature_angle > 0` it selects sharp edges
  (`edges_select_sharp`), inverts the selection, and smooths only the non-sharp geometry — so crate/bracket
  corners are preserved. `feature_angle=0` reproduces a uniform smooth (organic use).
- `model.reblock_form(object, merge_fraction=0.02, smooth_factor=0.5, face_threshold=60.0)` — the lighter
  form-recovery reblock (locked decision #3), made safe by MECHANISM: (a) `session_store.checkpoint(obj,
  label="reblock:pre")` BEFORE the first mutating op; (b) the op sequence runs inside `try/except` — on ANY
  exception `session_store.restore(obj, snapshot)` then re-raise (no partial mutation); (c) merge distance
  is **bbox-relative** — `merge_fraction` of the bbox diagonal, clamped ≤ 10% — never an absolute value
  that could weld an arbitrary-scale generated mesh to a point. Returns the checkpoint label;
  `postcheck_recommended` includes `session.revert`.

- [ ] **Step 1: Extend the fake bpy + write failing tests** in `tests/domains/test_modeling_verbs.py`.
  Add `vertices_smooth` to `_MeshOps`, a `transform` op group, and give `_FakeObj` a real `data`
  (with `.copy()`) + `dimensions` so reblock's checkpoint/restore and bbox-relative merge exercise:

```python
# inside _FakeBpy._MeshOps
            vertices_smooth = _Op(log, "mesh.vertices_smooth")
# add a transform op group and register it on self.ops:
        class _TransformOps:
            resize = _Op(log, "transform.resize")
        self.ops = types.SimpleNamespace(
            mesh=_MeshOps(), object=_ObjectOps(), transform=_TransformOps(), ed=_EdOps()
        )
```

```python
# a tiny mesh with .copy() so core.session checkpoint/restore round-trips under fake-bpy
class _FakeMesh:
    def __init__(self, verts=((0, 0, 0), (1, 0, 0), (0, 1, 0))):
        self.vertices = [types.SimpleNamespace(co=tuple(c)) for c in verts]
        self.polygons = []
    def copy(self):
        return _FakeMesh(tuple(v.co for v in self.vertices))
# ensure _FakeObj gets data + dimensions (extend its __init__ or set after construction)
```

```python
def test_proportion_adjust_resizes_in_object_mode(monkeypatch):
    bpy = _make_bpy_with_object(monkeypatch)
    reg = build_default_registry()
    out = dispatch_on_main(reg, "model.proportion_adjust",
                           {"object": "Cube", "scale_x": 2.0, "scale_z": 0.5}, Ctx(bpy))
    assert out["applied"] == ["resize"]
    assert ("transform.resize", {"value": (2.0, 1.0, 0.5)}) in bpy.op_calls
    assert bpy.undo_pushes == ["niua:model.proportion_adjust"]


def test_silhouette_refine_preserves_sharp_edges_by_default(monkeypatch):
    bpy = _make_bpy_with_object(monkeypatch)
    reg = build_default_registry()
    out = dispatch_on_main(reg, "model.silhouette_refine",
                           {"object": "Cube", "factor": 0.4, "iterations": 5}, Ctx(bpy))
    names = _names(bpy.op_calls)
    # deselects, selects sharp edges, inverts, THEN smooths only the non-sharp geometry
    assert "mesh.edges_select_sharp" in names
    assert names.index("mesh.edges_select_sharp") < names.index("mesh.vertices_smooth")
    assert ("mesh.vertices_smooth", {"factor": 0.4, "repeat": 5}) in bpy.op_calls
    assert bpy.undo_pushes == ["niua:model.silhouette_refine"]


def test_silhouette_refine_uniform_when_feature_angle_zero(monkeypatch):
    bpy = _make_bpy_with_object(monkeypatch)
    reg = build_default_registry()
    dispatch_on_main(reg, "model.silhouette_refine",
                     {"object": "Cube", "feature_angle": 0.0}, Ctx(bpy))
    assert "mesh.edges_select_sharp" not in _names(bpy.op_calls)   # nothing protected -> uniform smooth


def test_reblock_form_merge_is_bbox_relative_not_absolute(monkeypatch):
    bpy = _make_bpy_with_object(monkeypatch)
    obj = bpy.objects_by_name["Cube"]
    obj.data = _FakeMesh()
    obj.dimensions = (0.02, 0.02, 0.02)                # arbitrary tiny generated scale
    reg = build_default_registry()
    dispatch_on_main(reg, "model.reblock_form", {"object": "Cube"}, Ctx(bpy))
    threshold = dict(bpy.op_calls)["mesh.remove_doubles"]["threshold"]
    assert threshold < 0.02                            # NOT the old absolute 0.01 that would collapse it
    assert threshold == pytest.approx(0.02 * (0.02 ** 2 * 3) ** 0.5, rel=0.2)


def test_reblock_form_rolls_back_on_mid_op_failure(monkeypatch):
    bpy = _make_bpy_with_object(monkeypatch)
    obj = bpy.objects_by_name["Cube"]
    obj.data = _FakeMesh()
    obj.dimensions = (2.0, 2.0, 2.0)
    before = [v.co for v in obj.data.vertices]
    before_count = len(obj.data.vertices)

    # GENUINE rollback proof: remove_doubles is an EARLY op (3rd in the applied sequence) and here it
    # must actually MUTATE the mesh (simulate a real doubles-merge by dropping the last vertex) —
    # otherwise a byte-identical assertion after rollback would pass trivially even if
    # session.restore() is NEVER called (the vacuous version of this test: fake ops that never
    # touch obj.data.vertices can't distinguish "rollback happened" from "nothing ever changed").
    def fake_remove_doubles(**kw):
        obj.data.vertices = obj.data.vertices[:-1]
    bpy.ops.mesh.remove_doubles = fake_remove_doubles

    # force a LATER op (vertices_smooth, 4th in the sequence) to fail — AFTER the mesh has already
    # been mutated by remove_doubles above, so the rollback has real work to undo.
    def boom(**kw):
        raise RuntimeError("vertices_smooth failed")
    bpy.ops.mesh.vertices_smooth = boom

    reg = build_default_registry()
    with pytest.raises(Exception):
        dispatch_on_main(reg, "model.reblock_form", {"object": "Cube"}, Ctx(bpy))

    # If session_store.restore() is skipped, or checkpoint/restore use mismatched labels, the mesh
    # stays at (before_count - 1) vertices and this assertion catches it.
    assert len(obj.data.vertices) == before_count
    assert [v.co for v in obj.data.vertices] == before   # mesh restored to pre-reblock state
    assert bpy.undo_pushes == []                          # failed verb pushes NO undo


def test_reblock_form_checkpoints_and_recommends_revert(monkeypatch):
    bpy = _make_bpy_with_object(monkeypatch)
    obj = bpy.objects_by_name["Cube"]
    obj.data = _FakeMesh()
    obj.dimensions = (2.0, 2.0, 2.0)
    reg = build_default_registry()
    out = dispatch_on_main(reg, "model.reblock_form", {"object": "Cube"}, Ctx(bpy))
    assert out["applied"] == ["select_all", "normals_make_consistent", "remove_doubles",
                              "vertices_smooth", "tris_convert_to_quads"]
    assert out["checkpoint"] == "reblock:pre"
    assert "session.revert" in out["postcheck_recommended"]
    assert bpy.undo_pushes == ["niua:model.reblock_form"]


def test_form_verbs_are_curated_in_server_router():
    from niua_blender_mcp.domains import build_router
    specs = {s.name: s for s in build_router().specs()}
    for name in ("model.proportion_adjust", "model.silhouette_refine", "model.reblock_form"):
        assert specs[name].tier == "curated"
        assert specs[name].mutates is True
```
(Adapt the direct-attribute monkeypatch style above to the file's `_Op` mechanism if it differs — the
load-bearing assertions are "mesh restored to its ORIGINAL vertex count/positions" (not merely
"unchanged from whatever remove_doubles already mutated it to") + "no undo".)

- [ ] **Step 2: Run tests to verify they fail** — `pytest tests/domains/test_modeling_verbs.py -q` → FAIL (verbs unregistered); `pytest tests/test_parity.py -q` → FAIL.

- [ ] **Step 3: Add the 3 server `ToolSpec`s** to `src/niua_blender_mcp/domains/modeling_verbs.py`:

```python
    ToolSpec(
        name="model.proportion_adjust", category="modeling",
        summary="Scale a mesh's primary masses toward believable reference proportions (non-uniform resize)",
        command="model.proportion_adjust",
        params={
            "object": Str(required=True, summary="Mesh object to reproportion"),
            "scale_x": Float(default=1.0, minimum=0.01, summary="X scale factor"),
            "scale_y": Float(default=1.0, minimum=0.01, summary="Y scale factor"),
            "scale_z": Float(default=1.0, minimum=0.01, summary="Z scale factor"),
        },
        mutates=True, feedback="viewport", tier="curated",
    ),
    ToolSpec(
        name="model.silhouette_refine", category="modeling",
        summary="Smooth silhouette-defining geometry so the outline reads, preserving sharp feature edges",
        command="model.silhouette_refine",
        params={
            "object": Str(required=True, summary="Mesh object to refine"),
            "factor": Float(default=0.5, minimum=0.0, maximum=1.0, summary="Smoothing factor per iteration"),
            "iterations": Int(default=3, minimum=1, maximum=20, summary="Smoothing repeat count"),
            "feature_angle": Float(default=30.0, minimum=0.0, maximum=180.0, summary="Protect edges sharper than this (deg); 0 = uniform smooth"),
        },
        mutates=True, feedback="viewport", tier="curated",
    ),
    ToolSpec(
        name="model.reblock_form", category="modeling",
        summary="Checkpoint-safe form-recovery reblock: re-establish primary proportions on a noisy mesh (bbox-relative merge; not a full remesh)",
        command="model.reblock_form",
        params={
            "object": Str(required=True, summary="Noisy or generated mesh to reblock"),
            "merge_fraction": Float(default=0.02, minimum=0.0, maximum=0.1, summary="Merge distance as a fraction of the bbox diagonal"),
            "smooth_factor": Float(default=0.5, minimum=0.0, maximum=1.0, summary="Light smoothing factor"),
            "face_threshold": Float(default=60.0, minimum=0.0, maximum=180.0, summary="Relaxed tri-to-quad threshold (deg)"),
        },
        mutates=True, feedback="viewport", tier="curated",
    ),
```

- [ ] **Step 4: Add the 3 add-on handlers + `Command`s** to
  `blender_addon/niua_mcp_bridge/domains/modeling_verbs.py` (uses the existing `_mesh_object` helper;
  `import math` at top if not present):

```python
def proportion_adjust(ctx: Ctx, payload: dict) -> dict:
    obj = _mesh_object(ctx, payload)
    sx, sy, sz = (float(payload.get("scale_x", 1.0)), float(payload.get("scale_y", 1.0)),
                  float(payload.get("scale_z", 1.0)))
    ops = ctx.bpy.ops
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        ctx.check_poll(ops.transform.resize)
        ops.transform.resize(value=(sx, sy, sz))
    return {"object": obj.name, "applied": ["resize"], "scale": {"x": sx, "y": sy, "z": sz}}


def silhouette_refine(ctx: Ctx, payload: dict) -> dict:
    obj = _mesh_object(ctx, payload)
    factor = float(payload.get("factor", 0.5))
    iterations = int(payload.get("iterations", 3))
    feature_angle = float(payload.get("feature_angle", 30.0))
    ops = ctx.bpy.ops
    applied: list[str] = []
    with ctx.ensure(active=obj, mode="EDIT", select=[obj]):
        ctx.check_poll(ops.mesh.select_all)
        ops.mesh.select_all(action="SELECT"); applied.append("select_all")
        if feature_angle > 0.0:
            ops.mesh.select_all(action="DESELECT"); applied.append("select_all")
            ctx.check_poll(ops.mesh.edges_select_sharp)
            ops.mesh.edges_select_sharp(sharpness=math.radians(feature_angle)); applied.append("edges_select_sharp")
            ops.mesh.select_all(action="INVERT"); applied.append("select_all")   # smooth only non-sharp geometry
        ctx.check_poll(ops.mesh.vertices_smooth)
        ops.mesh.vertices_smooth(factor=factor, repeat=iterations); applied.append("vertices_smooth")
    return {"object": obj.name, "applied": applied, "factor": factor,
            "iterations": iterations, "feature_angle": feature_angle}


def reblock_form(ctx: Ctx, payload: dict) -> dict:
    from ..core import session as session_store
    obj = _mesh_object(ctx, payload)
    merge_fraction = max(0.0, min(float(payload.get("merge_fraction", 0.02)), 0.1))
    smooth_factor = float(payload.get("smooth_factor", 0.5))
    face_threshold = float(payload.get("face_threshold", 60.0))
    dims = getattr(obj, "dimensions", None) or (0.0, 0.0, 0.0)
    diag = math.sqrt(sum(d * d for d in dims))
    merge_distance = merge_fraction * diag            # bbox-relative, never absolute
    threshold_radians = math.radians(face_threshold)
    ops = ctx.bpy.ops

    checkpoint = session_store.checkpoint(obj, label="reblock:pre")   # BEFORE any mutation
    try:
        with ctx.ensure(active=obj, mode="EDIT", select=[obj]):
            ctx.check_poll(ops.mesh.select_all); ops.mesh.select_all(action="SELECT")
            ctx.check_poll(ops.mesh.normals_make_consistent); ops.mesh.normals_make_consistent()
            ctx.check_poll(ops.mesh.remove_doubles); ops.mesh.remove_doubles(threshold=merge_distance)
            ctx.check_poll(ops.mesh.vertices_smooth); ops.mesh.vertices_smooth(factor=smooth_factor, repeat=2)
            ctx.check_poll(ops.mesh.tris_convert_to_quads)
            ops.mesh.tris_convert_to_quads(face_threshold=threshold_radians, shape_threshold=threshold_radians)
    except Exception:
        snapshot = session_store.get_snapshot(obj.name, label=checkpoint["label"])
        if snapshot is not None:
            session_store.restore(obj, snapshot)          # roll back — no partial destructive mutation
        raise
    return {
        "object": obj.name,
        "applied": ["select_all", "normals_make_consistent", "remove_doubles",
                    "vertices_smooth", "tris_convert_to_quads"],
        "checkpoint": checkpoint["label"],
        "params": {"merge_fraction": merge_fraction, "merge_distance": merge_distance,
                   "smooth_factor": smooth_factor, "face_threshold": face_threshold},
        "warnings": [f"Reblock re-establishes primary proportions and drops fine detail (lighter than a full remesh). An automatic checkpoint '{checkpoint['label']}' was taken; revert with session.revert."],
        "postcheck_recommended": ["feedback.form_critique", "session.revert", "pipeline.gate_check"],
    }
```

Append to `COMMANDS`:

```python
    Command("model.proportion_adjust", proportion_adjust, mutates=True, feedback="viewport"),
    Command("model.silhouette_refine", silhouette_refine, mutates=True, feedback="viewport"),
    Command("model.reblock_form", reblock_form, mutates=True, feedback="viewport"),
```

- [ ] **Step 5: Run tests to verify pass** — `pytest tests/domains/test_modeling_verbs.py tests/test_parity.py -q` → PASS. Then `pytest -q`.

- [ ] **Step 6: Commit**

```bash
git add src/niua_blender_mcp/domains/modeling_verbs.py blender_addon/niua_mcp_bridge/domains/modeling_verbs.py \
  tests/domains/test_modeling_verbs.py
git commit -m "feat: add form-craft verbs (proportion_adjust, feature-aware silhouette_refine, transactional reblock_form)"
```

---

## Task C2: Form-craft workflows wired into `craft_workflow.recommend`

**Resolves:** IMPORTANT [12] (form_recovery_reblock scoped to `["blockout"]` so it does NOT silently
reorder the repair-stage recommendation — with an explicit repair-order lock test), [10] (a real
bbox-recovery path exists at blockout), [19] (hard_surface blockout_pass uses the feature-aware refine).

**Files:**
- Modify: `src/niua_blender_mcp/craft_workflows.py` (`_WORKFLOWS`)
- Modify: `blender_addon/niua_mcp_bridge/core/craft_workflows.py` (`_WORKFLOWS` — identical mirror)
- Test: `tests/test_craft_workflows.py`, `tests/domains/test_craft_workflow.py`

**Interfaces:** 4 new records so `craft_workflow.recommend(asset_class, stage="blockout")` surfaces the
right form-craft passes. **All four are stage `["blockout"]` only** — including
`generated_cleanup.form_recovery_reblock` (repair is topology, not form) — so no existing `repair`/`retopo`
recommendation order changes. New sorted `WORKFLOW_IDS` (7): `from_scratch.blockout_pass`,
`generated_cleanup.form_recovery_reblock`, `generated_cleanup.rebuild_noisy_mesh`,
`hard_surface.blockout_pass`, `hard_surface.panel_detail_pass`, `organic.blockout_pass`,
`organic.silhouette_retopo_prep`.

**Behavior change to record explicitly:** giving `from_scratch_prop` its first workflow makes the Tier-2
(asset-class-only) fallback in `recommend_workflows` fire for `recommend(from_scratch_prop, "retopo")`
instead of returning empty — the two "no fallback for from_scratch" tests are updated to assert the new
fallback. `generated_cleanup` at `repair` is UNCHANGED (only `rebuild_noisy_mesh`), asserted by a new lock.

- [ ] **Step 1: Update the failing tests.** In `tests/test_craft_workflows.py`:

```python
# replace the id list in test_server_and_addon_craft_workflow_registries_match
    assert sorted(server) == [
        "from_scratch.blockout_pass",
        "generated_cleanup.form_recovery_reblock",
        "generated_cleanup.rebuild_noisy_mesh",
        "hard_surface.blockout_pass",
        "hard_surface.panel_detail_pass",
        "organic.blockout_pass",
        "organic.silhouette_retopo_prep",
    ]
    assert server == addon


def test_recommend_workflows_falls_back_to_from_scratch_blockout() -> None:
    out = addon_workflows.recommend_workflows(asset_class="from_scratch_prop", stage="retopo")
    assert out["reason"] == "matched asset_class=from_scratch_prop stage=retopo"
    assert out["recommendations"][0]["id"] == "from_scratch.blockout_pass"
    assert out["recommendations"][0]["match"] == "asset_class"


def test_recommend_matches_blockout_stage_and_leaves_repair_order_unchanged() -> None:
    hs = addon_workflows.recommend_workflows(asset_class="hard_surface_prop", stage="blockout")
    assert hs["recommendations"][0]["id"] == "hard_surface.blockout_pass"
    assert hs["recommendations"][0]["match"] == "asset_class+stage"
    gen_block = addon_workflows.list_workflows(asset_class="generated_cleanup", stage="blockout")
    assert [w["id"] for w in gen_block] == ["generated_cleanup.form_recovery_reblock"]
    # repair-stage generated_cleanup order MUST stay exactly as before (I12 lock)
    gen_repair = addon_workflows.list_workflows(asset_class="generated_cleanup", stage="repair")
    assert [w["id"] for w in gen_repair] == ["generated_cleanup.rebuild_noisy_mesh"]
```

In `tests/domains/test_craft_workflow.py`:

```python
# replace test_craft_workflow_recommend_returns_no_fallback_for_unsupported_class
def test_craft_workflow_recommend_falls_back_to_from_scratch_blockout() -> None:
    out = _dispatch("craft_workflow.recommend", {"asset_class": "from_scratch_prop", "stage": "retopo"})
    assert out["reason"] == "matched asset_class=from_scratch_prop stage=retopo"
    assert out["recommendations"][0]["id"] == "from_scratch.blockout_pass"


def test_craft_workflow_recommend_surfaces_blockout_pass() -> None:
    out = _dispatch("craft_workflow.recommend", {"asset_class": "organic_prop", "stage": "blockout"})
    assert out["recommendations"][0]["id"] == "organic.blockout_pass"
    assert out["recommendations"][0]["rank"] == 1
```

- [ ] **Step 2: Run tests to verify they fail** — `pytest tests/test_craft_workflows.py tests/domains/test_craft_workflow.py -q` → FAIL.

- [ ] **Step 3: Add the 4 records to BOTH `_WORKFLOWS`** (keep the two files byte-identical). All four at
  `stages: ["blockout"]`. `hard_surface.blockout_pass` passes a non-zero `feature_angle` so
  `silhouette_refine` preserves corners; `generated_cleanup.form_recovery_reblock` leads with
  `model.reblock_form` (auto-checkpointed) and lists `session.revert` in its cautions.

```python
    "hard_surface.blockout_pass": {
        "id": "hard_surface.blockout_pass", "label": "Hard-surface blockout pass",
        "asset_class": "hard_surface_prop", "stages": ["blockout"],
        "summary": "Establish believable hard-surface primary masses and a clean-reading silhouette before detailing.",
        "required_tools": ["feedback.form_critique", "model.proportion_adjust", "model.silhouette_refine", "model.retopo_quads"],
        "default_params": {"scale_x": 1.0, "scale_y": 1.0, "scale_z": 1.0, "factor": 0.4, "iterations": 3, "feature_angle": 40.0, "face_threshold": 40.0},
        "gate_targets": ["form.fill_ratio_ok", "form.aspect_within_degenerate_guard"],
        "recipe_steps": [
            "observe form with feedback.form_critique against the per-subject target (records the observation)",
            "scale the primary masses toward the brief's believable proportion",
            "refine the silhouette while PRESERVING sharp corners (feature_angle > 0)",
            "normalize topology back toward quads",
            "re-observe with feedback.form_critique before advancing",
        ],
        "outputs": ["reference-proportioned primary masses", "clean-reading silhouette with crisp corners", "quad-normalized blockout"],
        "cautions": [
            "Blockout is low-detail; defer panels/bevels to the detail pass.",
            "Do NOT smooth hard-surface corners uniformly — keep feature_angle > 0.",
        ],
    },
    "organic.blockout_pass": {
        "id": "organic.blockout_pass", "label": "Organic blockout pass",
        "asset_class": "organic_prop", "stages": ["blockout"],
        "summary": "Establish believable organic masses and a flowing silhouette before detailing.",
        "required_tools": ["feedback.form_critique", "model.proportion_adjust", "model.silhouette_refine", "model.organic_retopo_prep"],
        "default_params": {"scale_x": 1.0, "scale_y": 1.0, "scale_z": 1.0, "factor": 0.5, "iterations": 4, "feature_angle": 0.0, "face_threshold": 50.0},
        "gate_targets": ["form.fill_ratio_ok", "form.aspect_within_degenerate_guard"],
        "recipe_steps": [
            "observe form with feedback.form_critique (records the observation)",
            "reproportion the primary masses toward a believable organic silhouette",
            "smooth silhouette-defining geometry to remove lumpiness (feature_angle 0)",
            "normalize organic topology without bevels",
            "re-observe before advancing",
        ],
        "outputs": ["believable organic masses", "flowing silhouette", "organic retopo-prep topology"],
        "cautions": ["Keep the blockout soft; verify the silhouette reads from all angles before advancing."],
    },
    "from_scratch.blockout_pass": {
        "id": "from_scratch.blockout_pass", "label": "From-scratch blockout construction",
        "asset_class": "from_scratch_prop", "stages": ["blockout"],
        "summary": "Proportion a primitive blockout to the brief's reference before detailing.",
        "required_tools": ["feedback.form_critique", "model.proportion_adjust", "model.retopo_quads"],
        "default_params": {"scale_x": 1.0, "scale_y": 1.0, "scale_z": 1.0, "face_threshold": 40.0},
        "gate_targets": ["form.fill_ratio_ok", "form.aspect_within_degenerate_guard"],
        "recipe_steps": [
            "observe form with feedback.form_critique (records the observation)",
            "scale the base primitive to the brief's believable proportion (e.g. barrel ~1:1:1.2)",
            "normalize topology toward quads",
            "re-observe before advancing",
        ],
        "outputs": ["reference-proportioned base", "quad topology"],
        "cautions": ["Keep the blockout to primary masses only; confirm scale/units before proportioning."],
    },
    "generated_cleanup.form_recovery_reblock": {
        "id": "generated_cleanup.form_recovery_reblock", "label": "Generated form-recovery reblock",
        "asset_class": "generated_cleanup", "stages": ["blockout"],
        "summary": "Recover coherent form from a noisy generated mesh with a checkpoint-safe reblock instead of cleaning noise in place.",
        "required_tools": ["feedback.form_critique", "model.reblock_form", "model.retopo_quads"],
        "default_params": {"merge_fraction": 0.02, "smooth_factor": 0.5, "face_threshold": 60.0},
        "gate_targets": ["form.fill_ratio_ok", "form.aspect_within_degenerate_guard", "topology.non_manifold_edges"],
        "recipe_steps": [
            "observe the noisy form with feedback.form_critique (records the observation)",
            "reblock primary proportions with model.reblock_form (auto-checkpoints 'reblock:pre'; bbox-relative merge)",
            "normalize topology toward quads",
            "re-observe recovered form; if worse, session.revert to the checkpoint",
        ],
        "outputs": ["recovered primary form", "reduced noise", "quad-normalized reblock"],
        "cautions": [
            "reblock is lighter than a full remesh and self-checkpoints; if it degrades the form, session.revert 'reblock:pre'.",
            "Re-check topology and the degenerate guard after reblocking.",
        ],
    },
```

- [ ] **Step 4: Run tests to verify pass** — `pytest tests/test_craft_workflows.py tests/domains/test_craft_workflow.py -q` → PASS. Then `pytest -q` (the `retopo`/`repair`-filtered list/recommend tests are unaffected — the new workflows live only at `blockout`).

- [ ] **Step 5: Commit**

```bash
git add src/niua_blender_mcp/craft_workflows.py blender_addon/niua_mcp_bridge/core/craft_workflows.py \
  tests/test_craft_workflows.py tests/domains/test_craft_workflow.py
git commit -m "feat: add blockout-stage form-craft workflows (form_recovery_reblock scoped to blockout)"
```

---

## Task C3: Wire `feedback.form_critique` into the altimeter finish loop (+ instrumentation)

**Resolves:** CRITICAL [6] (the form eye is actually exercised in the measurement run), IMPORTANT [6][17],
design §9 decision 6. Without this the wave could ship, re-run the altimeter, and never call the in-loop
form self-critique it is built around.

**Files:**
- Modify: `workflows/altimeter.mjs` (finish prompt + per-item result schema + Stage-2 assemble)
- Modify: `src/niua_blender_mcp/evals/scorecard.py` (`aggregate()` gains `per_lens_means`)
- Test: `tests/evals/test_altimeter_wiring.py` (new — a pure text assertion runnable under `pytest -q`)
- Test: `tests/evals/test_scorecard.py` (extend — `aggregate()` per-lens-means coverage)

**Interfaces:** the finish prompt's STEP 3 explicitly instructs the agent, **at the `blockout` stage**, to
OBSERVE form with `feedback.form_critique`, act on its checklist (proportion_adjust / silhouette_refine /
reblock_form on a `session.checkpoint`), and only then `pipeline.advance` — and to COUNT the calls,
returning `form_critique_calls` per item so the re-measure can prove the intervention ran. Separately,
`aggregate()` (`src/niua_blender_mcp/evals/scorecard.py`) already computes a per-lens mean internally
to pick `weakest_lens` but currently **discards** it — the FINAL success gate is defined on per-lens
**means** (silhouette/proportion post − baseline ≥ +1.0), so that internal computation must be surfaced
as a `per_lens_means: dict[str, float]` field on the returned reading; this is the concrete, computable
data source the FINAL exit gate reads from.

- [ ] **Step 1: Write the failing tests** — `tests/evals/test_altimeter_wiring.py` AND extend
  `tests/evals/test_scorecard.py`:

```python
from __future__ import annotations
from pathlib import Path

_MJS = Path(__file__).resolve().parents[2] / "workflows" / "altimeter.mjs"


def test_finish_prompt_observes_form_via_form_critique_at_blockout():
    text = _MJS.read_text()
    assert "feedback.form_critique" in text          # the form eye is wired into the finish loop
    assert "blockout" in text
    assert "form_critique_calls" in text             # per-item instrumentation is captured


def test_finish_prompt_still_uses_capture_views_for_the_judge_panel():
    text = _MJS.read_text()
    assert "feedback.capture_views" in text          # judge renders are unchanged


def test_stage2_assemble_propagates_form_critique_calls_into_raw_card():
    text = _MJS.read_text()
    # Stage-2 assemble rebuilds the raw card from a fixed field set; without this line
    # form_critique_calls never reaches raw_cards.json or the report (dropped on the floor).
    assert "fin && fin.form_critique_calls" in text
```

```python
# add to tests/evals/test_scorecard.py — aggregate() currently computes a per-lens mean
# internally (to pick weakest_lens) and discards it; the FINAL exit gate needs it surfaced.
def test_aggregate_reports_per_lens_means():
    cards = [
        score_item(ITEM, True, {"silhouette": 8.0, "proportion": 4.0}),
        score_item(ITEM, True, {"silhouette": 6.0, "proportion": 6.0}),
    ]
    agg = aggregate(cards)
    assert agg["per_lens_means"] == {"silhouette": 7.0, "proportion": 5.0}
```

- [ ] **Step 2: Run tests to verify they fail** — `pytest tests/evals/test_altimeter_wiring.py tests/evals/test_scorecard.py -q`
  → FAIL (`fin && fin.form_critique_calls` not present in `altimeter.mjs`; `KeyError: 'per_lens_means'`).

- [ ] **Step 3: Edit `workflows/altimeter.mjs`.** In the finish prompt (STEP 3, ~L90-93), add an explicit
  blockout observe-iterate instruction and count the calls; extend the returned JSON schema. For example,
  replace the "Use feedback.critique as your eyes between edits" line with:

```javascript
    `  Use feedback.critique '{"object":"bench_${item.id}"}' as your eyes between edits. AT THE "blockout" STAGE you MUST\n` +
    `  first OBSERVE form: feedback.form_critique '{"object":"bench_${item.id}","asset_class":"${item.asset_class}"}', then act on its\n` +
    `  checklist (session.checkpoint, then model.proportion_adjust / model.silhouette_refine / model.reblock_form) and RE-OBSERVE\n` +
    `  until reads_all_angles + proportion_ok + primary_masses_ok before pipeline.advance (advancing out of blockout REQUIRES a\n` +
    `  recorded form_critique). Count every feedback.form_critique call. If a stage gate cannot pass\n` +
```

  and extend the returned JSON (the finish result) with the instrumentation field:

```javascript
    `Return JSON: {id:"${item.id}", subject:"bench_${item.id}", gates_pass:<...>, reached_stage:"<...>", form_critique_calls:<integer count of feedback.form_critique calls>, images:[<png paths>], notes:"<one line>"}.`,
```

  (Update `FINISH_SCHEMA` to allow the new `form_critique_calls` integer. Leave STEP 4's
  `feedback.capture_views (preset ortho4)` for the judge panel unchanged.)

- [ ] **Step 3b: Propagate the count through Stage-2 assemble.** `form_critique_calls` now lands inside
  `fin` (the Stage-1 Finish result) — but Stage 2's assemble callback rebuilds the raw card from a FIXED
  field set:
  ```javascript
    return {
      id: item.id,
      asset_class: item.asset_class,
      senior_threshold: item.senior_threshold,
      gates_pass: !!(fin && fin.gates_pass),
      reached_stage: (fin && fin.reached_stage) || null,
      lens_scores,
    }
  ```
  and currently never copies `form_critique_calls` — so it never reaches `raw_cards.json` or the report,
  and FINAL's "every item `form_critique_calls ≥ 1`" gate is uncheckable. Add a field next to
  `reached_stage:`:
  ```javascript
      form_critique_calls: (fin && fin.form_critique_calls) || 0,
  ```
  This rides along through `cards = rawCards.filter(Boolean)` into the `${JSON.stringify(cards)}` blob the
  Score phase writes verbatim to `${OUTDIR}/raw_cards.json`, so it is present in both `raw_cards.json` and
  — once copied into the FINAL Step 5 report table — `docs/reports/altimeter-form-craft.md`.

- [ ] **Step 3c: Surface `per_lens_means` from `aggregate()`.** In
  `src/niua_blender_mcp/evals/scorecard.py`, `aggregate()` already builds `lens_totals` to pick
  `weakest_lens` and then discards it. Add the means dict and return it:
  ```python
      per_lens_means = {lens: sum(vals) / len(vals) for lens, vals in lens_totals.items()}
      return {
          "n_items": n,
          "n_senior_pass": n_pass,
          "pass_rate": (n_pass / n) if n else 0.0,
          "mean_overall": mean_overall,
          "per_class": per_class,
          "weakest_lens": weakest,
          "per_lens_means": per_lens_means,
      }
  ```
  This is additive (no existing test asserts an exact key-set on `aggregate()`'s return). Because
  `altimeter.mjs`'s Score phase already calls `aggregate(cards)` once at the end and prints the resulting
  `reading` JSON verbatim, `per_lens_means` rides through with no further `.mjs` change needed.

- [ ] **Step 4: Run tests to verify pass** — `pytest tests/evals/test_altimeter_wiring.py tests/evals/test_scorecard.py -q` → PASS. Then `pytest -q`.

- [ ] **Step 5: Commit**

```bash
git add workflows/altimeter.mjs src/niua_blender_mcp/evals/scorecard.py \
  tests/evals/test_altimeter_wiring.py tests/evals/test_scorecard.py
git commit -m "feat: wire feedback.form_critique into altimeter finish loop, propagate form_critique_calls through assemble, surface aggregate() per_lens_means"
```


---
---

# FINAL — Live acceptance + altimeter re-measure (controller-run; needs VISIBLE Blender)

*Deliberately triggered, NOT part of the offline TDD loop. This is the honest lift check and the wave's
success gate. Requires a visible Blender because the judge lenses need GL renders (a pure `--background`
run returns `available: false` and the panel has nothing to look at).*

**Prerequisite:** a visible Blender serving the bridge on port 8765:
`blender --python scripts/blender_gui.py -- <repo>/blender_addon 8765 0`

- [ ] **Step 1: Full offline suite green** — `pytest -q` (excluding the Blender-gated smoke) passes end to
  end after Sub-wave C, including the new `_GATES` equality test, the blockout `gate_check` pass+reject,
  the fill-discrimination + degenerate-guard `form` tests, the material-byte-identical `form_critique`
  test, the reblock rollback + bbox-relative merge tests, the repair-order lock, the 7-item intake-guard
  test, and the altimeter-wiring test.

- [ ] **Step 2: Real-Blender headless smoke** — with a `blender` binary available, run
  `pytest tests/test_smoke_headless.py -q`. Confirms the live bridge advances
  `intake → repair → blockout → (form_critique) → retopo → … → exported` for **all five** walks, that the
  blockout degenerate guard passes for the seed cube, that advancing out of blockout without a recorded
  `feedback.form_critique` raises, and — the live mesh-safety proof — add/execute a reblock recoverability
  assertion: `session.checkpoint` a known mesh (record vert count + bbox), `model.reblock_form`,
  `session.revert`, and assert the vertex count and bbox return to the pre-reblock values. (GL renders may
  degrade headless; the analytic `form` half and the checkpoint/revert round-trip must still hold.)
  Additionally, add a SECOND live safety assertion distinct from the clean checkpoint→reblock→revert
  round-trip above — the **forced-failure path**, which is what C1's offline rollback test now genuinely
  exercises and this proves holds live too: on a known mesh, record vert count + bbox, force
  `model.reblock_form` to fail mid-operation (e.g. drive it on a mesh/args combination that trips a real
  op error partway through the sequence, or monkeypatch the bridge process to raise after the first
  mutating op), and assert the mesh's vert count + bbox are byte-identical to the pre-call values
  **without calling `session.revert`** — proving the auto-checkpoint + rollback-on-exception fires on its
  own, not only when the agent manually reverts.

- [ ] **Step 2b: Live intake fill-ratio proof for all 7 benchmark items.** The offline B2 intake-guard
  test (`test_every_benchmark_item_intake_clears_its_class_degenerate_guard`) only proves the ASPECT half
  of "no legitimate item is blocked at blockout" — `fill_ratio` is unmeasurable offline because the
  recipe-built starting meshes are produced by live `scene.create_object`/`capabilities.invoke` calls, and
  at least one (`generated_shell`) is a deliberately OPEN mesh at intake (its recipe converts a cylinder to
  tris then runs `mesh.delete` with `type: "EDGE"` to simulate scan holes, per its item brief "needs
  manifold repair" — see the note in Task B2). Since that mesh still has some remaining
  polygons/vertices after the deletion, `_solid_volume`'s `None` path (Task A2: `None` only when the mesh
  has **zero** polygons/vertices) does not automatically apply — so `fill_ratio` is not guaranteed to
  degrade-to-pass via `None`; it may compute a real (and possibly low) number over the punctured mesh.
  With the visible bridge (reuse Step 3's instance, or run this before it), for EACH of the 7 benchmark
  items: run its `input.recipe` to build the deficient starting mesh, `pipeline.start`, `pipeline.advance`
  to `blockout`, then `pipeline.gate_check(object=<item>, stage="blockout")` and assert
  `metrics["form"]["fill_ratio_ok"] is True` for all 7 (whether via a real `fill_ratio >= fill_floor` or
  via degrade-to-pass `fill_ratio is None`). This closes the offline test's blind spot and proves BOTH gate
  paths (`aspect_within_degenerate_guard` from B2's offline test + `fill_ratio_ok` here) clear for every
  item at intake.

- [ ] **Step 3: Launch the visible Blender bridge** (background) and confirm it answers:
  `python scripts/bridge_call.py 8765 scene.info '{}'`. Sanity-check the new eye:
  `python scripts/bridge_call.py 8765 feedback.form_critique '{"object":"Cube","asset_class":"hard_surface_prop"}'`
  returns `available: true`, `preset: "ortho3"`, **≥ 3 distinct-hash** silhouette images (front/right/top;
  no persp), and a `form` block with `fill_ratio` populated.

- [ ] **Step 4: Record a baseline, then re-measure — each run TWICE to beat judge noise.** The exit gate is
  a **per-lens delta vs a recorded baseline**, not an absolute mean. Because the judge panel is stochastic
  and prompted to "default LOW when unsure", a single run's per-item variance dwarfs a 0.07 lens-mean
  rank-flip — so:
  - **Baseline:** run the altimeter on the **pre-wave** build (checkout the commit before Sub-wave A, or
    reuse `docs/reports/altimeter-baseline.md` if it is the true pre-wave reading) **twice**; each run's
    `Workflow` output is a `{reading, cards}` object where `reading["per_lens_means"]` (Task C3) is the
    per-lens mean for that run — record `per_lens_means["silhouette"]` / `["proportion"]` for both runs
    and their run-to-run spread (`max - min` across the two runs).
  - **Post:** run the altimeter on the wave build **twice**:
    `Workflow({ scriptPath: "<repo>/workflows/altimeter.mjs", args: { port: 8765, repo: "<repo>" } })`.
    The finish agent drives each item `craft_workflow.recommend → feedback.form_critique (observe) → verbs
    → pipeline.gate_check → pipeline.advance`, so the blockout gate, the enforced observation, and the
    form-craft workflows are all exercised automatically. Record each run's `reading["per_lens_means"]`,
    the run-to-run spread, and the per-item `form_critique_calls` (now present on each raw card per C3
    Step 3b).
  - (If agent nondeterminism is fixed instead, a single baseline+post pair is acceptable — but report it.)

- [ ] **Step 5: Save the reading** to `docs/reports/altimeter-form-craft.md` (date, per-class breakdown,
  `pass_rate`, per-lens **baseline mean ± spread** vs **post mean ± spread** — read directly from each
  run's `reading["per_lens_means"]` (Task C3) — the per-item `form_critique_calls`, and which items reached
  `exported`). Commit the report.

- [ ] **Step 6: Assert the re-scoped success gate** (design §9 decision 6; supersedes design §6). All
  "post-mean"/"baseline-mean" figures below are `per_lens_means[lens]` (Task C3's `aggregate()` field),
  averaged across the two runs on each side; "spread" is `max - min` of the two per-run
  `per_lens_means[lens]` values on that side — this is the concrete, computable source for the gate,
  not an informally-eyeballed number:
  - **`silhouette` post-mean − baseline-mean ≥ +1.0** AND **`proportion` post-mean − baseline-mean ≥ +1.0**,
    with each delta **exceeding 2× the max run-to-run spread** (so the lift is real, not judge noise), AND
  - **`pass_rate > 0`** (at least one item reaches a genuine senior ≥ 7.0), AND
  - **every item's `form_critique_calls ≥ 1`** (proves the in-loop form eye was actually exercised), AND
  - **every one of the 7 items still reaches `exported`** (no blockout deadlock/regression — cross-checked
    by the offline 7-item intake-guard test in B2 and confirmed live here).
  - **`mean_overall ≥ 5.5` is explicitly NOT this wave's gate.** It is arithmetically unreachable from a
    3-of-5-lens lift (even +2.0 on all three form lenses gives ≈5.1); it is a **later cumulative target**
    once material/topology waves also land. Record `mean_overall` for the trend, do not gate on it.
  - Do **not** hand-tune reference targets per benchmark item — the inputs are held out; measure
    generalization.

**The form-craft wave is done when:** all three sub-waves are committed with parity + full offline suite
green, the real-Blender smoke passes the blockout-gated + observation-enforced five walks and the reblock
recoverability round-trip, and `docs/reports/altimeter-form-craft.md` shows silhouette AND proportion each
lifted ≥ +1.0 over baseline (beyond run-to-run spread), `pass_rate > 0`, every item exercising
`feedback.form_critique`, and every item still reaching `exported`.

---

## Self-Review notes

- **Spec coverage (as corrected by design §9):** structured `form_critique` = A3; per-subject
  target+tolerance reference = A1; form knowledge pack = A4; real fill metric + degenerate guard = A2;
  blockout stage (degenerate guard + enforced observation) = B1/B2; form-craft verbs (transactional
  reblock, feature-aware refine, proportion) + workflows = C1/C2; altimeter wiring = C3; per-lens-delta
  re-measure + re-scoped gate = FINAL.
- **Design §9 corrections honored:** (1) blockout gate = degenerate guard (`fill_ratio_ok` +
  `aspect_within_degenerate_guard`) + enforced recorded `form_critique` observation, NOT a
  proportion-quality gate; (2) real `fill_ratio` added, `boxiness` kept but documented as bbox cubeness;
  (3) `form_critique` structured + ortho-only (`ortho3`) + records the observation + material-restore
  proven; (3b) target+tolerance per subject, dead aspect lower bound dropped; (4) `reblock_form`
  checkpoint-safe by mechanism (auto-checkpoint, revert-on-exception, bbox-relative merge); (5)
  `silhouette_refine` feature-angle-aware (preserves hard-surface corners); (6) `form_critique` wired into
  `altimeter.mjs` + instrumented; (7) success re-scoped to per-lens deltas run twice, `mean_overall ≥ 5.5`
  demoted to a later cumulative target.
- **Parity discipline:** the 4 new tools (`feedback.form_critique` + 3 `model.*` verbs) each land
  server-spec + add-on-command in the same task with `pytest tests/test_parity.py` green before commit. All
  4 data registries (`_PROFILES`, `_PACKS`, `_WORKFLOWS`, and now `_GATES`) are edited in both copies per
  task and asserted identical by dedicated equality tests.
- **Every stage-list / registry assertion updated in lockstep:** `test_pipeline_core` (registry +
  gate-profile map + bake/material flow + blockout-order + enforced-observation + `_GATES` equality),
  `test_pipeline` (offline `gate_check(blockout)` pass+reject), `test_knowledge` (`list_packs`),
  `test_smoke_headless` (**all five** walks), `test_benchmark` (item stages + 7-item intake guard), and the
  two craft-workflow suites (new ids + from-scratch fallback + repair-order lock).
- **No fake "believable-form" floor:** the objective gate is only a degenerate guard; believable form is
  agent-carried (enforced observation) and judge-measured. This is the exact inversion the red-team
  required, and it removes the deadlock (a legit 6.29:1 bracket now passes; only a >20:1 needle or a
  collapsed mesh fails).
- **Mesh safety by mechanism, not warning:** `reblock_form` auto-checkpoints before the first mutating op
  and rolls back on any exception (offline test + live round-trip), and merges bbox-relative so an
  arbitrary-scale generated mesh cannot be welded to a point.

---

## Red-team resolution ledger

Every CRITICAL [1..10] and IMPORTANT [1..20] finding maps to the task/section that resolves it. A second
adversarial verification pass over this plan (post-draft) found 5 further issues, tracked separately as
V1–V5 in **## Second-pass verification fixes** below (not renumbered into C/I to keep this table's
existing references stable).

| # | Severity | Finding (short) | Resolved by |
|---|---|---|---|
| C1 | CRITICAL | Only 1 of 5 real-Blender smoke walks updated for the new stage | **B2** Step 4 (all five: PipeHero, WorkflowHero, GeneratedWorkflowHero, OrganicWorkflowHero, CritPipeHero) + **FINAL** Step 2 |
| C2 | CRITICAL | `boxiness` is not fill; add a real fill ratio + cross-vs-cube test | **A2** (`_solid_volume`/`fill_ratio`, octa-vs-cube discrimination test) |
| C3 | CRITICAL | Gate is a no-op for its target cases; make it bite | **A2** (real fill) + **B1** (enforced recorded `form_critique` observation is the forcing function; gate is a degenerate floor by design §9.1) |
| C4 | CRITICAL | Gate blocks the legit `hard_surface_bracket` (aspect 6.29) | **A1**+**B1** (degenerate guard aspect ≤ 20, not a believable range) + **B2** 7-item intake-guard test |
| C5 | CRITICAL | Gate gives zero form discipline on the items that need it | **A3** (`form_critique` carries the judgment) + **B1** (enforced observation) + FINAL judge lenses |
| C6 | CRITICAL | `reblock_form` leaves a half-mutated mesh on mid-op failure | **C1** (try/except → `session_store.restore` → re-raise; offline rollback test) |
| C7 | CRITICAL | `reblock_form` "checkpoint-safe" was a warning string, not a mechanism | **C1** (auto `session.checkpoint(label="reblock:pre")` before first op; returns label; `session.revert` in postcheck) |
| C8 | CRITICAL | `boxiness = bbox_volume/longest³` measures nothing about fill | **A2** (replace the gate signal with real solid-volume fill; boxiness kept only as a labeled bbox-cubeness readout) |
| C9 | CRITICAL | Gate passes trivially → no primary-masses-first forcing | **B1** (advance out of blockout requires a recorded `form_critique`) + **C2** (blockout workflows lead with `form_critique`) |
| C10 | CRITICAL | `mean_overall ≥ 5.5` arithmetically unreachable by form-only lift | **FINAL** Step 6 (per-lens deltas ≥ +1.0; `mean_overall` demoted to a later cumulative target) |
| I1 | IMPORTANT | No server↔addon `_GATES` equality test | **B1** (`test_server_and_addon_gate_profiles_identical`) |
| I2 | IMPORTANT | Blockout gate has no offline coverage of real paths/values | **B1** (`gate_check(stage="blockout")` fake-bpy test, in-guard + out-of-guard) |
| I3 | IMPORTANT | No offline test exercises real form-metric gating | **B1** (blockout `gate_check` pass reads `form.fill_ratio_ok`/`aspect_within_degenerate_guard` end-to-end) |
| I4 | IMPORTANT | No test proves the gate REJECTS bad form | **B1** (needle dims (40,1,1) → `aspect_within_degenerate_guard` False → `gates_pass` False; note: corrected reject uses aspect > 20, superseding the red-team's literal 8:1 which is now a legit prop) |
| I5 | IMPORTANT | `form_critique` material-restore never executed by the test | **A3** (extend fake `bpy.data` with a `materials` collection + give Cube a mesh so `render_silhouette` runs; assert materials byte-identical before/after) |
| I6 | IMPORTANT | `form_critique` not wired into the measurement loop | **C3** (finish prompt observes form at blockout) + **FINAL** Step 4/6 |
| I7 | IMPORTANT | Reference targets are wide class bands that mislead | **A1** (per-class target+tolerance; dead aspect lower bound dropped) + **A3** (measured delta vs target) |
| I8 | IMPORTANT | `form_critique` bundle shallow / not structured | **A3** (structured `checklist{reads_all_angles, proportion_ok, primary_masses_ok, fixes}`, seeded from measured delta) |
| I9 | IMPORTANT | Multi-angle silhouette untested; persp preset wrong | **A3** (default `ortho3` = front/right/top, no persp; offline preset test) + **FINAL** Step 3 (≥3 distinct-hash live) |
| I10 | IMPORTANT | No verb can move a boxiness-blocked item → deadlock | **B1** (gate no longer uses boxiness/believable range) + **C1** (`proportion_adjust`/`reblock_form`) + **FINAL** Step 6 (all 7 reach `exported`) |
| I11 | IMPORTANT | `boxiness` documented incorrectly as fill/spindly | **A2** (renamed to bbox cubeness in docstring/pack; real fill is separate) |
| I12 | IMPORTANT | `form_recovery_reblock` at `['repair','blockout']` silently reorders repair | **C2** (scoped to `['blockout']` only + explicit repair-order lock test) |
| I13 | IMPORTANT | Zero tests exercise the recoverability path | **C1** (offline mid-op-failure rollback test) + **FINAL** Step 2 (live checkpoint→reblock→revert round-trip) |
| I14 | IMPORTANT | Absolute merge distance collapses arbitrary-scale meshes | **C1** (bbox-relative `merge_fraction` × diagonal, clamped; 0.02-unit-mesh test) |
| I15 | IMPORTANT | Gate is a no-op for the worst class (generated_cleanup) | **B1** (degenerate guard as a floor) + **A3**/**C2** (form recovery driven by the enforced observation + `reblock_form`, judged by lenses) |
| I16 | IMPORTANT | `weakest_lens` rank-flip is within 0.07 judge noise | **FINAL** Step 4/6 (absolute per-lens delta ≥ +1.0, each run twice, delta must exceed 2× spread) |
| I17 | IMPORTANT | New form eye never wired into the measurement loop | **C3** (finish prompt + `form_critique_calls` instrumentation) + **FINAL** Step 6 (assert every item ≥ 1 call) |
| I18 | IMPORTANT | `reblock_form` too weak to move the blob | **C1** (bbox-relative reblock) + **FINAL** Step 4 (measure blob/shell entry vs exit; if unmoved, escalate to remesh-based recovery — noted as the next lever, not shipped blind) |
| I19 | IMPORTANT | `silhouette_refine` uniform smooth degrades hard_surface | **C1** (feature-angle-aware: preserves sharp edges) + **C2** (`hard_surface.blockout_pass` sets `feature_angle=40`) |
| I20 | IMPORTANT | New gate-fail path can regress the aggregate to 0 | **B2** (7-item intake-guard test proves none newly fail) + **FINAL** Step 6 (confirm all 7 reach `exported`) |

*(Red-team "minor: 12" items are out of scope per the mandate — only CRITICAL + IMPORTANT are binding.)*

---

## Second-pass verification fixes

A second adversarial verification pass re-checked this plan's own TDD artifacts (fixtures, gate math,
instrumentation wiring, rollback tests, and the intake-guard proof) rather than the design. All 5 findings
were concrete bugs/gaps in the plan text itself and are now fixed in place (not deferred):

| # | Severity | Finding (short) | Fixed in |
|---|---|---|---|
| V1 | HIGH | `_CUBE_QUADS`' bottom face `[0,1,2,3]` is wound INWARD, so `_solid_volume` sums to 16/3 (not 8) and `fill_ratio` comes out 0.667 — failing the plan's own `pytest.approx(1.0, abs=0.05)` assertion | **A2** Step 1 (`_CUBE_QUADS` bottom face re-wound to `[0,3,2,1]`) + **A2** Interfaces/docstring note making explicit that `_solid_volume` assumes consistent outward winding, which real meshes get from `repair` running before `blockout` and `model.reblock_form` calling `normals_make_consistent()` |
| V2 | MEDIUM | The FINAL success gate needs per-lens MEANS, but `scorecard.py::aggregate()` computes `lens_totals` internally only to pick `weakest_lens`, then discards it — no field exists to read the gate from | **C3** Step 3c (`aggregate()` returns `per_lens_means`) + new `tests/evals/test_scorecard.py::test_aggregate_reports_per_lens_means` + **FINAL** Steps 4–6 reworded to read `reading["per_lens_means"]` explicitly |
| V3 | MEDIUM | `form_critique_calls` is added to the finish prompt/`FINISH_SCHEMA` but `altimeter.mjs` Stage-2 assemble rebuilds each raw card from a fixed field set and never copies it — absent from `raw_cards.json` and the report | **C3** Step 3b (assemble adds `form_critique_calls: (fin && fin.form_critique_calls) \|\| 0`) + `test_stage2_assemble_propagates_form_critique_calls_into_raw_card` |
| V4 | MEDIUM | `test_reblock_form_rolls_back_on_mid_op_failure` was vacuous — the fake ops never mutate `obj.data.vertices`, so the byte-identity assertion passed even if `session.restore` was never called | **C1** Step 1 rewrite (`remove_doubles` fake genuinely mutates the mesh, a LATER op fails, byte-identity is asserted against the mutated-then-restored state) + **FINAL** Step 2 (live forced-mid-op-failure assertion, distinct from the clean checkpoint→reblock→revert round-trip) |
| V5 | LOW | B2's intake-guard test proves only the aspect half of "no legitimate item is blocked at blockout"; `fill_ratio_ok` is untested offline for the recipe-built meshes | **FINAL** Step 2b (live per-item `pipeline.gate_check(stage="blockout")` proving `fill_ratio_ok` for all 7 items) + clarifying note in **B2** and **FINAL** Step 2b that `generated_shell`'s intake mesh is deliberately OPEN (cylinder → quads_to_tris → `mesh.delete type:"EDGE"`), so its `fill_ratio` is not guaranteed to degrade-to-pass via `None` and must be checked live |

