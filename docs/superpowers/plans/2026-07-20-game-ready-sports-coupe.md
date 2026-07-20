# Game-ready Sports Coupe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and validate a branded-neutral, all-angle PC sports-coupe asset in Blender and export a Godot-ready GLB.

**Architecture:** A deterministic `bpy` build script creates the full scene from reusable mesh and material helpers. A validator opens the saved `.blend`, enforces hierarchy/LOD/collision requirements, and renders a studio preview. Geometry is separated into collections for LOD0, LOD1, LOD2, collision, and studio presentation.

**Tech Stack:** Blender `bpy`, Principled BSDF, Python `unittest`, GLB exporter.

## Global Constraints

- Use the supplied image only as a styling reference; do not include manufacturer logos, badges, or exact proprietary panel geometry.
- Target PC: LOD0 about 45,000 triangles; LOD1 about 20,000; LOD2 about 7,000.
- Use meters, applied transforms, outward normals, non-overlapping UVs, metallic/roughness PBR, and Godot-compatible GLB conventions.
- Preserve existing uncommitted repository work; add only the files named below.

---

### Task 1: Establish the deterministic Blender scene builder

**Files:**
- Create: `scripts/build_sports_coupe.py`
- Create: `tests/art/test_sports_coupe_contract.py`

**Interfaces:**
- Produces `build_scene(output_blend: str, output_glb: str, preview_png: str) -> None`.
- Produces collections `Vehicle_LOD0`, `Vehicle_LOD1`, `Vehicle_LOD2`, `Vehicle_Collision`, and `Studio`.

- [ ] **Step 1: Write the failing contract test**

```python
from pathlib import Path

def test_builder_exposes_scene_contract():
    source = Path("scripts/build_sports_coupe.py").read_text()
    for required in (
        "def build_scene(output_blend: str, output_glb: str, preview_png: str) -> None:",
        '"Vehicle_LOD0"', '"Vehicle_LOD1"', '"Vehicle_LOD2"',
        '"Vehicle_Collision"', '"Studio"',
    ):
        assert required in source
```

- [ ] **Step 2: Verify the test fails**

Run: `python -m pytest tests/art/test_sports_coupe_contract.py -q`

Expected: FAIL because the builder file does not exist.

- [ ] **Step 3: Implement the scene foundation**

Create a fresh Blender scene, then create the five named collections. Add a `principled(name, base, metallic, roughness, coat=0.0)` material factory that assigns base color, metallic, roughness, and coat weight on a Principled BSDF. Add `build_scene(output_blend, output_glb, preview_png)`, which clears Blender's default objects, creates the collections, and delegates body, wheel, LOD, collision, lighting, export, and rendering to helpers added by the following tasks.

- [ ] **Step 4: Verify the test passes**

Run: `python -m pytest tests/art/test_sports_coupe_contract.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_sports_coupe.py tests/art/test_sports_coupe_contract.py
git commit -m "feat(art): scaffold sports coupe scene builder"
```

### Task 2: Build the LOD0 body, glazing, and exterior

**Files:**
- Modify: `scripts/build_sports_coupe.py`
- Modify: `tests/art/test_sports_coupe_contract.py`

**Interfaces:**
- Consumes: `Vehicle_LOD0` and the material factory.
- Produces: `Vehicle_Root`, `Body_Main`, `Glass_Canopy`, `Front_Intakes`, `Rear_Diffuser`, `Side_Skirts`, `Mirror_L`, and `Mirror_R`.

- [ ] **Step 1: Write the exterior contract test**

```python
def test_builder_declares_lod0_exterior_parts():
    source = Path("scripts/build_sports_coupe.py").read_text()
    for name in ("Body_Main", "Glass_Canopy", "Front_Intakes",
                 "Rear_Diffuser", "Side_Skirts", "Mirror_L", "Mirror_R"):
        assert f'"{name}"' in source
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/art/test_sports_coupe_contract.py::test_builder_declares_lod0_exterior_parts -q`

Expected: FAIL until the exterior part names are implemented.

- [ ] **Step 3: Implement the body**

Use X as vehicle length, Y as width, and Z as up. Build a symmetric, subdivision-surface body with overall dimensions: length `4.62`, width `1.98`, height `1.18`, wheelbase `2.70`. Shape the low nose, wide front arches, pinched canopy, rear haunches, and tapered rear deck using a mirror modifier, subdivision level 2, and weighted normals. Create separate thin meshes for the dark canopy, front intakes, rear diffuser, side skirts, and mirrors. Assign red clear-coat paint to `Body_Main`, black trim to openings and aero pieces, smoked glass to `Glass_Canopy`. Apply transforms, recalculate normals outward, and parent all LOD0 parts to `Vehicle_Root`.

- [ ] **Step 4: Verify pass and commit**

Run: `python -m pytest tests/art/test_sports_coupe_contract.py::test_builder_declares_lod0_exterior_parts -q`

Expected: PASS.

```bash
git add scripts/build_sports_coupe.py tests/art/test_sports_coupe_contract.py
git commit -m "feat(art): build sports coupe exterior"
```

### Task 3: Add wheel modules, cabin, lamps, and reference studio

**Files:**
- Modify: `scripts/build_sports_coupe.py`
- Modify: `tests/art/test_sports_coupe_contract.py`

**Interfaces:**
- Consumes: `Vehicle_Root` and LOD0 materials.
- Produces: `Wheel_FL`, `Wheel_FR`, `Wheel_RL`, `Wheel_RR`, `Headlamp_L`, `Headlamp_R`, `Taillamp_L`, `Taillamp_R`, `Interior`, and `Camera_Reference`.

- [ ] **Step 1: Write the modular-parts test**

