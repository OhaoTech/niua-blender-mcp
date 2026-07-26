"""Volume GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import json
import sys
import types
from contextlib import contextmanager

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, PRECONDITION, BridgeError


class FakeEnumItem:
    def __init__(self, identifier: str, name: str = "") -> None:
        self.identifier = identifier
        self.name = name or identifier.title()


class FakeRnaProp:
    def __init__(
        self,
        identifier: str,
        type: str,
        *,
        is_readonly: bool = False,
        enum_items: list[FakeEnumItem] | None = None,
    ) -> None:
        self.identifier = identifier
        self.name = identifier.replace("_", " ").title()
        self.description = ""
        self.type = type
        self.subtype = ""
        self.is_readonly = is_readonly
        self.is_array = False
        self.array_length = 0
        self.enum_items = list(enum_items or [])
        self.enum_items_static = list(enum_items or [])


class FakeRnaProperties(list):
    def get(self, identifier: str):
        return next((prop for prop in self if prop.identifier == identifier), None)

    def __getitem__(self, key):
        if isinstance(key, str):
            prop = self.get(key)
            if prop is None:
                raise KeyError(key)
            return prop
        return super().__getitem__(key)


def _rna(*props: FakeRnaProp):
    return types.SimpleNamespace(properties=FakeRnaProperties([FakeRnaProp("rna_type", "POINTER", is_readonly=True), *props]))


class FakeVolumeGrid:
    def __init__(self, name: str = "density") -> None:
        self.name = name
        self.data_type = "FLOAT"
        self.channels = 1
        self.matrix_object = [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
        self.is_loaded = True
        self.bl_rna = _rna(
            FakeRnaProp("name", "STRING", is_readonly=True),
            FakeRnaProp("data_type", "ENUM", is_readonly=True),
            FakeRnaProp("channels", "INT", is_readonly=True),
            FakeRnaProp("matrix_object", "FLOAT", is_readonly=True),
            FakeRnaProp("is_loaded", "BOOLEAN", is_readonly=True),
        )


class FakeVolumeGrids(list):
    def __init__(self) -> None:
        super().__init__([FakeVolumeGrid()])
        self.active_index = 0
        self.error_message = ""
        self.is_loaded = True
        self.frame = 1
        self.frame_filepath = ""
        self.bl_rna = _rna(
            FakeRnaProp("active_index", "INT"),
            FakeRnaProp("error_message", "STRING", is_readonly=True),
            FakeRnaProp("is_loaded", "BOOLEAN", is_readonly=True),
            FakeRnaProp("frame", "INT", is_readonly=True),
            FakeRnaProp("frame_filepath", "STRING", is_readonly=True),
        )

    def load(self) -> bool:
        self.is_loaded = True
        return True


DISPLAY_WIREFRAMES = [FakeEnumItem("NONE"), FakeEnumItem("BOUNDS"), FakeEnumItem("BOXES"), FakeEnumItem("POINTS")]
DISPLAY_INTERPOLATION = [FakeEnumItem("LINEAR"), FakeEnumItem("CUBIC"), FakeEnumItem("CLOSEST")]
DISPLAY_SLICE_AXES = [FakeEnumItem("AUTO"), FakeEnumItem("X"), FakeEnumItem("Y"), FakeEnumItem("Z")]
RENDER_SPACE = [FakeEnumItem("OBJECT"), FakeEnumItem("WORLD")]
RENDER_PRECISION = [FakeEnumItem("FULL"), FakeEnumItem("HALF"), FakeEnumItem("VARIABLE")]


class FakeVolumeDisplay:
    def __init__(self) -> None:
        self.density = 1.0
        self.wireframe_type = "BOUNDS"
        self.wireframe_detail = "COARSE"
        self.interpolation_method = "LINEAR"
        self.use_slice = False
        self.slice_axis = "AUTO"
        self.slice_depth = 0.5
        self.bl_rna = _rna(
            FakeRnaProp("density", "FLOAT"),
            FakeRnaProp("wireframe_type", "ENUM", enum_items=DISPLAY_WIREFRAMES),
            FakeRnaProp("wireframe_detail", "ENUM", enum_items=[FakeEnumItem("COARSE"), FakeEnumItem("FINE")]),
            FakeRnaProp("interpolation_method", "ENUM", enum_items=DISPLAY_INTERPOLATION),
            FakeRnaProp("use_slice", "BOOLEAN"),
            FakeRnaProp("slice_axis", "ENUM", enum_items=DISPLAY_SLICE_AXES),
            FakeRnaProp("slice_depth", "FLOAT"),
        )


class FakeVolumeRender:
    def __init__(self) -> None:
        self.precision = "FULL"
        self.space = "OBJECT"
        self.step_size = 0.0
        self.clipping = 0.001
        self.bl_rna = _rna(
            FakeRnaProp("precision", "ENUM", enum_items=RENDER_PRECISION),
            FakeRnaProp("space", "ENUM", enum_items=RENDER_SPACE),
            FakeRnaProp("step_size", "FLOAT"),
            FakeRnaProp("clipping", "FLOAT"),
        )


class FakeVolumeData:
    def __init__(self, name: str = "Volume") -> None:
        self.name = name
        self.id_type = "VOLUME"
        self.users = 1
        self.use_fake_user = False
        self.use_extra_user = False
        self.tag = False
        self.filepath = ""
        self.packed_file = None
        self.is_sequence = False
        self.frame_start = 1
        self.frame_duration = 0
        self.frame_offset = 0
        self.sequence_mode = "CLIP"
        self.grids = FakeVolumeGrids()
        self.materials = []
        self.display = FakeVolumeDisplay()
        self.render = FakeVolumeRender()
        self.velocity_grid = ""
        self.velocity_unit = "FRAME"
        self.velocity_scale = 1.0
        self.velocity_x_grid = ""
        self.velocity_y_grid = ""
        self.velocity_z_grid = ""
        self.animation_data = None
        self.bl_rna = _rna(
            FakeRnaProp("name", "STRING"),
            FakeRnaProp("id_type", "ENUM", is_readonly=True),
            FakeRnaProp("users", "INT", is_readonly=True),
            FakeRnaProp("use_fake_user", "BOOLEAN"),
            FakeRnaProp("use_extra_user", "BOOLEAN"),
            FakeRnaProp("tag", "BOOLEAN"),
            FakeRnaProp("filepath", "STRING"),
            FakeRnaProp("packed_file", "POINTER", is_readonly=True),
            FakeRnaProp("is_sequence", "BOOLEAN"),
            FakeRnaProp("frame_start", "INT"),
            FakeRnaProp("frame_duration", "INT"),
            FakeRnaProp("frame_offset", "INT"),
            FakeRnaProp("sequence_mode", "ENUM", enum_items=[FakeEnumItem("CLIP"), FakeEnumItem("EXTEND")]),
            FakeRnaProp("grids", "COLLECTION", is_readonly=True),
            FakeRnaProp("materials", "COLLECTION", is_readonly=True),
            FakeRnaProp("display", "POINTER", is_readonly=True),
            FakeRnaProp("render", "POINTER", is_readonly=True),
            FakeRnaProp("velocity_grid", "STRING"),
            FakeRnaProp("velocity_unit", "ENUM", enum_items=[FakeEnumItem("FRAME"), FakeEnumItem("SECOND")]),
            FakeRnaProp("velocity_scale", "FLOAT"),
            FakeRnaProp("velocity_x_grid", "STRING", is_readonly=True),
            FakeRnaProp("velocity_y_grid", "STRING", is_readonly=True),
            FakeRnaProp("velocity_z_grid", "STRING", is_readonly=True),
            FakeRnaProp("animation_data", "POINTER", is_readonly=True),
        )


class FakeObj:
    def __init__(self, name: str, type: str = "VOLUME", data: FakeVolumeData | None = None) -> None:
        self.name = name
        self.type = type
        self.data = data if data is not None else FakeVolumeData(name)
        self.location = [0.0, 0.0, 0.0]
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.mode = "OBJECT"
        self._selected = False

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


class FakeObjects(list):
    def get(self, name: str):
        return next((obj for obj in self if obj.name == name), None)


class FakeVolumes(list):
    def get(self, name: str):
        return next((volume for volume in self if volume.name == name), None)


class _Op:
    def __init__(self, log: list, name: str, on_call=None) -> None:
        self._log = log
        self._name = name
        self._on_call = on_call

    def poll(self) -> bool:
        return True

    def __call__(self, **kwargs):
        self._log.append((self._name, kwargs))
        if self._on_call is not None:
            return self._on_call(**kwargs)
        return {"FINISHED"}


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects = FakeObjects()
        self.volumes = FakeVolumes()
        self.op_calls: list = []
        self.mode_calls: list[str] = []
        self.undo_pushes: list[str] = []
        self._active_obj = None

        bpy = self

        class _Objects:
            @property
            def active(self_inner):
                return bpy._active_obj

            @active.setter
            def active(self_inner, value):
                bpy._active_obj = value

        self.view_layer = types.SimpleNamespace(objects=_Objects())
        self.scene = types.SimpleNamespace(objects=self.objects, name="Scene")

        class _Context:
            scene = self.scene
            view_layer = self.view_layer
            window_manager = types.SimpleNamespace(windows=[])

            @property
            def object(self_inner):
                return bpy._active_obj

            @staticmethod
            @contextmanager
            def temp_override(**kw):
                yield

        self.context = _Context()
        log = self.op_calls

        def _volume_add(location=None, **kwargs):
            obj = FakeObj("Volume")
            obj.location = list(location or [0.0, 0.0, 0.0])
            self.add(obj)
            return {"FINISHED"}

        def _volume_import(filepath: str = "", **kwargs):
            name = filepath.rsplit("/", 1)[-1].split(".", 1)[0] or "Volume"
            data = FakeVolumeData(name)
            data.filepath = filepath
            obj = FakeObj(name, data=data)
            self.add(obj)
            return {"FINISHED"}

        class _ObjectOps:
            volume_add = _Op(log, "object.volume_add", on_call=_volume_add)
            volume_import = _Op(log, "object.volume_import", on_call=_volume_import)

            @staticmethod
            def mode_set(mode="OBJECT", **kw):
                bpy.mode_calls.append(mode)
                if bpy._active_obj is not None:
                    bpy._active_obj.mode = mode

        class _EdOps:
            @staticmethod
            def undo_push(message: str = "", **kw):
                bpy.undo_pushes.append(message)

        self.ops = types.SimpleNamespace(object=_ObjectOps(), ed=_EdOps())

    def add(self, obj: FakeObj) -> FakeObj:
        self.objects.append(obj)
        if getattr(obj, "type", None) == "VOLUME" and getattr(obj, "data", None) is not None:
            self.volumes.append(obj.data)
        self._active_obj = obj
        return obj

    @property
    def data(self):
        return types.SimpleNamespace(objects=self.objects, volumes=self.volumes)


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def _op_names(bpy: FakeBpy) -> list[str]:
    return [name for name, _ in bpy.op_calls]


def test_router_contains_volume_gui_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "volume.create_empty",
        "volume.import",
        "volume.list",
        "volume.report",
        "volume.set",
    } <= names


def test_create_list_report_and_set_volume(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    created = dispatch_on_main(reg, "volume.create_empty", {"name": "Fog", "location": [1, 2, 3]}, ctx)

    assert created["object"] == "Fog"
    assert created["type"] == "VOLUME"
    assert created["volume"]["data"] == "Fog"
    assert created["location"] == [1.0, 2.0, 3.0]
    assert "object.volume_add" in _op_names(bpy)
    assert bpy.undo_pushes == ["mcp:volume.create_empty"]

    listed = dispatch_on_main(reg, "volume.list", {}, ctx)
    assert listed["volume_count"] == 1
    assert listed["volumes"][0]["name"] == "Fog"

    density = dispatch_on_main(reg, "volume.set", {"name_or_object": "Fog", "property": "display.density", "value": "2.5"}, ctx)
    assert density["value"] == 2.5
    assert bpy.objects.get("Fog").data.display.density == 2.5

    render_space = dispatch_on_main(
        reg,
        "volume.set",
        {"name_or_object": "Fog", "property": "render.space", "value": json.dumps("WORLD")},
        ctx,
    )
    assert render_space["value"] == "WORLD"

    report = dispatch_on_main(reg, "volume.report", {"name_or_object": "Fog"}, ctx)
    assert report["volume"]["display"]["properties"]["density"]["value"] == 2.5
    assert report["volume"]["render"]["properties"]["space"]["value"] == "WORLD"
    assert report["volume"]["grids"]["grid_count"] == 1


def test_import_volume_uses_operator_and_can_rename(env, tmp_path) -> None:
    ctx, bpy = env
    path = tmp_path / "smoke.vdb"
    path.write_text("fake")
    reg = build_default_registry()

    imported = dispatch_on_main(reg, "volume.import", {"path": str(path), "name": "ImportedFog"}, ctx)

    assert imported["object"] == "ImportedFog"
    assert imported["volume"]["filepath"] == str(path)
    assert "object.volume_import" in _op_names(bpy)


def test_report_can_resolve_by_data_block_name(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Fog", data=FakeVolumeData("FogData")))
    reg = build_default_registry()

    report = dispatch_on_main(reg, "volume.report", {"name_or_object": "FogData"}, ctx)

    assert report["object"] == "Fog"
    assert report["volume"]["data"] == "FogData"


def test_non_volume_object_and_missing_import_path_fail_without_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", type="MESH", data=None))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as non_volume:
        dispatch_on_main(reg, "volume.report", {"name_or_object": "Cube"}, ctx)

    with pytest.raises(BridgeError) as missing_path:
        dispatch_on_main(reg, "volume.import", {"path": "/no/such/file.vdb"}, ctx)

    assert non_volume.value.code == PRECONDITION
    assert missing_path.value.code == INVALID_PARAMS
    assert bpy.undo_pushes == []


def test_read_only_and_missing_properties_fail_without_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Fog", data=FakeVolumeData("FogData")))
    reg = build_default_registry()

    with pytest.raises(BridgeError) as readonly:
        dispatch_on_main(reg, "volume.set", {"name_or_object": "Fog", "property": "grids", "value": "[]"}, ctx)

    with pytest.raises(BridgeError) as missing:
        dispatch_on_main(reg, "volume.set", {"name_or_object": "Fog", "property": "display.missing", "value": "1"}, ctx)

    assert readonly.value.code == PRECONDITION
    assert missing.value.code == INVALID_PARAMS
    assert bpy.undo_pushes == []
