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

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError


class FakeSocket:
    def __init__(self, name: str = "", value=None) -> None:
        self.name = name
        self.identifier = name
        self.type = "VALUE"
        self.default_value = value
        self.links = []
        self.enabled = True
        self.is_linked = False
        self.node = None


class FakeLink:
    def __init__(self, output_socket: FakeSocket, input_socket: FakeSocket) -> None:
        self.from_socket = output_socket
        self.to_socket = input_socket
        self.from_node = output_socket.node
        self.to_node = input_socket.node
        output_socket.is_linked = True
        input_socket.is_linked = True


class FakeNode:
    def __init__(self, ntype: str, input_names, output_names) -> None:
        self.type = ntype
        self.name = ntype
        self.label = ""
        self.bl_idname = ntype
        self.location = [0.0, 0.0]
        self.inputs = {n: FakeSocket(n) for n in input_names}
        self.outputs = {n: FakeSocket(n) for n in output_names}
        for socket in [*self.inputs.values(), *self.outputs.values()]:
            socket.node = self
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
    if ntype == "ShaderNodeTexNoise":
        node = FakeNode("TEX_NOISE", ["Scale"], ["Fac", "Color"])
        node.bl_idname = "ShaderNodeTexNoise"
        node.inputs["Scale"].default_value = 5.0
        return node
    return FakeNode(ntype, [], [])


class FakeNodes(list):
    def new(self, ntype: str) -> FakeNode:
        node = _make_node(ntype)
        self.append(node)
        return node

    def get(self, name: str):
        return next((node for node in self if getattr(node, "name", None) == name), None)


class FakeLinks:
    def __init__(self) -> None:
        self.created = []
        self._links = []

    def new(self, input_socket, output_socket):
        self.created.append((output_socket, input_socket))
        link = FakeLink(output_socket, input_socket)
        self._links.append(link)
        return link

    def __iter__(self):
        return iter(self._links)


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
            tree.links.new(output.inputs["Surface"], principled.outputs["BSDF"])
            self.node_tree = tree


class FakeImage:
    def __init__(self, name: str) -> None:
        self.name = name
        self.filepath = ""
        self.size = [1024, 1024]
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
        self.created = []
        self.fail_load = False

    def load(self, path: str) -> FakeImage:
        import os

        if self.fail_load:
            raise RuntimeError("cannot load image")
        img = FakeImage(os.path.basename(path) or "image")
        self.loaded.append(path)
        return img

    def new(self, name: str, width: int, height: int, alpha: bool = True) -> FakeImage:
        image = FakeImage(name)
        image.size = [int(width), int(height)]
        image.alpha = bool(alpha)
        self.created.append(image)
        return image


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
    assert bpy.undo_pushes == ["mcp:shading.create_material"]


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
    assert bpy.undo_pushes == ["mcp:shading.assign_material"]


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


def test_add_image_texture_load_failure_is_precondition(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "shading.create_material", {"name": "M"}, ctx)
    bpy.images.fail_load = True

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "shading.add_image_texture",
            {"material": "M", "image_path": "/tmp/missing.png"},
            ctx,
        )

    assert exc.value.code == PRECONDITION


