from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, BridgeError


class _NamedList(list):
    def get(self, name: str):
        return next((item for item in self if getattr(item, "name", None) == name), None)


class FakeSocket:
    def __init__(self, name: str, socket_type: str = "GEOMETRY") -> None:
        self.name = name
        self.identifier = name
        self.type = socket_type
        self.enabled = True
        self.is_linked = False


class FakeNode:
    def __init__(self, name: str, bl_idname: str) -> None:
        self.name = name
        self.label = ""
        self.bl_idname = bl_idname
        self.type = bl_idname
        self.location = [0.0, 0.0]
        self.inputs = _NamedList()
        self.outputs = _NamedList()
        if bl_idname == "NodeGroupInput":
            self.outputs.append(FakeSocket("Geometry"))
        elif bl_idname == "NodeGroupOutput":
            self.inputs.append(FakeSocket("Geometry"))
        else:
            self.inputs.append(FakeSocket("Geometry"))
            self.outputs.append(FakeSocket("Geometry"))


class FakeNodes(_NamedList):
    def new(self, type: str):
        node = FakeNode(type, type)
        _attach_socket_nodes(node)
        self.append(node)
        return node


class FakeLink:
    def __init__(self, from_node: FakeNode, from_socket: FakeSocket, to_node: FakeNode, to_socket: FakeSocket) -> None:
        self.from_node = from_node
        self.from_socket = from_socket
        self.to_node = to_node
        self.to_socket = to_socket
        from_socket.is_linked = True
        to_socket.is_linked = True


class FakeLinks(list):
    def new(self, input_socket: FakeSocket, output_socket: FakeSocket):
        from_node = getattr(output_socket, "node", None)
        to_node = getattr(input_socket, "node", None)
        link = FakeLink(from_node, output_socket, to_node, input_socket)
        self.append(link)
        return link


def _attach_socket_nodes(node: FakeNode) -> None:
    for socket in [*node.inputs, *node.outputs]:
        socket.node = node


class FakeInterfaceItem:
    def __init__(self, name: str, in_out: str) -> None:
        self.name = name
        self.item_type = "SOCKET"
        self.in_out = in_out
        self.socket_type = "NodeSocketGeometry"


class FakeNodeGroup:
    def __init__(self, name: str) -> None:
        self.name = name
        self.type = "GEOMETRY"
        self.nodes = FakeNodes()
        group_input = FakeNode("Group Input", "NodeGroupInput")
        group_output = FakeNode("Group Output", "NodeGroupOutput")
        _attach_socket_nodes(group_input)
        _attach_socket_nodes(group_output)
        self.nodes.extend([group_input, group_output])
        self.links = FakeLinks()
        self.links.new(group_output.inputs[0], group_input.outputs[0])
        self.interface = types.SimpleNamespace(
            items_tree=[
                FakeInterfaceItem("Geometry", "OUTPUT"),
                FakeInterfaceItem("Geometry", "INPUT"),
            ]
        )


class FakeModifier:
    def __init__(self, name: str, mod_type: str) -> None:
        self.name = name
        self.type = mod_type
        self.show_viewport = True
        self.node_group = None


class FakeModifierStack(_NamedList):
    def new(self, name: str, type: str):
        mod = FakeModifier(name, type)
        self.append(mod)
        return mod


class FakeObject:
    def __init__(self, name: str) -> None:
        self.name = name
        self.type = "MESH"
        self.modifiers = FakeModifierStack()
        self.mode = "OBJECT"
        self._selected = False

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects = _NamedList()
        self.op_calls = []
        self.mode_calls = []
        self.active = None
        self.context = self._make_context()
        self.data = types.SimpleNamespace(objects=self.objects)
        self.ops = self._make_ops()

    def _make_context(self):
        bpy = self

        class _Objects:
            @property
            def active(self):
                return bpy.active

            @active.setter
            def active(self, value):
                bpy.active = value

        class _Context:
            scene = types.SimpleNamespace(objects=bpy.objects)
            view_layer = types.SimpleNamespace(objects=_Objects())
            window_manager = types.SimpleNamespace(windows=[])

            @property
            def object(self):
                return bpy.active

            @staticmethod
            @contextmanager
            def temp_override(**kw):
                yield

        return _Context()

    def _make_ops(self):
        bpy = self

        class ObjectOps:
            def mode_set(self, mode="OBJECT", **kwargs):
                bpy.mode_calls.append(mode)
                if bpy.active is not None:
                    bpy.active.mode = mode

        class NodeOps:
            def new_geometry_nodes_modifier(self, **kwargs):
                bpy.op_calls.append(("node.new_geometry_nodes_modifier", kwargs))
                obj = bpy.active
                mod = obj.modifiers.new(name="GeometryNodes", type="NODES")
                mod.node_group = FakeNodeGroup("Geometry Nodes")

        class EdOps:
            def undo_push(self, message="", **kwargs):
                bpy.op_calls.append(("ed.undo_push", {"message": message, **kwargs}))

        return types.SimpleNamespace(object=ObjectOps(), node=NodeOps(), ed=EdOps())

    def add(self, obj: FakeObject):
        self.objects.append(obj)
        self.active = obj
        return obj


