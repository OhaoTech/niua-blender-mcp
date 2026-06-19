"""Shading domain unit tests (fake-bpy).

Extends the FakeBpy pattern with a material/datablock model: ``data.materials``
(new/get/keys), ``data.images.load``, and a node-tree fake whose nodes carry named
``inputs``/``outputs`` sockets (so set_principled can write ``default_value`` and
add_image_texture can ``links.new`` to a Principled input). Objects carry a
``data.materials`` slot collection plus ``active_material``/``active_material_index``.

These ops are datablock-level (no edit-mode context), so the tests assert on the
resulting datablocks and on the kernel's single undo push, not on operator calls.
"""

from __future__ import annotations

import sys
import types

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError


class FakeSocket:
    def __init__(self, value=None) -> None:
        self.default_value = value
        self.links = []


class FakeNode:
    def __init__(self, ntype: str, input_names, output_names) -> None:
        self.type = ntype
        self.inputs = {n: FakeSocket() for n in input_names}
        self.outputs = {n: FakeSocket() for n in output_names}
        self.image = None


_PRINCIPLED_INPUTS = ["Base Color", "Alpha", "Metallic", "Roughness", "Emission Strength", "Normal"]


def _make_node(ntype: str) -> FakeNode:
    if ntype == "ShaderNodeBsdfPrincipled":
        return FakeNode("BSDF_PRINCIPLED", _PRINCIPLED_INPUTS, ["BSDF"])
    if ntype == "ShaderNodeOutputMaterial":
        return FakeNode("OUTPUT_MATERIAL", ["Surface"], [])
    if ntype == "ShaderNodeTexImage":
        return FakeNode("TEX_IMAGE", ["Vector"], ["Color", "Alpha"])
    if ntype == "ShaderNodeNormalMap":
        return FakeNode("NORMAL_MAP", ["Color"], ["Normal"])
    return FakeNode(ntype, [], [])


class FakeNodes(list):
    def new(self, ntype: str) -> FakeNode:
        node = _make_node(ntype)
        self.append(node)
        return node


class FakeLinks:
    def __init__(self) -> None:
        self.created = []

    def new(self, output_socket, input_socket):
        self.created.append((output_socket, input_socket))
        return (output_socket, input_socket)


class FakeNodeTree:
    def __init__(self) -> None:
        self.nodes = FakeNodes()
        self.links = FakeLinks()


class FakeMaterial:
    def __init__(self, name: str) -> None:
        self.name = name
        self._use_nodes = False
        self.node_tree = None

    @property
    def use_nodes(self) -> bool:
        return self._use_nodes

    @use_nodes.setter
    def use_nodes(self, value: bool) -> None:
        self._use_nodes = bool(value)
        if value and self.node_tree is None:
            tree = FakeNodeTree()
            # A fresh node-based material ships with Principled + Output, like Blender.
            principled = tree.nodes.new("ShaderNodeBsdfPrincipled")
            output = tree.nodes.new("ShaderNodeOutputMaterial")
            tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])
            self.node_tree = tree


class FakeImage:
    def __init__(self, name: str) -> None:
        self.name = name
        self.colorspace_settings = types.SimpleNamespace(name="sRGB")


class FakeMatSlots(list):
    """Object material slots: a list that also supports .append of materials."""


class FakeObjData:
    def __init__(self) -> None:
        self.materials = FakeMatSlots()


class FakeObj:
    def __init__(self, name: str, type: str = "MESH") -> None:
        self.name = name
        self.type = type
        self.data = FakeObjData()
        self.active_material_index = 0

    @property
    def active_material(self):
        slots = self.data.materials
        idx = self.active_material_index
        if 0 <= idx < len(slots):
            return slots[idx]
        return slots[0] if slots else None


class FakeMaterials(dict):
    def new(self, name: str) -> FakeMaterial:
        # Blender de-dupes names (Material -> Material.001); keep it simple but unique.
        final = name
        i = 1
        while final in self:
            final = f"{name}.{i:03d}"
            i += 1
        mat = FakeMaterial(final)
        self[final] = mat
        return mat


