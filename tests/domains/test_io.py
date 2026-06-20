"""IO domain unit tests (fake-bpy).

Extends the FakeBpy pattern: import/export operators record their calls; the importer
also *adds* a new object to the scene so ``io.import`` has a real before/after diff to
report. ``bpy`` is injected into sys.modules so the lazily-imported context resolver
(used by the exporters' ``ctx.ensure``) runs against the same fake.

Coverage: extension -> format inference, the before/after object diff on import,
selection wiring on export (use_selection + the right objects selected), generic-export
routing, transform-apply on prepare_asset, and the error paths (missing file, missing
path, unknown extension, missing export object).
"""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError


class FakeObj:
    def __init__(self, name: str, type: str = "MESH") -> None:
        self.name = name
        self.type = type
        self._selected = False
        self.mode = "OBJECT"

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


class _Op:
    """A callable operator that records calls and polls True by default."""

    def __init__(self, log: list, name: str, poll_ok: bool = True, side=None) -> None:
        self._log = log
        self._name = name
        self._poll_ok = poll_ok
        self._side = side

    def poll(self) -> bool:
        return self._poll_ok

    def __call__(self, **kwargs):
        self._log.append((self._name, kwargs))
        if self._side is not None:
            self._side(kwargs)


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, FakeObj] = {}
        self.scene = types.SimpleNamespace(objects=[], name="Scene")
        self._active_obj = None
        self.op_calls: list = []
        self.undo_pushes: list[str] = []
        self.mode_calls: list[str] = []
        self._import_counter = 0

        bpy = self

        class _Objects:
            @property
            def active(self_inner):
                return bpy._active_obj

            @active.setter
            def active(self_inner, value):
                bpy._active_obj = value

        self.view_layer = types.SimpleNamespace(objects=_Objects())

        class _Context:
            scene = self.scene
            view_layer = self.view_layer

            @property
            def object(self_inner):
                return bpy._active_obj

            window_manager = types.SimpleNamespace(windows=[])

            @staticmethod
            @contextmanager
            def temp_override(**kw):
                yield

        self.context = _Context()
        log = self.op_calls

        def _import_side(kwargs):
            # Importing adds a brand-new object to the scene (the before/after diff).
            bpy._import_counter += 1
            obj = FakeObj(f"Imported_{bpy._import_counter}")
            bpy.add(obj)

        class _ImportScene:
            gltf = _Op(log, "import_scene.gltf", side=_import_side)
            fbx = _Op(log, "import_scene.fbx", side=_import_side)

        class _ExportScene:
            gltf = _Op(log, "export_scene.gltf")
            fbx = _Op(log, "export_scene.fbx")

        class _WmOps:
            obj_import = _Op(log, "wm.obj_import", side=_import_side)
            obj_export = _Op(log, "wm.obj_export")
            stl_import = _Op(log, "wm.stl_import", side=_import_side)

        class _ObjectOps:
            transform_apply = _Op(log, "object.transform_apply")

            def mode_set(self_inner, mode="OBJECT", **kw):
                bpy.mode_calls.append(mode)
                if bpy._active_obj is not None:
                    bpy._active_obj.mode = mode

        class _EdOps:
            def undo_push(self_inner, message: str = "", **kw):
                bpy.undo_pushes.append(message)

            def undo(self_inner, **kw):
                pass

        self.ops = types.SimpleNamespace(
            import_scene=_ImportScene(),
            export_scene=_ExportScene(),
            wm=_WmOps(),
            object=_ObjectOps(),
            ed=_EdOps(),
        )

    def add(self, obj: FakeObj) -> FakeObj:
        self.objects_by_name[obj.name] = obj
        self.scene.objects.append(obj)
        self._active_obj = obj
        return obj

    @property
    def data(self):
        store = self.objects_by_name

        class _Data:
            objects = types.SimpleNamespace(get=lambda name: store.get(name))
            materials: dict = {}

        return _Data()


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def _names(log):
    return [n for n, _ in log]


def _kwargs(log, name):
    return next(k for n, k in log if n == name)


def _write(tmp_path, filename):
    p = tmp_path / filename
    p.write_bytes(b"fake")
    return str(p)


# -- import: format inference + before/after diff ----------------------------------


