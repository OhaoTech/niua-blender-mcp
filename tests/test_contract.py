from __future__ import annotations

import pytest

from niua_blender_mcp.kernel.contract import (
    Bool,
    Enum,
    Float,
    Int,
    Str,
    ToolSpec,
    Vec3,
    validate,
)
from niua_blender_mcp.kernel.errors import ValidationError


def spec() -> ToolSpec:
    return ToolSpec(
        name="scene.create_object",
        category="scene",
        summary="Create an object",
        command="scene.create_object",
        params={
            "type": Enum(["CUBE", "SPHERE", "PLANE"], required=True),
            "name": Str(),
            "size": Float(default=2.0, minimum=0.0, maximum=100.0),
            "segments": Int(default=32, minimum=1),
            "shade_smooth": Bool(default=False),
        },
        mutates=True,
        feedback="viewport",
    )


def test_input_schema_shapes_json_schema() -> None:
    schema = spec().input_schema()
    assert schema["type"] == "object"
    assert schema["required"] == ["type"]
    assert schema["properties"]["type"]["enum"] == ["CUBE", "SPHERE", "PLANE"]
    assert schema["properties"]["size"]["type"] == "number"
    assert schema["properties"]["size"]["default"] == 2.0
    assert schema["properties"]["size"]["maximum"] == 100.0
    assert schema["properties"]["segments"]["type"] == "integer"
    assert schema["properties"]["shade_smooth"]["type"] == "boolean"


def test_validate_fills_defaults_and_keeps_provided() -> None:
    out = validate(spec(), {"type": "CUBE", "size": 4})
    assert out["type"] == "CUBE"
    assert out["size"] == 4.0  # coerced int -> float
    assert out["segments"] == 32  # default applied
    assert out["shade_smooth"] is False


def test_validate_missing_required_raises() -> None:
    with pytest.raises(ValidationError) as exc:
        validate(spec(), {"size": 1.0})
    assert "type" in str(exc.value)


def test_validate_enum_membership_enforced() -> None:
    with pytest.raises(ValidationError):
        validate(spec(), {"type": "TORUS"})


def test_validate_range_enforced() -> None:
    with pytest.raises(ValidationError):
        validate(spec(), {"type": "CUBE", "size": 999.0})


def test_validate_type_mismatch_raises() -> None:
    with pytest.raises(ValidationError):
        validate(spec(), {"type": "CUBE", "shade_smooth": "yes"})


def test_validate_integer_rejects_non_integral_float() -> None:
    with pytest.raises(ValidationError):
        validate(spec(), {"type": "CUBE", "segments": 3.5})


def test_validate_ignores_unknown_params_for_forward_compat() -> None:
    out = validate(spec(), {"type": "CUBE", "future_flag": True})
    assert "future_flag" not in out


def _vec_spec() -> ToolSpec:
    return ToolSpec(
        name="scene.set_transform",
        category="scene",
        summary="Set transform",
        command="scene.set_transform",
        params={"object": Str(required=True), "location": Vec3()},
        mutates=True,
    )


def test_vec3_schema() -> None:
    schema = _vec_spec().input_schema()
    loc = schema["properties"]["location"]
    assert loc["type"] == "array"
    assert loc["items"] == {"type": "number"}
    assert loc["minItems"] == 3 and loc["maxItems"] == 3


def test_vec3_validate_coerces_numbers() -> None:
    out = validate(_vec_spec(), {"object": "Cube", "location": [1, 2, 3]})
    assert out["location"] == [1.0, 2.0, 3.0]


def test_vec3_wrong_length_rejected() -> None:
    with pytest.raises(ValidationError):
        validate(_vec_spec(), {"object": "Cube", "location": [1, 2]})


def test_vec3_non_number_item_rejected() -> None:
    with pytest.raises(ValidationError):
        validate(_vec_spec(), {"object": "Cube", "location": [1, "x", 3]})
