from __future__ import annotations

from niua_blender_mcp.codegen import generate_specs
from niua_blender_mcp.manifest import load_manifest


def test_generates_specs_for_allowlisted_ops() -> None:
    specs = generate_specs(load_manifest())
    names = {s.name for s in specs}
    assert "modeling.subdivide" in names


def test_generated_specs_are_tier_generated() -> None:
    specs = generate_specs(load_manifest())
    assert specs and all(s.tier == "generated" for s in specs)


def test_generated_spec_carries_real_idname_in_command() -> None:
    specs = generate_specs(load_manifest())
    sub = next(s for s in specs if s.name == "modeling.subdivide")
    assert sub.command == "mesh.subdivide"


def test_enum_param_becomes_enum() -> None:
    specs = generate_specs(load_manifest())
    for spec in specs:
        for param in spec.params.values():
            if param.kind == "enum":
                assert param.choices
                return
    raise AssertionError("expected at least one generated enum param")