class FakeImages:
    def __init__(self) -> None:
        self.loaded = []

    def load(self, path: str) -> FakeImage:
        import os

        img = FakeImage(os.path.basename(path) or "image")
        self.loaded.append(path)
        return img


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, FakeObj] = {}
        self.scene = types.SimpleNamespace(objects=[], name="Scene")
        self.materials = FakeMaterials()
        self.images = FakeImages()
        self.undo_pushes: list[str] = []

        bpy = self

        class _EdOps:
            def undo_push(self_inner, message: str = "", **kw):
                bpy.undo_pushes.append(message)

            def undo(self_inner, **kw):
                pass

        self.ops = types.SimpleNamespace(ed=_EdOps())

    def add(self, obj: FakeObj) -> FakeObj:
        self.objects_by_name[obj.name] = obj
        self.scene.objects.append(obj)
        return obj

    @property
    def data(self):
        store = self.objects_by_name
        materials = self.materials
        images = self.images

        class _Data:
            objects = types.SimpleNamespace(get=lambda name: store.get(name))

            @property
            def materials(self_inner):
                return materials

            @property
            def images(self_inner):
                return images

        return _Data()


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


# -- create_material -------------------------------------------------------------


def test_create_material_makes_node_based_material(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    result = dispatch_on_main(reg, "shading.create_material", {"name": "Steel"}, ctx)
    assert result["material"] == "Steel"
    mat = bpy.materials["Steel"]
    assert mat.use_nodes is True
    assert bpy.undo_pushes == ["niua:shading.create_material"]


def test_create_material_defaults_name(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    result = dispatch_on_main(reg, "shading.create_material", {}, ctx)
    assert result["material"] == "Material"


# -- set_principled --------------------------------------------------------------


def test_set_principled_writes_inputs(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "shading.create_material", {"name": "M"}, ctx)
    result = dispatch_on_main(
        reg,
        "shading.set_principled",
        {
            "material": "M",
            "base_color": [0.8, 0.1, 0.1],
            "alpha": 0.5,
            "metallic": 1.0,
            "roughness": 0.2,
            "emission_strength": 3.0,
        },
        ctx,
    )
    assert result["material"] == "M"
    tree = bpy.materials["M"].node_tree
    principled = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    assert principled.inputs["Base Color"].default_value == (0.8, 0.1, 0.1, 0.5)
    assert principled.inputs["Alpha"].default_value == 0.5
    assert principled.inputs["Metallic"].default_value == 1.0
    assert principled.inputs["Roughness"].default_value == 0.2
    assert principled.inputs["Emission Strength"].default_value == 3.0


def test_set_principled_base_color_defaults_alpha_to_one(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "shading.create_material", {"name": "M"}, ctx)
    dispatch_on_main(reg, "shading.set_principled", {"material": "M", "base_color": [0.2, 0.3, 0.4]}, ctx)
    tree = bpy.materials["M"].node_tree
    principled = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    assert principled.inputs["Base Color"].default_value == (0.2, 0.3, 0.4, 1.0)


def test_set_principled_resolves_via_object_active_material(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    obj = FakeObj("Cube")
    bpy.add(obj)
    dispatch_on_main(reg, "shading.assign_material", {"object": "Cube", "material": "Red"}, ctx)
    dispatch_on_main(reg, "shading.set_principled", {"object": "Cube", "roughness": 0.9}, ctx)
    tree = bpy.materials["Red"].node_tree
    principled = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    assert principled.inputs["Roughness"].default_value == 0.9


def test_set_principled_missing_material_not_found(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "shading.set_principled", {"material": "Ghost", "metallic": 1.0}, ctx)
    assert exc.value.code == NOT_FOUND


def test_set_principled_no_target_invalid_params(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "shading.set_principled", {"metallic": 1.0}, ctx)
    assert exc.value.code == INVALID_PARAMS


# -- assign_material -------------------------------------------------------------


def test_assign_material_creates_and_appends_slot(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    obj = FakeObj("Cube")
    bpy.add(obj)
    result = dispatch_on_main(reg, "shading.assign_material", {"object": "Cube", "material": "Gold"}, ctx)
    assert result["created"] is True
    assert result["slot"] == 0
    assert obj.data.materials[0].name == "Gold"
    assert obj.active_material_index == 0
    assert bpy.undo_pushes == ["niua:shading.assign_material"]


def test_assign_material_reuses_existing_material(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    obj = FakeObj("Cube")
    bpy.add(obj)
    dispatch_on_main(reg, "shading.create_material", {"name": "Gold"}, ctx)
    result = dispatch_on_main(reg, "shading.assign_material", {"object": "Cube", "material": "Gold"}, ctx)
    assert result["created"] is False
    assert len(obj.data.materials) == 1


def test_assign_material_same_material_twice_no_duplicate_slot(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    obj = FakeObj("Cube")
    bpy.add(obj)
    dispatch_on_main(reg, "shading.assign_material", {"object": "Cube", "material": "Gold"}, ctx)
    dispatch_on_main(reg, "shading.assign_material", {"object": "Cube", "material": "Gold"}, ctx)
    assert len(obj.data.materials) == 1


def test_assign_material_missing_object_not_found(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "shading.assign_material", {"object": "Ghost", "material": "M"}, ctx)
    assert exc.value.code == NOT_FOUND


# -- add_image_texture -----------------------------------------------------------


def test_add_image_texture_base_color_links_directly(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "shading.create_material", {"name": "M"}, ctx)
    result = dispatch_on_main(
        reg,
        "shading.add_image_texture",
        {"material": "M", "image_path": "/tmp/albedo.png", "target": "BASE_COLOR"},
        ctx,
    )
    assert result["target"] == "BASE_COLOR"
    assert result["image"] == "albedo.png"
    tree = bpy.materials["M"].node_tree
    tex = next(n for n in tree.nodes if n.type == "TEX_IMAGE")
    principled = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    assert (tex.outputs["Color"], principled.inputs["Base Color"]) in tree.links.created
    # Base color is sRGB color data, not Non-Color.
    assert tex.image.colorspace_settings.name == "sRGB"


def test_add_image_texture_roughness_sets_non_color(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "shading.create_material", {"name": "M"}, ctx)
    dispatch_on_main(
        reg,
        "shading.add_image_texture",
        {"material": "M", "image_path": "/tmp/rough.png", "target": "ROUGHNESS"},
        ctx,
    )
    tree = bpy.materials["M"].node_tree
    tex = next(n for n in tree.nodes if n.type == "TEX_IMAGE")
    principled = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    assert tex.image.colorspace_settings.name == "Non-Color"
    assert (tex.outputs["Color"], principled.inputs["Roughness"]) in tree.links.created


def test_add_image_texture_normal_inserts_normal_map(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "shading.create_material", {"name": "M"}, ctx)
    dispatch_on_main(
        reg,
        "shading.add_image_texture",
        {"material": "M", "image_path": "/tmp/nrm.png", "target": "NORMAL"},
        ctx,
    )
    tree = bpy.materials["M"].node_tree
    tex = next(n for n in tree.nodes if n.type == "TEX_IMAGE")
    nmap = next(n for n in tree.nodes if n.type == "NORMAL_MAP")
    principled = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    assert (tex.outputs["Color"], nmap.inputs["Color"]) in tree.links.created
    assert (nmap.outputs["Normal"], principled.inputs["Normal"]) in tree.links.created
    assert tex.image.colorspace_settings.name == "Non-Color"


def test_add_image_texture_default_target_is_base_color(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "shading.create_material", {"name": "M"}, ctx)
    result = dispatch_on_main(
        reg, "shading.add_image_texture", {"material": "M", "image_path": "/tmp/a.png"}, ctx
    )
    assert result["target"] == "BASE_COLOR"


def test_add_image_texture_missing_material_not_found(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg, "shading.add_image_texture", {"material": "Ghost", "image_path": "/tmp/a.png"}, ctx
        )
    assert exc.value.code == NOT_FOUND


# -- list_materials (read-only) --------------------------------------------------


def test_list_materials_global(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "shading.create_material", {"name": "B"}, ctx)
    dispatch_on_main(reg, "shading.create_material", {"name": "A"}, ctx)
    before = list(bpy.undo_pushes)
    result = dispatch_on_main(reg, "shading.list_materials", {}, ctx)
    assert result["materials"] == ["A", "B"]
    assert bpy.undo_pushes == before  # read-only pushes no new undo step


def test_list_materials_for_object(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    obj = FakeObj("Cube")
    bpy.add(obj)
    dispatch_on_main(reg, "shading.assign_material", {"object": "Cube", "material": "Gold"}, ctx)
    result = dispatch_on_main(reg, "shading.list_materials", {"object": "Cube"}, ctx)
    assert result["object"] == "Cube"
    assert result["materials"] == ["Gold"]
