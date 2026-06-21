"""End-to-end smoke test against a real headless Blender.

Launches `blender --background` running the bridge, then drives it through the same
BlenderBridge the MCP server uses. Skipped automatically when no blender binary is
available or NIUA_SKIP_BLENDER is set.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

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


def test_app_info_and_workspaces_round_trip(bridge: BlenderBridge) -> None:
    info = bridge.call("app.info", {})
    assert info["version_string"]
    assert isinstance(info["version"], list)
    assert isinstance(info["background"], bool)
    assert "filepath" in info
    assert "is_dirty" in info
    assert "scene" in info

    workspaces = bridge.call("app.workspaces", {})
    assert isinstance(workspaces["workspaces"], list)
    assert workspaces["workspaces"], "Blender should expose at least one workspace"
    assert workspaces["active"] in workspaces["workspaces"] or workspaces["active"] is None


def test_app_file_save_copy_save_as_and_open_round_trip(bridge: BlenderBridge) -> None:
    bridge.call("scene.create_object", {"type": "CUBE", "name": "FileHero"})
    with tempfile.TemporaryDirectory() as tmp:
        saved_path = os.path.join(tmp, "saved.blend")
        copy_path = os.path.join(tmp, "copy.blend")

        saved = bridge.call("app.file_save_as", {"path": saved_path})
        assert saved["filepath"] == saved_path
        assert saved["is_saved"] is True
        assert os.path.exists(saved_path) and os.path.getsize(saved_path) > 0

        copied = bridge.call("app.file_save_copy", {"path": copy_path})
        assert copied["filepath"] == saved_path
        assert os.path.exists(copy_path) and os.path.getsize(copy_path) > 0

        bridge.call("scene.create_object", {"type": "CUBE", "name": "AfterCopy"})
        opened = bridge.call("app.file_open", {"path": copy_path, "force": True})
        assert opened["filepath"] == copy_path
        assert opened["is_saved"] is True

        info = bridge.call("scene.info", {})
        names = {o["name"] for o in info["objects"]}
        assert "FileHero" in names
        assert "AfterCopy" not in names


def test_create_move_and_undo_semantics(bridge: BlenderBridge) -> None:
    created = bridge.call("scene.create_object", {"type": "CUBE", "name": "NiuaHero"})
    assert created["name"] == "NiuaHero"

    moved = bridge.call("scene.set_transform", {"object": "NiuaHero", "location": [1, 2, 3]})
    assert moved["location"] == [1.0, 2.0, 3.0]

    info = bridge.call("scene.info", {})
    assert any(o["name"] == "NiuaHero" for o in info["objects"])


def test_app_undo_redo_keep_bridge_alive(bridge: BlenderBridge) -> None:
    bridge.call("scene.create_object", {"type": "CUBE", "name": "UndoHero"})
    undo = bridge.call("app.undo", {})
    if undo.get("available") is False:
        assert "current Blender context" in undo["reason"]
        assert "objects" in bridge.call("scene.info", {})
        return
    assert undo == {"ok": True, "applied": ["ed.undo"]}

    redo = bridge.call("app.redo", {})
    if redo.get("available") is False:
        assert "current Blender context" in redo["reason"]
        assert "objects" in bridge.call("scene.info", {})
        return
    assert redo == {"ok": True, "applied": ["ed.redo"]}
    assert "objects" in bridge.call("scene.info", {})


def test_outliner_scene_tree_workflow(bridge: BlenderBridge) -> None:
    bridge.call("scene.create_object", {"type": "EMPTY", "name": "OutlinerParent"})
    bridge.call("scene.create_object", {"type": "CUBE", "name": "OutlinerChild"})

    created = bridge.call("outliner.collection_create", {"name": "OutlinerProps"})
    assert created["collection"]["name"] == "OutlinerProps"

    moved = bridge.call(
        "outliner.object_move",
        {"object": "OutlinerChild", "collection": "OutlinerProps"},
    )
    assert moved["object"]["collections"] == ["OutlinerProps"]

    parented = bridge.call(
        "outliner.parent_set",
        {"object": "OutlinerChild", "parent": "OutlinerParent"},
    )
    assert parented["object"]["parent"] == "OutlinerParent"

    cleared = bridge.call("outliner.parent_clear", {"object": "OutlinerChild"})
    assert cleared["object"]["parent"] is None

    obj_vis = bridge.call(
        "outliner.visibility_set",
        {"object": "OutlinerChild", "viewport": False, "render": False, "selectable": False},
    )
    assert obj_vis["object"]["visible"] is False
    assert obj_vis["object"]["renderable"] is False
    assert obj_vis["object"]["selectable"] is False

    col_vis = bridge.call(
        "outliner.collection_visibility_set",
        {"collection": "OutlinerProps", "viewport": False, "render": False, "selectable": False},
    )
    assert col_vis["collection"]["visible"] is False
    assert col_vis["collection"]["renderable"] is False
    assert col_vis["collection"]["selectable"] is False

    layers = bridge.call("outliner.view_layer_create", {"name": "OutlinerBeauty"})
    assert "OutlinerBeauty" in {layer["name"] for layer in layers["view_layers"]}

    restricted = bridge.call(
        "outliner.layer_collection_set",
        {
            "view_layer": "OutlinerBeauty",
            "collection": "OutlinerProps",
            "exclude": True,
            "viewport": False,
            "holdout": True,
            "indirect_only": True,
        },
    )
    assert restricted["layer_collection"]["collection"] == "OutlinerProps"
    assert restricted["layer_collection"]["exclude"] is True
    assert restricted["layer_collection"]["hide_viewport"] is True
    assert restricted["layer_collection"]["holdout"] is True
    assert restricted["layer_collection"]["indirect_only"] is True

    deleted = bridge.call("outliner.view_layer_delete", {"name": "OutlinerBeauty", "force": True})
    assert "OutlinerBeauty" not in {layer["name"] for layer in deleted["view_layers"]}

    tree = bridge.call("outliner.tree", {})
    child_collections = {child["name"] for child in tree["root"]["children"]}
    assert "OutlinerProps" in child_collections
    props = next(child for child in tree["root"]["children"] if child["name"] == "OutlinerProps")
    assert any(obj["name"] == "OutlinerChild" for obj in props["objects"])
    found = bridge.call("outliner.find", {"query": "OutlinerChild", "kind": "OBJECT"})
    assert found["matches"][0]["path"] == "Scene Collection/OutlinerProps/OutlinerChild"


def test_context_selection_mode_workflow(bridge: BlenderBridge) -> None:
    bridge.call("scene.create_object", {"type": "CUBE", "name": "CtxCube"})
    bridge.call("scene.create_object", {"type": "SPHERE", "name": "CtxSphere"})

    active = bridge.call("context.set_active", {"object": "CtxCube"})
    assert active["active"]["name"] == "CtxCube"
    assert "CtxCube" in {obj["name"] for obj in active["selected"]}

    selected = bridge.call(
        "context.select_objects",
        {"objects": "CtxSphere", "action": "REPLACE", "active": "CtxSphere"},
    )
    assert [obj["name"] for obj in selected["selected"]] == ["CtxSphere"]
    assert selected["active"]["name"] == "CtxSphere"

    added = bridge.call("context.select_objects", {"objects": "CtxCube", "action": "ADD"})
    assert {"CtxCube", "CtxSphere"} == {obj["name"] for obj in added["selected"]}

    toggled = bridge.call("context.select_objects", {"objects": "CtxSphere", "action": "TOGGLE"})
    assert [obj["name"] for obj in toggled["selected"]] == ["CtxCube"]

    edit = bridge.call("context.mode_set", {"mode": "EDIT", "object": "CtxCube"})
    assert edit["active"]["name"] == "CtxCube"
    assert edit["object_mode"] == "EDIT"

    mesh_mode = bridge.call("context.mesh_select_mode", {"mode": "EDGE"})
    assert mesh_mode["mesh_select_mode"] == {"vertex": False, "edge": True, "face": False}

    poll = bridge.call(
        "context.poll_operator",
        {"idname": "mesh.subdivide", "object": "CtxCube", "mode": "EDIT", "select": "CtxCube"},
    )
    assert poll == {"idname": "mesh.subdivide", "available": True, "ok": True}

    object_mode = bridge.call("context.mode_set", {"mode": "OBJECT", "object": "CtxCube"})
    assert object_mode["object_mode"] == "OBJECT"

    info = bridge.call("context.info", {})
    assert info["active"]["name"] == "CtxCube"
    assert "context_mode" in info


def test_object_lifecycle_transform_workflow(bridge: BlenderBridge) -> None:
    created = bridge.call(
        "object.create",
        {
            "type": "TORUS",
            "name": "ObjTorus",
            "major_radius": 1.25,
            "minor_radius": 0.25,
            "major_segments": 24,
            "minor_segments": 8,
            "location": [1, 2, 3],
            "rotation": [0.2, 0.1, 0.0],
            "scale": [1.5, 1.0, 0.5],
        },
    )
    assert created["name"] == "ObjTorus"
    assert created["location"] == [1.0, 2.0, 3.0]

    moved = bridge.call(
        "object.transform_set",
        {
            "object": "ObjTorus",
            "location": [2, 3, 4],
            "rotation": [0.4, 0.0, 0.2],
            "scale": [2, 1, 1],
            "delta_location": [0.1, 0.0, 0.0],
            "rotation_mode": "XYZ",
        },
    )
    assert moved["location"] == [2.0, 3.0, 4.0]
    assert moved["delta_location"] == pytest.approx([0.1, 0.0, 0.0])

    transform = bridge.call("object.transform_get", {"object": "ObjTorus"})
    assert transform["name"] == "ObjTorus"
    assert transform["scale"] == [2.0, 1.0, 1.0]

    bounds = bridge.call("object.bounds", {"object": "ObjTorus"})
    assert bounds["object"] == "ObjTorus"
    assert len(bounds["local"]) == 8
    assert len(bounds["world"]) == 8

    duplicate = bridge.call(
        "object.duplicate",
        {"object": "ObjTorus", "name": "ObjTorusCopy", "offset": [1, 0, 0]},
    )
    assert duplicate["name"] == "ObjTorusCopy"
    assert duplicate["location"][0] == 3.0

    origin = bridge.call(
        "object.origin_set",
        {"object": "ObjTorus", "type": "ORIGIN_GEOMETRY", "center": "BOUNDS"},
    )
    assert origin == {"object": "ObjTorus", "origin": "ORIGIN_GEOMETRY", "center": "BOUNDS"}

    applied = bridge.call("object.transform_apply", {"object": "ObjTorus"})
    assert applied["object"] == "ObjTorus"
    assert applied["applied"] == {
        "location": True,
        "rotation": True,
        "scale": True,
        "properties": True,
        "isolate_users": False,
    }
    after_apply = bridge.call("object.transform_get", {"object": "ObjTorus"})
    assert after_apply["location"] == [0.0, 0.0, 0.0]
    assert after_apply["scale"] == [1.0, 1.0, 1.0]

    deleted = bridge.call("object.delete", {"objects": "ObjTorusCopy"})
    assert deleted == {"deleted": ["ObjTorusCopy"], "count": 1}
    names = {obj["name"] for obj in bridge.call("scene.info", {})["objects"]}
    assert "ObjTorus" in names
    assert "ObjTorusCopy" not in names


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


def test_mesh_selection_topology_workflow(bridge: BlenderBridge) -> None:
    bridge.call("object.create", {"type": "CUBE", "name": "MeshSelectHero"})
    before = bridge.call("mesh.report", {"object": "MeshSelectHero"})
    assert before["faces"] == 6

    selected = bridge.call(
        "mesh.select_by_index",
        {"object": "MeshSelectHero", "mode": "FACE", "indices": "0", "action": "REPLACE"},
    )
    assert selected["faces"] == [0]
    assert selected["counts"]["faces"] == 1

    reported_selection = bridge.call("mesh.selection_report", {"object": "MeshSelectHero"})
    assert reported_selection["faces"] == [0]

    deleted = bridge.call("mesh.delete", {"object": "MeshSelectHero", "type": "FACE"})
    assert deleted == {"object": "MeshSelectHero", "deleted": "FACE"}
    after_delete = bridge.call("mesh.report", {"object": "MeshSelectHero"})
    assert after_delete["faces"] == 5

    bridge.call("object.create", {"type": "CUBE", "name": "MeshConvertHero"})
    bridge.call("mesh.select_all", {"object": "MeshConvertHero", "action": "SELECT"})
    converted = bridge.call("mesh.quads_to_tris", {"object": "MeshConvertHero"})
    assert converted == {"object": "MeshConvertHero", "applied": "quads_to_tris"}
    tri_report = bridge.call("mesh.report", {"object": "MeshConvertHero"})
    assert tri_report["faces"] == 12

    bridge.call("mesh.select_all", {"object": "MeshConvertHero", "action": "SELECT"})
    quads = bridge.call("mesh.tris_to_quads", {"object": "MeshConvertHero"})
    assert quads == {"object": "MeshConvertHero", "applied": "tris_to_quads"}
    quad_report = bridge.call("mesh.report", {"object": "MeshConvertHero"})
    assert quad_report["faces"] == 6

    bridge.call("mesh.select_all", {"object": "MeshConvertHero", "action": "SELECT"})
    cleanup = bridge.call("mesh.remove_doubles", {"object": "MeshConvertHero", "threshold": 0.0001})
    assert cleanup == {"object": "MeshConvertHero", "applied": "remove_doubles", "threshold": 0.0001}

    bridge.call("object.create", {"type": "CUBE", "name": "MeshMergeHero"})
    merge_selection = bridge.call(
        "mesh.select_by_index",
        {"object": "MeshMergeHero", "mode": "VERT", "indices": "0,1", "action": "REPLACE"},
    )
    assert merge_selection["vertices"] == [0, 1]
    assert merge_selection["edges"] == []
    assert merge_selection["faces"] == []
    assert bridge.call("mesh.merge", {"object": "MeshMergeHero"}) == {
        "object": "MeshMergeHero",
        "applied": "merge",
    }
    assert bridge.call("mesh.report", {"object": "MeshMergeHero"})["vertices"] == 7

    bridge.call("object.create", {"type": "PLANE", "name": "MeshFillHero"})
    bridge.call(
        "mesh.select_by_index",
        {"object": "MeshFillHero", "mode": "FACE", "indices": "0", "action": "REPLACE"},
    )
    assert bridge.call("mesh.delete", {"object": "MeshFillHero", "type": "ONLY_FACE"}) == {
        "object": "MeshFillHero",
        "deleted": "ONLY_FACE",
    }
    assert bridge.call("mesh.report", {"object": "MeshFillHero"})["faces"] == 0
    bridge.call(
        "mesh.select_by_index",
        {"object": "MeshFillHero", "mode": "EDGE", "indices": "0,1,2,3", "action": "REPLACE"},
    )
    assert bridge.call("mesh.fill", {"object": "MeshFillHero"}) == {
        "object": "MeshFillHero",
        "applied": "fill",
    }
    assert bridge.call("mesh.report", {"object": "MeshFillHero"})["faces"] >= 1

    bridge.call("object.create", {"type": "PLANE", "name": "MeshEdgeFaceHero"})
    bridge.call(
        "mesh.select_by_index",
        {"object": "MeshEdgeFaceHero", "mode": "FACE", "indices": "0", "action": "REPLACE"},
    )
    assert bridge.call("mesh.delete", {"object": "MeshEdgeFaceHero", "type": "ONLY_FACE"}) == {
        "object": "MeshEdgeFaceHero",
        "deleted": "ONLY_FACE",
    }
    bridge.call(
        "mesh.select_by_index",
        {
            "object": "MeshEdgeFaceHero",
            "mode": "EDGE",
            "indices": "0,1,2,3",
            "action": "REPLACE",
        },
    )
    assert bridge.call("mesh.edge_face_add", {"object": "MeshEdgeFaceHero"}) == {
        "object": "MeshEdgeFaceHero",
        "applied": "edge_face_add",
    }
    assert bridge.call("mesh.report", {"object": "MeshEdgeFaceHero"})["faces"] >= 1


def test_non_mesh_geometry_workflow(bridge: BlenderBridge) -> None:
    curve = bridge.call(
        "geometry.create_curve",
        {"type": "BEZIER_CIRCLE", "name": "GeoCurve", "radius": 1.5, "location": [1, 0, 0]},
    )
    assert curve["name"] == "GeoCurve"
    assert curve["type"] == "CURVE"
    assert curve["splines"]

    reported = bridge.call("geometry.report", {"object": "GeoCurve"})
    assert reported["name"] == "GeoCurve"
    assert "curve" in reported

    updated = bridge.call(
        "geometry.set_curve",
        {
            "object": "GeoCurve",
            "bevel_depth": 0.08,
            "bevel_resolution": 2,
            "extrude": 0.12,
            "resolution_u": 24,
            "dimensions": "3D",
            "use_fill_caps": True,
        },
    )
    assert updated["curve"]["bevel_depth"] == pytest.approx(0.08)
    assert updated["curve"]["bevel_resolution"] == 2
    assert updated["curve"]["extrude"] == pytest.approx(0.12)
    assert updated["curve"]["resolution_u"] == 24
    assert updated["curve"]["use_fill_caps"] is True

    text = bridge.call(
        "geometry.create_text",
        {"name": "GeoLabel", "body": "Niua", "align_x": "CENTER", "size": 1.25},
    )
    assert text["type"] == "FONT"
    assert text["text"]["body"] == "Niua"

    text_updated = bridge.call(
        "geometry.set_text",
        {"object": "GeoLabel", "body": "Niua MCP", "align_y": "CENTER", "offset_x": 0.2},
    )
    assert text_updated["text"]["body"] == "Niua MCP"
    assert text_updated["text"]["align_y"] == "CENTER"
    assert text_updated["text"]["offset_x"] == pytest.approx(0.2)

    surface = bridge.call("geometry.create_surface", {"type": "SURFACE", "name": "GeoSurface"})
    assert surface["type"] == "SURFACE"
    assert "splines" in surface

    metaball = bridge.call("geometry.create_metaball", {"type": "CAPSULE", "name": "GeoBlob"})
    assert metaball["type"] == "META"
    assert metaball["metaball"]["elements"] >= 1
    assert "CAPSULE" in metaball["metaball"]["types"]

    grease = bridge.call("geometry.create_grease_pencil", {"type": "EMPTY", "name": "GeoSketch"})
    assert grease["type"] == "GREASEPENCIL"
    assert "grease_pencil" in grease

    converted = bridge.call(
        "geometry.convert_to_mesh",
        {"object": "GeoCurve", "name": "GeoCurveMesh", "keep_original": False},
    )
    assert converted["name"] == "GeoCurveMesh"
    assert converted["type"] == "MESH"


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


def test_topology_overlay_renders_two_distinct_images(bridge: BlenderBridge) -> None:
    bridge.call(
        "rna.call_operator",
        {
            "idname": "mesh.primitive_circle_add",
            "args": json.dumps({"vertices": 5, "fill_type": "NGON"}),
        },
    )
    info = bridge.call("scene.info", {})
    names = [o["name"] for o in info["objects"] if o["name"].startswith("Circle")]
    assert names, "primitive_circle_add did not create a Circle"

    out = bridge.call("feedback.topology", {"object": names[0], "view": "persp", "res": 256})
    if not out.get("available"):
        reason = out.get("reason", "")
        if "OpenGL" in reason or "opengl" in reason or "GPU" in reason:
            pytest.skip(f"headless renderer unavailable: {reason}")
        pytest.fail(f"topology overlay failed: {reason}")
    assert out["available"] is True
    assert out["groups"]["ngons"] == 1
    assert len(out["images"]) == 2
    modes = {img["mode"] for img in out["images"]}
    assert modes == {"facetype", "wireframe"}
    data = {img["mode"]: img["data"] for img in out["images"]}
    assert data["facetype"] != data["wireframe"]


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


def test_rendering_cameras_lighting_compositor_workflow(bridge: BlenderBridge) -> None:
    bridge.call("scene.create_object", {"type": "CUBE", "name": "RenderSubject"})

    camera = bridge.call(
        "camera.create",
        {
            "name": "ShotCam",
            "location": [4, -6, 4],
            "rotation": [1.1, 0.0, 0.55],
            "lens": 35,
            "active": True,
        },
    )
    assert camera["camera"] == "ShotCam"
    assert camera["active"] is True
    assert bridge.call("camera.list", {})["active"] == "ShotCam"

    camera = bridge.call("camera.set", {"camera": "ShotCam", "clip_end": 750})
    assert camera["clip_end"] == 750.0

    light = bridge.call(
        "light.create",
        {
            "type": "AREA",
            "name": "KeyLight",
            "location": [0, -3, 4],
            "energy": 400,
            "color": [1.0, 0.9, 0.75],
            "size": 4,
        },
    )
    assert light["light"] == "KeyLight"
    assert light["type"] == "AREA"

    light = bridge.call("light.set", {"light": "KeyLight", "energy": 250})
    assert light["energy"] == 250.0
    assert bridge.call("light.list", {})["count"] >= 1

    render_settings = bridge.call(
        "render.set_settings",
        {"engine": "BLENDER_WORKBENCH", "resolution_x": 64, "resolution_y": 64, "image_format": "PNG"},
    )
    assert render_settings["engine"] == "BLENDER_WORKBENCH"
    assert render_settings["resolution"] == [64, 64]
    assert render_settings["camera"] == "ShotCam"

    world = bridge.call("world.set", {"color": [0.02, 0.03, 0.04], "strength": 0.8})
    assert world["color"] == pytest.approx([0.02, 0.03, 0.04])
    assert world["strength"] == pytest.approx(0.8)

    compositor = bridge.call("compositor.enable", {"enable": True})
    assert compositor["use_nodes"] is True
    assert compositor["nodes"]

    added = bridge.call("compositor.add_node", {"type": "CompositorNodeBlur", "name": "SoftBlur"})
    assert added["node"]["name"] == "SoftBlur"
    comp_report = bridge.call("compositor.report", {})
    assert any(node["name"] == "SoftBlur" for node in comp_report["nodes"])
    render_layers = next(node for node in comp_report["nodes"] if node["type"] == "R_LAYERS")
    output_node = next(node for node in comp_report["nodes"] if node["inputs"])
    linked = bridge.call(
        "compositor.link",
        {
            "from_node": render_layers["name"],
            "from_socket": "0",
            "to_node": output_node["name"],
            "to_socket": "0",
        },
    )
    assert linked["link"]["from_node"] == render_layers["name"]
    assert linked["link"]["to_node"] == output_node["name"]

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "still.png")
        still = bridge.call(
            "render.still",
            {
                "path": path,
                "camera": "ShotCam",
                "engine": "BLENDER_WORKBENCH",
                "resolution_x": 64,
                "resolution_y": 64,
                "image_format": "PNG",
            },
        )
        assert still["path"] == path
        assert still["format"] == "PNG"
        assert os.path.exists(path) and os.path.getsize(path) > 0


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


def test_modifiers_geometry_nodes_workflow(bridge: BlenderBridge) -> None:
    bridge.call("object.create", {"type": "CUBE", "name": "ModNodeHero"})

    modifier_types = bridge.call("modifiers.types", {})
    type_ids = {item["identifier"] for item in modifier_types["types"]}
    assert {"BEVEL", "TRIANGULATE", "NODES"} <= type_ids

    bridge.call("modifiers.add", {"object": "ModNodeHero", "type": "TRIANGULATE", "name": "Triangulate"})
    visibility = bridge.call(
        "modifiers.set_visibility",
        {"object": "ModNodeHero", "name": "Triangulate", "viewport": False, "render": True, "expanded": False},
    )
    assert visibility["modifier"]["show_viewport"] is False
    assert visibility["modifier"]["show_render"] is True
    assert visibility["modifier"]["show_expanded"] is False

    copied = bridge.call(
        "modifiers.copy",
        {"object": "ModNodeHero", "name": "Triangulate", "new_name": "TriCopy"},
    )
    assert copied["modifier"]["name"] == "TriCopy"
    moved = bridge.call("modifiers.move", {"object": "ModNodeHero", "name": "TriCopy", "index": 0})
    assert moved["modifier"]["index"] == 0

    listed = bridge.call("modifiers.list", {"object": "ModNodeHero"})
    stack = listed["modifiers"]
    assert stack[0]["name"] == "TriCopy"
    assert all("properties" in mod for mod in stack)

    created_nodes = bridge.call(
        "geometry_nodes.create_modifier",
        {"object": "ModNodeHero", "name": "Procedural"},
    )
    assert created_nodes["modifier"] == "Procedural"
    node_names = {node["name"] for node in created_nodes["nodes"]}
    assert {"Group Input", "Group Output"} <= node_names
    assert created_nodes["links"]

    node = bridge.call(
        "geometry_nodes.add_node",
        {
            "object": "ModNodeHero",
            "modifier": "Procedural",
            "type": "GeometryNodeTransform",
            "name": "Transform",
        },
    )
    assert node["node"]["name"] == "Transform"
    assert node["node"]["bl_idname"] == "GeometryNodeTransform"

    linked = bridge.call(
        "geometry_nodes.link",
        {
            "object": "ModNodeHero",
            "modifier": "Procedural",
            "from_node": "Group Input",
            "from_socket": "Geometry",
            "to_node": "Transform",
            "to_socket": "Geometry",
        },
    )
    assert linked["link"] == {
        "from_node": "Group Input",
        "from_socket": "Geometry",
        "to_node": "Transform",
        "to_socket": "Geometry",
    }

    report = bridge.call("geometry_nodes.report", {"object": "ModNodeHero", "modifier": "Procedural"})
    assert "Transform" in {item["name"] for item in report["nodes"]}


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


def test_materials_shading_textures_workflow(bridge: BlenderBridge) -> None:
    bridge.call("object.create", {"type": "CUBE", "name": "ShadeNodeHero"})
    bridge.call("shading.create_material", {"name": "Subsystem8Mat"})
    bridge.call("shading.assign_material", {"object": "ShadeNodeHero", "material": "Subsystem8Mat"})
    bridge.call(
        "shading.set_principled",
        {"material": "Subsystem8Mat", "base_color": [0.2, 0.4, 0.8], "metallic": 0.25, "roughness": 0.6},
    )

    report = bridge.call("shading.report", {"object": "ShadeNodeHero"})
    assert report["material"] == "Subsystem8Mat"
    assert report["object"] == "ShadeNodeHero"
    principled = next(node for node in report["nodes"] if node["type"] == "BSDF_PRINCIPLED")
    assert any(socket["name"] == "Roughness" for socket in principled["inputs"])

    noise = bridge.call(
        "shading.add_node",
        {"material": "Subsystem8Mat", "type": "ShaderNodeTexNoise", "name": "NoiseDriver"},
    )
    assert noise["node"]["name"] == "NoiseDriver"
    scaled = bridge.call(
        "shading.set_node_input",
        {"material": "Subsystem8Mat", "node": "NoiseDriver", "input": "Scale", "value": "12.0"},
    )
    assert scaled["input"]["default_value"] == pytest.approx(12.0)
    linked = bridge.call(
        "shading.link_nodes",
        {
            "material": "Subsystem8Mat",
            "from_node": "NoiseDriver",
            "from_socket": "Fac",
            "to_node": principled["name"],
            "to_socket": "Roughness",
        },
    )
    assert linked["link"]["from_node"] == "NoiseDriver"
    assert linked["link"]["to_socket"] == "Roughness"

    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    with tempfile.TemporaryDirectory() as tmp:
        image_path = os.path.join(tmp, "tiny.png")
        Path(image_path).write_bytes(tiny_png)
        image = bridge.call("textures.load", {"path": image_path, "name": "TinyTexture"})
        assert image["name"] == "TinyTexture"
        assert image["size"] == [1, 1]
        listed = bridge.call("textures.list", {})
        assert "TinyTexture" in {item["name"] for item in listed["images"]}
        assert bridge.call("textures.report", {"name": "TinyTexture"})["filepath"] == image_path

        wired = bridge.call(
            "shading.add_image_texture",
            {"material": "Subsystem8Mat", "image_path": image_path, "target": "BASE_COLOR"},
        )
        assert wired["target"] == "BASE_COLOR"

    final_report = bridge.call("shading.report", {"material": "Subsystem8Mat"})
    assert any(node["type"] == "TEX_IMAGE" for node in final_report["nodes"])


def test_animation_rigging_workflow(bridge: BlenderBridge) -> None:
    bridge.call("scene.create_object", {"type": "CUBE", "name": "AnimHero"})
    bridge.call("scene.create_object", {"type": "CUBE", "name": "RigBody"})

    timeline = bridge.call(
        "anim.set_timeline",
        {"frame_start": 1, "frame_end": 48, "frame_current": 12, "fps": 30},
    )
    assert timeline["frame_start"] == 1
    assert timeline["frame_end"] == 48
    assert timeline["frame_current"] == 12
    assert timeline["fps"] == 30
    assert bridge.call("anim.timeline", {})["frame_current"] == 12

    bridge.call("anim.insert_keyframe", {"object": "AnimHero", "data_path": "location", "frame": 1})
    bridge.call("anim.insert_keyframe", {"object": "AnimHero", "data_path": "location", "frame": 10})

    report = bridge.call("anim.report", {"object": "AnimHero"})
    assert report["fcurves"] == 3
    assert report["keyframes"] == 6
    assert report["action"] is not None

    keyframes = bridge.call("anim.keyframes", {"object": "AnimHero"})
    assert keyframes["fcurve_count"] == 3
    assert keyframes["keyframe_count"] == 6
    assert any(fcurve["data_path"] == "location" for fcurve in keyframes["fcurves"])

    interp = bridge.call("anim.set_interpolation", {"object": "AnimHero", "interpolation": "LINEAR"})
    assert interp["fcurves"] == 3 and interp["keyframes"] == 6

    actions = bridge.call("anim.list_actions", {})
    anim_action = next(action for action in actions["actions"] if action["name"] == report["action"])
    assert anim_action["fcurves"] >= 3

    bridge.call("rig.add_armature", {"name": "RigHero", "location": [0, 0, 0]})
    bridge.call(
        "rig.add_bone",
        {"armature": "RigHero", "name": "Spine", "head": [0, 0, 0], "tail": [0, 0, 1]},
    )

    pose = bridge.call(
        "rig.set_pose_bone",
        {
            "armature": "RigHero",
            "bone": "Spine",
            "location": [0.1, 0.2, 0.3],
            "rotation": [0.0, 0.0, 0.25],
            "scale": [1.0, 1.1, 1.0],
            "rotation_mode": "XYZ",
        },
    )
    assert pose["pose_bone"]["name"] == "Spine"
    assert pose["pose_bone"]["rotation_mode"] == "XYZ"

    constraint = bridge.call(
        "rig.constraint_add",
        {
            "armature": "RigHero",
            "bone": "Spine",
            "type": "COPY_LOCATION",
            "name": "CopyAnimHero",
            "target": "AnimHero",
            "influence": 0.5,
        },
    )
    assert constraint["constraint"]["name"] == "CopyAnimHero"
    assert constraint["constraint"]["target"] == "AnimHero"

    constraints = bridge.call("rig.constraints", {"armature": "RigHero", "bone": "Spine"})
    assert constraints["constraint_count"] == 1

    removed = bridge.call(
        "rig.constraint_remove",
        {"armature": "RigHero", "bone": "Spine", "name": "CopyAnimHero"},
    )
    assert removed["constraint_count"] == 0

    groups = bridge.call("rig.vertex_group_create", {"mesh": "RigBody", "name": "Spine"})
    assert groups["groups"][0]["name"] == "Spine"

    weighted = bridge.call(
        "rig.assign_weights",
        {"mesh": "RigBody", "group": "Spine", "vertices": "0,1,2", "weight": 0.8},
    )
    assert [item["index"] for item in weighted["groups"][0]["vertices"]] == [0, 1, 2]
    assert [item["weight"] for item in weighted["groups"][0]["vertices"]] == pytest.approx([0.8, 0.8, 0.8])

    rig_report = bridge.call("rig.report", {"armature": "RigHero"})
    assert "Spine" in {bone["name"] for bone in rig_report["bones"]}
    assert "Spine" in {bone["name"] for bone in rig_report["pose_bones"]}

    cleared = bridge.call("rig.clear_pose", {"armature": "RigHero"})
    spine = next(bone for bone in cleared["pose_bones"] if bone["name"] == "Spine")
    assert spine["location"] == [0.0, 0.0, 0.0]


def test_uv_images_workflow(bridge: BlenderBridge) -> None:
    bridge.call("scene.create_object", {"type": "CUBE", "name": "UVHero"})

    before = bridge.call("uv.report", {"object": "UVHero"})
    assert "has_uvs" in before

    created = bridge.call("uv.layer_create", {"object": "UVHero", "name": "Lightmap", "do_init": True})
    assert "Lightmap" in created["layers"]

    active = bridge.call("uv.layer_set_active", {"object": "UVHero", "name": "Lightmap"})
    assert active["active"] == "Lightmap"

    seams = bridge.call("uv.set_seams", {"object": "UVHero", "edges": "0,1", "action": "SET"})
    assert seams["seam_edges"] == [0, 1]

    removed = bridge.call("uv.set_seams", {"object": "UVHero", "edges": "1", "action": "REMOVE"})
    assert removed["seam_edges"] == [0]

    bridge.call("uv.unwrap", {"object": "UVHero", "method": "ANGLE_BASED", "island_margin": 0.02})
    bridge.call("uv.pack_islands", {"object": "UVHero", "margin": 0.01})

    after = bridge.call("uv.report", {"object": "UVHero"})
    assert after["has_uvs"] is True
    assert after["uv_layer_count"] >= 1
    assert after["active_uv_layer"] == "Lightmap"
    assert after["island_count"] is None or after["island_count"] >= 1

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "uv_layout.svg")
        exported = bridge.call(
            "uv.export_layout",
            {"object": "UVHero", "path": path, "size": 512, "opacity": 0.25},
        )
        assert exported["path"] == path
        assert exported["size"] == 512
        assert exported["format"] == "SVG"
        assert os.path.exists(path) and os.path.getsize(path) > 0


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


def test_capabilities_search_finds_bevel(bridge: BlenderBridge) -> None:
    out = bridge.call("capabilities.search", {"query": "bevel", "kind": "operator"})
    assert any(m["idname"] == "mesh.bevel" for m in out["matches"])


def test_manifest_matches_live_rna_sample(bridge: BlenderBridge) -> None:
    from niua_blender_mcp.manifest import load_manifest

    m = load_manifest()
    for idname in ["mesh.subdivide", "mesh.bevel", "uv.unwrap"]:
        if idname not in m.operators:
            continue
        live = bridge.call("capabilities.describe", {"id": idname})
        assert live["id"] == idname
        assert "properties" in live


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


def test_properties_object_report_and_stable_paths_round_trip(bridge: BlenderBridge) -> None:
    name = "Props.Cube/One"
    bridge.call("object.create", {"type": "CUBE", "name": name})

    report = bridge.call("properties.object_report", {"object": name})
    object_props = {prop["identifier"]: prop for prop in report["object_properties"]}
    data_props = {prop["identifier"]: prop for prop in report["data"]["properties"]}
    assert {"name", "type", "location", "data", "modifiers"} <= set(object_props)
    assert {"name", "vertices", "polygons"} <= set(data_props)
    assert report["coverage"]["missing_object_properties"] == []
    assert report["coverage"]["missing_data_properties"] == []

    location_path = object_props["location"]["path"]
    assert location_path == "object:Props.Cube%2FOne/location"
    written = bridge.call("properties.set", {"path": location_path, "value": json.dumps([2, 3, 4])})
    assert written["value"] == [2.0, 3.0, 4.0]
    assert bridge.call("properties.get", {"path": location_path})["value"] == [2.0, 3.0, 4.0]

    note_path = "object:Props.Cube%2FOne/idprops/artist_note"
    bridge.call("properties.set", {"path": note_path, "value": json.dumps("hero prop")})
    assert bridge.call("properties.get", {"path": note_path})["value"] == "hero prop"
    custom_report = bridge.call("properties.object_report", {"object": name})
    assert {"key": "artist_note", "path": note_path, "value": "hero prop"} in custom_report[
        "custom_properties"
    ]
    assert bridge.call("properties.unset", {"path": note_path}) == {"path": note_path, "removed": True}

    data_root = f"data:meshes/{quote(report['data']['name'], safe='')}"
    data_report = bridge.call("properties.report", {"path": data_root})
    data_report_props = {prop["identifier"] for prop in data_report["properties"]}
    assert {"name", "vertices", "polygons"} <= data_report_props
    assert data_report["coverage"]["missing_properties"] == []


def test_rna_call_operator_unknown_is_clean_error(bridge: BlenderBridge) -> None:
    # A bogus operator id must come back as a structured not_found, not crash Blender.
    from niua_blender_mcp.bridge import BridgeError

    with pytest.raises(BridgeError) as exc:
        bridge.call("rna.call_operator", {"idname": "mesh.no_such_operator_xyz"})
    assert exc.value.code == "not_found"
    # Bridge still alive afterward.
    assert "objects" in bridge.call("scene.info", {})


# --- IO smoke: generic import/export file seam, end to end ---------------------------
# glTF export/import needs no GPU, so the whole seam is verifiable headless. Each test
# uses a tempfile and cleans up. Together they prove export, round-trip import (export +
# import wired correctly), and the prepare_asset apply-transforms-then-export convenience.


def test_io_export_writes_nonempty_glb(bridge: BlenderBridge) -> None:
    # Create a cube, export the whole scene to a .glb, assert the file is real and non-empty.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "ExportHero"})

    fd, path = tempfile.mkstemp(suffix=".glb")
    os.close(fd)
    os.unlink(path)  # let Blender create it; we only wanted a unique name
    try:
        res = bridge.call("io.export", {"path": path, "format": "GLB", "objects": "ExportHero"})
        assert res["path"] == path
        assert res["format"] == "GLB"
        assert res["object_count"] == 1
        assert os.path.exists(path), "io.export did not write the file"
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
        bridge.call("io.export", {"path": path, "format": "GLB", "objects": "RoundTripHero"})
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


# --- Critique loop — objective metrics smoke (Phase 6 follow-up) -----------------------
# feedback.quality is pure geometry (bmesh + vertex coords), so every field is fully
# headless-verifiable in real Blender — no GPU/area context needed. These pin the metric
# semantics against two known meshes: a perfect cube and Suzanne (left-right symmetric).


def test_feedback_quality_on_default_cube(bridge: BlenderBridge) -> None:
    # A factory cube is the cleanest possible mesh: all quads, no n-gons, fully manifold,
    # perfectly symmetric on every axis, and no loose geometry. Real bmesh populates the
    # three fields that return null under fake-bpy.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "QualCube"})

    q = bridge.call("feedback.quality", {"object": "QualCube"})
    assert q["object"] == "QualCube"

    topo = q["topology"]
    assert topo["faces"] == 6
    assert topo["quads"] == 6
    assert topo["ngons"] == 0
    assert topo["quad_ratio"] == 1.0  # every face is a quad
    assert topo["ngon_ratio"] == 0.0
    assert topo["non_manifold_edges"] == 0  # a closed cube is fully manifold
    assert topo["loose_verts"] == 0
    # A cube's 8 corner verts are each valence-3 AND all cube edges are manifold (2 faces
    # each), so none are excluded as boundary — every corner is an interior valence!=4 pole.
    # pole_count == 8 is the geometrically correct answer (NOT 0): the cube has no valence-4
    # interior verts at all. (The task's predicted "0" was wrong; the implementation is right.)
    assert topo["pole_count"] == 8

    sym = q["symmetry"]
    assert sym["symmetry_x"] == 1.0
    assert sym["symmetry_y"] == 1.0
    assert sym["symmetry_z"] == 1.0  # a cube mirrors perfectly across all three planes

    prop = q["proportion"]
    assert prop["aspect_ratio"] == 1.0  # 2x2x2 — uniform
    assert prop["boxiness"] == 1.0  # bbox fully fills its longest-edge cube

    scale = q["scale"]
    assert scale["transform_applied"] is True  # freshly created at identity


def test_feedback_quality_on_suzanne(bridge: BlenderBridge) -> None:
    # Suzanne is the realistic case: a dense, left-right (X) symmetric mesh with genuine
    # poles and a few non-manifold border edges (the eyes). We assert the fields exist and
    # carry plausible real numbers, not exact counts that would brittle on a mesh revision.
    bridge.call("rna.call_operator", {"idname": "mesh.primitive_monkey_add", "args": json.dumps({})})
    info = bridge.call("scene.info", {})
    names = [o["name"] for o in info["objects"] if o["name"].startswith("Suzanne")]
    assert names, "monkey_add did not create a Suzanne"
    suz = names[0]

    q = bridge.call("feedback.quality", {"object": suz})

    topo = q["topology"]
    assert topo["faces"] > 400  # Suzanne ships with ~500 faces
    # All the bmesh-derived fields populate in real Blender (would be null under fake-bpy).
    assert isinstance(topo["pole_count"], int) and topo["pole_count"] > 0  # poles present
    assert isinstance(topo["non_manifold_edges"], int)
    assert isinstance(topo["loose_verts"], int)
    assert 0.0 <= topo["quad_ratio"] <= 1.0

    sym = q["symmetry"]
    # Suzanne is mirror-symmetric across the local YZ plane (the X axis), so symmetry_x is
    # high (~1.0), while she is NOT symmetric front-to-back (Y), so symmetry_x dominates.
    assert sym["symmetry_x"] > 0.9
    assert sym["symmetry_x"] > sym["symmetry_y"]  # X is the real symmetry axis, Y is not

    # proportion / scale blocks are present and sane.
    assert q["proportion"]["aspect_ratio"] is not None and q["proportion"]["aspect_ratio"] > 1.0
    assert q["scale"]["transform_applied"] is True


def test_feedback_critique_bundle_includes_quality_subdict(bridge: BlenderBridge) -> None:
    # The folded objective channel: one observe call returns images + counts + a compact
    # quality sub-dict, with REAL numbers headless (the analytic half needs no GPU).
    bridge.call("scene.create_object", {"type": "CUBE", "name": "CritQualCube"})

    result = bridge.call("feedback.critique", {"object": "CritQualCube", "preset": "ortho4"})
    report = result["report"]
    assert isinstance(report, dict)

    quality = report.get("quality")
    assert isinstance(quality, dict), "critique report is missing the folded quality sub-dict"
    # Compact block contract, with the cube's real values.
    assert quality["quad_ratio"] == 1.0
    assert quality["ngon_ratio"] == 0.0
    assert quality["pole_count"] == 8
    assert quality["non_manifold_edges"] == 0
    assert quality["loose_verts"] == 0
    assert quality["symmetry"] == {"symmetry_x": 1.0, "symmetry_y": 1.0, "symmetry_z": 1.0}
    assert quality["aspect_ratio"] == 1.0
    assert quality["transform_applied"] is True


# --- MCP prompts smoke (server-side; no Blender needed, runs in the real-Blender pass) --


def test_prompts_list_is_non_empty() -> None:
    from niua_blender_mcp.prompts import list_prompts

    prompts = list_prompts()
    assert isinstance(prompts, list) and prompts, "prompts/list is empty"
    names = {p["name"] for p in prompts}
    assert {"refine_mesh", "inspect"} <= names


def test_prompts_get_refine_mesh_scaffolds_the_loop() -> None:
    from niua_blender_mcp.prompts import get_prompt

    rendered = get_prompt("refine_mesh", None)
    messages = rendered["messages"]
    assert messages and messages[0]["role"] == "user"
    text = messages[0]["content"]["text"]
    # The loop scaffold must name its three load-bearing primitives.
    assert "checkpoint" in text
    assert "critique" in text
    assert "revert" in text


def test_io_prepare_asset_applies_transforms_and_exports(bridge: BlenderBridge) -> None:
    # prepare_asset on a translated + rotated cube: applies transforms, exports one object
    # to GLB, reports transform_applied:true. After apply, the object's transform is identity.
    bridge.call("scene.create_object", {"type": "CUBE", "name": "AssetHero"})
    bridge.call(
        "scene.set_transform",
        {"object": "AssetHero", "location": [3, 1, 2], "rotation": [0.5, 0.0, 0.3]},
    )

    fd, path = tempfile.mkstemp(suffix=".glb")
    os.close(fd)
    os.unlink(path)
    try:
        res = bridge.call("io.prepare_asset", {"object": "AssetHero", "path": path, "format": "GLB"})
        assert res["transform_applied"] is True
        assert res["object"] == "AssetHero"
        assert res["path"] == path
        assert res["format"] == "GLB"
        assert os.path.exists(path) and os.path.getsize(path) > 0, "prepare_asset wrote no GLB"
        with open(path, "rb") as fh:
            assert fh.read(4) == b"glTF"

        # transform_apply zeroes location/rotation and unit-izes scale on the object.
        loc = bridge.call("rna.get_property", {"path": "objects.AssetHero.location"})["value"]
        scale = bridge.call("rna.get_property", {"path": "objects.AssetHero.scale"})["value"]
        assert loc == [0.0, 0.0, 0.0], f"location not applied: {loc}"
        assert scale == [1.0, 1.0, 1.0], f"scale not applied: {scale}"
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_ui_automation_gui_parity_workflow(bridge: BlenderBridge) -> None:
    state = bridge.call("ui.state", {})
    assert state["background"] is True
    assert state["window_count"] >= 1
    assert state["active_window"] is not None
    assert state["capabilities"]["keyboard_events"]["available"] is False
    assert state["capabilities"]["mouse_events"]["available"] is False

    windows = bridge.call("ui.windows", {})
    assert windows["windows"]
    assert any(
        area["type"] == "VIEW_3D"
        for window in windows["windows"]
        for area in window["areas"]
    )

    poll = bridge.call(
        "ui.operator_poll",
        {"idname": "mesh.primitive_cube_add", "area": "VIEW_3D", "region": "WINDOW", "require_area": True},
    )
    assert poll["available"] is True
    assert poll["ui_context"]["override"] is True
    assert poll["ui_context"]["area"]["type"] == "VIEW_3D"

    before = {obj["name"] for obj in bridge.call("scene.info", {})["objects"]}
    bridge.call(
        "ui.operator_invoke",
        {
            "idname": "mesh.primitive_cube_add",
            "args": json.dumps({"size": 1.0}),
            "area": "VIEW_3D",
            "region": "WINDOW",
            "require_area": True,
        },
    )
    after = {obj["name"] for obj in bridge.call("scene.info", {})["objects"]}
    created = after - before
    assert created
    assert any(name.startswith("Cube") for name in created)

    with tempfile.TemporaryDirectory() as tmp:
        shot = bridge.call("ui.screenshot", {"path": os.path.join(tmp, "ui.png")})
    assert shot["available"] is False
    assert "screen.screenshot" in shot["reason"]

    redraw = bridge.call("ui.redraw", {})
    assert redraw["available"] is False
    assert "wm.redraw_timer" in redraw["reason"]
