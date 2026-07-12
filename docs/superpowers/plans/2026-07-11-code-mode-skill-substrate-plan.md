# Code-Mode Skill Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the hardcoded finisher into a code-mode skill substrate — a generated tool-client SDK, a Skill abstraction with the finisher ported as skill #1, and a runner that measures the token win vs tool-by-tool — with zero behavior change to the benchmark.

**Architecture:** A generator projects every non-`generated`-tier `ToolSpec` into committed, typed, per-domain Python modules under `src/niua_blender_mcp/client/` (interface layer). A `ToolSession(bridge)` exposes them as `session.<domain>.<tool>(...)`, each forwarding to `bridge.call`. Skills live in `src/niua_blender_mcp/finishing/skills/` (policy layer) and drive the SDK; the finisher is ported to `make_game_ready` and `evals/finisher.py` delegates to it (single source of loop logic). A runner records calls and a pure accounting module computes tool-by-tool vs code-mode token cost.

**Tech Stack:** Python 3 stdlib only (no new deps); pytest; the existing hand-rolled MCP kernel + TCP bridge; Blender 5.1 for the LIVE task.

## Global Constraints

- **ZERO niua knowledge in code.** The SDK is a generic projection of the tool surface; skills are niua-agnostic finishing policy.
- **Tool surface frozen:** no tool renamed/added/removed. The SDK is a projection, not a new surface.
- **Byte-identical benchmark:** after the finisher-delegates refactor, the objective bench in agent mode must produce readiness/preservation identical to today (real_character 0.76, real_character_light 0.80, real_creature 0.80, real_multipart 0.60, real_prop 0.64; and baseline mode 0.36/0.36/0.36/0.24/0.28, preservation 1.0).
- **Layer boundary green** (`tests/test_layer_boundary.py`): `client/` is interface (imports nothing from `finishing`/`evals`); `finishing/skills/` is policy (may import `client`). The boundary test's interface area must exclude nothing new that imports finishing.
- **Full offline suite green before every commit:** `NIUA_SKIP_BLENDER=1 python -m pytest -q` (currently 773 passed, 71 skipped).
- **SDK default policy (locked):** generated function parameters default to `None` and only explicitly-passed (non-`None`) args are sent on the wire — the server fills real defaults. The real default is documented in the function docstring, not the signature. This makes the ported skill's wire payloads identical to today's finisher.
- **Commit style:** one commit per task, conventional subject, trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

## File Structure

- `src/niua_blender_mcp/client/__init__.py` — exports `ToolSession`.
- `src/niua_blender_mcp/client/generate.py` — the generator: specs → per-domain source text.
- `src/niua_blender_mcp/client/session.py` — `ToolSession`, `_DomainNamespace`, `_drop_none`.
- `src/niua_blender_mcp/client/tools/__init__.py` — empty package marker.
- `src/niua_blender_mcp/client/tools/<domain>.py` — committed generated modules (one per domain).
- `src/niua_blender_mcp/client/accounting.py` — pure token-accounting.
- `src/niua_blender_mcp/finishing/skills/__init__.py` — `list_skills` / `get_skill`.
- `src/niua_blender_mcp/finishing/skills/base.py` — the `Skill` dataclass.
- `src/niua_blender_mcp/finishing/skills/make_game_ready.py` — finisher ported to the SDK.
- `src/niua_blender_mcp/evals/finisher.py` — becomes a thin adapter delegating to the skill.
- `scripts/run_skill.py` — the code-mode runner + `RecordingSession`.
- Tests: `tests/test_client_sdk.py`, `tests/test_skills.py`, `tests/test_accounting.py`, `tests/test_run_skill.py`, updates to `tests/test_layer_boundary.py`.

---

### Task 1: The tool-client SDK (generator + session + committed modules)

**Files:**
- Create: `src/niua_blender_mcp/client/__init__.py`, `client/generate.py`, `client/session.py`, `client/tools/__init__.py`, and the generated `client/tools/*.py`
- Test: `tests/test_client_sdk.py`

**Interfaces:**
- Consumes: `niua_blender_mcp.domains.build_router()` → `.specs()`; each `ToolSpec` has `.name`, `.category`, `.command`, `.summary`, `.tier`, `.params: dict[str, Param]`; `Param` has `.default`, `.summary`.
- Produces:
  - `generate.generate_all() -> dict[str, str]` — `{domain: module_source_text}`, deterministic (sorted).
  - `session.ToolSession(bridge)` — `.call(command: str, args: dict) -> Any` forwards to `bridge.call(command, args)`; `session.<domain>` returns a `_DomainNamespace`; `session.<domain>.<tool>(**kwargs)` calls the generated function.
  - Generated function contract: `def <tool>(_session, *, <param>=None, ...) -> Any` sends only non-`None` params to `_session.call("<domain>.<tool>", payload)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_client_sdk.py`:

