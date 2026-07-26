"""Rendering subsystem unit tests (fake-bpy).

Starts with cameras and lights, then grows through render/world/compositor tasks. The
fake mirrors the bits the handlers need: object.camera_add, object.light_add, scene
camera/render/world state, and bpy.data.objects lookup.
"""

from __future__ import annotations

import os
import sys
import types
from contextlib import contextmanager

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, BridgeError


class FakeCameraData:
    def __init__(self, name: str = "Camera") -> None:
        self.name = name
        self.type = "PERSP"
        self.lens = 50.0
        self.ortho_scale = 6.0
        self.clip_start = 0.1
        self.clip_end = 1000.0
        self.sensor_width = 36.0


class FakeLightData:
    def __init__(self, type: str = "POINT") -> None:
        self.type = type
        self.energy = 10.0
        self.color = [1.0, 1.0, 1.0]
        self.size = 1.0
        self.spot_size = 0.785398
        self.spot_blend = 0.15


class FakeObj:
    def __init__(self, name: str, type: str, data=None) -> None:
        self.name = name
        self.type = type
        self.data = data
        self.location = [0.0, 0.0, 0.0]
        self.rotation_euler = [0.0, 0.0, 0.0]
        self._selected = False
        self.mode = "OBJECT"

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


class FakeInput:
    def __init__(self, name: str, default_value=None) -> None:
        self.name = name
        self.identifier = name
        self.type = "VALUE"
        self.enabled = True
        self.is_linked = False
        self.default_value = default_value


class FakeSocket(FakeInput):
    pass


class FakeSocketList(list):
    def get(self, name: str):
        return next((socket for socket in self if socket.name == name or socket.identifier == name), None)


class FakeNode:
    def __init__(self, name: str, type: str = "BACKGROUND") -> None:
        self.name = name
        self.label = ""
        self.type = type
        self.bl_idname = "ShaderNodeBackground"
        self.location = [0.0, 0.0]
        self.inputs = {"Color": FakeInput("Color", [0.05, 0.05, 0.05]), "Strength": FakeInput("Strength", 1.0)}
        self.outputs = {}


class FakeCompositorNode:
    def __init__(self, name: str, bl_idname: str) -> None:
        self.name = name
        self.label = ""
        self.type = bl_idname.replace("CompositorNode", "").upper() or bl_idname
        self.bl_idname = bl_idname
        self.location = [0.0, 0.0]
        self.inputs = FakeSocketList([FakeSocket("Image")])
        self.outputs = FakeSocketList([FakeSocket("Image")])


class FakeCompositorNodes(list):
    def __init__(self) -> None:
        super().__init__(
            [
                FakeCompositorNode("Render Layers", "CompositorNodeRLayers"),
                FakeCompositorNode("Composite", "CompositorNodeComposite"),
            ]
        )

    def get(self, name: str):
        return next((node for node in self if node.name == name), None)

    def new(self, type: str):
        node = FakeCompositorNode(type.replace("CompositorNode", "") or type, type)
        self.append(node)
        return node


class FakeLink:
    def __init__(self, from_node, from_socket, to_node, to_socket) -> None:
        self.from_node = from_node
        self.from_socket = from_socket
        self.to_node = to_node
        self.to_socket = to_socket


class FakeLinks(list):
    def __init__(self, nodes: FakeCompositorNodes) -> None:
        super().__init__()
        self._nodes = nodes

    def new(self, input_socket, output_socket):
        from_node = next(node for node in self._nodes if output_socket in node.outputs)
        to_node = next(node for node in self._nodes if input_socket in node.inputs)
        link = FakeLink(from_node, output_socket, to_node, input_socket)
        input_socket.is_linked = True
        output_socket.is_linked = True
        self.append(link)
        return link


class FakeCompositorTree:
    def __init__(self) -> None:
        self.nodes = FakeCompositorNodes()
        self.links = FakeLinks(self.nodes)


class FakeNodes(list):
    def get(self, name: str):
        return next((node for node in self if node.name == name), None)


