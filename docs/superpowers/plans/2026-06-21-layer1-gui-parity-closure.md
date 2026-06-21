# Layer 1 GUI Parity Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drive `scripts/audit_blender_coverage.py --source ../blender-source --fail-on partial` to green by replacing every current generic fallback row with curated GUI-parity domain tools.

**Architecture:** Keep the existing server/add-on mirror pattern: server specs in `src/niua_blender_mcp/domains/<domain>.py`, add-on handlers in `blender_addon/niua_mcp_bridge/domains/<domain>.py`, fake-bpy tests in `tests/domains/test_<domain>.py`, and live headless coverage in `tests/test_smoke_headless.py`. `properties.*` and `rna.*` remain the completeness safety net, but audit rows only become "covered" when the domain has a purpose-built prefix.

**Tech Stack:** Python 3.14, pytest, fake-bpy domain tests, real Blender headless smoke, source-backed `scripts/audit_blender_coverage.py`.

## Global Constraints

- Do not move to the next subsystem until the current subsystem's audit row is `covered`.
- Every new domain must expose server `SPECS` and add-on `COMMANDS`; `tests/test_parity.py` must pass.
- Mutating scene/data operations must set `mutates=True` and push exactly one undo step through dispatch.
- Prefer Blender live RNA/properties for field reports instead of hard-coded UI property lists.
- Add fake-bpy unit tests first, verify red, implement, verify green, then add live smoke.
- Run `python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none` after every subsystem.
- End state requires `python scripts/audit_blender_coverage.py --source ../blender-source --fail-on partial` to pass.
- Commit each subsystem separately.

---

## Current Audit Baseline

Command:

```bash
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
```

Current summary:

```text
covered: 35
partial: 23
missing: 0
```

Current partial rows:

- Properties contexts: `TOOL`, `CONSTRAINT`, `PARTICLES`, `PHYSICS`, `SHADERFX`, `STRIP`, `STRIP_MODIFIER`
- Object data types: `lattice`, `lightprobe`, `pointcloud`, `shaderfx`, `speaker`, `volume`
- Editor spaces: `api`, `clip`, `info`, `project`, `script`, `sequencer`, `spreadsheet`, `statusbar`, `text`, `topbar`

## File Map

- Existing audit gate: `scripts/audit_blender_coverage.py`
- Existing router parity tests: `tests/test_parity.py`
- Existing live smoke suite: `tests/test_smoke_headless.py`
- New subsystem specs/plans:
  - `docs/superpowers/specs/2026-06-21-constraints-gui-parity-design.md`
  - `docs/superpowers/specs/2026-06-21-physics-gui-parity-design.md`
  - `docs/superpowers/specs/2026-06-21-particles-gui-parity-design.md`
  - `docs/superpowers/specs/2026-06-21-sequencer-gui-parity-design.md`
  - `docs/superpowers/specs/2026-06-21-tool-editor-gui-parity-design.md`
  - `docs/superpowers/specs/2026-06-21-object-data-leftovers-design.md`
  - `docs/superpowers/specs/2026-06-21-editor-utility-surfaces-design.md`

## Wave 1: High-Impact Properties Contexts

### Task 1: `constraints.*`

**Audit rows closed:** `CONSTRAINT`

**Files:**
- Create: `src/niua_blender_mcp/domains/constraints.py`
- Create: `blender_addon/niua_mcp_bridge/domains/constraints.py`
- Create: `tests/domains/test_constraints.py`
- Modify: `tests/test_smoke_headless.py`
- Modify: `scripts/audit_blender_coverage.py` only if the required prefix changes from `constraints`

**Interfaces:**
- `constraints.list(object, owner="OBJECT")`
- `constraints.add(object, type, name="", owner="OBJECT", bone="")`
- `constraints.remove(object, name, owner="OBJECT", bone="")`
- `constraints.report(object, name="", owner="OBJECT", bone="")`
- `constraints.set(object, name, property, value, owner="OBJECT", bone="")`

**Gate:**
- `CONSTRAINT` row becomes `covered`.
- Existing `rig.constraint_*` stays as a compatibility/rigging convenience, but `constraints.*` is the GUI parity owner.

**Commands:**

```bash
pytest tests/domains/test_constraints.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_constraints_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add constraints gui parity"
```

### Task 2: `physics.*`

**Audit rows closed:** `PHYSICS`

**Files:**
- Create: `src/niua_blender_mcp/domains/physics.py`
- Create: `blender_addon/niua_mcp_bridge/domains/physics.py`
- Create: `tests/domains/test_physics.py`
- Modify: `tests/test_smoke_headless.py`

**Interfaces:**
- `physics.report(object)`
- `physics.add(object, type)`
- `physics.remove(object, type)`
- `physics.set(object, type, property, value)`
- `physics.field_report(object)`
- `physics.field_set(object, property, value)`

**Supported `type` values for this pass:**

`RIGID_BODY`, `RIGID_BODY_CONSTRAINT`, `CLOTH`, `SOFT_BODY`, `FLUID`, `DYNAMIC_PAINT`, `FIELD`