def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_geometry_nodes_create_report() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"geometry_nodes.create_modifier", "geometry_nodes.report"} <= names


def test_create_modifier_uses_blender_operator_and_reports(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    obj = bpy.add(FakeObject("Cube"))
    obj.mode = "EDIT"
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "geometry_nodes.create_modifier",
        {"object": "Cube", "name": "Procedural"},
        ctx,
    )

    assert out["object"] == "Cube"
    assert out["modifier"] == "Procedural"
    assert out["node_group"] == "Geometry Nodes"
    assert [node["name"] for node in out["nodes"]] == ["Group Input", "Group Output"]
    assert out["links"] == [
        {
            "from_node": "Group Input",
            "from_socket": "Geometry",
            "to_node": "Group Output",
            "to_socket": "Geometry",
        }
    ]
    assert ("node.new_geometry_nodes_modifier", {}) in bpy.op_calls
    assert bpy.mode_calls == ["OBJECT", "EDIT"]


def test_report_returns_existing_geometry_node_group(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    obj = bpy.add(FakeObject("Cube"))
    mod = obj.modifiers.new(name="Nodes", type="NODES")
    mod.node_group = FakeNodeGroup("GeoNodes")
    reg = build_default_registry()

    out = dispatch_on_main(reg, "geometry_nodes.report", {"object": "Cube", "modifier": "Nodes"}, ctx)

    assert out["modifier"] == "Nodes"
    assert out["node_group"] == "GeoNodes"
    assert out["interface"] == [
        {"name": "Geometry", "item_type": "SOCKET", "in_out": "OUTPUT", "socket_type": "NodeSocketGeometry"},
        {"name": "Geometry", "item_type": "SOCKET", "in_out": "INPUT", "socket_type": "NodeSocketGeometry"},
    ]
    assert out["nodes"][0]["outputs"][0]["name"] == "Geometry"
    assert out["nodes"][1]["inputs"][0]["name"] == "Geometry"


def test_router_contains_geometry_nodes_edit_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"geometry_nodes.add_node", "geometry_nodes.link"} <= names


def test_add_node_creates_node_by_bl_idname_and_name(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    obj = bpy.add(FakeObject("Cube"))
    mod = obj.modifiers.new(name="Nodes", type="NODES")
    mod.node_group = FakeNodeGroup("GeoNodes")
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "geometry_nodes.add_node",
        {"object": "Cube", "modifier": "Nodes", "type": "GeometryNodeTransform", "name": "Transform"},
        ctx,
    )

    assert out["node"]["name"] == "Transform"
    assert out["node"]["bl_idname"] == "GeometryNodeTransform"
    assert mod.node_group.nodes.get("Transform") is not None


def test_link_resolves_node_and_socket_names(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    obj = bpy.add(FakeObject("Cube"))
    mod = obj.modifiers.new(name="Nodes", type="NODES")
    mod.node_group = FakeNodeGroup("GeoNodes")
    transform = mod.node_group.nodes.new(type="GeometryNodeTransform")
    transform.name = "Transform"
    reg = build_default_registry()

    out = dispatch_on_main(
        reg,
        "geometry_nodes.link",
        {
            "object": "Cube",
            "modifier": "Nodes",
            "from_node": "Group Input",
            "from_socket": "Geometry",
            "to_node": "Transform",
            "to_socket": "Geometry",
        },
        ctx,
    )

    assert out["link"] == {
        "from_node": "Group Input",
        "from_socket": "Geometry",
        "to_node": "Transform",
        "to_socket": "Geometry",
    }
    assert out["link"] in out["links"]


def test_link_missing_node_raises_invalid_params(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    obj = bpy.add(FakeObject("Cube"))
    mod = obj.modifiers.new(name="Nodes", type="NODES")
    mod.node_group = FakeNodeGroup("GeoNodes")
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "geometry_nodes.link",
            {
                "object": "Cube",
                "modifier": "Nodes",
                "from_node": "Missing",
                "from_socket": "Geometry",
                "to_node": "Group Output",
                "to_socket": "Geometry",
            },
            ctx,
        )
    assert exc.value.code == INVALID_PARAMS
