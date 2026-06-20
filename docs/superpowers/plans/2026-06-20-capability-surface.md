# Complete Capability Surface (Layer 1) — Implementation Plan

> **For the implementing agent (Codex):** This plan is self-contained. Execute it
> task-by-task, top to bottom. Each task ends with a green test run and a commit.
> Steps use checkbox (`- [ ]`) syntax. Do NOT skip the "run the test and watch it
> fail" steps — they prove the test is real. Read the linked existing files before
> editing; mirror their style exactly (this codebase is terse, typed, comment-rich).

**Goal:** Turn Blender's full 3D-craft surface into discoverable, validated,
undo-safe, addressable capability — a three-tier system (curated craft verbs →
generated domain catalogs → a reflection floor) backed by a single committed
manifest, fronted by a `capabilities` meta-domain.

**Architecture:** One `Router` holds all tools, each tagged with a `tier`. A
script run *inside* Blender introspects `bpy` and writes a version-stamped JSON
**manifest**. The manifest powers (a) a code generator that emits typed
`ToolSpec`s for high-frequency operators (tier 2), and (b) the `capabilities`
meta-domain's `search`/`describe` (tier 3), which can find and explain *any*
operator. Generic execution (`capabilities.invoke`) dispatches through the
existing addon-side `rna.call_operator` handler, which already validates against
live RNA and flows through `ctx.ensure → poll → undo`.

**Tech Stack:** Python 3.11+, zero runtime deps (stdlib only). Tests use pytest +
the existing fake-`bpy` fixtures. Blender 5.1.x is the target; the manifest is
regenerated per Blender version.

## Global Constraints

- **Zero runtime dependencies.** stdlib only (`pyproject.toml` `dependencies = []`). Do not add packages.
- **Python ≥ 3.11.** Use `from __future__ import annotations` at the top of every module (match existing files).
- **Standalone / decoupled.** No reference to "niua", Godot, or any orchestrator in this repo's code. Blender files are generic inputs.
- **Two processes, one contract.** Server side defines `SPECS: list[ToolSpec]` per domain (`src/niua_blender_mcp/domains/`); addon side defines `COMMANDS: list[Command]` per domain (`blender_addon/niua_mcp_bridge/domains/`). A parity test enforces they match. Both are auto-discovered — adding a domain is dropping a file, never editing `__init__.py`.
- **`bpy` only via `ctx.bpy`** in addon handlers, so modules stay importable under fake-bpy unit tests.
- **Undo pushed AFTER success**, never before (see `dispatch.py` docstring). Do not change this.
- **Run tests from repo root:** `pytest` (config in `pyproject.toml`; `pythonpath = ["src", "blender_addon"]`).
- **Commit after every task** with a `feat:`/`test:`/`docs:` prefixed message.

---

## File map (what this plan creates / modifies)