```python
"""The generated tool-client SDK: drift-guarded projection of the tool surface."""

from __future__ import annotations

import importlib
from pathlib import Path

from niua_blender_mcp.client import ToolSession
from niua_blender_mcp.client import generate
from niua_blender_mcp.domains import build_router

_TOOLS_DIR = Path(generate.__file__).resolve().parent / "tools"


def _non_generated_specs():
    return [s for s in build_router().specs() if s.tier != "generated"]


def test_generate_all_is_deterministic():
    a = generate.generate_all()
    b = generate.generate_all()
    assert a == b and a  # non-empty, stable


def test_committed_modules_match_generated_output_no_drift():
    generated = generate.generate_all()
    for domain, source in generated.items():
        committed = (_TOOLS_DIR / f"{domain}.py").read_text(encoding="utf-8")
        assert committed == source, f"drift in client/tools/{domain}.py — re-run the generator"
    # no committed module without a generating domain
    committed_domains = {p.stem for p in _TOOLS_DIR.glob("*.py") if p.stem != "__init__"}
    assert committed_domains == set(generated), "committed modules differ from generated set"


def test_every_non_generated_tool_has_a_function():
    session = ToolSession(bridge=None)
    for spec in _non_generated_specs():
        domain, _, tool = spec.name.partition(".")
        ns = getattr(session, domain)
        assert hasattr(ns, tool), f"missing SDK function for {spec.name}"


class _RecordingBridge:
    def __init__(self):
        self.calls = []

    def call(self, command, args):
        self.calls.append((command, args))
        return {"ok": True}


def test_dispatch_sends_only_explicit_args():
    bridge = _RecordingBridge()
    session = ToolSession(bridge)
    session.mesh.tris_to_quads(object="Cube")
    assert bridge.calls == [("mesh.tris_to_quads", {"object": "Cube"})]


def test_omitted_optionals_are_dropped():
    bridge = _RecordingBridge()
    session = ToolSession(bridge)
    session.mesh.select_all(object="Cube")  # 'action' omitted -> not sent
    (command, args), = bridge.calls
    assert command == "mesh.select_all"
    assert args == {"object": "Cube"}


def test_unknown_domain_raises_attribute_error():
    session = ToolSession(bridge=None)
    try:
        session.not_a_domain
    except AttributeError:
        return
    raise AssertionError("expected AttributeError for unknown domain")
```

- [ ] **Step 2: Run to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_client_sdk.py -q`
Expected: FAIL — `ModuleNotFoundError: niua_blender_mcp.client`.

- [ ] **Step 3: Write `client/generate.py`**

```python
"""Generate a typed Python client SDK from the ToolSpec surface.

Each non-`generated`-tier spec becomes a function in its domain's module, e.g.
`mesh.tris_to_quads` -> client/tools/mesh.py:tris_to_quads. Functions default every
param to None and send only explicitly-passed args, so the server fills real defaults
(documented in the docstring). Deterministic: sorted domains, sorted tools, param order
follows ToolSpec.params insertion order.
"""

from __future__ import annotations

import keyword

from ..domains import build_router

_HEADER = "# GENERATED by client/generate.py from the ToolSpec surface — do not edit by hand.\n"


def _arg_name(pname: str) -> str:
    return f"{pname}_" if keyword.iskeyword(pname) else pname


def _default_note(pname: str, param) -> str:
    d = getattr(param, "default", None)
    summ = (getattr(param, "summary", "") or "").strip()
    bits = []
    if summ:
        bits.append(summ)
    if d is not None:
        bits.append(f"server default: {d!r}")
    return f"    {pname}: {'; '.join(bits)}" if bits else f"    {pname}"


def _function_source(spec) -> str:
    _domain, _, tool = spec.name.partition(".")
    params = list(spec.params.items())
    sig = ["_session", "*"] + [f"{_arg_name(p)}=None" for p, _ in params]
    lines = [f"def {tool}({', '.join(sig)}):"]
    doc = [f'    """{spec.summary}']
    if params:
        doc.append("")
        doc.append("    Parameters (omit to use the server default):")
        doc.extend(_default_note(p, pinfo) for p, pinfo in params)
    doc.append('    """')
    lines.extend(doc)
    if params:
        pairs = ", ".join(f'"{p}": {_arg_name(p)}' for p, _ in params)
        lines.append(f"    _payload = {{{pairs}}}")
        lines.append('    return _session.call("' + spec.command + '", _drop_none(_payload))')
    else:
        lines.append('    return _session.call("' + spec.command + '", {})')
    return "\n".join(lines) + "\n"


def generate_all() -> dict[str, str]:
    """Return {domain: module_source_text} for every non-generated-tier tool."""
    by_domain: dict[str, list] = {}
    for spec in build_router().specs():
        if spec.tier == "generated":
            continue
        by_domain.setdefault(spec.category, []).append(spec)
    out: dict[str, str] = {}
    for domain in sorted(by_domain):
        specs = sorted(by_domain[domain], key=lambda s: s.name)
        body = [
            _HEADER,
            '"""Generated client functions for the ' + domain + ' domain."""',
            "",
            "from ..session import _drop_none",
            "",
            "",
        ]
        body.append("\n\n".join(_function_source(s) for s in specs))
        out[domain] = "\n".join(body).rstrip("\n") + "\n"
    return out
```

- [ ] **Step 4: Write `client/session.py`**

```python
"""ToolSession: the code-mode entrypoint. session.<domain>.<tool>(**kwargs) -> bridge.call."""

from __future__ import annotations

import importlib
from typing import Any


def _drop_none(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if v is not None}


class _DomainNamespace:
    """Binds a domain's generated functions to a session: ns.tool(**kw)."""

    def __init__(self, session: "ToolSession", module: Any) -> None:
        self._session = session
        self._module = module

    def __getattr__(self, tool: str):
        fn = getattr(self._module, tool, None)
        if fn is None or tool.startswith("_"):
            raise AttributeError(tool)
        return lambda **kwargs: fn(self._session, **kwargs)


class ToolSession:
    """Wraps a bridge; exposes generated tool functions as session.<domain>.<tool>()."""

    def __init__(self, bridge: Any) -> None:
        self.bridge = bridge
        self._namespaces: dict[str, _DomainNamespace] = {}

    def call(self, command: str, args: dict) -> Any:
        return self.bridge.call(command, args)

    def __getattr__(self, domain: str):
        if domain.startswith("_"):
            raise AttributeError(domain)
        cache = self.__dict__.setdefault("_namespaces", {})
        if domain not in cache:
            try:
                module = importlib.import_module(f"niua_blender_mcp.client.tools.{domain}")
            except ModuleNotFoundError as exc:
                raise AttributeError(domain) from exc
            cache[domain] = _DomainNamespace(self, module)
        return cache[domain]