class FakeWorld:
    def __init__(self) -> None:
        self.name = "World"
        self.color = [0.05, 0.05, 0.05]
        self.use_nodes = False
        self.node_tree = types.SimpleNamespace(nodes=FakeNodes([FakeNode("Background")]), links=[])


class FakeImageSettings:
    def __init__(self) -> None:
        self.file_format = "PNG"


class FakeRenderSettings:
    def __init__(self) -> None:
        self.engine = "BLENDER_WORKBENCH"
        self.filepath = ""
        self.resolution_x = 1920
        self.resolution_y = 1080
        self.resolution_percentage = 100
        self.film_transparent = False
        self.image_settings = FakeImageSettings()


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
            self._on_call(**kwargs)


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, FakeObj] = {}
        self.op_calls: list = []
        self.undo_pushes: list[str] = []
        self.mode_calls: list[str] = []
        self._active_obj = None
        self._camera_counter = 0
        self._light_counter = 0

        bpy = self

        class _Scene:
            def __init__(self_inner) -> None:
                self_inner.objects = []
                self_inner.name = "Scene"
                self_inner.camera = None
                self_inner.render = FakeRenderSettings()
                self_inner.world = FakeWorld()
                self_inner.use_nodes = False
                self_inner.node_tree = FakeCompositorTree()

        self.scene = _Scene()

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

        def _camera_add(**kwargs):
            bpy._camera_counter += 1
            name = "Camera" if bpy._camera_counter == 1 else f"Camera.{bpy._camera_counter:03d}"
            obj = FakeObj(name, "CAMERA", FakeCameraData(name))
            obj.location = [float(v) for v in kwargs.get("location", [0.0, 0.0, 0.0])]
            obj.rotation_euler = [float(v) for v in kwargs.get("rotation", [0.0, 0.0, 0.0])]
            bpy.add(obj)

        def _light_add(**kwargs):
            bpy._light_counter += 1
            name = "Light" if bpy._light_counter == 1 else f"Light.{bpy._light_counter:003d}"
            obj = FakeObj(name, "LIGHT", FakeLightData(str(kwargs.get("type", "POINT"))))
            obj.location = [float(v) for v in kwargs.get("location", [0.0, 0.0, 0.0])]
            obj.rotation_euler = [float(v) for v in kwargs.get("rotation", [0.0, 0.0, 0.0])]
            bpy.add(obj)

        class _ObjectOps:
            camera_add = _Op(log, "object.camera_add", on_call=_camera_add)
            light_add = _Op(log, "object.light_add", on_call=_light_add)

            def mode_set(self_inner, mode="OBJECT", **kw):
                bpy.mode_calls.append(mode)
                if bpy._active_obj is not None:
                    bpy._active_obj.mode = mode

        class _EdOps:
            def undo_push(self_inner, message: str = "", **kw):
                bpy.undo_pushes.append(message)

            def undo(self_inner, **kw):
                pass

        def _render(**kwargs):
            with open(bpy.scene.render.filepath, "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\nfake")

        class _RenderOps:
            render = _Op(log, "render.render", on_call=_render)

        self.ops = types.SimpleNamespace(object=_ObjectOps(), render=_RenderOps(), ed=_EdOps())

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


def _kwargs(log, name):
    return next(kwargs for op_name, kwargs in log if op_name == name)


def test_router_contains_camera_light_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "camera.create",
        "camera.list",
        "camera.report",
        "camera.set",
        "camera.set_active",
        "light.create",
        "light.list",
        "light.report",
        "light.set",
    } <= names


def test_camera_create_sets_data_and_active_scene_camera(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "camera.create",
        {
            "name": "ShotCam",
            "location": [1, 2, 3],
            "rotation": [0.1, 0.2, 0.3],
            "lens": 35,
            "clip_end": 500,
            "active": True,
        },
        ctx,
    )

    assert _kwargs(bpy.op_calls, "object.camera_add") == {
        "location": [1.0, 2.0, 3.0],
        "rotation": [0.1, 0.2, 0.3],
    }
    assert out["camera"] == "ShotCam"
    assert out["active"] is True
    assert out["lens"] == 35.0
    assert out["clip_end"] == 500.0
    assert bpy.scene.camera.name == "ShotCam"
    assert bpy.undo_pushes == ["mcp:camera.create"]


