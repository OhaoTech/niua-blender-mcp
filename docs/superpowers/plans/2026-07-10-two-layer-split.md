# Two-Layer Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Separate the codebase into two enforced layers — **interface** (generic Blender-MCP translation: hands, raw eyes, session, glue) and **finishing** (our opinionated tool: gates, asset classes, readiness/preservation, finisher, benchmark) — in one repo, with an import-direction test.

**Architecture:** No tool is renamed, added, or removed — the MCP surface is byte-identical before and after (parity test + live bench prove it). Only module organization changes: policy code moves into `finishing/` packages on both sides; policy tools register from dedicated policy domain modules (auto-discovery makes this free). Rule: **finishing may import interface; interface must never import finishing.**

## Global Constraints

- **Tool surface frozen:** every tool name and its params stay identical. `tests/test_parity.py` green; the live objective bench must stay byte-identical (readiness 0.36/0.36/0.36/0.24/0.28, preservation 1.0 in baseline mode).
- **Classification rule:** a module is *finishing* if it encodes game-asset policy (budgets, gate thresholds, PBR/LOD/collision conventions, engine profiles, done-definitions, do-no-harm); it is *interface* if it is neutral translation/measurement (drive an operator, render a view, count triangles, snapshot/restore).
- **Import direction:** interface modules must not import from `finishing` (or `evals`). Policy domain modules are the only `domains/` files allowed to.
- **Offline suite green before every commit:** `NIUA_SKIP_BLENDER=1 python -m pytest -q` (currently 715 passed, 71 skipped).
- Implementers hitting an unlisted classification edge: STOP and report (don't guess).

## Known classification (move lists)

**Addon → `blender_addon/niua_mcp_bridge/finishing/`:** `core/gates.py`, `core/asset_classes.py`, `core/preservation_ledger.py`, `core/engine_metrics.py`, `core/material_metrics.py`, `core/export_profiles.py`.
**Addon stays interface:** `core/{capture, silhouette, silhouette_metrics, uv_metrics, orientation_metrics, overlay, session, context}.py` and all hands domains.
**Addon policy COMMANDS move to a new `domains/finishing_feedback.py`:** `feedback.quality`, `feedback.critique`, `feedback.capture_intake`, `feedback.preservation`, `feedback.readiness` (from `domains/feedback.py`) + `io.profile_validate` (from `domains/io.py`). `domains/feedback.py` keeps capture/capture_views/silhouette/turntable. `domains/asset_class.py` stays in place but is a declared policy domain.
**Server → `src/niua_blender_mcp/finishing/`:** `asset_classes.py`. `evals/` stays where it is but is declared finishing-layer. Server SPECS mirror the addon split: new `src/niua_blender_mcp/domains/finishing_feedback.py` takes the same 6 tool specs out of `domains/feedback.py` and `domains/io.py`.

---

### Task A: Addon-side split

**Files:** create `blender_addon/niua_mcp_bridge/finishing/__init__.py` (docstring: the policy layer + the import-direction rule); `git mv` the 6 core modules listed above into `finishing/`; create `domains/finishing_feedback.py` (move the 6 policy handlers + their COMMANDS entries, plus private helpers used only by them, e.g. `_GATE_GROUPS`, `_hashable`, `_quality_compact`, quality's sub-metric helpers if policy-only); retarget every importer (grep `engine_metrics|material_metrics|export_profiles|asset_classes|preservation_ledger|core.gates|core import gates` across addon + tests); update test imports. Shared helpers used by BOTH layers (e.g. `_resolve_mesh`, `topology_counts` from `domains/mesh.py`) stay interface and are imported by finishing — that direction is allowed.

**Steps:** (1) grep-map all importers first and list them in the report; (2) moves + retargets; (3) `NIUA_SKIP_BLENDER=1 python -m pytest -q` green; (4) verify tool-name surface unchanged: `python -c` snippet comparing `build_default_registry()` command-name set before/after (record the count, must equal 309); (5) commit `refactor: addon two-layer split — finishing/ policy package, interface stays generic`.

### Task B: Server-side split

**Files:** create `src/niua_blender_mcp/finishing/__init__.py`; `git mv src/niua_blender_mcp/asset_classes.py src/niua_blender_mcp/finishing/asset_classes.py`; create `src/niua_blender_mcp/domains/finishing_feedback.py` with the specs for `feedback.quality/critique/capture_intake/preservation/readiness` + `io.profile_validate` moved out of `domains/feedback.py` / `domains/io.py`; retarget importers (`domains/asset_class.py`, `domains/finishing_feedback.py`, `evals/*`, tests — grep `from ..asset_classes|from .asset_classes|niua_blender_mcp.asset_classes`).

**Steps:** (1) grep-map importers; (2) moves + retargets; (3) full suite + parity green; (4) commit `refactor: server two-layer split — finishing/ mirrors the addon boundary`.

### Task C: Boundary enforcement + orientation doc

**Files:** create `tests/test_layer_boundary.py`; create `ARCHITECTURE.md` (repo root); modify `.superpowers/sdd/lean-rebuild.md` (on disk only, gitignored).

**Boundary test (AST-based, offline):** for each side, walk every `.py` under the interface area (addon: `niua_mcp_bridge/` excluding `finishing/` and the declared policy domain files `domains/finishing_feedback.py`, `domains/asset_class.py`; server: `niua_blender_mcp/` excluding `finishing/`, `evals/`, and the same two domain files) and assert no `import`/`from` references `finishing` or `evals`. Also assert the policy domain modules register exactly the expected tool names (addon COMMANDS: the 6 feedback/io names + `asset_class.list`/`asset_class.describe` — read the actual names from `domains/asset_class.py` first).

**ARCHITECTURE.md (~1 page, plain words, from the two-bucket table):** why the repo exists (generator → this tool → Godot); Part 1 interface (what it is, where it lives, "could serve any Blender automation"); Part 2 finishing (gates/readiness/preservation/finisher/benchmark, where it lives); the import-direction rule and the boundary test that enforces it; how to physically split later (auto-discovery means a policy pack just drops its domain modules in). Note that `prompts.py`'s `refine_mesh` doctrine is Part-2 prose hosted in a Part-1 file (documented exception).

**Steps:** boundary test written FIRST and run — it must PASS against the post-Task-A/B tree (if it fails, the split missed an edge: fix the split, not the test); full suite; commit `feat: enforce interface/finishing layer boundary + ARCHITECTURE.md orientation doc`.

### Task D: Live verification (controller)

Baseline bench `--no-godot` → must be byte-identical (0.36/0.36/0.36/0.24/0.28, pres 1.0, 5/5). Append one line to `docs/reports/objective-baseline.md`; commit.
