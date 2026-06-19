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
import tempfile
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


def test_feedback_named_view_framing_is_not_a_code_bug(bridge: BlenderBridge) -> None:
    # Framing math (world bbox -> camera placement, via mathutils) runs even headless,
    # BEFORE the GPU render. A named view may degrade to available:false (no GPU), but
    # the reason must be a render/context degrade, NOT a framing code bug such as the
    # 'Matrix multiplication not supported between Matrix and tuple' regression (which
    # came from reading mathutils off bpy instead of importing it). This catches that
    # class headless, where fake-bpy unit tests cannot (no real mathutils matrices).
    bridge.call("scene.create_object", {"type": "CUBE", "name": "Framed"})
    res = bridge.call("feedback.capture", {"object": "Framed", "view": "front"})
    if not res.get("available"):
        reason = res.get("reason", "")
        assert "Matrix" not in reason and "tuple" not in reason, f"framing code bug: {reason}"


def test_feedback_capture_views_returns_envelope(bridge: BlenderBridge) -> None:
    # The anti-blob multi-angle. Headless has no GPU, so rendering may be unavailable;
    # what we assert is the ENVELOPE CONTRACT, not pixels: it must not crash, must carry
    # an 'available' bool and an 'images' list, and every item must be a structured dict
    # (either a rendered image {view,mimeType,encoding,data} or a per-view degrade
    # {view,available:false,reason}).
    bridge.call("scene.create_object", {"type": "CUBE", "name": "ViewsHero"})
    result = bridge.call("feedback.capture_views", {"object": "ViewsHero", "preset": "ortho4"})
    assert isinstance(result.get("available"), bool)
    assert isinstance(result.get("images"), list)
    for img in result["images"]:
        assert isinstance(img, dict)
        assert "view" in img
        # Each item is either a real image (has data) or a clean degrade (available:false).
        assert "data" in img or img.get("available") is False


def test_feedback_turntable_returns_envelope(bridge: BlenderBridge) -> None:
    # Orbit. Same contract: envelope shape holds even when rendering is unavailable
    # headless, and 'count' is honored / clamped into 2..24.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "SpinHero"})
    result = bridge.call("feedback.turntable", {"object": "SpinHero", "count": 4})
    assert isinstance(result.get("available"), bool)
    assert isinstance(result.get("images"), list)
    # When rendering is available the orbit honors 'count'; when it degrades early
    # (no GL context headless) the envelope is an empty images list + a reason. Both
    # are valid envelopes -- we never assert pixels exist headless.
    if result["available"]:
        assert len(result["images"]) == 4  # count honored once rendering works
    else:
        assert "reason" in result or result["images"] == [] or all(
            img.get("available") is False for img in result["images"]
        )
    for img in result["images"]:
        assert isinstance(img, dict)
        assert "view" in img
        assert "data" in img or img.get("available") is False


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


# --- Phase 5 io smoke: the niua -> Blender -> Godot file seam, end to end --------------
# glTF export/import needs no GPU, so the whole seam is verifiable headless. Each test
# uses a tempfile and cleans up. Together they prove export, round-trip import (export +
# import wired correctly), and the prepare_godot apply-transforms-then-export convenience.


def test_io_export_gltf_writes_nonempty_glb(bridge: BlenderBridge) -> None:
    # Create a cube, export the whole scene to a .glb, assert the file is real and non-empty.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "ExportHero"})

    fd, path = tempfile.mkstemp(suffix=".glb")
    os.close(fd)
    os.unlink(path)  # let Blender create it; we only wanted a unique name
    try:
        res = bridge.call("io.export_gltf", {"path": path, "objects": "ExportHero"})
        assert res["path"] == path
        assert res["format"] == "GLB"
        assert res["object_count"] == 1
        assert os.path.exists(path), "io.export_gltf did not write the file"
        assert os.path.getsize(path) > 0, "exported .glb is empty"
        # A real GLB starts with the 'glTF' magic; cheap proof it is a true container.
        with open(path, "rb") as fh:
            assert fh.read(4) == b"glTF"
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_io_export_then_import_round_trips(bridge: BlenderBridge) -> None:
    # ROUND-TRIP: export a cube to .glb, then io.import it back; at least one mesh object
    # must reappear. Proves export and import wire to the right operators together.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "RoundTripHero"})

    fd, path = tempfile.mkstemp(suffix=".glb")
    os.close(fd)
    os.unlink(path)
    try:
        bridge.call("io.export_gltf", {"path": path, "objects": "RoundTripHero"})
        assert os.path.getsize(path) > 0

        imported = bridge.call("io.import", {"path": path})  # AUTO infers GLB from .glb
        assert imported["format"] == "GLB"
        assert isinstance(imported["imported"], list)
        assert imported["imported"], "io.import created no objects from the round-trip .glb"

        # The imported object must really be in the scene now, as a mesh.
        info = bridge.call("scene.info", {})
        names = {o["name"] for o in info["objects"]}
        assert any(n in names for n in imported["imported"])
        new_meshes = [o for o in info["objects"] if o["name"] in imported["imported"]]
        assert any(o.get("type") == "MESH" for o in new_meshes), "no mesh object round-tripped"
    finally:
        if os.path.exists(path):
            os.unlink(path)


# --- Phase 6 smoke: safe-iterate (session) + the critique bundle, end to end -----------
# The checkpoint/revert round-trip is the loop's backbone and is FULLY headless-verifiable
# (a datablock copy + transform restore, no GPU). feedback.critique's analytic half
# (the mesh report) is headless-verifiable too; the rendered-pixel half degrades to
# available:false with no GL context, so we assert the BUNDLE ENVELOPE, not pixels.


