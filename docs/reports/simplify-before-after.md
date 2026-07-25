# Simplify pass — before / after (2026-07-14)

Goal: make the **product** legible again without deleting the Blender remote-control library.

## Story

| | **Before** | **After** |
|--|------------|-----------|
| First sentence of README | “Agentic Blender” / MCP / RNA tiers | NIUA mesh → polish → Godot |
| Where do I start? | DESIGN.md, PLAN.md, 80 superpowers docs | **`START_HERE.md`** |
| What is the product? | Implied by architecture essays | One loop: reduce → bake → gates → Godot |
| Default finisher | Was `make_game_ready` (blob path); later code fixed to bake | **Documented + registry-enforced** `bake_and_finish` |
| Skill list order | Legacy first | **Default first**, `legacy: true` on decimate path |
| Superpowers docs | Look like the source of truth | **`docs/superpowers/README.md`**: archive, do not start here |
| Architecture doc | Long founder essay | Short two-layer + freeze rule; points to START_HERE |
| Fail-closed harm | Unmeasured = silent pass (fixed in prior commit) | Still fail-closed (product rule in START_HERE) |

## Mental model size

| | **Before** | **After** |
|--|------------|-----------|
| Concepts to hold | kernel, RNA, 40 domains, layer2 waves, two skills, altimeter, FSM ghosts… | **7-step finish loop** + “ignore frozen domains” |
| Files to open for craft work | Unclear | **Island table** in START_HERE (~10 paths) |
| New domain tools | Always “coverage” temptation | **Freeze** unless bake path is blocked |

## Code / registry

| | **Before** | **After** |
|--|------------|-----------|
| `list_skills()` | Two peers, make_game_ready first | `bake_and_finish` first; `default` / `legacy` flags |
| `DEFAULT_SKILL` | Implicit | Explicit constant + `get_default_skill()` |
| `evals/finisher` | Points at bake (prior fix) | Asserts alignment with `DEFAULT_SKILL` |
| `run_skill.py` default | hard-coded string | `DEFAULT_SKILL` |

## What we did **not** do (on purpose)

- Did **not** delete ~300 domain tools (library stays; freeze means “don’t grow”).
- Did **not** rewrite the kernel.
- Did **not** claim craft quality is done (UV / multipart / organics still open).

Simplification = **story + entrypoints + freeze**, not a greenfield rewrite.

## How to verify you “get it”

1. Read only `START_HERE.md` (≈3 minutes).  
2. Open `finishing/skills/bake_and_finish.py`.  
3. Run (GUI Blender + bridge):  
   `python scripts/run_skill.py --outdir /tmp/niua_finish`  
4. If a change doesn’t affect that loop — don’t make it.
