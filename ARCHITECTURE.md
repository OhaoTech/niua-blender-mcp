# Architecture (short)

**Lost?** Open [`START_HERE.md`](START_HERE.md) first.

## Job

```
rough mesh → game-ready-enough asset → any engine
```

![the finishing bay](docs/images/pipeline-concept.jpg)

Read it left to right — every part maps to something real:

| In the picture | In the system |
|---|---|
| Rough mesh on the conveyor | a dense mesh arriving from any generator, scan, or sculpt |
| **Calipers + scan beam** | `feedback.*` — silhouette IoU, surface-fidelity SSIM, topology |
| Lit pedestal, refined asset | budgeted, baked, UV'd, engine-importable glTF |
| **The reject pile** | the fail-closed rule: *unmeasured or unproven → revert* |

Most Blender integrations build the conveyor. The calipers and the reject pile are the
product.

## The system

Two processes, four strata, one loop.

![architecture](docs/images/architecture.svg)

Most Blender integrations stop at strata ①+② — *can an LLM drive Blender?* Strata ③+④
answer a different question: *can it prove the asset is shippable?*

**Hard rule:** unmeasured quality = **revert**, never a silent pass. The ruler is
deterministic and judge-free — no LLM grades its own homework.

## Two layers (the import rule)

| Layer | Question it answers | Where |
|-------|---------------------|--------|
| **Interface** | “How do I drive Blender safely?” | kernel, bridge, most `domains/`, capture |
| **Finishing** | “Is this a shippable game asset?” | `finishing/`, policy domains |

Two invariants, both enforced by the test suite:

- finishing may import interface; **interface must never import finishing** — `tests/test_layer_boundary.py`
- **the server must never import `bpy`** — `tests/test_no_bpy_in_server.py`; this one also
  keeps the two licenses separable, see [`LICENSING.md`](LICENSING.md)

## What is and isn't the MCP

Four kinds of content live in this repo. Only the first ships.

| | What it is | Where | Ships |
|---|---|---|---|
| **The MCP** | transport, the tool surface, the eyes — neutral Blender translation plus measurement that reports without judging | `src/niua_blender_mcp/`, `blender_addon/niua_mcp_bridge/` (both minus the rows below) | ✅ wheel (Apache) + add-on zip (GPL) |
| **The policy** | budgets, gates, asset classes, the finisher skills, and the `retopo`/LOD/collision recipes | `finishing/`, `domains/policy/` — **both sides** | ❌ held back |
| **The harness** | benchmark items, reference finisher, unit tests, dev/ops scripts | `evals/`, `tests/`, `scripts/` | ❌ |
| **The evidence** | live run reports, plans, specs, design notes | `docs/reports/`, `docs/superpowers/`, `docs/DESIGN.md` | ❌ |

**Why policy is held back.** Not because opinions are wrong to have, but because these
ones are not good enough to stand behind. The reducer reaches its triangle budget on
simple props and cannot take a dense character there without destroying it. Shipping a
`retopo` tool that fails on the hard case makes the whole MCP look broken when the Blender
surface underneath is fine — so it waits in the repo, under benchmark, until it earns the
release. Nothing is lost meanwhile: `modifiers.add` with a `DECIMATE` modifier is still
there, unopinionated, and the agent decides how far to take it.

**How the exclusion is guaranteed.** By *absence*, not by a flag. `domains/__init__.py`
discovers a domain by the presence of its module, so an artifact without `domains/policy/`
is one where those tools do not exist — nothing to disable, nothing to re-enable by
accident. Measured on the real artifacts: 304 tools become **292**, and the 12 that
disappear are exactly `feedback.quality/readiness/critique/preservation/capture_intake`,
`io.profile_validate`, `asset_class.list/describe`, and
`object.retopo/lod_create/collision_hulls_create/collision_proxy_create`.

Three things that surprise people:

- **The eyes stay, the verdicts go.** `feedback.capture`, `silhouette`, `topology`, `uv`,
  `wire_shaded`, `turntable` all ship: they look at the mesh and report. `feedback.quality`
  and `readiness` do not: they fold budgets and gates in and return a verdict.
  `wire_shaded`/`lookdev` will still garnish their output with quality analytics *if* the
  policy layer happens to be installed, and degrade quietly when it is not.
- **`evals/` sits inside the server package but is not part of it.** Import convenience
  only. It is a strict leaf — nothing in the server imports it — and its fixtures
  (`evals/benchmark/assets/*.glb`, ~72 MB) are deliberately untracked, so a shipped harness
  could only fail: `list_items()` returns `[]`, `load_item()` raises `KeyError`.
- **The add-on is not in the wheel.** That is the license boundary, not an oversight — see
  [`LICENSING.md`](LICENSING.md).

CI builds both artifacts and fails if an add-on, harness, or policy file appears in either.
`tests/test_product_surface.py` fails if a policy tool is ever registered from a module
that ships — which is the property the whole arrangement rests on.

## Whose name goes on what

The tool is *called* Niua Blender MCP, and the product wears that name: the add-on's
`bl_info`, its N-panel, its operator ids, its env vars, its distribution name.

Nothing we write into **your** file does. Datablocks injected into your scene, custom
property keys that ride along on your exported asset, files written to your disk, and
entries pushed onto your undo stack all get a functional `mcp_` prefix — `__mcp_capture_cam`,
`mcp:intake`, `mcp_decimate` — so the name says what the thing is, not who made it.
`tests/test_no_vendor_brand_in_user_data.py` enforces the line.

This is the same instinct as the layer rule: the parts of this repo that could serve any
Blender automation should carry no opinion, and no ownership, that isn't yours.

## Product vs library

| You care about | Frozen library (do not grow) |
|----------------|------------------------------|
| the shipped tool surface staying honest | Extra Blender domains (sequencer, UI chrome, …) |
| the eyes: capture, silhouette, topology, UV | RNA “list all tools” expansion |
| the reducer earning its way back into the release | Old plans under `docs/superpowers/` |

Held-back finisher (repo only): `evals/finisher.py` → `finishing/skills/bake_and_finish.py`.
Run it with `scripts/run_skill.py`; measure it with `scripts/run_objective_benchmark.py`.

## Keep / freeze

- **Keep improving:** the reducer (this is what gates the policy layer's release), bake,
  UV, multipart stability, export verification.
- **Freeze:** new domain packs, second finishers, platform chrome — and do not add
  opinions to the shipped surface. If a tool decides what "good" means, it belongs in
  `domains/policy/`.

## Historical

Long design: `docs/DESIGN.md`. Build plans/specs: `docs/superpowers/` (archive).