def test_prepare_pbr_maps_creates_material_images_and_shader_nodes(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    obj = FakeObj("Cube")
    bpy.add(obj)

    out = dispatch_on_main(
        reg,
        "shading.prepare_pbr_maps",
        {"object": "Cube", "material": "HeroMat", "prefix": "Hero", "size": 512},
        ctx,
    )

    assert out["object"] == "Cube"
    assert out["material"] == "HeroMat"
    assert out["maps"] == ["BASE_COLOR", "NORMAL", "ROUGHNESS", "AO", "CAVITY"]
    assert [image.name for image in bpy.images.created] == [
        "Hero_BASE_COLOR",
        "Hero_NORMAL",
        "Hero_ROUGHNESS",
        "Hero_AO",
        "Hero_CAVITY",
    ]
    assert [image.size for image in bpy.images.created] == [[512, 512]] * 5
    assert [image.colorspace_settings.name for image in bpy.images.created] == [
        "sRGB",
        "Non-Color",
        "Non-Color",
        "Non-Color",
        "Non-Color",
    ]
    assert obj.active_material.name == "HeroMat"
    tree = bpy.materials["HeroMat"].node_tree
    assert {node.label for node in tree.nodes if node.type == "TEX_IMAGE"} == {
        "BASE_COLOR",
        "NORMAL",
        "ROUGHNESS",
        "AO",
        "CAVITY",
    }
    principled = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    normal_map = next(n for n in tree.nodes if n.type == "NORMAL_MAP")
    assert principled.inputs["Base Color"].is_linked is True
    assert principled.inputs["Roughness"].is_linked is True
    assert normal_map.inputs["Color"].is_linked is True
    assert principled.inputs["Normal"].is_linked is True
    assert bpy.undo_pushes == ["mcp:shading.prepare_pbr_maps"]


def test_prepare_pbr_maps_is_exposed_in_router() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert "shading.prepare_pbr_maps" in names


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


# -- report ----------------------------------------------------------------------


def test_router_contains_shading_report() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert "shading.report" in names


def test_report_material_node_tree(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "shading.create_material", {"name": "M"}, ctx)
    dispatch_on_main(reg, "shading.set_principled", {"material": "M", "roughness": 0.42}, ctx)

    out = dispatch_on_main(reg, "shading.report", {"material": "M"}, ctx)

    assert out["material"] == "M"
    assert out["use_nodes"] is True
    assert {node["type"] for node in out["nodes"]} == {"BSDF_PRINCIPLED", "OUTPUT_MATERIAL"}
    principled = next(node for node in out["nodes"] if node["type"] == "BSDF_PRINCIPLED")
    assert any(socket["name"] == "Roughness" and socket["default_value"] == 0.42 for socket in principled["inputs"])
    assert out["links"] == [
        {
            "from_node": "BSDF_PRINCIPLED",
            "from_socket": "BSDF",
            "to_node": "OUTPUT_MATERIAL",
            "to_socket": "Surface",
        }
    ]


def test_report_object_material_slots(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    obj = FakeObj("Cube")
    bpy.add(obj)
    dispatch_on_main(reg, "shading.assign_material", {"object": "Cube", "material": "Gold"}, ctx)

    out = dispatch_on_main(reg, "shading.report", {"object": "Cube"}, ctx)

    assert out["object"] == "Cube"
    assert out["material"] == "Gold"
    assert out["active_material_index"] == 0
    assert out["slots"] == [{"index": 0, "material": "Gold"}]


# -- generic node editing --------------------------------------------------------


def test_router_contains_shader_node_edit_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"shading.add_node", "shading.link_nodes", "shading.set_node_input"} <= names


def test_add_node_creates_shader_node_by_bl_idname(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "shading.create_material", {"name": "M"}, ctx)

    out = dispatch_on_main(
        reg,
        "shading.add_node",
        {"material": "M", "type": "ShaderNodeTexNoise", "name": "Noise"},
        ctx,
    )

    assert out["node"]["name"] == "Noise"
    assert out["node"]["bl_idname"] == "ShaderNodeTexNoise"
    assert bpy.materials["M"].node_tree.nodes.get("Noise") is not None


def test_set_node_input_parses_json_value(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "shading.create_material", {"name": "M"}, ctx)
    dispatch_on_main(reg, "shading.add_node", {"material": "M", "type": "ShaderNodeTexNoise", "name": "Noise"}, ctx)

    out = dispatch_on_main(
        reg,
        "shading.set_node_input",
        {"material": "M", "node": "Noise", "input": "Scale", "value": "12.5"},
        ctx,
    )

    assert out["input"]["default_value"] == 12.5
    assert bpy.materials["M"].node_tree.nodes.get("Noise").inputs["Scale"].default_value == 12.5


def test_set_node_input_parses_json_vector_value(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "shading.create_material", {"name": "M"}, ctx)
    noise = dispatch_on_main(
        reg,
        "shading.add_node",
        {"material": "M", "type": "ShaderNodeTexNoise", "name": "Noise"},
        ctx,
    )
    node = bpy.materials["M"].node_tree.nodes.get(noise["node"]["name"])
    node.inputs["Scale"].default_value = (0.0, 0.0, 0.0)

    out = dispatch_on_main(
        reg,
        "shading.set_node_input",
        {"material": "M", "node": "Noise", "input": "Scale", "value": "[1, 2, 3]"},
        ctx,
    )

    assert out["input"]["default_value"] == [1.0, 2.0, 3.0]
    assert node.inputs["Scale"].default_value == (1.0, 2.0, 3.0)


def test_set_node_input_missing_node_raises_invalid_params(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "shading.create_material", {"name": "M"}, ctx)

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "shading.set_node_input",
            {"material": "M", "node": "Missing", "input": "Scale", "value": "1"},
            ctx,
        )

    assert exc.value.code == INVALID_PARAMS


def test_link_nodes_resolves_node_and_socket_names(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "shading.create_material", {"name": "M"}, ctx)
    dispatch_on_main(reg, "shading.add_node", {"material": "M", "type": "ShaderNodeTexNoise", "name": "Noise"}, ctx)

    out = dispatch_on_main(
        reg,
        "shading.link_nodes",
        {
            "material": "M",
            "from_node": "Noise",
            "from_socket": "Fac",
            "to_node": "BSDF_PRINCIPLED",
            "to_socket": "Roughness",
        },
        ctx,
    )

    assert out["link"] == {
        "from_node": "Noise",
        "from_socket": "Fac",
        "to_node": "BSDF_PRINCIPLED",
        "to_socket": "Roughness",
    }


def test_link_nodes_missing_socket_raises_invalid_params(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    dispatch_on_main(reg, "shading.create_material", {"name": "M"}, ctx)

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "shading.link_nodes",
            {
                "material": "M",
                "from_node": "BSDF_PRINCIPLED",
                "from_socket": "Missing",
                "to_node": "OUTPUT_MATERIAL",
                "to_socket": "Surface",
            },
            ctx,
        )
    assert exc.value.code == INVALID_PARAMS