```python
def test_builder_declares_modular_parts():
    source = Path("scripts/build_sports_coupe.py").read_text()
    for name in ("Wheel_FL", "Wheel_FR", "Wheel_RL", "Wheel_RR",
                 "Headlamp_L", "Headlamp_R", "Taillamp_L", "Taillamp_R",
                 "Interior", "Camera_Reference"):
        assert f'"{name}"' in source
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/art/test_sports_coupe_contract.py::test_builder_declares_modular_parts -q`

Expected: FAIL until the parts exist.

- [ ] **Step 3: Implement detailed modules**

Create one reusable wheel assembly at each `(±1.35, ±0.92, 0.34)`: tire radius `0.34`, tire width `0.29`, dark alloy rim, ten paired spokes, brake disc, and red caliper. Ensure every copy faces outward. Add inset dark lamp housings with restrained white/red emission. Create a simple cockpit: two bucket seats, dash, steering wheel, center console, and door cards. Add a low front-three-quarter `Camera_Reference` at `(6.8, -8.6, 3.0)` pointing to `(0, 0, 0.7)`, with 58 mm lens. In `Studio`, create a neutral gray sweep, neutral world, and large area key/fill/rim lights.

- [ ] **Step 4: Verify pass and commit**

Run: `python -m pytest tests/art/test_sports_coupe_contract.py::test_builder_declares_modular_parts -q`

Expected: PASS.

```bash
git add scripts/build_sports_coupe.py tests/art/test_sports_coupe_contract.py
git commit -m "feat(art): add sports coupe wheels lamps and studio"
```

### Task 4: Generate LODs, collision, UVs, and artifacts

**Files:**
- Modify: `scripts/build_sports_coupe.py`
- Modify: `tests/art/test_sports_coupe_contract.py`

**Interfaces:**
- Consumes: the complete LOD0 hierarchy.
- Produces: `LOD1_Body`, `LOD2_Body`, `Collision_Body`, `/tmp/niua_model/sports_coupe.blend`, `/tmp/niua_model/sports_coupe.glb`, and `/tmp/niua_model/sports_coupe_preview.png`.

- [ ] **Step 1: Write LOD/export contract**

```python
def test_builder_declares_lods_collision_and_export():
    source = Path("scripts/build_sports_coupe.py").read_text()
    for required in ("LOD1_Body", "LOD2_Body", "Collision_Body",
                     "export_scene.gltf", "sports_coupe.glb"):
        assert required in source
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/art/test_sports_coupe_contract.py::test_builder_declares_lods_collision_and_export -q`

Expected: FAIL until LOD, collision, and export code exists.

- [ ] **Step 3: Implement assets and export**

Duplicate render parts into `Vehicle_LOD1` and `Vehicle_LOD2`, renaming their primary shells to `LOD1_Body` and `LOD2_Body`. Decimate only duplicate geometry to approximately 20k and 7k triangles; replace lower-LOD wheels with simpler spoke/cylinder versions. Build `Collision_Body` plus four wheel cylinders in `Vehicle_Collision`, each with custom property `godot_collision = True`. Smart-project render UVs at `0.02` island margin, apply transforms, save the blend, export LOD0 to GLB with `export_yup=True` and `export_apply=True`, and render the camera to the supplied preview path at 1280×720.

- [ ] **Step 4: Build and verify artifacts**

Run: `mkdir -p /tmp/niua_model && blender --background --factory-startup --python scripts/build_sports_coupe.py -- /tmp/niua_model/sports_coupe.blend /tmp/niua_model/sports_coupe.glb /tmp/niua_model/sports_coupe_preview.png`

Expected: Blender exits 0 and creates the blend, GLB, and PNG.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_sports_coupe.py tests/art/test_sports_coupe_contract.py
git commit -m "feat(art): export sports coupe lods and collision"
```

### Task 5: Validate and inspect the game asset

**Files:**
- Create: `scripts/validate_sports_coupe.py`
- Modify: `tests/art/test_sports_coupe_contract.py`

**Interfaces:**
- Consumes: the blend from Task 4.
- Produces: a JSON report with collection presence, object names, evaluated triangle counts, material use, transforms, and verdict.

- [ ] **Step 1: Write the validator contract**

```python
def test_validator_checks_required_collections_and_triangles():
    source = Path("scripts/validate_sports_coupe.py").read_text()
    for required in ("Vehicle_LOD0", "Vehicle_LOD1", "Vehicle_LOD2",
                     "Vehicle_Collision", "evaluated_triangles", '"pass"'):
        assert required in source
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/art/test_sports_coupe_contract.py::test_validator_checks_required_collections_and_triangles -q`

Expected: FAIL because the validator does not exist.

- [ ] **Step 3: Implement validation**

Use the evaluated dependency graph to count triangles per collection. Require all four vehicle collections, all four LOD0 wheel names, paint/glass/lamp material assignments, applied scales of `(1.0, 1.0, 1.0)` on exported render meshes, positive-volume collision geometry, and triangle ceilings of 52k, 24k, and 9k for LOD0/1/2. Print JSON containing `"status": "pass"` only when every check passes; otherwise print `"status": "fail"` plus explicit failures and exit nonzero.

- [ ] **Step 4: Run validation and visual inspection**

Run: `blender --background /tmp/niua_model/sports_coupe.blend --python scripts/validate_sports_coupe.py`

Expected: JSON with `"status": "pass"`, all LODs below cap, and no invalid transforms. Open the preview and confirm the low red coupe silhouette, dark canopy, wide arches, detailed wheels, and studio front-three-quarter composition.

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_sports_coupe.py tests/art/test_sports_coupe_contract.py
git commit -m "test(art): validate sports coupe deliverable"
```