**Gate:**
- `PHYSICS` row becomes `covered`.
- Live smoke must add at least one rigid body and one force field and mutate one RNA-backed setting through the curated API.

**Commands:**

```bash
pytest tests/domains/test_physics.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_physics_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add physics gui parity"
```

### Task 3: `particles.*`

**Audit rows closed:** `PARTICLES`

**Files:**
- Create: `src/niua_blender_mcp/domains/particles.py`
- Create: `blender_addon/niua_mcp_bridge/domains/particles.py`
- Create: `tests/domains/test_particles.py`
- Modify: `tests/test_smoke_headless.py`

**Interfaces:**
- `particles.systems(object)`
- `particles.add(object, name="")`
- `particles.remove(object, name)`
- `particles.report(object, name="")`
- `particles.set(object, name, property, value)`

**Gate:**
- `PARTICLES` row becomes `covered`.
- Live smoke must add a particle system, set `count` and one timing/display property, and report them back.

**Commands:**

```bash
pytest tests/domains/test_particles.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_particles_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add particles gui parity"
```

### Task 4: `sequencer.*`

**Audit rows closed:** `STRIP`, `STRIP_MODIFIER`, editor space `sequencer`

**Files:**
- Create: `src/niua_blender_mcp/domains/sequencer.py`
- Create: `blender_addon/niua_mcp_bridge/domains/sequencer.py`
- Create: `tests/domains/test_sequencer.py`
- Modify: `tests/test_smoke_headless.py`

**Interfaces:**
- `sequencer.report()`
- `sequencer.strip_add(type, name="", frame_start=1, channel=1, path="")`
- `sequencer.strip_remove(name)`
- `sequencer.strip_set(name, property, value)`
- `sequencer.modifiers(name)`
- `sequencer.modifier_add(name, type, modifier_name="")`
- `sequencer.modifier_set(name, modifier, property, value)`
- `sequencer.modifier_remove(name, modifier)`

**Gate:**
- `STRIP`, `STRIP_MODIFIER`, and editor space `sequencer` rows become `covered`.
- Live smoke must create a scene strip or color strip, mutate timing/channel/name, add a strip modifier where supported, and report it.

**Commands:**

```bash
pytest tests/domains/test_sequencer.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_sequencer_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add sequencer gui parity"
```

### Task 5: `shaderfx.*`

**Audit rows closed:** `SHADERFX`, object data type `shaderfx`

**Files:**
- Create: `src/niua_blender_mcp/domains/shaderfx.py`
- Create: `blender_addon/niua_mcp_bridge/domains/shaderfx.py`
- Create: `tests/domains/test_shaderfx.py`
- Modify: `tests/test_smoke_headless.py`

**Interfaces:**
- `shaderfx.list(object)`
- `shaderfx.types()`
- `shaderfx.add(object, type, name="")`
- `shaderfx.remove(object, name)`
- `shaderfx.report(object, name="")`
- `shaderfx.set(object, name, property, value)`

**Gate:**
- `SHADERFX` and `shaderfx` rows become `covered`.
- If the running Blender exposes shader effects only for Grease Pencil object types, the live smoke must create a Grease Pencil object first.

**Commands:**

```bash
pytest tests/domains/test_shaderfx.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_shaderfx_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add shader effects gui parity"
```

### Task 6: `tool.*`

**Audit rows closed:** `TOOL`, editor space `topbar` if paired with Task 14

**Files:**
- Create: `src/niua_blender_mcp/domains/tool.py`
- Create: `blender_addon/niua_mcp_bridge/domains/tool.py`
- Create: `tests/domains/test_tool.py`
- Modify: `tests/test_smoke_headless.py`

**Interfaces:**
- `tool.active(area_type="VIEW_3D", mode="")`
- `tool.set(idname, area_type="VIEW_3D", mode="")`
- `tool.settings(area_type="VIEW_3D", mode="")`
- `tool.setting_get(path)`
- `tool.setting_set(path, value)`

**Gate:**
- `TOOL` row becomes `covered`.
- Live smoke must read and switch an active workspace tool where available without requiring foreground mouse input.

**Commands:**

```bash
pytest tests/domains/test_tool.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_tool_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add tool settings gui parity"
```

## Wave 2: Remaining Object Data Types

### Task 7: `lattice.*`

**Audit rows closed:** object data type `lattice`

**Interfaces:**
- `lattice.create(name="", location=[0,0,0])`
- `lattice.report(object)`
- `lattice.set(object, property, value)`
- `lattice.point_set(object, index, co_deform)`
- `lattice.convert_to_mesh(object, name="")`

**Gate command:**

```bash
pytest tests/domains/test_lattice.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_lattice_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add lattice gui parity"
```

### Task 8: `lightprobe.*`

**Audit rows closed:** object data type `lightprobe`

**Interfaces:**
- `lightprobe.create(type, name="", location=[0,0,0])`
- `lightprobe.list()`
- `lightprobe.report(name)`
- `lightprobe.set(name, property, value)`

**Gate command:**

```bash
pytest tests/domains/test_lightprobe.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_lightprobe_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add light probe gui parity"
```

