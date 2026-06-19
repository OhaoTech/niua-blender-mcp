from __future__ import annotations

from niua_blender_mcp.kernel.contract import Str, ToolSpec
from niua_blender_mcp.kernel.router import Router


def _spec(name: str, category: str, source: str = "curated") -> ToolSpec:
    return ToolSpec(
        name=name,
        category=category,
        summary=name,
        command=name,
        params={"object": Str(required=True)},
        source=source,
    )


def test_add_and_get() -> None:
    r = Router()
    r.add([_spec("scene.info", "scene"), _spec("mesh.bevel", "mesh")])
    assert r.get("scene.info").category == "scene"
    assert r.get("missing") is None
    assert {s.name for s in r.specs()} == {"scene.info", "mesh.bevel"}


def test_categories() -> None:
    r = Router()
    r.add([_spec("scene.info", "scene"), _spec("mesh.bevel", "mesh"), _spec("mesh.subdivide", "mesh")])
    assert r.categories() == {"scene", "mesh"}


def test_select_by_category_for_lazy_loading() -> None:
    r = Router()
    r.add([_spec("scene.info", "scene"), _spec("mesh.bevel", "mesh")])
    selected = r.select(categories={"scene"})
    assert {s.name for s in selected} == {"scene.info"}


def test_curated_overrides_rna_regardless_of_order() -> None:
    r = Router()
    r.add([_spec("mesh.bevel", "mesh", source="rna")])
    r.add([_spec("mesh.bevel", "mesh", source="curated")])
    assert r.get("mesh.bevel").source == "curated"

    r2 = Router()
    r2.add([_spec("mesh.bevel", "mesh", source="curated")])
    r2.add([_spec("mesh.bevel", "mesh", source="rna")])  # must NOT clobber curated
    assert r2.get("mesh.bevel").source == "curated"