```

- [ ] **Step 5: Write `client/__init__.py` and `client/tools/__init__.py`**

`client/__init__.py`:
```python
"""Generated tool-client SDK (interface layer): a typed Python projection of the tool surface."""

from .session import ToolSession

__all__ = ["ToolSession"]
```
`client/tools/__init__.py`:
```python
"""Generated per-domain client modules. Regenerate with client/generate.py; do not hand-edit."""
```

- [ ] **Step 6: Generate the committed modules**

Write and run a one-off generation script (delete it after):
```bash
cat > /tmp/gen_sdk.py <<'PY'
from pathlib import Path
from niua_blender_mcp.client import generate
out = Path("src/niua_blender_mcp/client/tools")
for domain, source in generate.generate_all().items():
    (out / f"{domain}.py").write_text(source, encoding="utf-8")
    print("wrote", domain)
PY
NIUA_SKIP_BLENDER=1 python /tmp/gen_sdk.py && rm /tmp/gen_sdk.py
```
Expected: prints one line per domain (mesh, uv, object, feedback, shading, modifiers, io, session, system, scene, geometry, …).

- [ ] **Step 7: Run the tests**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_client_sdk.py -q`
Expected: PASS (6 tests). If `test_dispatch_sends_only_explicit_args` fails because `mesh.tris_to_quads` has more params than `object`, inspect the generated `client/tools/mesh.py` — the test asserts only `object` is sent, which holds because the other params default to `None` and are dropped. If a real param name collided with a Python keyword and broke import, confirm `_arg_name` added the trailing underscore.

- [ ] **Step 8: Full suite + commit**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
```bash
git add src/niua_blender_mcp/client tests/test_client_sdk.py
git commit -m "feat: generated tool-client SDK (code-mode substrate, interface layer)"
```

---

### Task 2: Skill abstraction + finisher ported + delegation

**Files:**
- Create: `src/niua_blender_mcp/finishing/skills/__init__.py`, `skills/base.py`, `skills/make_game_ready.py`
- Modify: `src/niua_blender_mcp/evals/finisher.py` (becomes a thin adapter)
- Test: `tests/test_skills.py`; `tests/evals/test_finisher.py` (must stay green unchanged)

**Interfaces:**
- Consumes: `client.ToolSession` (Task 1); `bridge.BridgeError`.
- Produces:
  - `skills.base.Skill` — frozen dataclass: `name: str`, `description: str`, `asset_classes: tuple[str, ...]`, `run: Callable[[ToolSession, str, dict], dict]`, and module constant `TOOLS_USED: set[str]` on `make_game_ready`.
  - `skills.list_skills() -> list[dict]` ({name, description, asset_classes}); `skills.get_skill(name) -> Skill`.
  - `make_game_ready.run(session, subject, params) -> dict` — same report shape as today's finisher (`readiness_start`, `readiness_final`, `moves`).
  - `evals.finisher.finish(bridge, subject, item) -> dict` — unchanged signature; now wraps bridge in a ToolSession and delegates. `TOOLS_USED` re-exported from finisher for the benchmark guard.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_skills.py`:

```python
"""The skills registry + make_game_ready ported onto the SDK, driven by a FakeSession."""

from __future__ import annotations

from niua_blender_mcp.bridge import BridgeError
from niua_blender_mcp.client import ToolSession
from niua_blender_mcp.domains import build_router
from niua_blender_mcp.finishing import skills
from niua_blender_mcp.finishing.skills import make_game_ready


def _readiness(score, failing=()):
    per_gate = [{"path": p, "op": "==", "value": True, "actual": False, "pass": False} for p in failing]
    per_gate.append({"path": "always.pass", "op": "==", "value": True, "actual": True, "pass": True})
    return {"readiness": score, "per_gate": per_gate}


class FakeBridge:
    """Behavior-driven: readiness is a state; tools in `effects` transition it; revert restores."""

    def __init__(self, before, effects=None, preservation=1.0, fail_tools=()):
        self.before = before
        self.state = before
        self.effects = dict(effects or {})
        self.preservation = preservation
        self.fail_tools = set(fail_tools)
        self.calls = []

    def call(self, tool, payload):
        self.calls.append((tool, payload))
        if tool in self.fail_tools:
            raise BridgeError("internal_error", f"{tool} exploded")
        if tool in self.effects:
            self.state = self.effects[tool]
        if tool == "session.revert":
            self.state = self.before
        if tool == "feedback.readiness":
            return self.state
        if tool == "feedback.preservation":
            return {"available": True, "preservation": self.preservation}
        if tool == "feedback.quality":
            return {"topology": {"tris": 100000},
                    "asset_class": {"effective_defaults": {"triangle_budget": 5000}}}
        if tool == "scene.info":
            return {"objects": [{"name": "subject", "type": "MESH"}]}
        return {}


ITEM_CLASS = "hard_surface_prop"


def test_registry_lists_make_game_ready_with_description():
    listed = {s["name"]: s for s in skills.list_skills()}
    assert "make_game_ready" in listed
    assert listed["make_game_ready"]["description"].strip()
    assert skills.get_skill("make_game_ready").name == "make_game_ready"


def test_improving_move_is_kept_via_sdk():
    seq = _readiness(0.5, ["uv.has_uvs"])
    after = _readiness(0.7)
    bridge = FakeBridge(before=seq, effects={"uv.smart_unwrap": after})
    session = ToolSession(bridge)
    report = make_game_ready.run(session, "subject", {"asset_class": ITEM_CLASS})
    kept = [m for m in report["moves"] if m["move"] == "uv_unwrap"]
    assert kept and kept[0]["kept"] is True
    assert not any(c[0] == "session.revert" for c in bridge.calls)