def test_camera_list_report_set_and_set_active(env) -> None:
    ctx, bpy = env
    cam_a = bpy.add(FakeObj("A", "CAMERA", FakeCameraData("A")))
    cam_b = bpy.add(FakeObj("B", "CAMERA", FakeCameraData("B")))
    bpy.scene.camera = cam_a
    reg = build_default_registry()

    listed = dispatch_on_main(reg, "camera.list", {}, ctx)
    assert listed["active"] == "A"
    assert [cam["camera"] for cam in listed["cameras"]] == ["A", "B"]

    updated = dispatch_on_main(
        reg,
        "camera.set",
        {"camera": "B", "type": "ORTHO", "ortho_scale": 8.0, "clip_start": 0.25},
        ctx,
    )
    assert updated["type"] == "ORTHO"
    assert updated["ortho_scale"] == 8.0
    assert updated["clip_start"] == 0.25

    active = dispatch_on_main(reg, "camera.set_active", {"camera": "B"}, ctx)
    assert active["active"] == "B"
    assert bpy.scene.camera is cam_b

    report = dispatch_on_main(reg, "camera.report", {"camera": "B"}, ctx)
    assert report["camera"] == "B"
    assert report["active"] is True


def test_light_create_and_set(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    created = dispatch_on_main(
        reg,
        "light.create",
        {
            "type": "AREA",
            "name": "Key",
            "location": [0, -3, 4],
            "energy": 500,
            "color": [1.0, 0.8, 0.6],
            "size": 5,
        },
        ctx,
    )

    assert _kwargs(bpy.op_calls, "object.light_add")["type"] == "AREA"
    assert created["light"] == "Key"
    assert created["energy"] == 500.0
    assert created["color"] == [1.0, 0.8, 0.6]
    assert created["size"] == 5.0

    updated = dispatch_on_main(
        reg,
        "light.set",
        {"light": "Key", "energy": 250, "spot_size": 0.5, "spot_blend": 0.2},
        ctx,
    )
    assert updated["energy"] == 250.0
    assert updated["spot_size"] == 0.5
    assert updated["spot_blend"] == 0.2

    listed = dispatch_on_main(reg, "light.list", {}, ctx)
    assert listed["count"] == 1
    assert listed["lights"][0]["light"] == "Key"
    assert bpy.undo_pushes == ["mcp:light.create", "mcp:light.set"]


def test_router_contains_render_world_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"render.settings", "render.set_settings", "render.still", "world.report", "world.set"} <= names


def test_render_settings_reports_and_set(env) -> None:
    ctx, bpy = env
    cam = bpy.add(FakeObj("ShotCam", "CAMERA", FakeCameraData("ShotCam")))
    bpy.scene.camera = cam
    reg = build_default_registry()

    before = dispatch_on_main(reg, "render.settings", {}, ctx)
    assert before["engine"] == "BLENDER_WORKBENCH"
    assert before["resolution"] == [1920, 1080]
    assert before["image_format"] == "PNG"
    assert before["camera"] == "ShotCam"

    after = dispatch_on_main(
        reg,
        "render.set_settings",
        {
            "engine": "CYCLES",
            "filepath": "/tmp/out.png",
            "resolution_x": 640,
            "resolution_y": 360,
            "image_format": "OPEN_EXR",
            "transparent": True,
        },
        ctx,
    )
    assert after["engine"] == "CYCLES"
    assert after["filepath"] == "/tmp/out.png"
    assert after["resolution"] == [640, 360]
    assert after["image_format"] == "OPEN_EXR"
    assert after["transparent"] is True
    assert bpy.undo_pushes == ["mcp:render.set_settings"]


