# Layer proofs — interface vs finishing (2026-07-14)

**Question:** Are the Blender-loyal tools working? Is *our* finishing layer working at high quality?  
**Answer in one line:** **Loyal interface: yes (proven live).** **Our craft verbs: mostly yes (budget/bake/LOD/Godot).** **Our quality bar (anti-blob / full game-ready): not yet — fidelity needs GUI; multipart retopo still kills Blender; UV/material gates still fail.**

Raw data: `/tmp/niua_proofs/proofs.json` · export: `/tmp/niua_proofs/proof_bake.glb`  
Environment: Blender **5.1.2** headless · Godot **4.6.3** · branch work includes fail-closed + `bake_and_finish` default.

---

## 1. Offline proofs (no Blender)

| Suite | Result | Proof |
|-------|--------|--------|
| Parity server ↔ addon | **PASS** | `tests/test_parity.py` |
| Layer boundary (interface ↛ finishing) | **PASS** | `tests/test_layer_boundary.py` |
| Finisher fail-closed + default skill | **PASS** | `tests/evals/test_finisher.py`, `tests/test_skills.py` |
| Fidelity / gates / retopo registration | **PASS** | `tests/core/*`, `tests/domains/test_retopo.py`, bake tests |
| Critical batch this session | **128 passed** | pytest exit 0 |

Offline proves **contracts and control law**, not “looks good in Godot.”

---

## 2. Loyal interface — LIVE (headless bridge)

| Proof | Result | Evidence |
|-------|--------|----------|
| `system.health` | **PASS** | `bridge=alive`, Blender 5.1.2 |
| `scene.info` | **PASS** | returns objects |
| `object.create` (CUBE) | **PASS** | `proof_cube` MESH |
| `uv.smart_unwrap` | **PASS** | unwrap on cube |
| `modifiers.add` + `apply` (SUBSURF) | **PASS** | applied |

**Verdict: loyal layer works.** Bridge, create, UV, modifiers fire end-to-end.

---

## 3. Our finishing layer — LIVE

### 3a. Rulers (measure without pretty pixels)

| Proof | Result | Evidence |
|-------|--------|----------|
| `feedback.quality` on real asset | **PASS** | `real_character_light`: **49996 tris**, non_manifold 16092, class `character` |
| `feedback.readiness` | **PASS** | readiness **0.36**, 25 gates, 16 failing (honest intake) |
| Capture/preservation headless | **PASS (behavior)** | `available: false` — *no OpenGL in background* (expected) |

### 3b. Control law (anti-blob)

| Proof | Result | Evidence |
|-------|--------|----------|
| `bake_and_finish` fail-closed | **PASS** | **7/7 moves REVERTED**, **0 kept** when `pres=? fid=?` |
| Skill log | — | every line ends `REVERTED` (not KEPT with blind harm) |

This is the opposite of the old silent-pass bug. **Without measured fidelity, we do not keep finish moves.**

**Defect found:** `readiness_final` rose **0.36 → 0.52** even with 0 kept — after some reverts the next move still saw higher readiness (e.g. lod before=0.52). So **“kept” is fail-closed, but checkpoint/revert may leave score-visible side effects** (or re-measure is not pure intake). Track as finishing-layer hygiene, not interface failure.

### 3c. Craft verbs (our recipes on Blender muscle)

| Proof | Result | Evidence |
|-------|--------|----------|
| `object.retopo` hits budget | **PASS** | **49996 → 18000** tris (character budget) |
| bake pipeline (dup → retopo → shrinkwrap → UV → bake) | **PASS (ops)** | bake returned `NORMAL`, `AO` images |
| `material.bake_maps_present` after bake | **WEAK** | quality still `bake_maps_present: false` / `data_maps_non_color: false` — **metric or wiring mismatch** |
| UV after craft | **FAIL quality** | `uv_overlap: true`, stretch **~13.6** (gate wants ≤2) |
| LOD + collision | **PASS** | `has_lods`, `has_collision_proxy/hulls`, within tri budget |
| Export + Godot | **PASS** | GLB **3.6 MB**, Godot import **ok=true**, errors=[] |
| Multipart import + measure | **PASS** | 24500 tris |
| Multipart `object.retopo` | **FAIL** | Blender **died** (empty response → connection refused) |

### 3d. Surface fidelity / “looks game-ready”

| Proof | Result | Why |
|-------|--------|-----|
| Surface fidelity live this session | **NOT PROVEN** | Headless has no OpenGL — cannot score SSIM |
| Prior GUI report (`retopo-bake-run.md`) | **Historical** | 3/5 looked good by eye + fidelity; not re-run here |

**Best quality is not proven in this headless session.** Craft ops work; **anti-blob ruler cannot greenlight** without GUI (or offscreen GL).

---

## 7. Re-proof after fixes (2026-07-15) — `/tmp/niua_proofs/reproof.json`

| Fix | Live result | Evidence |
|-----|-------------|----------|
| Control-state after REVERT | **PASS** | `readiness_final == readiness_start == 0.36`, 7/7 reverted, 0 kept; next moves no longer start at polluted 0.52 |
| Bake map metrics vs bake_transfer | **PASS** | `bake_maps_present: true`, `data_maps_non_color: true` after NORMAL+AO bake |
| Multipart retopo survival | **PASS** | `path: decimate_only`, `voxel_skipped: loose_parts=431`, 24500→17999 tris, **bridge alive** |

Still not proven: GUI surface fidelity, UV stretch/overlap quality.

---

## 4. Scoreboard

| Layer | Score | Meaning |
|-------|-------|---------|
| Loyal Blender interface | **5 / 5 live** + offline green | Safe to trust as hands |
| Our metrics / fail-closed | **Working** | Measures real meshes; refuses unmeasured keeps |
| Our craft (retopo/bake/LOD/export/Godot) | **Working with gaps** | Budget + bake ops + engine package + Godot OK |
| Our **quality bar** (fidelity + UV + full readiness + multipart) | **Not cleared** | Blind fidelity here; UV fails; multipart crash; bake map flags disagree |

---

## 5. What “best quality” still requires (next proofs only on GUI)

1. **Visible Blender** (or EGL offscreen) → fidelity measured and pass on 5 fixtures  
2. UV quality after reduce (stretch/overlap gates)  
3. `bake_maps_present` / Non-Color alignment with actual bake wiring  
4. Multipart retopo without kill  
5. Revert hygiene so readiness doesn’t drift when every move is REVERTED  

---

## 6. Bottom line for Frank

| Claim | Proof status |
|-------|----------------|
| “Loyal tools work” | **Yes** — live create/UV/modifiers + health |
| “Our layer runs” | **Yes** — quality, readiness, retopo-to-budget, bake NORMAL/AO, LOD/collision, Godot |
| “Our layer ships top-tier game quality” | **No** — not with this evidence; fidelity unproven headless; UV/multipart/material flags still fail |

**Trust the hands. Do not claim senior polish until GUI fidelity proofs land on the five real assets.**
