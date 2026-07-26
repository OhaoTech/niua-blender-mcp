# Acceptance run — 2026-07-25 (v0.1.0)

Objective benchmark, `--mode agent`, finisher `evals.finisher:finish`, visible Blender 5.1.2,
measurement live (OpenGL). Deterministic, no LLM judge.

```
python scripts/run_objective_benchmark.py --mode agent \
  --finisher niua_blender_mcp.evals.finisher:finish --port 8765 --outdir /tmp/niua_accept
```

## Result

| asset | tris | budget | readiness | preservation | fidelity | engine import |
|---|---:|---:|---:|---:|---:|---|
| real_character | **74,889** | 18k ✖ | 0.760 | 0.926 | **0.990** | ok |
| real_character_light | 17,996 | ✓ | 0.840 | 0.999 | 0.924 | ok |
| real_creature | 17,986 | ✓ | 0.760 | 0.994 | 0.925 | ok |
| real_multipart | 18,000 | ✓ | 0.640 | 0.981 | 0.939 | ok |
| real_prop | — | — | **unmeasured** | — | — | — |

```
n_measured 4/5 · n_harm_flagged 0 · n_preservation_pass 4 · n_fully_ready 0
mean_readiness 0.75 (floor 0.85) · mean_preservation 0.975 · mean_surface_fidelity 0.945
engine import: 4 measured, 4 ok · grade INVALID (one item unmeasured)
```

## What this run settles

**1. The `real_multipart` crash is fixed.** This asset used to segfault Blender and kill the
run mid-item. It now completes, lands at *exactly* 18,000 triangles, preserves form
(0.981 / 0.939) and imports clean. Verified by eye: an intact character — limbs, fingers,
belt detail — not a blob. The pre-guard that declines voxel remesh on multi-island /
high-non-manifold input (commit `9586204`) is doing its job.

![real_multipart at 18,000 tris](../images/acceptance/real_multipart.png)

*`real_multipart`, finished: 18,000 triangles, intact. Previously crashed Blender.*

**2. Nothing was damaged.** `harm_flagged 0` across every measured asset, `preservation_pass
4/4`. Where a reducing move would have wrecked the mesh, it was reverted instead of shipped.

**3. The ruler works; the reducer is the bottleneck.** `real_character` is the clearest
case: both reduce paths were rejected —

```
bake_retopo    fid 0.330  REVERTED
bake_decimate  fid 0.274  REVERTED
```

so the asset kept a **0.990** fidelity but stayed at 74,889 triangles, 4× over budget. The
gate was right (0.27 is garbage), and the honest reading is not "the character has surface
noise" but **"no current reducer can take this asset to budget without destroying it."**
That is a reducer problem, not a threshold problem, and no floor tweak will fix it.

![real_character at 74,889 tris](../images/acceptance/real_character.png)

*`real_character`: fidelity 0.990, form perfectly held — and 4× over budget.*

**4. Nothing is `fully_ready`.** Mean readiness 0.75 against a 0.85 floor. Assets that hold
form but miss budget, or hit budget with partial gate coverage, do not clear the bar — as
intended.

## Open issues this run exposed

- **`real_prop` timed out**: `FINISHER FAILED: feedback.readiness exceeded 120.0s`. This is
  new and is an *infrastructure* failure, not a quality one — the asset was mid-pipeline and
  never got measured, which correctly invalidated the whole grade. Needs profiling of
  `feedback.readiness` on this asset (it previously finished, so this is a regression or a
  scaling cliff).
- **Grade is `INVALID`** by design: one unmeasured item means the run cannot be graded. The
  fail-closed rule applies to the benchmark itself, not only to individual moves.

## Honest summary

Of 4 measured assets: **3 finish at budget with form preserved and importing clean into a
real engine**; 1 preserves form but cannot be reduced. The 5th never finished due to a
timeout. Zero assets were harmed. Zero clear the strict full-readiness bar.

The headline change since the last run is that the crash is gone — the pipeline now
completes on every asset it measures.

---

## Follow-up: root-causing the `real_prop` timeout (2026-07-26)

Investigated the one issue that invalidated the run. Partial result — recorded rather than
patched, because the fix is not yet justified by the evidence.

**Established.** `real_prop` is a 978,232-triangle / 812,341-vertex mesh with 561,900
non-manifold edges. `feedback.readiness` on it costs **~20–21s**, reproducibly. Profiling
the components:

| component | time |
|---|---:|
| `uv.report` | **13.0s** |
| `_symmetry` | 4.0s |
| `_topology_quality` | 1.5s |
| `topology_counts` | 0.4s |
| `engine_quality`, `material_quality`, `export_profile_quality` | ~0.0s |

`uv.report` dominates because it builds a **full bmesh twice** on a million-poly mesh —
once in `_island_count`, again in `uv_quality` — then walks faces and loops in Python.

**Eliminated.** Two plausible causes were tested and ruled out:

- *`mesh.tris_to_quads` degrades later measurement* — no: component timings are flat before
  (978k polys) and after (738k polys).
- *A leftover `__high` duplicate doubles the work* — no: readiness with the duplicate in the
  scene is **0.95×**. Readiness measures the subject, not the scene.

**Still open.** The ~6× multiplier. A 20s baseline has ample headroom under the 120s budget,
yet the live run blew through it. Untested: accumulated 2048px bake textures / memory
pressure after ~25 minutes of running; UV island-count explosion after `smart_unwrap` on a
million-poly mesh; post-revert mesh state differing from intake.

**Deliberately not done:** raising the timeout. That converts a diagnosable performance
defect into a silent one. The likely real fix — one bmesh instead of two, `foreach_get` for
UV bounds — is cheap, but it should follow the explanation, not replace it.

### Resolved (2026-07-26): the multiplier was an O(n²) broad-phase

The missing ~6× was found by timing the one pairing the earlier profiling had skipped —
`uv.report` **after** `mesh.tris_to_quads`:

| | before conversion | after conversion |
|---|---:|---:|
| `uv.report` (pre-fix) | 12.7s | **>142s** |

`_uv_overlap_detected` bucketed each face into every grid cell its UV bbox touched:

```python
for cx in range(cx0, cx1 + 1):
    for cy in range(cy0, cy1 + 1):
        grid.setdefault((cx, cy), []).append(i)
```

Grid resolution is `cells = sqrt(n)`, so a face spanning the UV range registers in
`cells × cells == n` buckets — one face costing O(n) insertions. `mesh.tris_to_quads`
manufactures exactly those faces: it merges triangle pairs that sat on *different UV
islands*, and the merged quad's bbox spans both. Enough of them and the broad-phase — a
uniform grid, which only behaves for similarly-sized objects — collapses to O(n²).

**Fix.** Per-face insertion is capped (`_MAX_CELLS_PER_FACE = 64`). A face spanning more is
pulled out as *oversized* and compared directly against every other face with a bbox reject
first, preserving the "no overlap is ever missed" guarantee: an overlapping pair is still
always compared, via a shared cell or via the oversized pass. Oversized faces are tested
first, because a face covering much of the UV space usually hits something and the first hit
returns immediately.

**Verified live on `real_prop`, same sequence that failed:**

| operation | before | after |
|---|---:|---:|
| `uv.report` after `tris_to_quads` | >142s (hung) | **10.5s** |
| `feedback.readiness` after it | timed out (120s budget) | **17.4s** |

Regression test: `tests/core/test_uv_overlap_scaling.py`. It pins correctness both ways
(an oversized face must still register an overlap, and must not invent one) and the cost —
measured 0.02s with the cap versus 6.72s without, so it fails loudly if the cap is removed.