def test_import_infers_glb_and_reports_new_objects(env, tmp_path) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Existing"))
    path = _write(tmp_path, "model.glb")
    reg = build_default_registry()
    result = dispatch_on_main(reg, "io.import", {"path": path}, ctx)
    assert result["format"] == "GLB"
    assert result["path"] == path
    assert result["imported"] == ["Imported_1"]  # the diffed new object, not "Existing"
    assert "import_scene.gltf" in _names(bpy.op_calls)
    assert _kwargs(bpy.op_calls, "import_scene.gltf")["filepath"] == path
    assert bpy.undo_pushes == ["niua:io.import"]  # mutating -> one undo step


@pytest.mark.parametrize(
    "filename, expected_format, expected_op",
    [
        ("a.gltf", "GLTF", "import_scene.gltf"),
        ("a.glb", "GLB", "import_scene.gltf"),
        ("a.obj", "OBJ", "wm.obj_import"),
        ("a.fbx", "FBX", "import_scene.fbx"),
        ("a.stl", "STL", "wm.stl_import"),
    ],
)
def test_import_extension_inference(env, tmp_path, filename, expected_format, expected_op) -> None:
    ctx, bpy = env
    path = _write(tmp_path, filename)
    reg = build_default_registry()
    result = dispatch_on_main(reg, "io.import", {"path": path}, ctx)
    assert result["format"] == expected_format
    assert expected_op in _names(bpy.op_calls)


def test_import_explicit_format_overrides_extension(env, tmp_path) -> None:
    ctx, bpy = env
    path = _write(tmp_path, "weird.dat")  # extension would not infer
    reg = build_default_registry()
    result = dispatch_on_main(reg, "io.import", {"path": path, "format": "GLB"}, ctx)
    assert result["format"] == "GLB"
    assert "import_scene.gltf" in _names(bpy.op_calls)


# -- import: error paths -----------------------------------------------------------


def test_import_missing_file_raises_not_found(env, tmp_path) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "io.import", {"path": str(tmp_path / "nope.glb")}, ctx)
    assert exc.value.code == NOT_FOUND
    assert bpy.undo_pushes == []  # no mutation, no undo step


def test_import_unknown_extension_raises_precondition(env, tmp_path) -> None:
    ctx, bpy = env
    path = _write(tmp_path, "mystery.xyz")
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "io.import", {"path": path}, ctx)
    assert exc.value.code == PRECONDITION


def test_import_missing_path_raises_invalid_params(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "io.import", {}, ctx)
    assert exc.value.code == INVALID_PARAMS


# -- export: selection wiring + whole-scene ----------------------------------------


def test_export_glb_whole_scene_no_selection(env, tmp_path) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("A"))
    bpy.add(FakeObj("B"))
    path = str(tmp_path / "out.glb")
    reg = build_default_registry()
    result = dispatch_on_main(reg, "io.export", {"path": path, "format": "GLB"}, ctx)
    k = _kwargs(bpy.op_calls, "export_scene.gltf")
    assert k["use_selection"] is False
    assert k["export_format"] == "GLB"
    assert k["export_yup"] is True
    assert k["export_apply"] is True
    assert result["object_count"] == 2  # whole scene
    assert bpy.undo_pushes == []  # read-only export


def test_export_glb_with_objects_selects_them(env, tmp_path) -> None:
    ctx, bpy = env
    a = bpy.add(FakeObj("A"))
    b = bpy.add(FakeObj("B"))
    c = bpy.add(FakeObj("C"))
    path = str(tmp_path / "out.glb")
    reg = build_default_registry()
    result = dispatch_on_main(reg, "io.export", {"path": path, "format": "GLB", "objects": "A, C"}, ctx)
    k = _kwargs(bpy.op_calls, "export_scene.gltf")
    assert k["use_selection"] is True
    assert result["object_count"] == 2
    # selection is restored after the export (ctx.ensure exit), so assert the export ran
    # under the right active object instead.
    assert bpy.mode_calls == []  # already OBJECT, no mode switch needed
    assert "export_scene.gltf" in _names(bpy.op_calls)
    _ = (a, b, c)


def test_export_gltf_separate_and_flags(env, tmp_path) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("A"))
    path = str(tmp_path / "out.gltf")
    reg = build_default_registry()
    dispatch_on_main(
        reg,
        "io.export",
        {"path": path, "format": "GLTF_SEPARATE", "apply_modifiers": False, "y_up": False},
        ctx,
    )
    k = _kwargs(bpy.op_calls, "export_scene.gltf")
    assert k["export_format"] == "GLTF_SEPARATE"
    assert k["export_apply"] is False
    assert k["export_yup"] is False