def test_render_still_writes_file_and_restores_settings(env, tmp_path) -> None:
    ctx, bpy = env
    cam = bpy.add(FakeObj("ShotCam", "CAMERA", FakeCameraData("ShotCam")))
    bpy.scene.camera = cam
    bpy.scene.render.filepath = "/keep/old.png"
    bpy.scene.render.resolution_x = 1920
    bpy.scene.render.resolution_y = 1080
    bpy.scene.render.engine = "BLENDER_WORKBENCH"
    path = tmp_path / "still.png"
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "render.still",
        {"path": str(path), "camera": "ShotCam", "engine": "CYCLES", "resolution_x": 64, "resolution_y": 32},
        ctx,
    )

    assert out["path"] == str(path)
    assert out["bytes"] > 0
    assert os.path.exists(path)
    assert bpy.scene.render.filepath == "/keep/old.png"
    assert bpy.scene.render.resolution_x == 1920
    assert bpy.scene.render.resolution_y == 1080
    assert bpy.scene.render.engine == "BLENDER_WORKBENCH"
    assert bpy.scene.camera is cam
    assert _kwargs(bpy.op_calls, "render.render") == {"write_still": True}
    assert bpy.undo_pushes == []


def test_world_report_and_set_color_strength(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    before = dispatch_on_main(reg, "world.report", {}, ctx)
    assert before["world"] == "World"
    assert before["color"] == [0.05, 0.05, 0.05]
    assert before["strength"] == 1.0

    after = dispatch_on_main(reg, "world.set", {"color": [0.1, 0.2, 0.3], "strength": 2.5}, ctx)
    assert after["color"] == [0.1, 0.2, 0.3]
    assert after["use_nodes"] is True
    assert after["strength"] == 2.5
    assert bpy.scene.world.node_tree.nodes.get("Background").inputs["Strength"].default_value == 2.5
    assert bpy.undo_pushes == ["mcp:world.set"]


def test_router_contains_compositor_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"compositor.enable", "compositor.report", "compositor.add_node", "compositor.link"} <= names


def test_compositor_enable_and_report(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    enabled = dispatch_on_main(reg, "compositor.enable", {"enable": True}, ctx)

    assert enabled["use_nodes"] is True
    assert {node["name"] for node in enabled["nodes"]} == {"Render Layers", "Composite"}
    assert bpy.scene.use_nodes is True
    assert bpy.undo_pushes == ["mcp:compositor.enable"]

    reported = dispatch_on_main(reg, "compositor.report", {}, ctx)
    assert reported["use_nodes"] is True
    assert reported["links"] == []


def test_compositor_add_node(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    out = dispatch_on_main(reg, "compositor.add_node", {"type": "CompositorNodeBlur", "name": "SoftBlur"}, ctx)

    assert out["use_nodes"] is True
    assert out["node"]["name"] == "SoftBlur"
    assert out["node"]["bl_idname"] == "CompositorNodeBlur"
    assert bpy.scene.node_tree.nodes.get("SoftBlur") is not None
    assert bpy.undo_pushes == ["mcp:compositor.add_node"]


def test_compositor_link(env) -> None:
    ctx, bpy = env
    bpy.scene.use_nodes = True
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "compositor.link",
        {
            "from_node": "Render Layers",
            "from_socket": "Image",
            "to_node": "Composite",
            "to_socket": "Image",
        },
        ctx,
    )

    assert out["link"] == {
        "from_node": "Render Layers",
        "from_socket": "Image",
        "to_node": "Composite",
        "to_socket": "Image",
    }
    assert len(bpy.scene.node_tree.links) == 1
    assert bpy.undo_pushes == ["mcp:compositor.link"]


def test_compositor_link_missing_socket_is_invalid_params(env) -> None:
    ctx, bpy = env
    bpy.scene.use_nodes = True
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "compositor.link",
            {
                "from_node": "Render Layers",
                "from_socket": "Missing",
                "to_node": "Composite",
                "to_socket": "Image",
            },
            ctx,
        )
    assert exc.value.code == INVALID_PARAMS
    assert bpy.undo_pushes == []
