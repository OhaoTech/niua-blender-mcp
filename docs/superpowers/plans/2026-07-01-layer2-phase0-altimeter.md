# Layer 2 Phase 0 — The Altimeter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the vestigial single-crate battery + stub judge with a diverse held-out
benchmark and a real perceptual "altimeter" that measures *senior quality* (not just gate-pass),
so every later Layer-2 wave has a number to move.

**Architecture:** Three pure-Python pieces built with TDD — a **benchmark** module (diverse
input items + loader), **senior rubrics**, and a **scorecard** module (combine objective gate
pass + multi-lens judge scores into a per-item senior score, then aggregate a benchmark
reading). Plus a **workflow** (`workflows/altimeter.mjs`) that drives the live pipeline per
item, runs a skeptical multi-lens judge panel anchored by the objective gates, and aggregates
the reading. The old convergence-loop stack (`judge.py` stub, `harness.py`, `battery/`,
`eval_observe.py`, `converge_modeling.mjs`) is retired. The **baseline run** is Phase 0's
final, live, deliberately-triggered step.

**Tech Stack:** Python 3.14, pytest, pure-Python (no bpy) for benchmark/scorecard so they're
unit-testable offline; the Workflow tool (`.mjs`) for the live judged run against a visible
Blender bridge.

## Global Constraints

- Standalone repo — **zero niua/Godot references in code**; benchmark inputs are generic
  Blender meshes/briefs.
- `from __future__ import annotations` at the top of every new `.py`.
- Benchmark and scorecard modules are **pure Python, no `bpy`, no network** — fully offline-testable.
- Objective gates remain the **un-gameable floor**: a benchmark item can only reach a senior
  score if its gates pass. The judge only arbitrates the taste delta above the floor.