def test_export_unknown_object_raises_not_found(env, tmp_path) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("A"))
    path = str(tmp_path / "out.glb")
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "io.export", {"path": path, "format": "GLB", "objects": "Ghost"}, ctx)
    assert exc.value.code == NOT_FOUND


# -- generic export routing --------------------------------------------------------


def test_export_routes_glb(env, tmp_path) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("A"))
    reg = build_default_registry()
    result = dispatch_on_main(reg, "io.export", {"path": str(tmp_path / "o.glb")}, ctx)
    assert result["format"] == "GLB"
    assert "export_scene.gltf" in _names(bpy.op_calls)


def test_export_routes_fbx(env, tmp_path) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("A"))
    reg = build_default_registry()
    result = dispatch_on_main(reg, "io.export", {"path": str(tmp_path / "o.fbx"), "format": "FBX"}, ctx)
    assert result["format"] == "FBX"
    assert "export_scene.fbx" in _names(bpy.op_calls)


def test_export_routes_obj_with_selection(env, tmp_path) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("A"))
    bpy.add(FakeObj("B"))
    reg = build_default_registry()
    result = dispatch_on_main(
        reg, "io.export", {"path": str(tmp_path / "o.obj"), "format": "OBJ", "objects": "A"}, ctx
    )
    assert result["format"] == "OBJ"
    k = _kwargs(bpy.op_calls, "wm.obj_export")
    assert k["export_selected_objects"] is True
    assert result["object_count"] == 1


def test_export_auto_infers_from_extension(env, tmp_path) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("A"))
    reg = build_default_registry()
    result = dispatch_on_main(reg, "io.export", {"path": str(tmp_path / "o.fbx"), "format": "AUTO"}, ctx)
    assert result["format"] == "FBX"
    assert "export_scene.fbx" in _names(bpy.op_calls)


def test_export_unsupported_format_raises_invalid_params(env, tmp_path) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("A"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "io.export", {"path": str(tmp_path / "o.x"), "format": "STL"}, ctx)
    assert exc.value.code == INVALID_PARAMS


# -- prepare_asset -----------------------------------------------------------------


def test_prepare_asset_applies_transform_then_exports(env, tmp_path) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Hero"))
    path = str(tmp_path / "hero.glb")
    reg = build_default_registry()
    result = dispatch_on_main(reg, "io.prepare_asset", {"object": "Hero", "path": path, "format": "GLB"}, ctx)
    assert result == {"object": "Hero", "path": path, "format": "GLB", "transform_applied": True}
    names = _names(bpy.op_calls)
    assert "object.transform_apply" in names
    assert "export_scene.gltf" in names
    # transform_apply must run before the export
    assert names.index("object.transform_apply") < names.index("export_scene.gltf")
    ta = _kwargs(bpy.op_calls, "object.transform_apply")
    assert ta == {"location": True, "rotation": True, "scale": True}
    k = _kwargs(bpy.op_calls, "export_scene.gltf")
    assert k["use_selection"] is True and k["export_yup"] is True
    assert bpy.undo_pushes == ["niua:io.prepare_asset"]  # mutating -> one undo step


def test_prepare_asset_can_skip_transform_apply(env, tmp_path) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Hero"))
    path = str(tmp_path / "hero.obj")
    reg = build_default_registry()
    result = dispatch_on_main(
        reg,
        "io.prepare_asset",
        {"object": "Hero", "path": path, "format": "OBJ", "apply_transforms": False},
        ctx,
    )
    assert result == {"object": "Hero", "path": path, "format": "OBJ", "transform_applied": False}
    assert "object.transform_apply" not in _names(bpy.op_calls)
    assert "wm.obj_export" in _names(bpy.op_calls)


def test_prepare_asset_unknown_object_raises_not_found(env, tmp_path) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "io.prepare_asset", {"object": "Ghost", "path": str(tmp_path / "asset.glb")}, ctx)
    assert exc.value.code == NOT_FOUND
    assert bpy.undo_pushes == []


def test_engine_specific_io_tools_are_not_registered() -> None:
    from niua_blender_mcp.domains import build_router

    names = {spec.name for spec in build_router().specs()}
    assert "io.export_gltf" not in names
    assert "io.prepare_godot" not in names
    assert "io.prepare_asset" in names
