# Blender Finisher

[![tests](https://github.com/OhaoTech/niua-blender-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/OhaoTech/niua-blender-mcp/actions/workflows/tests.yml)

**Rough mesh → measured game-ready asset.** An MCP server with a ruler.

Point an LLM at a dense, generated mesh and get back a budgeted, baked, importable game
asset — where every step that cannot be *proven* to preserve the form is reverted.

> Package name is `niua-blender-mcp`; the product is the finisher.
> **New here?** Read [`START_HERE.md`](START_HERE.md) — one page, then come back.

![architecture](docs/images/architecture.svg)

## What makes it different

Most Blender integrations answer *“can an LLM drive Blender?”* — that is strata ①–②, and
this repo has one of the larger ones. What it adds is stratum ③: **eyes**. The agent can
look at what it just did — silhouette, wireframe density, UV stretch, a lit turntable —
instead of driving blind and hoping.

| | Typical Blender MCP | This one |
|---|---|---|
| Drive Blender from an LLM | ✅ | ✅ **292 tools, 48 domains**, schema-validated |
| Run arbitrary `bpy` | ✅ (usually ungated) | ✅ **off by default** |
| See the result | ✖ | ✅ silhouette · topology · UV checker · wire-shaded · turntable |
| Decide what "good" means | — | **you do.** No budgets, no gates, no house style |

That last row is deliberate. An earlier version shipped an opinionated finisher — triangle
budgets per asset class, readiness gates, a `retopo` recipe. It is still in this repo and
still runs under `scripts/`, but it is **not in the release**, because it is not good
enough to stand behind: the reducer hits budget on simple props and cannot take a dense
character there without wrecking it. A tool that fails on the hard case makes the whole
MCP look broken when the Blender surface underneath is fine.

So the released MCP does not decide anything for you. `modifiers.add` with a `DECIMATE`
modifier does exactly what it does in Blender; how far to take it is the agent's call, and
the eyes are there to check the answer.

**Status of the held-back layer:** `src/niua_blender_mcp/finishing/`,
`domains/policy/`, and the benchmark under `evals/`. It ships when a dense character
survives the round trip. See [ARCHITECTURE.md](ARCHITECTURE.md#what-is-and-isnt-the-mcp).

## Install

### Let your agent do it

Paste this into Claude Code, Cursor, or any coding agent with shell access:

```text
Install the Blender Finisher MCP server here. Follow these steps in order and STOP and
report if any check fails — do not improvise around a failure.

1. Check prerequisites:  `blender --version` (need 4.0+) and `python --version` (need 3.11+).
   If Blender is missing, stop and tell me how to install it for this OS.

2. Clone and install the server:
     git clone https://github.com/OhaoTech/niua-blender-mcp && cd niua-blender-mcp
     python -m pip install -e .

3. Install the Blender add-on (this asks Blender where its add-ons live, so no guessing):
     python scripts/install_addon.py
   Expect "add-on symlinked" (or "copied") and "__init__.py present = True".

4. Start the bridge. Blender must be VISIBLE, not headless — quality measurement needs
   OpenGL, and headless runs will revert finishing moves instead of passing them blind:
     blender --python scripts/blender_gui.py -- ./blender_addon 8765
   (Or open Blender normally → Preferences → Add-ons → enable "Niua MCP Bridge" →
   press N in the viewport → Niua tab → Start.)

5. Verify the bridge is alive:
     python scripts/bridge_call.py 8765 system.health '{}'
   Expect {"bridge": "alive", ...}. If not, report the exact error and stop.

6. Register the MCP server in my client config:
     {"mcpServers": {"blender-finisher": {"command": "python",
                                          "args": ["-m", "niua_blender_mcp"]}}}

7. Confirm the tool surface loaded — around 305 tools across domains including
   mesh, object, uv, shading, modifiers, io and feedback.

Then tell me: Blender version, whether the add-on is symlinked or copied, and the
health-check output.
```

### Or by hand

```bash
python -m pip install -e .          # 1. server
python scripts/install_addon.py     # 2. add-on → Blender's add-ons dir
                                    # 3. enable "Niua MCP Bridge" in Preferences → Add-ons
python scripts/bridge_call.py 8765 system.health '{}'   # 4. verify
```

Then finish the benchmark fixtures:

```bash
python scripts/run_skill.py --skill bake_and_finish --port 8765 --outdir /tmp/niua_finish
```

`install_addon.py` supports `--copy`, `--blender /path/to/blender`, and `--uninstall`.

## Status — honest

Pre-1.0. Latest acceptance run ([full report](docs/reports/acceptance-2026-07-25.md)),
objective benchmark against real generator meshes:

| | |
|---|---|
| Assets measured | 4 of 5 |
| Reached triangle budget, form preserved, imports clean | **3** |
| Assets harmed | **0** |
| Mean surface fidelity | 0.945 |
| Clear the strict full-readiness bar (0.85) | **0** — mean 0.75 |

Two open issues, stated plainly: `real_character` holds form beautifully (fidelity 0.990)
but **no current reducer can take it to budget without destroying it** — both paths scored
~0.3 and were reverted, so it ships 4× over budget or not at all. And `real_prop` timed out
in `feedback.readiness`, which left it unmeasured and correctly invalidated the run's grade.

Those numbers exist *because the ruler exists*. The claim worth attention is not the score —
it is that the tool can tell you at all, and reverts what it cannot prove instead of
shipping it.

## Layout

`▪` ships · `▫` stays in the repo (policy, harness, evidence)

```
START_HERE.md                 ← read this first
▪ src/niua_blender_mcp/       ← MCP server (Apache-2.0, never imports bpy)
▪   bridge.py / server.py       MCP ↔ Blender socket
▪   domains/                    the tool surface, minus policy/
▫   domains/policy/             budgets, gates, retopo/LOD/collision recipes
▫   finishing/                  asset classes + the finisher skills
▫   evals/                      benchmark harness (fixtures ~72 MB, untracked)
▪ blender_addon/niua_mcp_bridge/ ← Blender add-on (GPL-3.0, imports bpy)
▪   domains/eyes.py               the eyes: topology, UV checker, wire-shaded
▪   domains/objects.py            create, transform, shrinkwrap, bake_transfer
▫   domains/policy/ · finishing/  same held-back layer, add-on side
▫ tests/ · scripts/           ← how we prove it works
▫ docs/reports/               ← what we proved, and when
▫ docs/superpowers/           ← ARCHIVE (old plans) — do not start here
```

The split is enforced, not just described. Domains are discovered by module *presence*, so
an artifact without `domains/policy/` is one where those tools do not exist — there is no
flag to forget. CI builds both artifacts and fails if a policy file appears in either;
`tests/test_product_surface.py` fails if a policy tool is ever registered from a module
that ships. Build the release add-on yourself with:

```bash
python scripts/build_addon_zip.py                 # the pure MCP (62 files)
python scripts/build_addon_zip.py --include-policy # dev build, everything
```

## Develop

```bash
NIUA_SKIP_BLENDER=1 python -m pytest -q   # unit only
python -m pytest -q                       # + smoke if blender is installed
```

Three invariants are enforced by the test suite: the interface never imports finishing, the server never
imports `bpy`, and every server tool has a matching add-on handler.

**Optional:** the export check imports the finished `.glb` into a headless game engine to
prove it loads outside Blender — it uses a `godot` binary if one is on `PATH` purely as a
reference importer, and reports *unmeasured* (never a fake pass) when none is found. The
finisher itself has no engine dependency.

## Security

`system.execute_python` is **off by default**; the bridge is localhost-only. Enable Python
only for trusted local sessions (`NIUA_BLENDER_MCP_ALLOW_PYTHON=1`, or the N-panel toggle).

## License

Two programs, two licenses, split on a real process boundary:

| Component | License |
|---|---|
| MCP server (`src/`) — never imports `bpy` | **Apache-2.0** |
| Blender add-on (`blender_addon/`) — runs inside Blender | **GPL-3.0-or-later** |

The add-on calls `bpy`, so Blender's GPL applies to it; the server is a separate process
that talks over a socket and is permissively licensed. See [`LICENSING.md`](LICENSING.md).

## Deeper docs

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — the four strata and the loop
- [`LICENSING.md`](LICENSING.md) — why the server is Apache-2.0 and the add-on is GPL
- [`docs/reports/`](docs/reports/) — live run evidence, including the honest failures
- [`docs/DESIGN.md`](docs/DESIGN.md) — original full design (historical)