- Reuse the existing `evals/gates.py::check_gates` and `evals/stage_gates.py::stage_gates`
  (keep them — they become the scorecard's objective channel). Do **not** duplicate gate logic.
- TDD: write the failing test, watch it fail, implement minimally, watch it pass, commit.
- Run the whole suite (`pytest -q`) green before each commit that touches shared modules.

---

## File Structure

**Create:**
- `src/niua_blender_mcp/evals/benchmark/__init__.py` — loader: `list_items()`, `load_item(id)`.
- `src/niua_blender_mcp/evals/benchmark/items/<id>/item.json` — one per benchmark item.
- `src/niua_blender_mcp/evals/benchmark/rubrics/<class>.md` — senior rubric per asset class.
- `src/niua_blender_mcp/evals/scorecard.py` — `score_item()`, `aggregate()`.
- `tests/evals/test_benchmark.py`, `tests/evals/test_scorecard.py`.
- `workflows/altimeter.mjs` — the live judged benchmark runner.

**Delete (retire the old-loop stack):**
- `src/niua_blender_mcp/evals/judge.py`, `src/niua_blender_mcp/evals/harness.py`,
  `src/niua_blender_mcp/evals/battery/` (whole dir),
  `scripts/eval_observe.py`, `workflows/converge_modeling.mjs`,
  `tests/evals/test_judge.py`, `tests/evals/test_harness.py`, `tests/evals/test_battery.py`.

**Keep untouched:** `evals/gates.py`, `evals/stage_gates.py` (live objective channel),
the whole `pipeline`/`feedback`/`asset_class`/`knowledge`/`craft_workflow` surface.

---

## Task 1: Benchmark item schema + loader

**Files:**
- Create: `src/niua_blender_mcp/evals/benchmark/__init__.py`
- Create: `src/niua_blender_mcp/evals/benchmark/items/hard_surface_crate/item.json`
- Create: `src/niua_blender_mcp/evals/benchmark/rubrics/hard_surface_prop.md`
- Test: `tests/evals/test_benchmark.py`

**Interfaces:**
- Produces:
  - `list_items() -> list[str]` — sorted benchmark item ids (directory names under `items/`).
  - `load_item(item_id: str) -> dict` — the item's `item.json` parsed, with an added
    `"rubric_text": str` key resolved from `rubrics/<rubric>.md`. Raises `KeyError(item_id)`
    if the item dir is missing, `KeyError(rubric)` if the rubric file is missing.

**Item JSON shape** (the contract every item file follows):
```json
{
  "id": "hard_surface_crate",
  "asset_class": "hard_surface_prop",
  "brief": "A wooden shipping crate: chamfered edges, shallow recessed side panels, game-ready.",
  "input": {
    "recipe": [
      {"tool": "scene.create_object", "args": {"type": "CUBE"}},
      {"tool": "mesh.subdivide", "args": {"cuts": 2}}
    ]
  },
  "stages": ["repair", "retopo", "uv", "bake", "material", "optimize", "export_preflight"],
  "rubric": "hard_surface_prop",
  "senior_threshold": 7.0
}
```
(`input.recipe` describes the deficient STARTING mesh the agent must finish; `<subject>` object
name is injected by the runner, so recipes omit the name.)

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_benchmark.py
from niua_blender_mcp.evals.benchmark import list_items, load_item


def test_list_items_includes_seed():
    assert "hard_surface_crate" in list_items()
    assert list_items() == sorted(list_items())


def test_load_item_resolves_rubric_text():
    item = load_item("hard_surface_crate")
    assert item["asset_class"] == "hard_surface_prop"
    assert item["senior_threshold"] == 7.0
    assert item["stages"][0] == "repair"
    assert isinstance(item["input"]["recipe"], list)
    assert "0-10" in item["rubric_text"]  # the rubric markdown was loaded and inlined


def test_load_item_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        load_item("does_not_exist")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/evals/test_benchmark.py -q`
Expected: FAIL (module `benchmark` not importable).

- [ ] **Step 3: Create the seed rubric**

Create `src/niua_blender_mcp/evals/benchmark/rubrics/hard_surface_prop.md` by copying the
existing senior rubric (it already has score anchors) from
`src/niua_blender_mcp/evals/battery/modeling_prop/rubric.md` verbatim (do this before deleting
the battery in Task 4). It must contain the "0-10" scale text the test asserts.

- [ ] **Step 4: Create the seed item**

Create `src/niua_blender_mcp/evals/benchmark/items/hard_surface_crate/item.json` with the JSON
shape above.

- [ ] **Step 5: Write the loader**

```python
# src/niua_blender_mcp/evals/benchmark/__init__.py
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
```

- [ ] **Step 6: Run tests to verify pass**

Run: `pytest tests/evals/test_benchmark.py -q`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add src/niua_blender_mcp/evals/benchmark tests/evals/test_benchmark.py
git commit -m "feat: add layer2 benchmark loader + seed item"
```

---

## Task 2: Scorecard — per-item score + aggregation

**Files:**
- Create: `src/niua_blender_mcp/evals/scorecard.py`
- Test: `tests/evals/test_scorecard.py`

**Interfaces:**
- Consumes: `evals/gates.py::check_gates` (already present) for the objective floor.
- Produces:
  - `score_item(item: dict, gates_pass: bool, lens_scores: dict[str, float]) -> dict`
    Returns `{"id", "asset_class", "gates_pass", "lens_scores", "overall", "senior_pass"}`
    where `overall` is the mean of `lens_scores` values (0.0 if empty), and
    `senior_pass` is `gates_pass and overall >= item["senior_threshold"]`.
    **The floor rule:** if `gates_pass` is False, `overall` is forced to `0.0` regardless of
    lens scores (objective gates cap the judge).
  - `aggregate(cards: list[dict]) -> dict`
    Returns `{"n_items", "n_senior_pass", "pass_rate", "mean_overall",
    "per_class": {class: {"n", "n_pass", "mean_overall"}},
    "weakest_lens": <lens name with lowest mean across cards, or None>}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_scorecard.py
from niua_blender_mcp.evals.scorecard import score_item, aggregate

ITEM = {"id": "x", "asset_class": "hard_surface_prop", "senior_threshold": 7.0}


def test_gates_fail_forces_zero():
    card = score_item(ITEM, gates_pass=False, lens_scores={"silhouette": 9.0, "topology": 9.0})
    assert card["overall"] == 0.0
    assert card["senior_pass"] is False


def test_pass_needs_gates_and_threshold():
    card = score_item(ITEM, gates_pass=True, lens_scores={"silhouette": 8.0, "topology": 6.0})
    assert card["overall"] == 7.0
    assert card["senior_pass"] is True


def test_below_threshold_not_senior():
    card = score_item(ITEM, gates_pass=True, lens_scores={"silhouette": 5.0, "topology": 6.0})
    assert card["senior_pass"] is False


def test_aggregate_reports_breakdown_and_weakest_lens():
    cards = [
        score_item(ITEM, True, {"silhouette": 8.0, "topology": 4.0}),
        score_item(ITEM, True, {"silhouette": 9.0, "topology": 5.0}),
    ]
    agg = aggregate(cards)
    assert agg["n_items"] == 2
    assert agg["per_class"]["hard_surface_prop"]["n"] == 2
    assert agg["weakest_lens"] == "topology"
    assert 0.0 <= agg["pass_rate"] <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/evals/test_scorecard.py -q`
Expected: FAIL (module `scorecard` not found).

- [ ] **Step 3: Write the implementation**

```python
# src/niua_blender_mcp/evals/scorecard.py
from __future__ import annotations


def score_item(item: dict, gates_pass: bool, lens_scores: dict[str, float]) -> dict:
    if gates_pass and lens_scores:
        overall = sum(lens_scores.values()) / len(lens_scores)
    else:
        overall = 0.0
    threshold = float(item.get("senior_threshold", 7.0))
    return {
        "id": item.get("id"),
        "asset_class": item.get("asset_class"),
        "gates_pass": gates_pass,
        "lens_scores": dict(lens_scores),
        "overall": overall,
        "senior_pass": bool(gates_pass) and overall >= threshold,
    }


def aggregate(cards: list[dict]) -> dict:
    n = len(cards)
    n_pass = sum(1 for c in cards if c["senior_pass"])
    mean_overall = (sum(c["overall"] for c in cards) / n) if n else 0.0
    per_class: dict[str, dict] = {}
    for c in cards:
        bucket = per_class.setdefault(c["asset_class"], {"n": 0, "n_pass": 0, "_sum": 0.0})
        bucket["n"] += 1
        bucket["n_pass"] += 1 if c["senior_pass"] else 0
        bucket["_sum"] += c["overall"]
    for bucket in per_class.values():
        bucket["mean_overall"] = bucket.pop("_sum") / bucket["n"]
    lens_totals: dict[str, list[float]] = {}
    for c in cards:
        for lens, val in c["lens_scores"].items():
            lens_totals.setdefault(lens, []).append(val)
    weakest = min(lens_totals, key=lambda k: sum(lens_totals[k]) / len(lens_totals[k])) if lens_totals else None
    return {
        "n_items": n,
        "n_senior_pass": n_pass,
        "pass_rate": (n_pass / n) if n else 0.0,
        "mean_overall": mean_overall,
        "per_class": per_class,
        "weakest_lens": weakest,
    }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/evals/test_scorecard.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/niua_blender_mcp/evals/scorecard.py tests/evals/test_scorecard.py
git commit -m "feat: add altimeter scorecard + aggregation"
```

---

## Task 3: Broaden the benchmark to a diverse held-out set

**Files:**
- Create: `src/niua_blender_mcp/evals/benchmark/items/<id>/item.json` (6 new items)
- Create: `src/niua_blender_mcp/evals/benchmark/rubrics/<class>.md` (3 new rubrics)
- Modify: `tests/evals/test_benchmark.py`

**Interfaces:** Consumes Task 1's loader unchanged.

The diverse set covers the asset classes the finisher must handle. Each item's `input.recipe`
creates a characteristic *deficient* starting mesh (the thing the agent must finish). Use only
Layer-1 tools that exist (`scene.create_object`, `mesh.subdivide`,
`capabilities.invoke` for `mesh.quads_convert_to_tris`, `object` transforms).

Items to add (one `item.json` each, following Task 1's shape):

| id | asset_class | starting mesh (recipe intent) |
|----|-------------|-------------------------------|
| `hard_surface_bracket` | `hard_surface_prop` | cube, scaled non-uniformly, unapplied transform |
| `organic_rock` | `organic_prop` | ico_sphere subdivided + randomized (lumpy blob) |
| `organic_pumpkin` | `organic_prop` | uv_sphere, squashed, ngon poles |
| `generated_blob` | `generated_cleanup` | cube → subdivide 3 → triangulate (noisy scan-like) |
| `generated_shell` | `generated_cleanup` | cylinder, triangulated, loose verts |
| `from_scratch_barrel` | `from_scratch_prop` | cylinder primitive only (author from near-scratch) |

Add rubrics `organic_prop.md`, `generated_cleanup.md`, `from_scratch_prop.md` — each a copy of
the hard-surface rubric structure with class-appropriate emphasis (organic: silhouette/flow over
hard edges; generated_cleanup: topology recovery + watertightness; from_scratch: proportion +
believable form). Each MUST keep the "0-10" scale line and the "## Score anchors" section.

- [ ] **Step 1: Extend the failing test**

```python
# add to tests/evals/test_benchmark.py
def test_benchmark_is_diverse():
    items = [load_item(i) for i in list_items()]
    classes = {i["asset_class"] for i in items}
    assert classes >= {"hard_surface_prop", "organic_prop", "generated_cleanup", "from_scratch_prop"}
    assert len(items) >= 7
    for i in items:
        assert i["input"]["recipe"], f"{i['id']} has empty recipe"
        assert "0-10" in i["rubric_text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/evals/test_benchmark.py::test_benchmark_is_diverse -q`
Expected: FAIL (only 1 item / 1 class present).

- [ ] **Step 3: Add the 6 item.json files and 3 rubric files** (as tabled above).

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/evals/test_benchmark.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/niua_blender_mcp/evals/benchmark
git commit -m "feat: broaden altimeter benchmark to 4 asset classes"
```

---

## Task 4: Retire the vestigial old-loop stack

**Files:**
- Delete: `src/niua_blender_mcp/evals/judge.py`, `src/niua_blender_mcp/evals/harness.py`,
  `src/niua_blender_mcp/evals/battery/` (dir), `scripts/eval_observe.py`,
  `workflows/converge_modeling.mjs`,
  `tests/evals/test_judge.py`, `tests/evals/test_harness.py`, `tests/evals/test_battery.py`.

- [ ] **Step 1: Re-confirm nothing live depends on them**

Run:
```bash
grep -rn --include=*.py -E "evals\.(judge|harness|battery)|stub_judge|run_task|load_task|eval_observe" src blender_addon | grep -v "evals/battery"
```
Expected: **no output** (only the files being deleted referenced these). If anything in
`src/` or `blender_addon/` prints, STOP and resolve before deleting.

- [ ] **Step 2: Delete the files**

```bash
git rm -r src/niua_blender_mcp/evals/judge.py src/niua_blender_mcp/evals/harness.py \
  src/niua_blender_mcp/evals/battery scripts/eval_observe.py workflows/converge_modeling.mjs \
  tests/evals/test_judge.py tests/evals/test_harness.py tests/evals/test_battery.py
```

- [ ] **Step 3: Run the full suite green**

Run: `pytest -q`
Expected: PASS, no collection errors, no import errors from the deletions.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: retire vestigial convergence-loop eval stack"
```

---

## Task 5: The altimeter runner workflow

**Files:**
- Create: `workflows/altimeter.mjs`

**Interfaces:** Consumes `benchmark.list_items/load_item` (via a small python `-c` call in an
agent step) and `scorecard.score_item/aggregate` (imported by a final python step). Drives the
live bridge via `scripts/bridge_call.py` (existing).

The workflow is the live judged run. Per benchmark item, a pipeline stage:
1. **Setup** — build the item's deficient input mesh from `input.recipe` (rename to a unique
   subject), then `pipeline.start(asset_class=...)`.
2. **Finish** — an agent acting as a senior finisher drives the pipeline stage-by-stage
   (`craft_workflow.recommend` → curated verbs / Layer-1 tools → `pipeline.gate_check` →
   `pipeline.advance`) toward the brief, using `feedback.critique` as its eyes. Bounded.
3. **Observe** — capture the objective `gates_pass` (did every stage's gates pass) + save the
   eye renders (`feedback.topology`, `feedback.capture_views`) to a per-item dir.
4. **Judge** — a skeptical multi-lens panel (`parallel`): lenses = `silhouette`, `proportion`,
   `topology`, `material_read`, `design_intent`; each reads the saved PNGs + the item's
   `rubric_text` and returns `{score 0-10, critique}`. Median per lens → `lens_scores`.
5. **Score** — `score_item(item, gates_pass, lens_scores)`.

After all items: `aggregate(cards)` → write the reading to
`docs/reports/altimeter-<runid>.md` (uncommitted; human reviews). The workflow `meta.name` is
`altimeter`; args `{port, repo, maxStageRounds}`.

- [ ] **Step 1: Write the workflow script** (structure — the panel is the verify stage):

```javascript
// workflows/altimeter.mjs
export const meta = {
  name: 'altimeter',
  description: 'Run the Layer-2 benchmark through the live pipeline and score senior quality.',
  phases: [{ title: 'Setup' }, { title: 'Finish' }, { title: 'Judge' }, { title: 'Score' }],
}
const PORT = (args && args.port) || 8765
const REPO = (args && args.repo) || '/home/frankyin/Desktop/lab/lab-niua-blender'
const CALL = `python ${REPO}/scripts/bridge_call.py ${PORT}`
const LENSES = ['silhouette', 'proportion', 'topology', 'material_read', 'design_intent']
const JUDGE_SCHEMA = { type: 'object', properties: { score: { type: 'number' }, critique: { type: 'string' } }, required: ['score', 'critique'] }

const ids = JSON.parse(await agent(
  `Run and return ONLY stdout: python -c "import sys;sys.path.insert(0,'${REPO}/src');from niua_blender_mcp.evals.benchmark import list_items;import json;print(json.dumps(list_items()))"`,
  { phase: 'Setup', label: 'list items' }))

const cards = await pipeline(ids,
  (id) => agent(`Finish benchmark item ${id} as a senior game-asset artist against the live Blender on port ${PORT}. Load it via benchmark.load_item, build input.recipe as subject "bench_${id}", pipeline.start, then drive each stage (craft_workflow.recommend -> verbs -> pipeline.gate_check -> pipeline.advance) using feedback.critique as your eyes. Save eye renders. Return JSON {id, subject, gates_pass, images:[paths]}.`,
    { phase: 'Finish', label: `finish:${id}`, schema: { type: 'object', properties: { id: {type:'string'}, subject:{type:'string'}, gates_pass:{type:'boolean'}, images:{type:'array', items:{type:'string'}} }, required:['id','gates_pass','images'] } }),
  async (fin, id) => {
    const votes = await parallel(LENSES.map(lens => () =>
      agent(`Judge benchmark item ${id} via the "${lens}" lens. Open the renders with your Read tool: ${(fin.images||[]).join(', ')}. Score 0-10 against this rubric (default LOW when unsure):\n<load rubric_text for ${id} via benchmark.load_item>\nReturn {"score","critique"}.`,
        { phase: 'Judge', label: `judge:${id}:${lens}`, schema: JUDGE_SCHEMA })))
    const lens_scores = {}
    LENSES.forEach((lens, k) => { const v = votes[k]; if (v) lens_scores[lens] = v.score })
    return await agent(`Run and return ONLY stdout: python -c "import sys,json;sys.path.insert(0,'${REPO}/src');from niua_blender_mcp.evals.benchmark import load_item;from niua_blender_mcp.evals.scorecard import score_item;print(json.dumps(score_item(load_item('${id}'), ${fin.gates_pass ? 'True' : 'False'}, ${JSON.stringify(lens_scores)})))"`,
      { phase: 'Score', label: `score:${id}` }).then(s => JSON.parse(s))
  })

const reading = await agent(`Run and return ONLY stdout: python -c "import sys,json;sys.path.insert(0,'${REPO}/src');from niua_blender_mcp.evals.scorecard import aggregate;print(json.dumps(aggregate(${JSON.stringify(cards.filter(Boolean))})))"`,
  { phase: 'Score', label: 'aggregate' })
return { reading: JSON.parse(reading), cards: cards.filter(Boolean) }
```

- [ ] **Step 2: Structural sanity check** (no live Blender needed)

Run: `node --check workflows/altimeter.mjs`
Expected: no syntax error. (Full behavior is exercised in Task 6 against a live Blender.)

- [ ] **Step 3: Commit**

```bash
git add workflows/altimeter.mjs
git commit -m "feat: add altimeter benchmark runner workflow"
```

---

## Task 6: Baseline run (LIVE — deliberately triggered, not in the TDD loop)

**Prerequisite:** a visible Blender serving the bridge on port 8765:
`blender --python scripts/blender_gui.py -- <repo>/blender_addon 8765 0`
(eyes need a GL context; a pure `--background` run returns `available:false` and the judge has
nothing to look at).

- [ ] **Step 1:** Launch the visible Blender bridge (background) and confirm it answers
  `python scripts/bridge_call.py 8765 scene.info '{}'`.
- [ ] **Step 2:** Run the workflow:
  `Workflow({ scriptPath: "<repo>/workflows/altimeter.mjs", args: { port: 8765, repo: "<repo>" } })`
- [ ] **Step 3:** Save the returned `reading` to `docs/reports/altimeter-baseline.md` with the
  date, the per-class breakdown, `pass_rate`, `mean_overall`, and `weakest_lens`. This is the
  **baseline number** every later wave must beat. Commit the report.
- [ ] **Step 4:** Sanity-verify the eyes actually rendered (open 2–3 saved PNGs and confirm the
  topology overlay is readable, not gray clay — the render-bug regression check).

**Phase 0 is done when:** the benchmark loads, the scorecard math is green, the old stack is
gone, the workflow runs against a live Blender, and `docs/reports/altimeter-baseline.md` records
the current pipeline's honest senior score across the 4 classes.

---

## Self-Review notes

- **Spec coverage:** benchmark (W0.1) = Tasks 1+3; altimeter judge+scorecard (W0.2) = Tasks 2+5;
  retire vestigial (W0.2) = Task 4; baseline run (W0.3) = Task 6. All roadmap Phase-0 items covered.
- **Floor rule** is enforced in one place (`score_item`) and asserted by
  `test_gates_fail_forces_zero` — the judge cannot lift a gate-failing asset.
- **No duplicate gate logic:** scorecard consumes the existing `check_gates`; gates/stage_gates kept.
- **Types consistent:** `score_item(item, gates_pass, lens_scores)` / `aggregate(cards)` names match
  between Task 2, Task 5's python calls, and the tests.
