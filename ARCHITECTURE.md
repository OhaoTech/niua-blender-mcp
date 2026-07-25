# Architecture (short)

**Lost?** Open [`START_HERE.md`](START_HERE.md) first.

## Job

```
rough mesh → game-ready-enough asset → Godot
```

![pipeline concept](docs/images/pipeline-concept.jpg)

*Rough mesh → driven over a socket → **measured** → verified asset. The caliper is the
point: whatever we cannot measure, we revert.*

## The system

Two processes, four strata, one loop.

```mermaid
flowchart TB
    client["MCP client · Claude / any LLM"]

    subgraph server["① SERVER PROCESS · Apache-2.0 · never imports bpy"]
        tools["② TOOL SURFACE · ~305 ToolSpecs / 48 domains<br/>schema-validated, parity-enforced · frozen library"]
        policy["④ FINISHING · asset classes, budgets, gates,<br/>skills (bake_and_finish), evals, Godot round-trip"]
    end

    subgraph blender["BLENDER PROCESS · GPL-3.0 add-on"]
        addon["niua_mcp_bridge · main-thread queue · imports bpy"]
        eyes["③ PERCEPTION · capture, silhouette IoU,<br/>surface-fidelity SSIM, topology, readiness"]
    end

    client -- "MCP stdio JSON-RPC" --> server
    policy --> tools
    tools -- "localhost socket · newline JSON<br/>(also the license boundary)" --> addon
    addon --- eyes
    supervisor["supervisor · relaunches Blender on crash"] -.-> blender

    style server fill:#e8f0fe,stroke:#4a6fa5
    style blender fill:#fff4e6,stroke:#c98a2b
    style eyes fill:#e6f7ed,stroke:#3f9e6a
    style policy fill:#f3e8fd,stroke:#8a5cc4
```

### The loop that defines the product

Most Blender MCPs stop at ①+②: *can an LLM drive Blender?* Strata ③+④ answer a
different question: *can it prove the asset is shippable?*

```mermaid
flowchart LR
    A["act<br/>(tools)"] --> M["measure<br/>(perception)"]
    M --> J["judge<br/>(gates)"]
    J -->|"passed + proven"| K["keep"]
    J -->|"failed OR unmeasured"| R["revert"]
    K --> A
    R --> A
    style M fill:#e6f7ed,stroke:#3f9e6a
    style R fill:#fde8e8,stroke:#c44
```

**Hard rule:** unmeasured quality = **revert**, never a silent pass. The ruler is
deterministic and judge-free — no LLM grades its own homework.

## Two layers (the import rule)

| Layer | Question it answers | Where |
|-------|---------------------|--------|
| **Interface** | “How do I drive Blender safely?” | kernel, bridge, most `domains/`, capture |
| **Finishing** | “Is this a shippable game asset?” | `finishing/`, `evals/`, policy domains |

Two invariants, both CI-enforced:

- finishing may import interface; **interface must never import finishing** — `tests/test_layer_boundary.py`
- **the server must never import `bpy`** — `tests/test_no_bpy_in_server.py`; this one also
  keeps the two licenses separable, see [`LICENSING.md`](LICENSING.md)

## Product vs library

| You care about | Frozen library (do not grow) |
|----------------|------------------------------|
| `bake_and_finish` skill | Extra Blender domains (sequencer, UI chrome, …) |
| gates + asset classes + fidelity | RNA “list all tools” expansion |
| objective bench + Godot | Old plans under `docs/superpowers/` |

Default finisher: `evals/finisher.py` → `finishing/skills/bake_and_finish.py`.

## Keep / freeze

- **Keep improving:** retopo, bake, UV, fail-closed fidelity, multipart stability, Godot export.
- **Freeze:** new domain packs, second finishers, platform chrome — unless the product loop is blocked.

## Historical

Long design: `docs/DESIGN.md`. Build plans/specs: `docs/superpowers/` (archive).
