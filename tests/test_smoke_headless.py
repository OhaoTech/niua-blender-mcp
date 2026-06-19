"""End-to-end smoke test against a real headless Blender.

Launches `blender --background` running the bridge, then drives it through the same
BlenderBridge the MCP server uses. Skipped automatically when no blender binary is
available or NIUA_SKIP_BLENDER is set.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from niua_blender_mcp.bridge import BlenderBridge

REPO = Path(__file__).resolve().parents[1]
ADDON_DIR = REPO / "blender_addon"
LAUNCHER = REPO / "scripts" / "blender_serve.py"

BLENDER = os.environ.get("NIUA_BLENDER_BIN") or shutil.which("blender")

pytestmark = pytest.mark.skipif(
    not BLENDER or os.environ.get("NIUA_SKIP_BLENDER"),
    reason="blender binary not available (set NIUA_BLENDER_BIN or install blender)",
)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_port(port: int, proc: subprocess.Popen, timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"blender exited early with code {proc.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.5)
    raise TimeoutError("blender bridge did not open the port in time")


@pytest.fixture()
def bridge():
    port = _free_port()
    proc = subprocess.Popen(
        [
            BLENDER, "--background", "--factory-startup",
            "--python", str(LAUNCHER), "--",
            str(ADDON_DIR), str(port), "0", "20",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_port(port, proc)
        yield BlenderBridge(port=port, timeout=30.0)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_scene_info_round_trips(bridge: BlenderBridge) -> None:
    info = bridge.call("scene.info", {})
    assert "objects" in info
    assert isinstance(info["objects"], list)


def test_create_move_and_undo_semantics(bridge: BlenderBridge) -> None:
    created = bridge.call("scene.create_object", {"type": "CUBE", "name": "NiuaHero"})
    assert created["name"] == "NiuaHero"

    moved = bridge.call("scene.set_transform", {"object": "NiuaHero", "location": [1, 2, 3]})
    assert moved["location"] == [1.0, 2.0, 3.0]

    info = bridge.call("scene.info", {})
    assert any(o["name"] == "NiuaHero" for o in info["objects"])


def test_rna_describe_reads_live_api(bridge: BlenderBridge) -> None:
    described = bridge.call("rna.describe", {"path": "op:mesh.primitive_cube_add"})
    assert described["kind"] == "operator"
    assert isinstance(described["properties"], list)


def test_set_transform_missing_object_is_clean_error(bridge: BlenderBridge) -> None:
    from niua_blender_mcp.bridge import BridgeError

    with pytest.raises(BridgeError) as exc:
        bridge.call("scene.set_transform", {"object": "DoesNotExist", "location": [0, 0, 0]})
    assert exc.value.code == "not_found"  # Blender survived; clean structured error


def test_failed_call_does_not_undo_prior_work(bridge: BlenderBridge) -> None:
    # Regression: a failed mutation must not revert the previous legitimate operation.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "KeepA"})
    from niua_blender_mcp.bridge import BridgeError

    with pytest.raises(BridgeError):
        bridge.call("scene.set_transform", {"object": "Ghost", "location": [0, 0, 0]})
    bridge.call("scene.create_object", {"type": "SPHERE", "name": "KeepB"})

    names = {o["name"] for o in bridge.call("scene.info", {})["objects"]}
    assert {"KeepA", "KeepB"} <= names  # neither was clobbered by the failed call


def test_mesh_edit_changes_geometry_end_to_end(bridge: BlenderBridge) -> None:
    # Full mesh pipeline in real Blender: create -> edit-mode op -> analytic report.
    # The kernel must guarantee EDIT mode + active mesh + selection (headless, no
    # VIEW_3D area), run one undoable mutation, and the geometry counts must change.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "MeshHero"})

    before = bridge.call("mesh.report", {"object": "MeshHero"})
    assert before["vertices"] == 8 and before["edges"] == 12 and before["faces"] == 6

    bridge.call("mesh.subdivide", {"object": "MeshHero", "cuts": 2})

    after = bridge.call("mesh.report", {"object": "MeshHero"})
    # A 2-cut subdivide turns each of the 6 cube faces into a 3x3 grid: 56v/108e/54f.
    assert after["vertices"] == 56
    assert after["edges"] == 108
    assert after["faces"] == 54
    # Strictly more geometry than before, and the edit was actually applied.
    assert after["vertices"] > before["vertices"]
    assert after["faces"] > before["faces"]
    assert after["ngons"] == 0


def test_feedback_capture_returns_a_verdict(bridge: BlenderBridge) -> None:
    # Headless has no GPU/display, so this may report unavailable; it must not crash.
    result = bridge.call("feedback.capture", {"mode": "viewport"})
    assert "available" in result


# --- Phase 2 domain smoke: one safe op per pack, end to end in real Blender ----------
# Each verifies the pack's command actually dispatches, mutates (where applicable), and
# the analytic read reflects the change. All headless-safe (no GPU/area context needed).


def test_modifiers_add_and_list(bridge: BlenderBridge) -> None:
    # modifiers.add SUBSURF then modifiers.list should reflect it on the object stack.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "ModHero"})
    added = bridge.call("modifiers.add", {"object": "ModHero", "type": "SUBSURF"})
    assert added["type"] == "SUBSURF"

    listed = bridge.call("modifiers.list", {"object": "ModHero"})
    types = {m["type"] for m in listed["modifiers"]}
    assert "SUBSURF" in types


def test_shading_create_and_assign(bridge: BlenderBridge) -> None:
    # Create a material, set Principled inputs (verifies 5.x socket names), assign it.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "ShadeHero"})
    bridge.call("shading.create_material", {"name": "SmokeMat"})
    # base_color / metallic / roughness must resolve to live Principled BSDF sockets.
    bridge.call(
        "shading.set_principled",
        {"material": "SmokeMat", "base_color": [0.8, 0.1, 0.1], "metallic": 0.5, "roughness": 0.3},
    )
    assigned = bridge.call("shading.assign_material", {"object": "ShadeHero", "material": "SmokeMat"})
    assert assigned["material"] == "SmokeMat"

    mats = bridge.call("shading.list_materials", {"object": "ShadeHero"})
    assert "SmokeMat" in mats["materials"]


def test_anim_keyframe_and_report(bridge: BlenderBridge) -> None:
    # Insert two location keyframes, then anim.report must count the f-curves/keys.
    # Regression guard for Blender 4.4+ slotted actions: f-curves moved off
    # action.fcurves into action.layers[].strips[].channelbag(slot).fcurves; a naive
    # reader reports 0 keyframes and set_interpolation wrongly fails preconditions.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "AnimHero"})
    bridge.call("anim.insert_keyframe", {"object": "AnimHero", "data_path": "location", "frame": 1})
    bridge.call("anim.insert_keyframe", {"object": "AnimHero", "data_path": "location", "frame": 10})

    report = bridge.call("anim.report", {"object": "AnimHero"})
    assert report["fcurves"] == 3  # location x/y/z
    assert report["keyframes"] == 6  # two keys per channel
    assert report["action"] is not None

    interp = bridge.call("anim.set_interpolation", {"object": "AnimHero", "interpolation": "LINEAR"})
    assert interp["fcurves"] == 3 and interp["keyframes"] == 6


def test_uv_smart_unwrap_then_report(bridge: BlenderBridge) -> None:
    # Smart-unwrap a cube (verifies uv.smart_project kwargs in 5.x), then uv.report.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "UVHero"})

    before = bridge.call("uv.report", {"object": "UVHero"})
    # A factory cube already ships with a default UVMap; smart_unwrap rebuilds it.
    assert "has_uvs" in before

    bridge.call("uv.smart_unwrap", {"object": "UVHero", "angle_limit": 66.0, "island_margin": 0.02})

    after = bridge.call("uv.report", {"object": "UVHero"})
    assert after["has_uvs"] is True
    assert after["uv_layer_count"] >= 1
    # bmesh island detection should find at least one island after a real unwrap.
    assert after["island_count"] is None or after["island_count"] >= 1


def test_rig_armature_bone_and_list(bridge: BlenderBridge) -> None:
    # Create an armature, author an edit-bone, confirm it persists into object mode.
    # Verifies edit_bones authoring survives the EDIT->OBJECT mode round-trip headless.
    bridge.call("rig.add_armature", {"name": "RigHero", "location": [0, 0, 0]})
    bridge.call(
        "rig.add_bone",
        {"armature": "RigHero", "name": "Spine", "head": [0, 0, 0], "tail": [0, 0, 1]},
    )

    bones = bridge.call("rig.list_bones", {"armature": "RigHero"})
    names = {b["name"] for b in bones["bones"]}
    assert "Spine" in names  # the authored edit-bone is now a rest-pose Bone


# --- Phase 3 smoke: live RNA discovery + generic execution, end to end -----------------
# Everything flows through the same validate -> ctx.ensure -> undo pipeline as curated
# tools. These prove the long-tail escape hatch works against a real Blender, including
# the headless EDIT-mode context path that has no VIEW_3D area to override.
#
# args / value / select cross the bridge as JSON-encoded *strings* (the kernel has no
# free-form object param kind); json.dumps here mirrors what the MCP server emits.


def test_rna_search_finds_operator_by_query(bridge: BlenderBridge) -> None:
    # rna.search mines live bpy.ops; 'bevel' must surface the mesh.bevel operator.
    result = bridge.call("rna.search", {"query": "bevel"})
    op_idnames = {m["idname"] for m in result["matches"] if m.get("kind") == "operator"}
    assert "mesh.bevel" in op_idnames
    assert result["count"] == len(result["matches"]) >= 1


def test_rna_call_operator_creates_object(bridge: BlenderBridge) -> None:
    # Generic operator execution: add a UV sphere, confirm it lands in the scene.
    before = {o["name"] for o in bridge.call("scene.info", {})["objects"]}
    bridge.call(
        "rna.call_operator",
        {"idname": "mesh.primitive_uv_sphere_add", "args": json.dumps({"radius": 2.0})},
    )
    after = {o["name"] for o in bridge.call("scene.info", {})["objects"]}
    created = after - before
    assert created, "rna.call_operator did not create any object"
    # Blender names a fresh UV sphere 'Sphere' (or 'Sphere.NNN' if one already exists).
    assert any(name.startswith("Sphere") for name in created)


def test_rna_call_operator_edits_mesh_with_mode_hint(bridge: BlenderBridge) -> None:
    # The hard one: drive an EDIT-mode mesh operator generically, headless. The kernel
    # must honor the mode/object/select hints, set up EDIT mode with no VIEW_3D area,
    # run mesh.subdivide, push one undo step, and the geometry must actually change.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "RnaMeshHero"})

    before = bridge.call("mesh.report", {"object": "RnaMeshHero"})
    assert before["vertices"] == 8 and before["faces"] == 6

    bridge.call(
        "rna.call_operator",
        {
            "idname": "mesh.subdivide",
            "args": json.dumps({"number_cuts": 1}),
            "object": "RnaMeshHero",
            "mode": "EDIT",
            "select": json.dumps(["RnaMeshHero"]),
        },
    )

    after = bridge.call("mesh.report", {"object": "RnaMeshHero"})
    # One subdivide cut on a cube: 8v/12e/6f -> 26v/48e/24f.
    assert after["vertices"] == 26 and after["faces"] == 24
    assert after["vertices"] > before["vertices"] and after["faces"] > before["faces"]
    assert after["ngons"] == 0  # subdivide produces quads, not n-gons


def test_rna_call_operator_object_mode_resize_mutates(bridge: BlenderBridge) -> None:
    # OBJECT-mode generic op with a vector arg: transform.resize must change scale.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "RnaResizeHero"})
    assert bridge.call("rna.get_property", {"path": "objects.RnaResizeHero.scale"})["value"] == [
        1.0,
        1.0,
        1.0,
    ]

    bridge.call(
        "rna.call_operator",
        {
            "idname": "transform.resize",
            "args": json.dumps({"value": [2.0, 2.0, 2.0]}),
            "object": "RnaResizeHero",
            "mode": "OBJECT",
            "select": json.dumps(["RnaResizeHero"]),
        },
    )

    assert bridge.call("rna.get_property", {"path": "objects.RnaResizeHero.scale"})["value"] == [
        2.0,
        2.0,
        2.0,
    ]


def test_rna_set_then_get_property_round_trips(bridge: BlenderBridge) -> None:
    # Drift guard: set_property writes location via a dotted bpy.data path, get_property
    # reads it back. The readback MUST be the exact non-empty value -- a getattr-with-
    # default path would mask RNA drift as a clean-but-wrong empty/None result.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "RnaPropHero"})

    written = bridge.call(
        "rna.set_property",
        {"path": "objects.RnaPropHero.location", "value": json.dumps([1, 2, 3])},
    )
    assert written["value"] == [1.0, 2.0, 3.0]

    read = bridge.call("rna.get_property", {"path": "objects.RnaPropHero.location"})
    assert read["value"] == [1.0, 2.0, 3.0]  # non-empty, correct: RNA path resolved live


def test_rna_call_operator_unknown_is_clean_error(bridge: BlenderBridge) -> None:
    # A bogus operator id must come back as a structured not_found, not crash Blender.
    from niua_blender_mcp.bridge import BridgeError

    with pytest.raises(BridgeError) as exc:
        bridge.call("rna.call_operator", {"idname": "mesh.no_such_operator_xyz"})
    assert exc.value.code == "not_found"
    # Bridge still alive afterward.
    assert "objects" in bridge.call("scene.info", {})
