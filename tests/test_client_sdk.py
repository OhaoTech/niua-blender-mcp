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
