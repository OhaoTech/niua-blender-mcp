# Real-asset benchmark — first run finding (2026-07-03)

The benchmark was moved from synthetic primitives (cubes/cylinders) to **real AI-generated assets**
(git-ignored generic .glb fixtures; provenance in `evals/benchmark/assets/MANIFEST.json`). The item format
changed from `input.recipe` (Blender ops) to `input.asset` (import a fixture); the runner imports + joins
multi-part assets and is resilient to per-call timeouts.

## The 5 real items (triangle counts, parsed from the glb)
| item | tris | category |
|---|---:|---|
| real_multipart | 24,500 (9 parts) | humanoid character, multi-part |
| real_character_light | 50,000 | humanoid character |
| real_character | 76,726 | humanoid character |
| real_creature | 77,658 | creature |
| real_prop | 978,260 | prop / vessel (dense scan) |

## Finding: feedback.quality is pathologically slow (the #1 blocker)
On the very first run, `feedback.readiness` (which calls `feedback.quality` topology analysis) **timed out
(>60s) on real_character at only ~77k tris**, then Blender stayed wedged on the abandoned main-thread call
so the next `scene.info` also timed out — a cascade that halts the whole run.

- 77k tris is a **normal** generator mesh, not an outlier. A correct topology pass does 1M tris in <1s.
- >60s at 77k tris ⇒ **O(n^2)** (or worse) in the pure-Python topology metrics (likely naive non-manifold /
  quad-ratio / island loops).
- The toy benchmark (dozens of faces) hid this entirely — the tool had never seen a real mesh.

## Implication + next work
The tool's core measurement (and therefore the agent's ability to *observe* a real intake mesh before
finishing it) cannot handle real generator output. **Next work item: profile `feedback.quality` and rewrite
the topology metrics to O(n) (bmesh/numpy).** This is a concrete, tractable perf fix, not a fundamental limit.
Secondary: the main-thread cascade (one slow op wedges the session) argues for a time-budget/guard on the
heavy metrics.

## Resolution (2026-07-03) — the tool now handles real generator meshes
- **UV overlap O(n^2)->O(n)** (spatial-grid broad-phase in `core/uv_metrics.py`): `feedback.quality` on the
  77k-tri character went **>300s -> 1.4s**; the ~1M-tri prop measures in ~16s. Correctness proven by a random
  cross-check vs the all-pairs reference.
- **Foundational robustness**: `ResolvedContext` (`core/context.py`) now snapshots active/selection **by name**
  and restores by lookup, skipping objects the wrapped operator removed — fixes the "StructRNA ... removed"
  crash that hit `object.join`/`object.delete` (and any destructive op) via `capabilities.invoke`.
- **Multi-part assets**: the runner joins parts and cleans up stray un-joined accessories.
- **Result: the real benchmark measures 5/5** (readiness 0.24–0.36 on raw generator assets, preservation 1.0
  at baseline). The tool can now observe/measure real dense, multi-part generator output — its actual inputs.