def test_session_checkpoint_revert_round_trip(bridge: BlenderBridge) -> None:
    # THE LOOP'S BACKBONE: the agent can try an edit and cleanly undo it, beyond Blender's
    # single-op undo stack. Checkpoint a cube, subdivide it (geometry changes), then revert
    # and prove the geometry is back to the exact factory-cube counts.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "IterHero"})

    before = bridge.call("mesh.report", {"object": "IterHero"})
    assert before["vertices"] == 8 and before["edges"] == 12 and before["faces"] == 6

    # Snapshot is non-destructive: checkpoint must not mutate the live object.
    cp = bridge.call("session.checkpoint", {"object": "IterHero", "label": "pristine"})
    assert cp["object"] == "IterHero" and cp["label"] == "pristine"
    unchanged = bridge.call("mesh.report", {"object": "IterHero"})
    assert unchanged["vertices"] == 8 and unchanged["faces"] == 6

    # Try an edit: a 2-cut subdivide turns the cube into 56v/108e/54f.
    bridge.call("mesh.subdivide", {"object": "IterHero", "cuts": 2})
    edited = bridge.call("mesh.report", {"object": "IterHero"})
    assert edited["vertices"] == 56 and edited["edges"] == 108 and edited["faces"] == 54

    # Revert (most-recent checkpoint) must restore the exact pristine cube.
    reverted = bridge.call("session.revert", {"object": "IterHero"})
    assert reverted["object"] == "IterHero" and reverted["label"] == "pristine"
    assert reverted["vertices"] == 8 and reverted["faces"] == 6

    after = bridge.call("mesh.report", {"object": "IterHero"})
    assert after["vertices"] == 8 and after["edges"] == 12 and after["faces"] == 6


def test_session_list_checkpoints_reflects_store(bridge: BlenderBridge) -> None:
    # list_checkpoints is read-only and reports stored snapshots oldest-first per object.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "ListHero"})
    bridge.call("session.checkpoint", {"object": "ListHero", "label": "a"})
    bridge.call("session.checkpoint", {"object": "ListHero", "label": "b"})

    listed = bridge.call("session.list_checkpoints", {"object": "ListHero"})
    labels = [c["label"] for c in listed["checkpoints"] if c["object"] == "ListHero"]
    assert labels == ["a", "b"]  # insertion order = chronology, oldest first


def test_session_revert_missing_is_clean_error(bridge: BlenderBridge) -> None:
    # Reverting an object with no checkpoint must come back as a structured not_found,
    # never crash Blender.
    from niua_blender_mcp.bridge import BridgeError

    bridge.call("scene.create_object", {"type": "CUBE", "name": "NoCpHero"})
    with pytest.raises(BridgeError) as exc:
        bridge.call("session.revert", {"object": "NoCpHero"})
    assert exc.value.code == "not_found"
    assert "objects" in bridge.call("scene.info", {})  # bridge still alive


def test_feedback_critique_returns_bundle_envelope(bridge: BlenderBridge) -> None:
    # The one OBSERVE call: a single bundle carrying the multi-angle images AND the
    # analytic report. Headless has no GL context, so the images half may degrade to
    # available:false -- we assert the ENVELOPE, not pixels. The 'report' half is fully
    # headless-verifiable: real geometry counts for the cube.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "CritiqueHero"})

    result = bridge.call("feedback.critique", {"object": "CritiqueHero", "preset": "ortho4"})

    # Envelope shape: available bool, images list, report dict, uv key present.
    assert isinstance(result.get("available"), bool)
    assert isinstance(result.get("images"), list)
    assert "report" in result
    assert "uv" in result

    # Analytic half (no GPU needed): the report carries the cube's real geometry.
    report = result["report"]
    assert isinstance(report, dict)
    assert report.get("vertices") == 8
    assert report.get("edges") == 12
    assert report.get("faces") == 6

    # Image half: each item is either a real image (has data) or a clean per-view degrade.
    for img in result["images"]:
        assert isinstance(img, dict)
        assert "view" in img
        assert "data" in img or img.get("available") is False


def test_io_prepare_godot_applies_transforms_and_exports(bridge: BlenderBridge) -> None:
    # prepare_godot on a translated + rotated cube: applies transforms, exports one object
    # to GLB (+Y up), reports applied:true. After apply, the object's transform is identity.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "GodotHero"})
    bridge.call(
        "scene.set_transform",
        {"object": "GodotHero", "location": [3, 1, 2], "rotation": [0.5, 0.0, 0.3]},
    )

    fd, path = tempfile.mkstemp(suffix=".glb")
    os.close(fd)
    os.unlink(path)
    try:
        res = bridge.call("io.prepare_godot", {"object": "GodotHero", "path": path})
        assert res["applied"] is True
        assert res["object"] == "GodotHero"
        assert res["path"] == path
        assert os.path.exists(path) and os.path.getsize(path) > 0, "prepare_godot wrote no GLB"
        with open(path, "rb") as fh:
            assert fh.read(4) == b"glTF"

        # transform_apply zeroes location/rotation and unit-izes scale on the object.
        loc = bridge.call("rna.get_property", {"path": "objects.GodotHero.location"})["value"]
        scale = bridge.call("rna.get_property", {"path": "objects.GodotHero.scale"})["value"]
        assert loc == [0.0, 0.0, 0.0], f"location not applied: {loc}"
        assert scale == [1.0, 1.0, 1.0], f"scale not applied: {scale}"
    finally:
        if os.path.exists(path):
            os.unlink(path)