def test_regressing_move_is_reverted_via_sdk():
    bridge = FakeBridge(before=_readiness(0.5, ["uv.has_uvs"]),
                        effects={"uv.smart_unwrap": _readiness(0.3, ["uv.has_uvs"])})
    session = ToolSession(bridge)
    report = make_game_ready.run(session, "subject", {"asset_class": ITEM_CLASS})
    move = next(m for m in report["moves"] if m["move"] == "uv_unwrap")
    assert move["kept"] is False
    assert any(c[0] == "session.revert" for c in bridge.calls)


def test_all_tools_used_are_registered():
    known = {("capabilities.invoke" if s.tier == "generated" else s.command)
             for s in build_router().specs()}
    assert make_game_ready.TOOLS_USED <= known, sorted(make_game_ready.TOOLS_USED - known)


def test_finisher_delegates_to_skill_same_report_shape():
    # evals.finisher.finish still works and returns the same keys.
    from niua_blender_mcp.evals import finisher
    bridge = FakeBridge(before=_readiness(0.5, ["uv.has_uvs"]),
                        effects={"uv.smart_unwrap": _readiness(0.7)})
    report = finisher.finish(bridge, "subject", {"id": "t", "asset_class": ITEM_CLASS})
    assert set(report) == {"readiness_start", "readiness_final", "moves"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_skills.py -q`
Expected: FAIL — `ModuleNotFoundError: niua_blender_mcp.finishing.skills`.

- [ ] **Step 3: Write `skills/base.py`**

```python
"""The Skill abstraction: a named, described, code-mode finishing procedure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    asset_classes: tuple[str, ...]
    run: Callable[[Any, str, dict], dict]  # (ToolSession, subject, params) -> report
```

- [ ] **Step 4: Write `skills/make_game_ready.py` (finisher ported onto the SDK)**

The loop logic is copied verbatim from today's `evals/finisher.py`, with two changes only: (1) `bridge` becomes `session` and every `bridge.call("domain.tool", {...})` becomes `session.<domain>.<tool>(...)`; (2) `run(session, subject, params)` replaces `finish(bridge, subject, item)`, reading `params["asset_class"]`.

```python
"""Skill #1: make an asset game-ready. The deterministic finisher, ported onto the SDK.

Same accept/revert loop as the original finisher (checkpoint -> act -> re-measure
readiness + preservation -> keep iff readiness held AND preservation >= floor, else
revert + delete stray helpers), but every tool call goes through the code-mode SDK
(session.<domain>.<tool>(...)) instead of raw bridge.call. This is the single source
of the loop logic; evals/finisher.py delegates here.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from ...bridge import BridgeError
from .base import Skill

PRESERVATION_FLOOR = 0.85
_EPS = 1e-9


def _fmt(x: Any) -> str:
    return f"{x:.3f}" if isinstance(x, (int, float)) else "?"


def _log(item_id: str, msg: str) -> None:
    print(f"    [skill:{item_id}] {msg}", file=sys.stderr)


def _readiness(session, subject, asset_class):
    return session.feedback.readiness(object=subject, asset_class=asset_class)


def _failing(readiness, *paths):
    by_path = {g["path"]: g for g in (readiness or {}).get("per_gate", [])}
    return any(p in by_path and not by_path[p]["pass"] for p in paths)


def _preservation_ok(session, subject):
    try:
        pres = session.feedback.preservation(object=subject)
    except BridgeError:
        return True, None
    score = pres.get("preservation")
    if not pres.get("available") or score is None:
        return True, None
    return score >= PRESERVATION_FLOOR, score


def _scene_objects(session):
    return {o["name"] for o in session.scene.info().get("objects", [])}


def _select_all(session, subject):
    session.mesh.select_all(object=subject, action="SELECT")


def _repair(session, subject, info):
    _select_all(session, subject)
    session.mesh.remove_doubles(object=subject)
    session.mesh.recalc_normals(object=subject)


def _decimate_to_budget(session, subject, info):
    q = session.feedback.quality(object=subject, asset_class=info["asset_class"])
    tris = int(q.get("topology", {}).get("tris") or 0)
    budget = int(q.get("asset_class", {}).get("effective_defaults", {}).get("triangle_budget") or 0)
    if tris <= 0 or budget <= 0 or budget >= tris:
        return
    ratio = max(0.01, min(1.0, budget / tris))
    session.modifiers.add(object=subject, type="DECIMATE", name="niua_decimate")
    session.modifiers.set(object=subject, name="niua_decimate", property="ratio", value=str(ratio))
    session.modifiers.apply(object=subject, name="niua_decimate")


def _tris_to_quads(session, subject, info):
    _select_all(session, subject)
    session.mesh.tris_to_quads(object=subject)


def _uv_unwrap(session, subject, info):
    _select_all(session, subject)
    session.uv.smart_unwrap(object=subject)
    session.uv.pack_islands(object=subject)


def _pbr_maps(session, subject, info):
    session.shading.prepare_pbr_maps(object=subject)


def _lod(session, subject, info):
    session.object.lod_create(object=subject, ratio=0.5, apply=True)


def _collision(session, subject, info):
    session.object.collision_proxy_create(object=subject)
    session.object.collision_hulls_create(object=subject)


def _apply_transform(session, subject, info):
    session.object.transform_apply(object=subject)


MOVES: list[tuple[str, tuple[str, ...], Callable[[Any, str, dict], None]]] = [
    ("repair", ("orientation.degenerate_faces", "orientation.inward_facing_faces",
                "topology.non_manifold_edges"), _repair),
    ("decimate_to_budget", ("engine.within_triangle_budget",), _decimate_to_budget),
    ("tris_to_quads", ("topology.quad_ratio", "topology.ngons"), _tris_to_quads),
    ("uv_unwrap", ("uv.has_uvs", "uv.overlap_detected", "uv.out_of_bounds_loops",
                   "uv.stretch_ratio"), _uv_unwrap),
    ("pbr_maps", ("material.pbr_maps_present", "material.bake_maps_present",
                  "material.data_maps_non_color", "material.textures_within_size",
                  "material.atlas_ready"), _pbr_maps),
    ("lod", ("engine.has_lods", "engine.lod_triangle_reduction_ok",
             "engine.lod_silhouette_preserved"), _lod),
    ("collision", ("engine.has_collision_proxy", "engine.has_collision_hulls",
                   "engine.collision_bounds_valid"), _collision),
    ("apply_transform", ("scale.transform_applied",), _apply_transform),
]

TOOLS_USED = {
    "feedback.readiness", "feedback.preservation", "feedback.quality",
    "session.checkpoint", "session.revert", "scene.info", "object.delete",
    "mesh.select_all", "mesh.remove_doubles", "mesh.recalc_normals", "mesh.tris_to_quads",
    "modifiers.add", "modifiers.set", "modifiers.apply",
    "uv.smart_unwrap", "uv.pack_islands",
    "shading.prepare_pbr_maps",
    "object.lod_create", "object.collision_proxy_create", "object.collision_hulls_create",
    "object.transform_apply",
}


def _revert(session, subject, label, objs_before):
    strays = sorted(_scene_objects(session) - objs_before)
    if strays:
        session.object.delete(objects=",".join(strays))
    session.session.revert(object=subject, label=label)


def run(session, subject: str, params: dict) -> dict:
    asset_class = params.get("asset_class")
    item_id = str(params.get("id", subject))
    info = {"asset_class": asset_class}
    moves_report: list[dict] = []
    start = _readiness(session, subject, asset_class)
    current = start

    for name, paths, apply_move in MOVES:
        before = current if current is not None else _readiness(session, subject, asset_class)
        current = before
        if not _failing(before, *paths):
            continue
        label = f"finisher:{name}"
        session.session.checkpoint(object=subject, label=label)
        objs_before = _scene_objects(session)
        current = None
        try:
            apply_move(session, subject, info)
        except BridgeError as exc:
            _revert(session, subject, label, objs_before)
            moves_report.append({"move": name, "kept": False, "error": str(exc)[:120]})
            _log(item_id, f"{name}: ERROR {str(exc)[:80]} -> reverted")
            continue
        after = _readiness(session, subject, asset_class)
        r_before = before.get("readiness") or 0.0
        r_after = after.get("readiness") or 0.0
        pres_ok, pres = _preservation_ok(session, subject)
        kept = (r_after >= r_before - _EPS) and pres_ok
        if kept:
            current = after
        else:
            _revert(session, subject, label, objs_before)
        moves_report.append({"move": name, "kept": kept,
                             "readiness_before": before.get("readiness"),
                             "readiness_after": after.get("readiness"),
                             "preservation": pres})
        _log(item_id, f"{name}: {_fmt(before.get('readiness'))} -> {_fmt(after.get('readiness'))} "
                      f"pres={_fmt(pres)} {'KEPT' if kept else 'REVERTED'}")

    final = _readiness(session, subject, asset_class)
    return {"readiness_start": start.get("readiness"),
            "readiness_final": final.get("readiness"), "moves": moves_report}


SKILL = Skill(
    name="make_game_ready",
    description=("Take a raw generated mesh to game-ready: repair, decimate to the triangle "
                 "budget, quads, UV unwrap, PBR maps, LODs, collision, apply transforms — each "
                 "step kept only if readiness holds and the silhouette is preserved."),
    asset_classes=("hard_surface_prop", "organic_prop", "generated_cleanup", "from_scratch_prop"),
    run=run,
)
```

Note: `session.session.checkpoint(...)` is correct — the outer `session` is the ToolSession, the inner `.session` is the `session` domain namespace. `session.object.*` likewise reaches the `object` domain.

- [ ] **Step 5: Write `skills/__init__.py`**

```python
"""Skills registry: the cheap progressive-disclosure index over finishing skills."""

from __future__ import annotations

from .base import Skill
from .make_game_ready import SKILL as _MAKE_GAME_READY

_SKILLS: dict[str, Skill] = {_MAKE_GAME_READY.name: _MAKE_GAME_READY}


def list_skills() -> list[dict]:
    return [{"name": s.name, "description": s.description, "asset_classes": list(s.asset_classes)}
            for s in _SKILLS.values()]


def get_skill(name: str) -> Skill:
    try:
        return _SKILLS[name]
    except KeyError as exc:
        raise KeyError(f"unknown skill: {name}") from exc
```

- [ ] **Step 6: Rewrite `evals/finisher.py` as a thin adapter**

Replace the ENTIRE contents of `src/niua_blender_mcp/evals/finisher.py` with:

```python
"""Deterministic gate-driven finisher — the benchmark's reference finishing agent.

The finishing LOOP now lives in finishing/skills/make_game_ready.py (driven through the
code-mode SDK). This module keeps the benchmark's stable entrypoint: `finish(bridge,
subject, item)` wraps the bridge in a ToolSession and delegates to that skill, so the
objective benchmark measures the exact same behavior. `TOOLS_USED` is re-exported for
the runner's startup registration guard.

Wired into scripts/run_objective_benchmark.py via
  --mode agent --finisher niua_blender_mcp.evals.finisher:finish
"""

from __future__ import annotations

from typing import Any

from ..client import ToolSession
from ..finishing.skills.make_game_ready import PRESERVATION_FLOOR, TOOLS_USED, run

__all__ = ["finish", "TOOLS_USED", "PRESERVATION_FLOOR"]


def finish(bridge: Any, subject: str, item: dict) -> dict:
    """Runner entrypoint: finish `subject` in place; returns a per-move report."""
    params = {"asset_class": item.get("asset_class"), "id": item.get("id", subject)}
    return run(ToolSession(bridge), subject, params)
```

- [ ] **Step 7: Run the tests**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_skills.py tests/evals/test_finisher.py -q`
Expected: PASS. `tests/evals/test_finisher.py` must pass UNCHANGED — its `FakeBridge` only checks tool names and the ToolSession forwards identical `(command, args)` pairs (only-explicit-args → same names). If a `test_finisher.py` assertion checked an exact payload dict with extra keys, STOP and report — the delegation changed a payload, which must not happen.

- [ ] **Step 8: Full suite + commit**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
```bash
git add src/niua_blender_mcp/finishing/skills src/niua_blender_mcp/evals/finisher.py tests/test_skills.py
git commit -m "feat: Skill abstraction + finisher ported to make_game_ready (finisher delegates)"
```

---

### Task 3: Pure token accounting

**Files:**
- Create: `src/niua_blender_mcp/client/accounting.py`
- Test: `tests/test_accounting.py`

**Interfaces:**
- Produces: `accounting.token_accounting(calls, sdk_sources, tool_schemas, summary) -> dict` where
  - `calls: list[dict]` — each `{"tool": str, "arguments": dict, "result": Any}`
  - `sdk_sources: dict[str, str]` — `{domain: module_source_text}` for the domains the skill touched
  - `tool_schemas: dict[str, dict]` — `{tool_name: input_schema_dict}` for the distinct tools used
  - `summary: Any` — the skill's returned report
  - returns `{tool_by_tool_tokens, code_mode_tokens, ratio, tool_by_tool_bytes, code_mode_bytes, n_calls, note}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_accounting.py`:

```python
"""Pure token accounting: tool-by-tool (args+results+schemas) vs code-mode (SDK read once + summary)."""

from __future__ import annotations

from niua_blender_mcp.client import accounting


def test_tool_by_tool_exceeds_code_mode_and_ratio_is_correct():
    calls = [
        {"tool": "feedback.readiness", "arguments": {"object": "x"},
         "result": {"readiness": 0.5, "per_gate": [{"path": "a", "pass": False}] * 40}},
        {"tool": "mesh.tris_to_quads", "arguments": {"object": "x"}, "result": {"ok": True}},
    ]
    sdk_sources = {"mesh": "def tris_to_quads(...): ...\n", "feedback": "def readiness(...): ...\n"}
    tool_schemas = {"feedback.readiness": {"type": "object"}, "mesh.tris_to_quads": {"type": "object"}}
    summary = {"readiness_final": 0.7, "moves": []}
    out = accounting.token_accounting(calls, sdk_sources, tool_schemas, summary)
    assert out["n_calls"] == 2
    assert out["tool_by_tool_tokens"] > out["code_mode_tokens"]
    assert out["ratio"] == out["tool_by_tool_tokens"] / out["code_mode_tokens"]
    assert out["tool_by_tool_bytes"] > 0 and out["code_mode_bytes"] > 0
    assert "approx" in out["note"].lower()


def test_empty_run_does_not_divide_by_zero():
    out = accounting.token_accounting([], {}, {}, {})
    assert out["n_calls"] == 0
    assert out["ratio"] is None or out["ratio"] >= 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_accounting.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `client/accounting.py`**

```python
"""Deterministic token accounting for the code-mode win — pure, offline, no tokenizer dep.

approx_tokens(x) = ceil(len(json_or_str(x)) / 4), the standard rough estimate; raw byte
counts are reported alongside. Both are labelled approximate. Tool-by-tool charges every
call's arguments + FULL result (what would flow into an agent's context) plus the schema
cost of the distinct tools held; code-mode charges the touched SDK source read once plus
the single returned summary — intermediates never enter context.
"""

from __future__ import annotations

import json
import math
from typing import Any


def _text(x: Any) -> str:
    if isinstance(x, str):
        return x
    try:
        return json.dumps(x, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(x)


def _bytes(x: Any) -> int:
    return len(_text(x).encode("utf-8"))


def approx_tokens(x: Any) -> int:
    return math.ceil(len(_text(x)) / 4)


def token_accounting(calls: list[dict], sdk_sources: dict[str, str],
                     tool_schemas: dict[str, dict], summary: Any) -> dict:
    tbt_tokens = sum(approx_tokens(c.get("arguments", {})) + approx_tokens(c.get("result"))
                     for c in calls)
    tbt_tokens += sum(approx_tokens(s) for s in tool_schemas.values())
    tbt_bytes = sum(_bytes(c.get("arguments", {})) + _bytes(c.get("result")) for c in calls)
    tbt_bytes += sum(_bytes(s) for s in tool_schemas.values())

    cm_tokens = sum(approx_tokens(src) for src in sdk_sources.values()) + approx_tokens(summary)
    cm_bytes = sum(_bytes(src) for src in sdk_sources.values()) + _bytes(summary)

    ratio = (tbt_tokens / cm_tokens) if cm_tokens else None
    return {
        "tool_by_tool_tokens": tbt_tokens,
        "code_mode_tokens": cm_tokens,
        "ratio": ratio,
        "tool_by_tool_bytes": tbt_bytes,
        "code_mode_bytes": cm_bytes,
        "n_calls": len(calls),
        "note": "approx tokens = ceil(chars/4); bytes are utf-8; both approximate",
    }
```

- [ ] **Step 4: Run the tests**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_accounting.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Full suite + commit**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
```bash
git add src/niua_blender_mcp/client/accounting.py tests/test_accounting.py
git commit -m "feat: pure token accounting for the code-mode win"
```

---

### Task 4: The code-mode runner (`scripts/run_skill.py`)

**Files:**
- Create: `scripts/run_skill.py`
- Test: `tests/test_run_skill.py`

**Interfaces:**
- Consumes: `finishing.skills.get_skill`; `client.ToolSession`, `client.generate`, `client.accounting`; benchmark helpers `_build_input`, `_clear_meshes`, `assert_tools_registered` from `run_objective_benchmark`; `domains.build_router` (for schemas); `bridge.BlenderBridge`.
- Produces: module-level `RecordingSession(ToolSession)` (records `{tool, arguments, result}` per call); `main(argv) -> int`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_run_skill.py`:

```python
"""Offline guards for the code-mode skill runner."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def _load_runner():
    sys.path.insert(0, str(_REPO / "scripts"))
    import run_skill  # noqa: E402
    return run_skill


def test_runner_parses():
    import ast
    ast.parse((_REPO / "scripts" / "run_skill.py").read_text(encoding="utf-8"))


def test_recording_session_records_calls():
    runner = _load_runner()

    class _Bridge:
        def call(self, command, args):
            return {"echo": command}

    session = runner.RecordingSession(_Bridge())
    session.mesh.select_all(object="Cube", action="SELECT")
    assert session.recorded == [
        {"tool": "mesh.select_all", "arguments": {"object": "Cube", "action": "SELECT"},
         "result": {"echo": "mesh.select_all"}}
    ]


def test_skill_tools_used_are_registered():
    runner = _load_runner()
    from niua_blender_mcp.finishing.skills.make_game_ready import TOOLS_USED
    assert TOOLS_USED <= runner.known_tools()
```

- [ ] **Step 2: Run to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_run_skill.py -q`
Expected: FAIL — no `scripts/run_skill.py`.

- [ ] **Step 3: Write `scripts/run_skill.py`**

```python
#!/usr/bin/env python3
"""Code-mode skill runner: run one skill on benchmark assets in a single pass, and measure
the token win vs tool-by-tool.

Each item: build the intake (reusing the benchmark's builders), run the skill through a
RecordingSession (which captures every SDK call + full result), then compute the token
accounting from those records. The skill's whole loop runs here in the runner; only its
summary would return to an agent's context — that is the code-mode win the accounting sizes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling: run_objective_benchmark

from niua_blender_mcp.bridge import BlenderBridge  # noqa: E402
from niua_blender_mcp.client import ToolSession, accounting, generate  # noqa: E402
from niua_blender_mcp.domains import build_router  # noqa: E402
from niua_blender_mcp.evals.benchmark import list_items, load_item  # noqa: E402
from niua_blender_mcp.finishing.skills import get_skill  # noqa: E402
from run_objective_benchmark import _build_input, _clear_meshes, assert_tools_registered  # noqa: E402


class RecordingSession(ToolSession):
    """A ToolSession that records {tool, arguments, result} for every call (for accounting)."""

    def __init__(self, bridge):
        super().__init__(bridge)
        self.recorded: list[dict] = []

    def call(self, command, args):
        result = super().call(command, args)
        self.recorded.append({"tool": command, "arguments": args, "result": result})
        return result


def known_tools() -> set[str]:
    return {("capabilities.invoke" if s.tier == "generated" else s.command)
            for s in build_router().specs()}


def _schemas_for(tools: set[str]) -> dict[str, dict]:
    by_name = {s.name: s for s in build_router().specs()}
    out = {}
    for t in tools:
        spec = by_name.get(t)
        if spec is not None:
            out[t] = spec.input_schema()
    return out


def _sdk_sources_for(tools: set[str]) -> dict[str, str]:
    domains = {t.split(".", 1)[0] for t in tools}
    generated = generate.generate_all()
    return {d: generated[d] for d in domains if d in generated}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run a skill in code mode and size the token win.")
    ap.add_argument("--skill", default="make_game_ready")
    ap.add_argument("--items", default="", help="comma-separated item ids (all if empty)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--outdir", default="/tmp/niua_skill_run")
    args = ap.parse_args(argv)

    skill = get_skill(args.skill)
    ids = list_items()
    if args.items:
        wanted = set(args.items.split(","))
        ids = [i for i in ids if i in wanted]
    items = [load_item(i) for i in ids]

    # The skill declares its tools on the module; guard them offline before any bridge call.
    from niua_blender_mcp.finishing.skills import make_game_ready
    assert_tools_registered(items, extra_tools=frozenset(make_game_ready.TOOLS_USED))

    schemas = _schemas_for(make_game_ready.TOOLS_USED)
    sdk_sources = _sdk_sources_for(make_game_ready.TOOLS_USED)

    bridge = BlenderBridge(port=args.port, timeout=600.0)
    cards = []
    for item in items:
        subject = f"bench_{item['id']}"
        _clear_meshes(bridge)
        _build_input(bridge, item, subject)
        session = RecordingSession(bridge)
        summary = skill.run(session, subject, {"asset_class": item["asset_class"], "id": item["id"]})
        acct = accounting.token_accounting(session.recorded, sdk_sources, schemas, summary)
        cards.append({"id": item["id"], "readiness_final": summary.get("readiness_final"),
                      "accounting": acct})
        print(f"[{item['id']}] readiness_final={summary.get('readiness_final')} "
              f"tool_by_tool={acct['tool_by_tool_tokens']} code_mode={acct['code_mode_tokens']} "
              f"ratio={acct['ratio']:.1f}x" if acct["ratio"] else f"[{item['id']}] (no ratio)",
              file=sys.stderr)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "skill-run.json").write_text(
        json.dumps({"skill": args.skill, "items": cards}, indent=2), encoding="utf-8")
    print(json.dumps({"skill": args.skill, "items": cards}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_run_skill.py -q`
Expected: PASS (3 tests). If `test_recording_session_records_calls` fails on the exact `arguments` dict, confirm the SDK sent exactly `{"object": "Cube", "action": "SELECT"}` (both explicit → both sent).

- [ ] **Step 5: Full suite + commit**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
```bash
git add scripts/run_skill.py tests/test_run_skill.py
git commit -m "feat: code-mode skill runner — one-pass skill run + token accounting"
```

---

### Task 5: Layer-boundary guard + LIVE verification

**Files:**
- Modify: `tests/test_layer_boundary.py` (ensure `client/` is interface, `finishing/skills/` is policy)
- Create: `docs/reports/code-mode-token-win.md`
- Modify: `docs/reports/objective-baseline.md` (append confirmation)

**Interfaces:**
- Consumes: everything from Tasks 1–4.

- [ ] **Step 1: Confirm the boundary test already covers the new packages**

Read `tests/test_layer_boundary.py`. The addon/server interface areas are walked by directory. `src/niua_blender_mcp/client/` is a NEW interface package that must NOT import `finishing`/`evals`; `src/niua_blender_mcp/finishing/skills/` is inside the already-excluded `finishing/` policy area. Add an explicit assertion so `client/` can never import finishing:

```python
def test_client_sdk_is_interface_never_imports_finishing_or_evals():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "src/niua_blender_mcp/client"
    offenders = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mod = ""
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
            elif isinstance(node, ast.Import):
                mod = ",".join(a.name for a in node.names)
            if "finishing" in mod or "evals" in mod:
                offenders.append(f"{path.name}: {mod}")
    assert not offenders, offenders
```

- [ ] **Step 2: Run the boundary test**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_layer_boundary.py -q`
Expected: PASS. If it fails, the SDK imported finishing/evals — fix the SDK (it must not), not the test.

- [ ] **Step 3: Commit the guard**

```bash
git add tests/test_layer_boundary.py
git commit -m "test: assert the client SDK stays interface-layer (no finishing/evals imports)"
```

- [ ] **Step 4: LIVE — launch Blender (controller runs this)**

```bash
pkill -f blender_supervise.py || true
pkill -x blender || true
```
Then (separate command, background): `python scripts/blender_supervise.py --port 8765`
Wait for the bridge (bash tcp probe): loop `(exec 3<>/dev/tcp/127.0.0.1/8765)` until it connects.

- [ ] **Step 5: LIVE — benchmark still byte-identical (the delegation didn't change behavior)**

Run: `python scripts/run_objective_benchmark.py --mode agent --finisher niua_blender_mcp.evals.finisher:finish --no-godot --outdir /tmp/niua_post_skill`
Expected: readiness real_character 0.76, real_character_light 0.80, real_creature 0.80, real_multipart 0.60, real_prop 0.64; n_harm_flagged 0. **Any drift = the SDK port changed behavior: STOP and diff the ported skill against the original finisher before proceeding.**

- [ ] **Step 6: LIVE — run the skill runner and capture the token win**

Run: `python scripts/run_skill.py --skill make_game_ready --outdir /tmp/niua_skill_run`
Expected: per-item `readiness_final` matching Step 5, plus a `ratio` per item (expectation ≥5×, driven by the ~30–40 verbose intermediate results that code mode keeps out of context).

- [ ] **Step 7: Write the report**

Create `docs/reports/code-mode-token-win.md`: a per-asset table (n_calls, tool_by_tool_tokens, code_mode_tokens, ratio, tool_by_tool_bytes, code_mode_bytes) from `/tmp/niua_skill_run/skill-run.json`, the readiness-parity line proving the numbers came from a run identical to the benchmark, and a "Method" paragraph stating the chars/4 approximation and exactly what each side counts (tool-by-tool = every call's args + full result + the schemas held; code-mode = the touched SDK modules read once + one summary). Append a one-line post-substrate confirmation to `docs/reports/objective-baseline.md`.

- [ ] **Step 8: Commit**

```bash
git add docs/reports/code-mode-token-win.md docs/reports/objective-baseline.md
git commit -m "docs: code-mode token-win report — one-pass skill run, benchmark-identical readiness"
```

---

## Self-Review

1. **Spec coverage:** SDK generated + committed + drift-guarded (Task 1) ✓; Skill abstraction + registry + finisher ported + delegation (Task 2) ✓; pure accounting (Task 3) ✓; runner + RecordingSession + token report (Tasks 4–5) ✓; LIVE readiness parity + token-win report (Task 5) ✓; layer boundary (Task 5 Step 1) ✓; byte-identical bench gate (Task 5 Step 5) ✓; out-of-scope items (LLM authoring, sandbox, tools/list curation, new skills) correctly absent.
2. **Placeholder scan:** every code step carries complete code; the one-off generation script in Task 1 Step 6 is real and self-deleting; no TBDs.
3. **Type consistency:** `ToolSession.call(command, args)` matches `bridge.call(command, args)` (2-arg, verified against finisher.py); `session.<domain>.<tool>(**kwargs)` → `_session.call("<domain>.<tool>", payload)`; `make_game_ready.run(session, subject, params)` ↔ `finisher.finish` adapter (params = `{asset_class, id}`); `token_accounting(calls, sdk_sources, tool_schemas, summary)` identical across Task 3 def, Task 4 caller, and its test; report shape `{readiness_start, readiness_final, moves}` preserved end to end (guarded by `test_finisher_delegates_to_skill_same_report_shape` + the LIVE bench). The `session.session.*` / `session.object.*` double-name is intentional and noted.
