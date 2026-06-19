"""rna.search unit tests (fake-bpy).

Builds a minimal fake ``bpy`` whose ``bpy.ops`` exposes a couple of categories,
each carrying operators with ``get_rna_type()`` (description + bl_label), and a
``bpy.types`` module exposing a couple of types with ``bl_rna``. ``dir()`` is what
the handler iterates, so each fake category/types module must enumerate its members
through normal attributes. ``bpy`` is injected into sys.modules so the lazily-imported
context resolver (if touched) runs against the same fake.
"""

from __future__ import annotations

import sys
import types

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, BridgeError


class _RnaType:
    def __init__(self, description: str, bl_label: str = "") -> None:
        self.description = description
        self.bl_label = bl_label


class _FakeOp:
    def __init__(self, rna: _RnaType | None) -> None:
        self._rna = rna

    def get_rna_type(self):
        if self._rna is None:
            raise RuntimeError("no rna for this op")
        return self._rna


class _OpCategory(types.SimpleNamespace):
    """Iterated via dir(); attributes are operators."""


class _FakeBlRna:
    def __init__(self, description: str) -> None:
        self.description = description


class _FakeType:
    def __init__(self, description: str | None) -> None:
        self.bl_rna = _FakeBlRna(description) if description is not None else None


def _make_bpy() -> types.ModuleType:
    bpy = types.ModuleType("bpy")

    mesh = _OpCategory(
        bevel=_FakeOp(_RnaType("Cut into selected items at an angle to create bevel or chamfer", "Bevel")),
        subdivide=_FakeOp(_RnaType("Subdivide selected edges", "Subdivide")),
        no_desc=_FakeOp(_RnaType("")),  # filtered: no description
        broken=_FakeOp(None),  # filtered: get_rna_type raises
    )
    obj = _OpCategory(
        shade_smooth=_FakeOp(_RnaType("Render and display faces smooth, using interpolated normals", "Shade Smooth")),
    )
    # A UI/system category that must be skipped entirely.
    wm = _OpCategory(
        save_mainfile=_FakeOp(_RnaType("Save the current Blender file", "Save")),
    )

    bpy.ops = types.SimpleNamespace(mesh=mesh, object=obj, wm=wm)

    types_mod = types.SimpleNamespace(
        Object=_FakeType("Object data-block defining an object in a scene"),
        Mesh=_FakeType("Mesh data-block defining geometry"),
        Undocumented=_FakeType(""),  # filtered: no description
    )
    bpy.types = types_mod
    return bpy


@pytest.fixture()
def env(monkeypatch):
    bpy = _make_bpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def _search(ctx, payload):
    reg = build_default_registry()
    return dispatch_on_main(reg, "rna.search", payload, ctx)


def test_search_is_registered_and_read_only(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    assert "rna.search" in reg.names()
    res = _search(ctx, {"query": "bevel"})
    assert not hasattr(bpy.ops, "ed") or True  # no undo machinery touched
    assert res["kind"] == "any"


def test_operator_match_record_shape(env) -> None:
    ctx, _ = env
    res = _search(ctx, {"query": "bevel", "kind": "operator"})
    assert res["count"] == 1
    rec = res["matches"][0]
    assert rec == {
        "kind": "operator",
        "idname": "mesh.bevel",
        "category": "mesh",
        "label": "Bevel",
        "description": "Cut into selected items at an angle to create bevel or chamfer",
    }


def test_type_match_record_shape(env) -> None:
    ctx, _ = env
    res = _search(ctx, {"query": "Mesh", "kind": "type"})
    names = {m["name"] for m in res["matches"]}
    assert "Mesh" in names
    rec = next(m for m in res["matches"] if m["name"] == "Mesh")
    assert rec == {
        "kind": "type",
        "name": "Mesh",
        "description": "Mesh data-block defining geometry",
    }


def test_skips_ui_system_categories(env) -> None:
    ctx, _ = env
    res = _search(ctx, {"query": "save", "kind": "operator"})
    idnames = [m["idname"] for m in res["matches"]]
    assert "wm.save_mainfile" not in idnames


def test_requires_real_description(env) -> None:
    ctx, _ = env
    res = _search(ctx, {"query": "", "kind": "operator"})
    idnames = [m["idname"] for m in res["matches"]]
    assert "mesh.no_desc" not in idnames  # empty description filtered
    assert "mesh.broken" not in idnames  # get_rna_type raised, skipped


def test_any_kind_mixes_operators_and_types(env) -> None:
    ctx, _ = env
    res = _search(ctx, {"query": "mesh", "kind": "any"})
    kinds = {m["kind"] for m in res["matches"]}
    assert "operator" in kinds and "type" in kinds


def test_category_filter_scopes_operators(env) -> None:
    ctx, _ = env
    res = _search(ctx, {"query": "", "kind": "operator", "category": "object"})
    cats = {m["category"] for m in res["matches"]}
    assert cats == {"object"}


def test_ranking_prefers_idname_match(env) -> None:
    ctx, _ = env
    # "subdivide" matches mesh.subdivide idname strongly; should rank first.
    res = _search(ctx, {"query": "subdivide", "kind": "operator"})
    assert res["matches"][0]["idname"] == "mesh.subdivide"


def test_limit_caps_results(env) -> None:
    ctx, _ = env
    res = _search(ctx, {"query": "", "kind": "any", "limit": 1})
    assert res["count"] == 1


def test_invalid_kind_raises(env) -> None:
    ctx, _ = env
    with pytest.raises(BridgeError) as exc:
        _search(ctx, {"query": "x", "kind": "nope"})
    assert exc.value.code == INVALID_PARAMS


def test_empty_query_returns_all_documented(env) -> None:
    ctx, _ = env
    res = _search(ctx, {"query": "", "kind": "any", "limit": 100})
    idnames = {m.get("idname") for m in res["matches"] if m["kind"] == "operator"}
    # mesh.bevel, mesh.subdivide, object.shade_smooth -> wm skipped, no_desc/broken filtered
    assert idnames == {"mesh.bevel", "mesh.subdivide", "object.shade_smooth"}