**Create:**
- `src/niua_blender_mcp/manifest/__init__.py` — manifest loader + dataclasses (server side, offline).
- `src/niua_blender_mcp/manifest/blender_5_1.json` — the committed, generated manifest (written by Task 2's script).
- `src/niua_blender_mcp/codegen/__init__.py` — manifest → generated `ToolSpec`s (tier 2).
- `src/niua_blender_mcp/domains/capabilities.py` — server SPECS for the `capabilities` meta-domain.
- `blender_addon/niua_mcp_bridge/domains/capabilities.py` — addon COMMANDS (handlers) for `capabilities.*`.
- `scripts/gen_manifest.py` — producer; run *inside* Blender to (re)write the manifest JSON.
- Tests: `tests/test_tier.py`, `tests/test_manifest.py`, `tests/codegen/__init__.py`, `tests/codegen/test_codegen.py`, `tests/domains/test_capabilities.py`, plus additions to `tests/test_server.py` and `tests/test_parity.py`.

**Modify:**
- `src/niua_blender_mcp/kernel/contract.py` — add `tier` field to `ToolSpec`.
- `src/niua_blender_mcp/kernel/router.py` — tier precedence + a search index.
- `src/niua_blender_mcp/domains/__init__.py` — fold generated tier-2 specs into `build_router`.
- `src/niua_blender_mcp/server.py` — default-exposure filtering for `tools/list`.
- `docs/DESIGN.md`, `docs/PLAN.md`, `README.md` — document the three tiers + manifest.

---

## Task 1: Add `tier` to the tool contract

**Files:**
- Modify: `src/niua_blender_mcp/kernel/contract.py` (the `ToolSpec` dataclass, ~line 82-91)
- Test: `tests/test_tier.py` (create)

**Interfaces:**
- Produces: `ToolSpec(..., tier: str = "curated")` where `tier ∈ {"curated","generated","reflection"}`. Existing `source` field is retained unchanged for back-compat (it stays `"curated"|"rna"`); `tier` is the new, richer axis used by the router and `capabilities`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tier.py
from niua_blender_mcp.kernel import ToolSpec


def test_toolspec_defaults_to_curated_tier():
    spec = ToolSpec(name="x.y", category="x", summary="s", command="x.y")
    assert spec.tier == "curated"


def test_toolspec_tier_is_settable():
    spec = ToolSpec(name="x.y", category="x", summary="s", command="x.y", tier="generated")
    assert spec.tier == "generated"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_tier.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'tier'`.

- [ ] **Step 3: Add the field**

In `src/niua_blender_mcp/kernel/contract.py`, in the `ToolSpec` dataclass, add the field directly under `source`:

```python
    source: str = "curated"  # "curated" | "rna"; curated wins on name collision
    tier: str = "curated"  # "curated" | "generated" | "reflection"; precedence in that order
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/test_tier.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Full suite still green**

Run: `pytest`
Expected: all pass (no existing test constructs `ToolSpec` positionally past `source`).

- [ ] **Step 6: Commit**

```bash
git add src/niua_blender_mcp/kernel/contract.py tests/test_tier.py
git commit -m "feat: add tier field to ToolSpec"
```

---

## Task 2: Manifest producer script (runs inside Blender)

This script is the only code that touches a live `bpy`. It is **not** imported by
the server; it is run by a human/CI with `blender --background --python`. Its
output (the JSON) is committed and consumed offline by later tasks.

**Files:**
- Create: `scripts/gen_manifest.py`
- (No unit test — it requires real Blender. Task 8 adds an in-Blender completeness check. The JSON it produces is validated structurally by Task 3's loader tests against a small committed fixture.)

**Interfaces:**
- Produces: `src/niua_blender_mcp/manifest/blender_5_1.json` with this exact shape:

```json
{
  "blender_version": "5.1.1",
  "generated_by": "scripts/gen_manifest.py",
  "operators": {
    "mesh.bevel": {
      "category": "mesh",
      "label": "Bevel",
      "description": "Cut into selected items at an angle ...",
      "properties": {
        "offset": {"type": "FLOAT", "default": 0.0, "min": 0.0, "max": 1e9, "array_length": 0},
        "segments": {"type": "INT", "default": 1, "min": 1, "max": 1000, "array_length": 0},
        "affect": {"type": "ENUM", "enum": ["VERTICES", "EDGES"], "default": "EDGES"}
      }
    }
  },
  "domains": {
    "modeling": {"categories": ["mesh", "object", "transform"], "allowlist": ["mesh.bevel", "mesh.subdivide", "mesh.extrude_region_move"]},
    "uv": {"categories": ["uv"], "allowlist": ["uv.unwrap", "uv.smart_project", "uv.pack_islands"]}
  }
}
```

- `operators` = every operator outside the skip set (mirror `_SKIP_CATEGORIES` in `blender_addon/niua_mcp_bridge/domains/introspection.py`: `wm screen file ui console preferences`) that has a non-empty description. Drop `POINTER`/`COLLECTION` props' detail but keep their name+type.
- `domains` = the curated category→domain mapping + the tier-2 `allowlist` per domain (the high-frequency operators that become typed tools). Seed it with the wave-1 domains in Task 6; expand over time.

- [ ] **Step 1: Write the script**

```python
# scripts/gen_manifest.py
"""Generate the committed Blender capability manifest. Run INSIDE Blender:

    blender --background --python scripts/gen_manifest.py

Walks bpy.ops via RNA and writes src/niua_blender_mcp/manifest/blender_5_1.json.
The server reads that JSON offline (it never imports this script or bpy).
"""

import json
import os

import bpy  # available only inside Blender

SKIP = {"wm", "screen", "file", "ui", "console", "preferences"}

# Curated category -> craft domain + tier-2 allowlist. Extend as coverage grows.
DOMAINS = {
    "modeling": {
        "categories": ["mesh", "object", "transform"],
        "allowlist": [
            "mesh.subdivide", "mesh.bevel", "mesh.extrude_region_move",
            "mesh.inset", "mesh.loopcut_slide", "mesh.merge",
            "mesh.tris_convert_to_quads", "mesh.quads_convert_to_tris",
            "mesh.normals_make_consistent", "mesh.remove_doubles",
        ],
    },
    "uv": {
        "categories": ["uv"],
        "allowlist": ["uv.unwrap", "uv.smart_project", "uv.pack_islands", "uv.seams_from_islands"],
    },
    "shading": {
        "categories": ["node", "material"],
        "allowlist": ["material.new"],
    },
    "modifiers": {
        "categories": ["object"],
        "allowlist": ["object.modifier_add", "object.modifier_apply", "object.shade_smooth", "object.shade_flat"],
    },
}


def _prop(p):
    entry = {"type": getattr(p, "type", "")}
    if entry["type"] == "ENUM":
        entry["enum"] = [e.identifier for e in getattr(p, "enum_items", [])]
        default = getattr(p, "default", None)
        if default is not None:
            entry["default"] = default
        return entry
    default = getattr(p, "default", None)
    if default is not None:
        entry["default"] = default
    hard_min, hard_max = getattr(p, "hard_min", None), getattr(p, "hard_max", None)
    if hard_min is not None:
        entry["min"] = hard_min
    if hard_max is not None:
        entry["max"] = hard_max
    entry["array_length"] = int(getattr(p, "array_length", 0) or 0)
    if getattr(p, "is_required", False):
        entry["required"] = True
    return entry


def _operators():
    ops = bpy.ops
    out = {}
    for cat in dir(ops):
        if cat.startswith("_") or cat in SKIP:
            continue
        try:
            module = getattr(ops, cat)
        except Exception:
            continue
        for name in dir(module):
            if name.startswith("_"):
                continue
            try:
                rna = getattr(module, name).get_rna_type()
            except Exception:
                continue
            desc = (getattr(rna, "description", "") or "").strip()
            if not desc:
                continue
            props = {}
            for p in getattr(rna, "properties", []):
                ident = getattr(p, "identifier", "")
                if ident in ("", "rna_type"):
                    continue
                props[ident] = _prop(p)
            out[f"{cat}.{name}"] = {
                "category": cat,
                "label": getattr(rna, "bl_label", "") or getattr(rna, "name", "") or "",
                "description": desc,
                "properties": props,
            }
    return out


def main():
    manifest = {
        "blender_version": bpy.app.version_string,
        "generated_by": "scripts/gen_manifest.py",
        "operators": _operators(),
        "domains": DOMAINS,
    }
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(here, "..", "src", "niua_blender_mcp", "manifest")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "blender_5_1.json")
    with open(out_path, "w") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=True)
    print(f"wrote {out_path}: {len(manifest['operators'])} operators")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Generate the manifest (requires Blender on PATH)**

Run: `blender --background --python scripts/gen_manifest.py`
Expected: prints `wrote .../blender_5_1.json: <N> operators` with N in the low thousands.
If Blender is not installed on this machine, create a **minimal hand-written** `src/niua_blender_mcp/manifest/blender_5_1.json` containing the example shape above (a few real operators: `mesh.subdivide`, `mesh.bevel`, `uv.unwrap`, plus the `domains` block) so later tasks can proceed; flag in the commit message that the full manifest must be regenerated inside Blender.

- [ ] **Step 3: Commit**

```bash
git add scripts/gen_manifest.py src/niua_blender_mcp/manifest/blender_5_1.json
git commit -m "feat: add Blender capability manifest generator + manifest"
```

---

## Task 3: Manifest loader (server side, offline)

**Files:**
- Create: `src/niua_blender_mcp/manifest/__init__.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Produces:
  - `load_manifest(path: str | None = None) -> Manifest` — loads the committed JSON (defaults to the packaged `blender_5_1.json`). Cached.
  - `Manifest` with: `.version: str`, `.operators: dict[str, OperatorInfo]`, `.domains: dict[str, DomainInfo]`, `.search(query: str, *, kind="any", domain=None, limit=30) -> list[dict]` (same ranking contract as `introspection._score`: exact > prefix > substring over idname/label/description), `.describe(idname: str) -> dict | None` (returns `{"id","category","label","description","properties"}` or None).
  - `OperatorInfo` = dataclass with `idname, category, label, description, properties: dict`.
  - `DomainInfo` = dataclass with `name, categories: list[str], allowlist: list[str]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_manifest.py
from niua_blender_mcp.manifest import load_manifest


def test_loads_committed_manifest():
    m = load_manifest()
    assert m.version  # non-empty
    assert m.operators  # at least the seed operators
    assert "modeling" in m.domains


def test_describe_returns_operator_schema():
    m = load_manifest()
    info = m.describe("mesh.subdivide")
    assert info is not None
    assert info["id"] == "mesh.subdivide"
    assert "properties" in info


def test_describe_unknown_returns_none():
    assert load_manifest().describe("nope.nope") is None


def test_search_ranks_exact_match_first():
    m = load_manifest()
    hits = m.search("subdivide", kind="operator", limit=5)
    assert hits
    assert hits[0]["idname"] == "mesh.subdivide"


def test_search_scopes_to_domain():
    m = load_manifest()
    hits = m.search("", domain="uv", limit=50)
    assert all(h["idname"].split(".")[0] in m.domains["uv"].categories for h in hits)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `pytest tests/test_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'niua_blender_mcp.manifest'` (the package has only the JSON, no `__init__.py`).

- [ ] **Step 3: Implement the loader**

```python
# src/niua_blender_mcp/manifest/__init__.py
"""Offline loader for the committed Blender capability manifest.

The manifest is generated inside Blender (scripts/gen_manifest.py) and committed
as JSON. The server reads it here without ever importing bpy, so it works on
machines with no Blender install. Powers capabilities.search/describe (tier 3)
and the tier-2 code generator.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache

_DEFAULT = os.path.join(os.path.dirname(__file__), "blender_5_1.json")


@dataclass(frozen=True)
class OperatorInfo:
    idname: str
    category: str
    label: str
    description: str
    properties: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DomainInfo:
    name: str
    categories: list[str]
    allowlist: list[str]


def _score(query: str, *fields: str) -> int:
    """Mirror introspection._score: exact > prefix > substring, identifying-field-first."""
    if not query:
        return 1
    q = query.lower()
    best = 0
    for weight, fld in zip((100, 60, 30), fields):
        f = (fld or "").lower()
        if not f:
            continue
        if f == q:
            best = max(best, weight + 5)
        elif f.startswith(q):
            best = max(best, weight + 3)
        elif q in f:
            best = max(best, weight)
    return best


@dataclass
class Manifest:
    version: str
    operators: dict[str, OperatorInfo]
    domains: dict[str, DomainInfo]

    def describe(self, idname: str) -> dict | None:
        op = self.operators.get(idname)
        if op is None:
            return None
        return {
            "id": op.idname,
            "category": op.category,
            "label": op.label,
            "description": op.description,
            "properties": op.properties,
        }

    def search(self, query: str, *, kind: str = "any", domain: str | None = None, limit: int = 30) -> list[dict]:
        cats = set(self.domains[domain].categories) if domain and domain in self.domains else None
        scored: list[tuple[int, dict]] = []
        if kind in ("operator", "any"):
            for op in self.operators.values():
                if cats is not None and op.category not in cats:
                    continue
                s = _score(query, op.idname, op.label, op.description)
                if s:
                    scored.append((s, {
                        "kind": "operator", "idname": op.idname, "category": op.category,
                        "label": op.label, "description": op.description,
                    }))
        scored.sort(key=lambda it: (-it[0], it[1].get("idname", "")))
        return [rec for _, rec in scored[: max(1, int(limit))]]


@lru_cache(maxsize=4)
def load_manifest(path: str | None = None) -> Manifest:
    with open(path or _DEFAULT) as fh:
        raw = json.load(fh)
    operators = {
        idn: OperatorInfo(idname=idn, category=o.get("category", ""), label=o.get("label", ""),
                          description=o.get("description", ""), properties=o.get("properties", {}))
        for idn, o in raw.get("operators", {}).items()
    }
    domains = {
        name: DomainInfo(name=name, categories=list(d.get("categories", [])), allowlist=list(d.get("allowlist", [])))
        for name, d in raw.get("domains", {}).items()
    }
    return Manifest(version=raw.get("blender_version", ""), operators=operators, domains=domains)
```

- [ ] **Step 4: Ensure the manifest JSON ships with the package**

In `pyproject.toml`, under `[tool.setuptools.packages.find]` add package-data so the JSON is included. Append this block:

```toml
[tool.setuptools.package-data]
"niua_blender_mcp.manifest" = ["*.json"]
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_manifest.py -v`
Expected: PASS (5 passed). If `test_search_ranks_exact_match_first` fails because your hand-written stub manifest lacks `mesh.subdivide`, add it to the stub JSON.

- [ ] **Step 6: Commit**

```bash
git add src/niua_blender_mcp/manifest/__init__.py tests/test_manifest.py pyproject.toml
git commit -m "feat: offline manifest loader with search/describe"
```

---

## Task 4: Router tier precedence + search index

**Files:**
- Modify: `src/niua_blender_mcp/kernel/router.py`
- Test: extend `tests/test_router.py` (read it first to match fixture style)

**Interfaces:**
- Produces:
  - `Router.register` precedence generalized: on a name collision, keep the spec with the higher-priority tier where `curated > generated > reflection`. (Equal tier → last write wins, preserving today's behavior.) The existing `source`-based guard is replaced by this tier rule.
  - `Router.index() -> list[dict]` — a lightweight catalog for `capabilities.search` over registered tools: `[{"id": name, "summary", "category", "tier"}]`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_router.py`)

```python
def test_generated_does_not_clobber_curated():
    from niua_blender_mcp.kernel import Router, ToolSpec
    r = Router()
    r.register(ToolSpec(name="a.b", category="a", summary="curated", command="a.b", tier="curated"))
    r.register(ToolSpec(name="a.b", category="a", summary="generated", command="a.b", tier="generated"))
    assert r.get("a.b").summary == "curated"


def test_higher_tier_overrides_lower_regardless_of_order():
    from niua_blender_mcp.kernel import Router, ToolSpec
    r = Router()
    r.register(ToolSpec(name="a.b", category="a", summary="reflection", command="a.b", tier="reflection"))
    r.register(ToolSpec(name="a.b", category="a", summary="generated", command="a.b", tier="generated"))
    assert r.get("a.b").summary == "generated"


def test_index_lists_id_summary_category_tier():
    from niua_blender_mcp.kernel import Router, ToolSpec
    r = Router()
    r.register(ToolSpec(name="a.b", category="a", summary="s", command="a.b", tier="generated"))
    entry = next(e for e in r.index() if e["id"] == "a.b")
    assert entry == {"id": "a.b", "summary": "s", "category": "a", "tier": "generated"}
```

- [ ] **Step 2: Run and watch fail**

Run: `pytest tests/test_router.py -v`
Expected: `test_higher_tier_overrides_lower_regardless_of_order` and `test_index_*` FAIL.

- [ ] **Step 3: Implement**

Replace the body of `register` and add `index` in `src/niua_blender_mcp/kernel/router.py`:

```python
_TIER_RANK = {"curated": 3, "generated": 2, "reflection": 1}


@dataclass
class Router:
    _specs: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> None:
        existing = self._specs.get(spec.name)
        if existing is not None:
            # Higher-priority tier wins; equal tier => last write wins.
            if _TIER_RANK.get(existing.tier, 0) > _TIER_RANK.get(spec.tier, 0):
                return
        self._specs[spec.name] = spec

    def index(self) -> list[dict]:
        return [
            {"id": s.name, "summary": s.summary, "category": s.category, "tier": s.tier}
            for s in self._specs.values()
        ]
```

(Keep `add`, `get`, `specs`, `categories`, `select` exactly as they are.)

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_router.py -v`
Expected: PASS (all, including the existing ones).

- [ ] **Step 5: Full suite**

Run: `pytest`
Expected: green. (Existing `rna_exec`/`introspection` specs default to `tier="curated"`, so precedence is unchanged for them.)

- [ ] **Step 6: Commit**

```bash
git add src/niua_blender_mcp/kernel/router.py tests/test_router.py
git commit -m "feat: tier precedence and search index on Router"
```

---

## Task 5: The `capabilities` meta-domain (server SPECS + addon handlers)

This is the discoverability front door. Four tools. `search`/`describe` are
served from the manifest **server-side** (they do not need a round-trip to
Blender for known operators); `invoke` dispatches to the addon. `rna.*` names are
kept as aliases so nothing already built breaks.

**Files:**
- Create: `src/niua_blender_mcp/domains/capabilities.py` (SPECS)
- Create: `blender_addon/niua_mcp_bridge/domains/capabilities.py` (COMMANDS)
- Test: `tests/domains/test_capabilities.py`

**Interfaces:**
- Consumes: `load_manifest()` (Task 3), `Router.index()` (Task 4), the addon `rna_exec.call_operator` handler (existing).
- Produces these tools (server `SPECS`, addon `COMMANDS` mirror by name):
  - `capabilities.domains` — params: none. Returns `{"domains": [{"name","categories","tier2_count","reachable_count"}]}` from the manifest.
  - `capabilities.search` — params: `query: Str`, `kind: Enum(operator,type,any)=any`, `domain: Str?`, `limit: Int=30`. Returns the manifest search result `{"query","count","matches":[...]}`.
  - `capabilities.describe` — params: `id: Str(required)` (an operator idname, e.g. `mesh.bevel`). Returns the manifest `describe` dict; if absent from the manifest, falls back to live RNA via the addon (dispatch to `rna.describe` with `op:<id>`).
  - `capabilities.invoke` — params identical to `rna.call_operator` (`idname`, `args`, `object`, `mode`, `select`), `mutates=True`, `feedback="viewport"`. The addon handler simply **delegates to `rna_exec.call_operator`**.

**Key design note for the implementer:** `capabilities.search`, `capabilities.domains`, and the manifest path of `capabilities.describe` are pure server-side computation — but the bridge/dispatch architecture sends every `tools/call` to the addon. To keep the architecture uniform AND avoid a Blender round-trip, implement the addon handlers for `domains`/`search`/`describe` to ALSO answer from a manifest copy is NOT desired (the addon should stay thin). Instead: register addon COMMANDS for all four (so parity holds), where `domains`/`search`/`describe` handlers call into the **live RNA** implementation already in `introspection.py` (reuse `rna_search`/`rna_describe`) as the source of truth on the Blender side, and `invoke` delegates to `call_operator`. The server's manifest is used by the **code generator (Task 6)** and by offline tests; runtime search/describe go to the addon's live RNA (which is always correct for the running Blender). This keeps one source of truth at runtime (live Blender) and uses the manifest for generation + offline validation. Document this choice in the module docstring.

- [ ] **Step 1: Write the failing test** (mirror `tests/domains/test_rna_search.py` fixture style — read it first)

```python
# tests/domains/test_capabilities.py
import json

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.domains import capabilities as cap
from tests.domains.test_rna_search import make_fake_bpy  # reuse the existing fake-bpy builder


def test_search_delegates_to_live_rna():
    ctx = Ctx(make_fake_bpy())
    out = cap.search(ctx, {"query": "subdivide", "kind": "operator"})
    assert out["count"] >= 1
    assert any("subdivide" in m["idname"] for m in out["matches"])


def test_describe_returns_properties():
    ctx = Ctx(make_fake_bpy())
    out = cap.describe(ctx, {"id": "mesh.subdivide"})
    assert out["id"] == "mesh.subdivide"
    assert "properties" in out


def test_invoke_delegates_to_call_operator():
    ctx = Ctx(make_fake_bpy())
    out = cap.invoke(ctx, {"idname": "mesh.subdivide", "args": json.dumps({"number_cuts": 2})})
    assert out["operator"] == "mesh.subdivide"
```

If `tests/domains/test_rna_search.py` does not expose a reusable `make_fake_bpy`, replicate its fake-bpy setup inline in this test file (copy the fixture). Do not import private test internals that don't exist.

- [ ] **Step 2: Run and watch fail**

Run: `pytest tests/domains/test_capabilities.py -v`
Expected: FAIL — module `capabilities` not found.

- [ ] **Step 3: Implement the addon handlers**

```python
# blender_addon/niua_mcp_bridge/domains/capabilities.py
"""The capabilities meta-domain: the agent's discoverability front door.

domains / search / describe / invoke. At runtime these answer from the LIVE
Blender RNA (always correct for the running version) by reusing the introspection
and rna_exec handlers. The server-side committed manifest is used for code
generation and offline tests, not for runtime answers. rna.* names remain as
aliases (their COMMANDS still register) so existing callers keep working.
"""

from __future__ import annotations

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, BridgeError
from .introspection import rna_describe, rna_search
from .rna_exec import call_operator


def domains(ctx: Ctx, payload: dict) -> dict:
    # Group the live operator categories the agent may drive. Mirrors rna_search's
    # category surface; coverage detail comes from the committed manifest offline.
    from .introspection import _iter_operators  # reuse the live walker
    cats: dict[str, int] = {}
    for _idname, cat, _label, _desc in _iter_operators(ctx.bpy, None):
        cats[cat] = cats.get(cat, 0) + 1
    return {"domains": [{"name": c, "reachable_count": n} for c, n in sorted(cats.items())]}


def search(ctx: Ctx, payload: dict) -> dict:
    # Reuse the live RNA search; accept an optional 'domain' alias for 'category'.
    if payload.get("domain") and not payload.get("category"):
        payload = {**payload, "category": payload["domain"]}
    return rna_search(ctx, payload)


def describe(ctx: Ctx, payload: dict) -> dict:
    idn = payload.get("id")
    if not isinstance(idn, str) or not idn:
        raise BridgeError(INVALID_PARAMS, "id is required, e.g. 'mesh.bevel'")
    return rna_describe(ctx, {"path": f"op:{idn}"})


def invoke(ctx: Ctx, payload: dict) -> dict:
    return call_operator(ctx, payload)


COMMANDS = [
    Command("capabilities.domains", domains, mutates=False),
    Command("capabilities.search", search, mutates=False),
    Command("capabilities.describe", describe, mutates=False),
    Command("capabilities.invoke", invoke, mutates=True, feedback="viewport"),
]
```

- [ ] **Step 4: Implement the server SPECS**

```python
# src/niua_blender_mcp/domains/capabilities.py
"""capabilities meta-domain (server side): the discoverability front door.

Mirrors blender_addon/.../domains/capabilities.py COMMANDS by name (parity test).
search/describe/invoke supersede the rna.* tools (kept as aliases); the agent is
told to start here.
"""

from __future__ import annotations

from ..kernel import Enum, Int, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="capabilities.domains",
        category="capabilities",
        summary="List the craft domains and how many operations each exposes",
        command="capabilities.domains",
        tier="reflection",
    ),
    ToolSpec(
        name="capabilities.search",
        category="capabilities",
        summary="Search ALL of Blender for a capability by keyword, ranked (start here)",
        command="capabilities.search",
        params={
            "query": Str(required=True, summary="What you want to do, e.g. 'bevel', 'unwrap', 'smooth'"),
            "kind": Enum(["operator", "type", "any"], default="any", summary="Restrict to operators, types, or both"),
            "domain": Str(summary="Optional craft domain/category to scope to, e.g. 'mesh', 'uv'"),
            "limit": Int(default=30, minimum=1, summary="Max matches"),
        },
        tier="reflection",
    ),
    ToolSpec(
        name="capabilities.describe",
        category="capabilities",
        summary="Get the full typed parameter schema for one operation before calling it",
        command="capabilities.describe",
        params={"id": Str(required=True, summary="Operator id, e.g. 'mesh.bevel'")},
        tier="reflection",
    ),
    ToolSpec(
        name="capabilities.invoke",
        category="capabilities",
        summary="Run any Blender operator with args validated against its schema (undo-safe)",
        command="capabilities.invoke",
        params={
            "idname": Str(required=True, summary="Operator id, e.g. 'mesh.bevel'"),
            "args": Str(summary="Args as a JSON object string, e.g. '{\"offset\": 0.2}'"),
            "object": Str(summary="Active object name to set before running (optional)"),
            "mode": Str(summary="Interaction mode, e.g. 'EDIT' / 'OBJECT' (optional)"),
            "select": Str(summary="Object names to select as a JSON array string, e.g. '[\"Cube\"]'"),
        },
        mutates=True,
        feedback="viewport",
        tier="reflection",
    ),
]
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/domains/test_capabilities.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Parity + full suite**

Run: `pytest`
Expected: green. The parity test should now see `capabilities.*` on both sides. If `tests/test_parity.py` fails, read it — it likely compares the set of server command strings to addon command names; both now include the four `capabilities.*`, so it should pass without edits. If it needs the new domain explicitly acknowledged, fix per its assertion.

- [ ] **Step 7: Commit**

```bash
git add src/niua_blender_mcp/domains/capabilities.py blender_addon/niua_mcp_bridge/domains/capabilities.py tests/domains/test_capabilities.py
git commit -m "feat: capabilities meta-domain (domains/search/describe/invoke)"
```

---

## Task 6: Tier-2 code generator (manifest → typed ToolSpecs)

Generate typed `ToolSpec`s for the allowlisted operators in each domain, so the
common path has first-class tools (not just `capabilities.invoke`). Generated
tools share the addon's `rna.call_operator` handler — they carry the operator
idname in their `command`'s payload via a fixed convention, so **no new addon
handlers are needed** and parity stays trivially true.

**Files:**
- Create: `src/niua_blender_mcp/codegen/__init__.py`
- Test: `tests/codegen/__init__.py` (empty), `tests/codegen/test_codegen.py`

**Interfaces:**
- Consumes: `load_manifest()` (Task 3), `ToolSpec`/`Str`/`Int`/`Float`/`Bool`/`Enum` (kernel).
- Produces: `generate_specs(manifest=None) -> list[ToolSpec]`. For each domain, for each `allowlist` idname present in `manifest.operators`, emit one `ToolSpec`:
  - `name = f"{domain}.{op_name}"` where `op_name` is the part after the category dot, e.g. domain `modeling` + `mesh.bevel` → `modeling.bevel`. **If that name collides with a curated tool, the router drops the generated one (Task 4 precedence) — that's intended.**
  - `command = "capabilities.invoke"`, and the spec carries the real idname so the server can inject it. **Mechanism:** generated specs get a fixed param default. Add a hidden `idname` param with `default=<real idname>` and `required=False`; the typed craft params map onto `args`. To keep the existing `validate → bridge.call(command, clean)` flow unchanged, the generator instead emits specs whose `command` is the operator idname-bearing form and relies on a thin server adaptation (next bullet).
  - **Server adaptation (do this in Task 7, not here):** when `spec.tier == "generated"`, the server packs the validated typed args into the `args` JSON string and calls `capabilities.invoke`. The generator's job is only to PRODUCE specs + remember each spec's source idname. Store the idname on the spec via the existing `command` field set to the operator idname (e.g. `command="mesh.bevel"`); the server special-cases generated tier in Task 7.
  - Map manifest prop types → kernel params: `INT→Int(default,min,max)`, `FLOAT→Float(default,min,max)` (skip min/max if they are ±1e38-ish sentinels: treat `abs >= 1e30` as unbounded), `BOOLEAN→Bool(default)`, `ENUM→Enum(enum, default)`, `STRING→Str(default)`. Skip props whose type is `POINTER`/`COLLECTION`. Skip array props (`array_length > 1`) for now (document the limitation).

- [ ] **Step 1: Write the failing test**

```python
# tests/codegen/test_codegen.py
from niua_blender_mcp.codegen import generate_specs
from niua_blender_mcp.manifest import load_manifest


def test_generates_specs_for_allowlisted_ops():
    specs = generate_specs(load_manifest())
    names = {s.name for s in specs}
    # modeling.subdivide comes from mesh.subdivide in the modeling allowlist
    assert "modeling.subdivide" in names


def test_generated_specs_are_tier_generated():
    specs = generate_specs(load_manifest())
    assert specs and all(s.tier == "generated" for s in specs)


def test_generated_spec_carries_real_idname_in_command():
    specs = generate_specs(load_manifest())
    sub = next(s for s in specs if s.name == "modeling.subdivide")
    assert sub.command == "mesh.subdivide"


def test_enum_param_becomes_enum():
    specs = generate_specs(load_manifest())
    # find any generated spec that has an enum param; assert choices preserved
    for s in specs:
        for p in s.params.values():
            if p.kind == "enum":
                assert p.choices  # non-empty
                return
```

- [ ] **Step 2: Run and watch fail**

Run: `pytest tests/codegen/test_codegen.py -v`
Expected: FAIL — `codegen` module not found. (If your stub manifest lacks `mesh.subdivide` in the modeling allowlist, add it.)

- [ ] **Step 3: Implement the generator**

```python
# src/niua_blender_mcp/codegen/__init__.py
"""Tier-2 code generation: committed manifest -> typed ToolSpecs.

Each allowlisted operator becomes a named craft tool (e.g. modeling.subdivide).
Generated specs carry the real operator idname in `command`; the server packs the
validated typed args and routes them through capabilities.invoke (see server.py).
The router drops any generated name that collides with a curated tool.
"""

from __future__ import annotations

from ..kernel import Bool, Enum, Float, Int, Str, ToolSpec
from ..manifest import Manifest, load_manifest

_UNBOUNDED = 1e30  # treat |hard_min/max| >= this as "no bound"


def _param(pinfo: dict):
    ptype = pinfo.get("type", "")
    if ptype == "ENUM":
        choices = pinfo.get("enum", [])
        if not choices:
            return None
        return Enum(choices, default=pinfo.get("default"))
    if ptype == "INT":
        return Int(default=pinfo.get("default"), minimum=_bound(pinfo.get("min")), maximum=_bound(pinfo.get("max")))
    if ptype == "FLOAT":
        return Float(default=pinfo.get("default"), minimum=_bound(pinfo.get("min")), maximum=_bound(pinfo.get("max")))
    if ptype == "BOOLEAN":
        return Bool(default=pinfo.get("default"))
    if ptype == "STRING":
        return Str(default=pinfo.get("default"))
    return None  # POINTER / COLLECTION / unknown -> skip


def _bound(v):
    if v is None:
        return None
    try:
        return None if abs(float(v)) >= _UNBOUNDED else v
    except (TypeError, ValueError):
        return None


def generate_specs(manifest: Manifest | None = None) -> list[ToolSpec]:
    m = manifest or load_manifest()
    specs: list[ToolSpec] = []
    for domain in m.domains.values():
        for idname in domain.allowlist:
            op = m.operators.get(idname)
            if op is None:
                continue
            op_name = idname.split(".", 1)[1]
            params = {}
            for pid, pinfo in op.properties.items():
                if int(pinfo.get("array_length", 0) or 0) > 1:
                    continue  # arrays not supported yet
                param = _param(pinfo)
                if param is not None:
                    params[pid] = param
            specs.append(ToolSpec(
                name=f"{domain.name}.{op_name}",
                category=domain.name,
                summary=(op.description.split(".")[0] or op.label or op_name)[:160],
                command=idname,  # real operator idname; server routes via capabilities.invoke
                params=params,
                mutates=True,
                feedback="viewport",
                tier="generated",
            ))
    return specs
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/codegen/test_codegen.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/niua_blender_mcp/codegen/__init__.py tests/codegen/
git commit -m "feat: tier-2 code generator from manifest"
```

---

## Task 7: Wire generated specs into the router + server routing for generated tools

**Files:**
- Modify: `src/niua_blender_mcp/domains/__init__.py` (`build_router`)
- Modify: `src/niua_blender_mcp/server.py` (`_tools_call`, `_tool_defs`)
- Test: extend `tests/test_server.py` (read it first for the fake-bridge fixture)

**Interfaces:**
- Consumes: `generate_specs()` (Task 6), `Router` precedence (Task 4).
- Produces:
  - `build_router()` now also registers `generate_specs()` (curated specs still win on name collisions).
  - `server._tools_call`: when the resolved `spec.tier == "generated"`, the server (a) validates typed args against the spec as usual, (b) JSON-encodes them into an `args` string, (c) calls the bridge with command `capabilities.invoke` and payload `{"idname": spec.command, "args": <json>}` (carrying through `object`/`mode`/`select` if the spec declares them — wave-1 generated tools don't, so just pass `idname`+`args`). Curated/reflection tools dispatch exactly as before.
  - `server._tool_defs` (the `tools/list` payload): by default expose only `tier != "generated"` tools PLUS allow opt-in to list everything via env `NIUA_BLENDER_MCP_LIST_ALL=1`. Generated tools remain fully callable by name regardless (so an agent that learned a name from `capabilities.search` can call it); they're just not flooded into `tools/list`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_server.py`; reuse its existing fake bridge)

```python
def test_generated_tools_hidden_from_list_by_default(monkeypatch):
    monkeypatch.delenv("NIUA_BLENDER_MCP_LIST_ALL", raising=False)
    from niua_blender_mcp.server import create_server
    srv = create_server(bridge=_FakeBridge())  # _FakeBridge defined in this test module
    listed = {t["name"] for t in srv._tool_defs()}
    assert not any(t.startswith("modeling.") for t in listed)
    assert "capabilities.search" in listed


def test_generated_tool_routes_through_invoke():
    from niua_blender_mcp.server import create_server
    bridge = _RecordingBridge()  # captures (command, payload); returns {}
    srv = create_server(bridge=bridge)
    srv._tools_call({"name": "modeling.subdivide", "arguments": {"number_cuts": 3}})
    assert bridge.last_command == "capabilities.invoke"
    assert bridge.last_payload["idname"] == "mesh.subdivide"
    assert '"number_cuts": 3' in bridge.last_payload["args"]
```

Add the small `_RecordingBridge` helper in the test module if not present:

```python
class _RecordingBridge:
    def __init__(self):
        self.last_command = None
        self.last_payload = None
    def call(self, command, payload):
        self.last_command, self.last_payload = command, payload
        return {}
```

- [ ] **Step 2: Run and watch fail**

Run: `pytest tests/test_server.py -v`
Expected: the two new tests FAIL (generated tools not registered / not routed).

- [ ] **Step 3: Register generated specs**

In `src/niua_blender_mcp/domains/__init__.py`, extend `build_router`:

```python
from ..codegen import generate_specs


def build_router() -> Router:
    router = Router()
    router.add(_discover_specs())          # curated + reflection (tier precedence in register)
    router.add(generate_specs())           # tier-2 generated; curated names win on collision
    return router
```

- [ ] **Step 4: Route generated tools + filter the list in `server.py`**

In `_tool_defs`, filter by tier unless the env opts in:

```python
    def _tool_defs(self) -> list[JSON]:
        list_all = os.environ.get("NIUA_BLENDER_MCP_LIST_ALL") == "1"
        return [
            {"name": s.name, "description": s.summary, "inputSchema": s.input_schema()}
            for s in self.router.specs()
            if list_all or s.tier != "generated"
        ]
```

In `_tools_call`, after `clean = validate(...)` and the python-gate check, special-case generated tier before the normal `self.bridge.call`:

```python
        try:
            if spec.tier == "generated":
                import json
                payload = {"idname": spec.command, "args": json.dumps(clean)}
                result = self.bridge.call("capabilities.invoke", payload)
            else:
                result = self.bridge.call(spec.command, clean)
        except BridgeError as exc:
            return self._tool_error(exc.code, exc.message, exc.detail)
        return self._tool_result(result)
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_server.py -v`
Expected: PASS (new + existing).

- [ ] **Step 6: Full suite**

Run: `pytest`
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add src/niua_blender_mcp/domains/__init__.py src/niua_blender_mcp/server.py tests/test_server.py
git commit -m "feat: register generated tools and route them via capabilities.invoke"
```

---

## Task 8: Completeness + manifest-drift checks (in-Blender, skipped without Blender)

**Files:**
- Modify: `tests/test_smoke_headless.py` (read it first — it already guards on Blender being available and talks to a live bridge). Add two checks.

**Interfaces:**
- Consumes: a live bridge connection (existing helper in that file), `load_manifest()`.

- [ ] **Step 1: Add the checks** (follow the file's existing skip-guard + bridge fixture)

```python
def test_capabilities_search_finds_bevel(live_bridge):  # use the file's existing fixture name
    out = live_bridge.call("capabilities.search", {"query": "bevel", "kind": "operator"})
    assert any(m["idname"] == "mesh.bevel" for m in out["matches"])


def test_manifest_matches_live_rna_sample(live_bridge):
    from niua_blender_mcp.manifest import load_manifest
    m = load_manifest()
    # Sample a few committed operators; each must still exist + describe live.
    for idname in ["mesh.subdivide", "mesh.bevel", "uv.unwrap"]:
        if idname not in m.operators:
            continue
        live = live_bridge.call("capabilities.describe", {"id": idname})
        assert live["id"] == idname
        assert "properties" in live
```

If the file's fixture is not named `live_bridge`, match whatever it uses (read the top of the file).

- [ ] **Step 2: Run (with Blender running the addon, or expect skip)**

Run: `pytest tests/test_smoke_headless.py -v`
Expected: PASS if a live Blender bridge is reachable; SKIPPED otherwise (same as the existing tests in that file).

- [ ] **Step 3: Commit**

```bash
git add tests/test_smoke_headless.py
git commit -m "test: capabilities search + manifest-drift smoke checks"
```

---

## Task 9: Docs

**Files:**
- Modify: `docs/DESIGN.md` (add a "Three-tier capability surface" section), `docs/PLAN.md` (add this milestone), `README.md` (one paragraph + how to regenerate the manifest).

- [ ] **Step 1: DESIGN.md** — add a section summarizing: the three tiers, the manifest (producer `scripts/gen_manifest.py`, committed JSON, consumers = codegen + capabilities), the `capabilities` front door, lazy listing (generated hidden from `tools/list` by default, reachable by name; `NIUA_BLENDER_MCP_LIST_ALL=1` to list all). Keep it consistent with the spec at `docs/superpowers/specs/2026-06-20-blender-mcp-capability-surface-design.md`.

- [ ] **Step 2: README.md** — add: "Regenerate the capability manifest after a Blender upgrade: `blender --background --python scripts/gen_manifest.py`."

- [ ] **Step 3: PLAN.md** — add this milestone as done/in-progress with the four sub-steps (manifest, capabilities, tier-2 generator, coverage fill).

- [ ] **Step 4: Commit**

```bash
git add docs/DESIGN.md docs/PLAN.md README.md
git commit -m "docs: document three-tier capability surface and manifest workflow"
```

---

## Final verification

- [ ] Run the whole suite: `pytest` → all green (Blender-dependent tests skip cleanly without Blender).
- [ ] `git log --oneline` shows one commit per task.
- [ ] Sanity: `python -c "from niua_blender_mcp.domains import build_router; r=build_router(); print(len(r.specs()), 'tools;', sum(s.tier=='generated' for s in r.specs()), 'generated')"` prints a tool count with a non-zero generated count.
- [ ] Regenerate the real manifest inside Blender (`blender --background --python scripts/gen_manifest.py`) if Task 2 used the hand-written stub, then re-run `pytest` and commit the regenerated JSON.

---

## Notes / known limitations (carry forward to layer 2)

- **POINTER/COLLECTION operator args** (datablock references) are not yet
  supported by the generic coercer; generated tools skip those params. Craft
  verbs (layer 2) will handle datablock wiring explicitly.
- **Array props** (`array_length > 1`) are skipped in tier-2 generation; reachable
  via `capabilities.invoke` with a JSON array in `args`.
- **Runtime search/describe use live RNA** (always correct for the running
  Blender); the committed manifest drives codegen + offline tests. The
  manifest-drift smoke test (Task 8) catches divergence after a Blender upgrade.
- **Deferred (layer 2, separate spec):** craft verbs + judgment playbooks; deeper
  eyes (topology-flow / UV-layout / texel-density / shading-error / silhouette;
  includes fixing the known `feedback.capture` WIREFRAME-renders-as-solid bug);
  game pipeline (LOD / collision / atlas / engine conventions).
```