### Task 9: `pointcloud.*`

**Audit rows closed:** object data type `pointcloud`

**Interfaces:**
- `pointcloud.list()`
- `pointcloud.report(name_or_object)`
- `pointcloud.set(name_or_object, property, value)`
- `pointcloud.attributes(name_or_object)`

**Gate command:**

```bash
pytest tests/domains/test_pointcloud.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_pointcloud_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add point cloud gui parity"
```

### Task 10: `speaker.*`

**Audit rows closed:** object data type `speaker`

**Interfaces:**
- `speaker.create(name="", location=[0,0,0])`
- `speaker.list()`
- `speaker.report(name)`
- `speaker.set(name, property, value)`

**Gate command:**

```bash
pytest tests/domains/test_speaker.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_speaker_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add speaker gui parity"
```

### Task 11: `volume.*`

**Audit rows closed:** object data type `volume`

**Interfaces:**
- `volume.create_empty(name="", location=[0,0,0])`
- `volume.import(path, name="")`
- `volume.list()`
- `volume.report(name_or_object)`
- `volume.set(name_or_object, property, value)`

**Gate command:**

```bash
pytest tests/domains/test_volume.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_volume_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add volume gui parity"
```

## Wave 3: Editor Utility Spaces

### Task 12: `tracking.*`

**Audit rows closed:** editor space `clip`

**Interfaces:**
- `tracking.report()`
- `tracking.clip_load(path, name="")`
- `tracking.clips()`
- `tracking.marker_report(clip)`
- `tracking.track_report(clip)`

**Gate command:**

```bash
pytest tests/domains/test_tracking.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_tracking_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add tracking gui parity"
```

### Task 13: `text.*`

**Audit rows closed:** editor space `text`, contributes to `script`

**Interfaces:**
- `text.list()`
- `text.create(name, body="")`
- `text.open(path, name="")`
- `text.read(name)`
- `text.write(name, body)`
- `text.append(name, body)`
- `text.save(name, path="")`
- `text.remove(name)`

**Gate command:**

```bash
pytest tests/domains/test_text.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_text_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add text editor gui parity"
```

### Task 14: `info.*`, `topbar.*`, `statusbar.*`

**Audit rows closed:** editor spaces `info`, `topbar`, `statusbar`

**Interfaces:**
- `info.report()`
- `info.messages(limit=100)`
- `topbar.report()`
- `topbar.command_search(query, limit=20)`
- `statusbar.report()`

**Gate command:**

```bash
pytest tests/domains/test_info.py tests/domains/test_topbar.py tests/domains/test_statusbar.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_info_topbar_statusbar_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add editor chrome gui parity"
```

### Task 15: `spreadsheet.*`

**Audit rows closed:** editor space `spreadsheet`

**Interfaces:**
- `spreadsheet.report(object="", component="")`
- `spreadsheet.columns(object="", component="")`
- `spreadsheet.rows(object="", component="", limit=100, offset=0)`

**Gate command:**

```bash
pytest tests/domains/test_spreadsheet.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_spreadsheet_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add spreadsheet gui parity"
```

### Task 16: `project.*` and `api.*`

**Audit rows closed:** editor spaces `project`, `api`

**Interfaces:**
- `project.report()`
- `project.files()`
- `project.settings()`
- `api.report()`
- `api.search(query, limit=20)`

**Gate command:**

```bash
pytest tests/domains/test_project.py tests/domains/test_api.py tests/test_parity.py -v
pytest tests/test_smoke_headless.py::test_project_api_gui_parity_workflow -v
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on none
git commit -m "feat: add project and api gui parity"
```

### Task 17: Final Strict Audit Gate

**Files:**
- Modify: `docs/PLAN.md`
- Modify: `docs/superpowers/specs/2026-06-20-blender-subsystem-roadmap.md`

**Steps:**

- [ ] Run the strict audit:

```bash
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on partial
```

Expected:

```text
Summary: {'covered': <all rows>, 'partial': 0, 'missing': 0}
```

- [ ] Run the full suite:

```bash
pytest -v
```

Expected:

```text
passed, 1 skipped
```

- [ ] Update docs with final command counts and strict audit result.

- [ ] Commit:

```bash
git add docs/PLAN.md docs/superpowers/specs/2026-06-20-blender-subsystem-roadmap.md
git commit -m "docs: mark layer one gui parity complete"
```

## Execution Strategy

Use one detailed child plan per task, in this order. Do not combine tasks unless the audit rows are inseparable in Blender source. Before implementing each task, create a focused plan at:

`docs/superpowers/plans/YYYY-MM-DD-<domain>-gui-parity.md`

Each focused plan must include:

- exact server specs
- exact add-on handlers
- fake-bpy tests
- live smoke workflow
- audit row expected before/after
- commit command

## Final Definition of Done

Layer 1 GUI parity is done only when all are true:

```bash
python scripts/audit_blender_coverage.py --source ../blender-source --fail-on partial
pytest -v
git status --short --branch
```

Expected:

- audit exits 0
- `partial: 0`
- `missing: 0`
- full pytest passes
- worktree clean
