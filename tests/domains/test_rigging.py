"""Rigging domain unit tests (fake-bpy).

Extends the FakeBpy pattern from tests/test_dispatch.py / test_mesh.py with armature
data: an ``edit_bones`` collection (``new``/``get``, only authored while in EDIT mode in
real Blender, but always present on the fake) and a read-only ``bones`` list for
``rig.list_bones``. Adds the operators the handlers call (``object.armature_add``,
``object.mode_set``, ``object.parent_set``) as callable ops carrying ``poll``. ``bpy`` is
injected into sys.modules so the lazily-imported context resolver runs against the same
fake.
"""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError


class FakeEditBone:
    def __init__(self, name: str) -> None:
        self.name = name
        self.head = [0.0, 0.0, 0.0]
        self.tail = [0.0, 0.0, 1.0]
        self.parent = None


class FakeEditBones:
    """Mimics armature.data.edit_bones: new(name) + get(name), name uniquification."""

    def __init__(self) -> None:
        self._bones: dict[str, FakeEditBone] = {}

    def new(self, name: str) -> FakeEditBone:
        unique = name
        i = 1
        while unique in self._bones:
            unique = f"{name}.{i:03d}"
            i += 1
        bone = FakeEditBone(unique)
        self._bones[unique] = bone
        return bone

    def get(self, name: str):
        return self._bones.get(name)

    def __iter__(self):
        return iter(self._bones.values())

    def __len__(self) -> int:
        return len(self._bones)


class FakeArmatureData:
    def __init__(self) -> None:
        self.edit_bones = FakeEditBones()

    @property
    def bones(self):
        # Read-only object-mode view mirrors whatever edit_bones holds.
        return list(self.edit_bones)


class FakePoseConstraint:
    def __init__(self, name: str, type: str = "COPY_LOCATION") -> None:
        self.name = name
        self.type = type
        self.influence = 1.0
        self.target = None
        self.subtarget = ""
        self.mute = False


class FakePoseConstraints(list):
    def get(self, name: str):
        return next((constraint for constraint in self if constraint.name == name), None)

    def new(self, type: str):
        if type == "NOPE":
            raise TypeError("unsupported constraint")
        constraint = FakePoseConstraint(type, type)
        self.append(constraint)
        return constraint

    def remove(self, constraint) -> None:
        super().remove(constraint)


class FakePoseBone:
    def __init__(self, name: str) -> None:
        self.name = name
        self.location = [0.0, 0.0, 0.0]
        self.rotation_mode = "XYZ"
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.constraints = FakePoseConstraints()


class FakePoseBones:
    def __init__(self, edit_bones: FakeEditBones) -> None:
        self._edit_bones = edit_bones
        self._pose_bones: dict[str, FakePoseBone] = {}

    def get(self, name: str):
        if self._edit_bones.get(name) is None:
            return None
        if name not in self._pose_bones:
            self._pose_bones[name] = FakePoseBone(name)
        return self._pose_bones[name]

    def __iter__(self):
        for edit_bone in self._edit_bones:
            yield self.get(edit_bone.name)


class FakePose:
    def __init__(self, edit_bones: FakeEditBones) -> None:
        self.bones = FakePoseBones(edit_bones)


class FakeVertexAssignment:
    def __init__(self, group: int, weight: float) -> None:
        self.group = group
        self.weight = weight


class FakeVertex:
    def __init__(self, index: int) -> None:
        self.index = index
        self.groups: list[FakeVertexAssignment] = []


class FakeMesh:
    def __init__(self, vertex_count: int = 4) -> None:
        self.vertices = [FakeVertex(index) for index in range(vertex_count)]


class FakeVertexGroup:
    def __init__(self, obj, name: str, index: int) -> None:
        self._obj = obj
        self.name = name
        self.index = index
        self.lock_weight = False
        self.add_calls: list = []

    def add(self, vertices, weight: float, mode: str) -> None:
        self.add_calls.append((list(vertices), weight, mode))
        for vertex_index in vertices:
            vertex = self._obj.data.vertices[vertex_index]
            assignment = next((item for item in vertex.groups if item.group == self.index), None)
            if assignment is None:
                assignment = FakeVertexAssignment(self.index, 0.0)
                vertex.groups.append(assignment)
            if mode == "ADD":
                assignment.weight += weight
            elif mode == "SUBTRACT":
                assignment.weight -= weight
            else:
                assignment.weight = weight


class FakeVertexGroups(list):
    def __init__(self, obj) -> None:
        super().__init__()
        self._obj = obj

    def new(self, name: str):
        group = FakeVertexGroup(self._obj, name, len(self))
        self.append(group)
        return group

    def get(self, name: str):
        return next((group for group in self if group.name == name), None)


class FakeObj:
    def __init__(self, name: str, type: str = "ARMATURE", data: object | None = None) -> None:
        self.name = name
        self.type = type
        if data is not None:
            self.data = data
        elif type == "ARMATURE":
            self.data = FakeArmatureData()
        else:
            self.data = FakeMesh()
        self.pose = FakePose(self.data.edit_bones) if type == "ARMATURE" else None
        self.vertex_groups = FakeVertexGroups(self) if type == "MESH" else []
        self._selected = False
        self.mode = "OBJECT"
        self.parent = None

    def select_set(self, value: bool) -> None:
        self._selected = bool(value)

    def select_get(self) -> bool:
        return self._selected


class _Op:
    """A callable operator that records calls and polls True by default."""

    def __init__(self, log: list, name: str, poll_ok: bool = True, on_call=None) -> None:
        self._log = log
        self._name = name
        self._poll_ok = poll_ok
        self._on_call = on_call

    def poll(self) -> bool:
        return self._poll_ok

    def __call__(self, **kwargs):
        self._log.append((self._name, kwargs))
        if self._on_call is not None:
            self._on_call(**kwargs)


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.objects_by_name: dict[str, FakeObj] = {}
        self.scene = types.SimpleNamespace(objects=[], name="Scene")
        self._active_obj = None
        self.op_calls: list = []
        self.undo_pushes: list[str] = []
        self.mode_calls: list[str] = []
        self._armature_counter = 0

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

        def _armature_add(**kwargs):
            bpy._armature_counter += 1
            name = "Armature" if bpy._armature_counter == 1 else f"Armature.{bpy._armature_counter:03d}"
            bpy.add(FakeObj(name, type="ARMATURE"))

        class _ObjectOps:
            armature_add = _Op(log, "object.armature_add", on_call=_armature_add)
            parent_set = _Op(log, "object.parent_set")

            def mode_set(self_inner, mode="OBJECT", **kw):
                bpy.mode_calls.append(mode)
                if bpy._active_obj is not None:
                    bpy._active_obj.mode = mode

        class _EdOps:
            def undo_push(self_inner, message: str = "", **kw):
                bpy.undo_pushes.append(message)

            def undo(self_inner, **kw):
                pass

        self.ops = types.SimpleNamespace(object=_ObjectOps(), ed=_EdOps())

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


# -- add_armature ------------------------------------------------------------------


def test_router_contains_rig_pose_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"rig.report", "rig.pose_report", "rig.set_pose_bone", "rig.clear_pose"} <= names


def test_add_armature_creates_and_renames(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    result = dispatch_on_main(reg, "rig.add_armature", {"name": "Rig", "location": [1, 2, 3]}, ctx)
    assert result["armature"] == "Rig"
    assert result["location"] == [1.0, 2.0, 3.0]
    assert "object.armature_add" in _names(bpy.op_calls)
    assert bpy.undo_pushes == ["mcp:rig.add_armature"]
    # The created object was renamed to "Rig" (dict still keyed by its add-time name).
    assert any(o.name == "Rig" for o in bpy.scene.objects)


def test_add_armature_defaults_location_and_name(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    result = dispatch_on_main(reg, "rig.add_armature", {}, ctx)
    assert result["location"] == [0.0, 0.0, 0.0]
    assert result["armature"] == "Armature"  # blender default name kept


# -- add_bone ----------------------------------------------------------------------


def test_add_bone_creates_edit_bone_in_edit_mode(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Rig"))
    reg = build_default_registry()
    result = dispatch_on_main(
        reg,
        "rig.add_bone",
        {"armature": "Rig", "name": "Spine", "head": [0, 0, 0], "tail": [0, 0, 2]},
        ctx,
    )
    assert result["bone"] == "Spine"
    assert result["head"] == [0.0, 0.0, 0.0]
    assert result["tail"] == [0.0, 0.0, 2.0]
    # entered EDIT, restored to OBJECT
    assert bpy.mode_calls == ["EDIT", "OBJECT"]
    assert bpy.undo_pushes == ["mcp:rig.add_bone"]
    bone = bpy.objects_by_name["Rig"].data.edit_bones.get("Spine")
    assert bone is not None
    assert bone.tail == [0.0, 0.0, 2.0]


def test_add_bone_defaults_head_tail(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Rig"))
    reg = build_default_registry()
    result = dispatch_on_main(reg, "rig.add_bone", {"armature": "Rig", "name": "B"}, ctx)
    assert result["head"] == [0.0, 0.0, 0.0]
    assert result["tail"] == [0.0, 0.0, 1.0]


def test_add_bone_requires_name(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Rig"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "rig.add_bone", {"armature": "Rig"}, ctx)
    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


def test_add_bone_on_non_armature_raises_precondition(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", type="MESH"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "rig.add_bone", {"armature": "Cube", "name": "B"}, ctx)
    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


def test_add_bone_missing_armature_raises_not_found(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "rig.add_bone", {"armature": "Ghost", "name": "B"}, ctx)
    assert exc.value.code == NOT_FOUND


# -- set_bone_transform ------------------------------------------------------------


def test_set_bone_transform_updates_head_and_tail(env) -> None:
    ctx, bpy = env
    rig = FakeObj("Rig")
    bone = rig.data.edit_bones.new("Spine")
    bpy.add(rig)
    reg = build_default_registry()
    result = dispatch_on_main(
        reg,
        "rig.set_bone_transform",
        {"armature": "Rig", "bone": "Spine", "head": [1, 1, 1], "tail": [1, 1, 5]},
        ctx,
    )
    assert result["head"] == [1.0, 1.0, 1.0]
    assert result["tail"] == [1.0, 1.0, 5.0]
    assert bone.head == [1.0, 1.0, 1.0]
    assert bone.tail == [1.0, 1.0, 5.0]
    assert bpy.undo_pushes == ["mcp:rig.set_bone_transform"]


def test_set_bone_transform_head_only(env) -> None:
    ctx, bpy = env
    rig = FakeObj("Rig")
    bone = rig.data.edit_bones.new("Spine")
    bone.tail = [0.0, 0.0, 9.0]
    bpy.add(rig)
    reg = build_default_registry()
    result = dispatch_on_main(
        reg, "rig.set_bone_transform", {"armature": "Rig", "bone": "Spine", "head": [2, 0, 0]}, ctx
    )
    assert result["head"] == [2.0, 0.0, 0.0]
    assert "tail" not in result  # untouched
    assert bone.tail == [0.0, 0.0, 9.0]


def test_set_bone_transform_missing_bone_raises_not_found(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Rig"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "rig.set_bone_transform", {"armature": "Rig", "bone": "Nope"}, ctx)
    assert exc.value.code == NOT_FOUND


# -- parent_with_auto_weights ------------------------------------------------------


def test_parent_with_auto_weights_runs_parent_set(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Body", type="MESH"))
    bpy.add(FakeObj("Rig"))
    reg = build_default_registry()
    result = dispatch_on_main(
        reg, "rig.parent_with_auto_weights", {"mesh": "Body", "armature": "Rig"}, ctx
    )
    assert result == {"mesh": "Body", "armature": "Rig", "parented": True}
    _, kwargs = next(c for c in bpy.op_calls if c[0] == "object.parent_set")
    assert kwargs == {"type": "ARMATURE_AUTO"}
    assert bpy.undo_pushes == ["mcp:rig.parent_with_auto_weights"]


def test_parent_with_auto_weights_wrong_mesh_type_raises_precondition(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("NotMesh", type="EMPTY"))
    bpy.add(FakeObj("Rig"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg, "rig.parent_with_auto_weights", {"mesh": "NotMesh", "armature": "Rig"}, ctx
        )
    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


def test_parent_with_auto_weights_failing_poll_is_clean(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Body", type="MESH"))
    bpy.add(FakeObj("Rig"))
    bpy.ops.object.parent_set._poll_ok = False
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "rig.parent_with_auto_weights", {"mesh": "Body", "armature": "Rig"}, ctx)
    assert exc.value.code == PRECONDITION
    assert bpy.undo_pushes == []


# -- list_bones (read-only) --------------------------------------------------------


def test_list_bones_reports_skeleton(env) -> None:
    ctx, bpy = env
    rig = FakeObj("Rig")
    b1 = rig.data.edit_bones.new("Spine")
    b1.head = [0.0, 0.0, 0.0]
    b1.tail = [0.0, 0.0, 2.0]
    b2 = rig.data.edit_bones.new("Head")
    b2.head = [0.0, 0.0, 2.0]
    b2.tail = [0.0, 0.0, 3.0]
    b2.parent = b1
    bpy.add(rig)
    reg = build_default_registry()
    rep = dispatch_on_main(reg, "rig.list_bones", {"armature": "Rig"}, ctx)
    assert rep["bone_count"] == 2
    names = {b["name"] for b in rep["bones"]}
    assert names == {"Spine", "Head"}
    head_entry = next(b for b in rep["bones"] if b["name"] == "Head")
    assert head_entry["parent"] == "Spine"
    assert head_entry["head"] == [0.0, 0.0, 2.0]
    assert head_entry["tail"] == [0.0, 0.0, 3.0]


def test_list_bones_is_read_only_no_undo(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Rig"))
    reg = build_default_registry()
    dispatch_on_main(reg, "rig.list_bones", {"armature": "Rig"}, ctx)
    assert bpy.undo_pushes == []


def test_list_bones_on_non_armature_raises_precondition(env) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", type="MESH"))
    reg = build_default_registry()
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "rig.list_bones", {"armature": "Cube"}, ctx)
    assert exc.value.code == PRECONDITION


# -- pose reports / transforms -----------------------------------------------------


def test_pose_report_reports_all_and_named_bone(env) -> None:
    ctx, bpy = env
    rig = FakeObj("Rig")
    rig.data.edit_bones.new("Root")
    rig.data.edit_bones.new("Tip")
    tip = rig.pose.bones.get("Tip")
    tip.location = [1.0, 2.0, 3.0]
    tip.rotation_mode = "XYZ"
    tip.rotation_euler = [0.1, 0.2, 0.3]
    tip.scale = [1.0, 1.5, 2.0]
    tip.constraints.append(FakePoseConstraint("CopyLoc"))
    bpy.add(rig)
    reg = build_default_registry()

    all_bones = dispatch_on_main(reg, "rig.pose_report", {"armature": "Rig"}, ctx)
    one_bone = dispatch_on_main(reg, "rig.pose_report", {"armature": "Rig", "bone": "Tip"}, ctx)

    assert all_bones["pose_bone_count"] == 2
    assert [bone["name"] for bone in one_bone["pose_bones"]] == ["Tip"]
    assert one_bone["pose_bones"][0]["location"] == [1.0, 2.0, 3.0]
    assert one_bone["pose_bones"][0]["rotation_euler"] == [0.1, 0.2, 0.3]
    assert one_bone["pose_bones"][0]["scale"] == [1.0, 1.5, 2.0]
    assert one_bone["pose_bones"][0]["constraints"][0]["name"] == "CopyLoc"
    assert bpy.undo_pushes == []


def test_set_pose_bone_updates_transform_in_pose_mode(env) -> None:
    ctx, bpy = env
    rig = FakeObj("Rig")
    rig.data.edit_bones.new("Tip")
    bpy.add(rig)
    reg = build_default_registry()

    result = dispatch_on_main(
        reg,
        "rig.set_pose_bone",
        {
            "armature": "Rig",
            "bone": "Tip",
            "location": [1, 2, 3],
            "rotation": [0.1, 0.2, 0.3],
            "scale": [1, 1.5, 2],
            "rotation_mode": "XYZ",
        },
        ctx,
    )

    pose_bone = rig.pose.bones.get("Tip")
    assert pose_bone.location == [1.0, 2.0, 3.0]
    assert pose_bone.rotation_euler == [0.1, 0.2, 0.3]
    assert pose_bone.scale == [1.0, 1.5, 2.0]
    assert result["pose_bone"]["name"] == "Tip"
    assert result["pose_bone"]["location"] == [1.0, 2.0, 3.0]
    assert bpy.mode_calls == ["POSE", "OBJECT"]
    assert bpy.undo_pushes == ["mcp:rig.set_pose_bone"]


def test_clear_pose_resets_all_pose_bones(env) -> None:
    ctx, bpy = env
    rig = FakeObj("Rig")
    rig.data.edit_bones.new("Root")
    rig.data.edit_bones.new("Tip")
    for pose_bone in rig.pose.bones:
        pose_bone.location = [1.0, 2.0, 3.0]
        pose_bone.rotation_euler = [0.1, 0.2, 0.3]
        pose_bone.scale = [2.0, 2.0, 2.0]
    bpy.add(rig)
    reg = build_default_registry()

    result = dispatch_on_main(reg, "rig.clear_pose", {"armature": "Rig"}, ctx)

    assert result["pose_bone_count"] == 2
    for pose_bone in rig.pose.bones:
        assert pose_bone.location == [0.0, 0.0, 0.0]
        assert pose_bone.rotation_euler == [0.0, 0.0, 0.0]
        assert pose_bone.scale == [1.0, 1.0, 1.0]
    assert bpy.mode_calls == ["POSE", "OBJECT"]
    assert bpy.undo_pushes == ["mcp:rig.clear_pose"]


def test_rig_report_includes_rest_pose_and_child_meshes(env) -> None:
    ctx, bpy = env
    rig = FakeObj("Rig")
    root = rig.data.edit_bones.new("Root")
    tip = rig.data.edit_bones.new("Tip")
    tip.parent = root
    rig.pose.bones.get("Tip").constraints.append(FakePoseConstraint("CopyLoc"))
    body = FakeObj("Body", type="MESH")
    body.parent = rig
    bpy.add(rig)
    bpy.add(body)
    reg = build_default_registry()

    report = dispatch_on_main(reg, "rig.report", {"armature": "Rig"}, ctx)

    assert report["bone_count"] == 2
    assert report["pose_bone_count"] == 2
    assert report["child_meshes"] == ["Body"]
    tip_pose = next(bone for bone in report["pose_bones"] if bone["name"] == "Tip")
    assert tip_pose["constraints"][0]["name"] == "CopyLoc"


# -- pose constraints --------------------------------------------------------------


def test_router_contains_rig_constraint_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"rig.constraints", "rig.constraint_add", "rig.constraint_remove"} <= names


def test_constraints_reports_all_and_named_bone(env) -> None:
    ctx, bpy = env
    rig = FakeObj("Rig")
    rig.data.edit_bones.new("Root")
    rig.data.edit_bones.new("Tip")
    rig.pose.bones.get("Root").constraints.append(FakePoseConstraint("CopyRoot", "COPY_LOCATION"))
    rig.pose.bones.get("Tip").constraints.append(FakePoseConstraint("CopyTip", "COPY_ROTATION"))
    bpy.add(rig)
    reg = build_default_registry()

    all_constraints = dispatch_on_main(reg, "rig.constraints", {"armature": "Rig"}, ctx)
    tip_constraints = dispatch_on_main(reg, "rig.constraints", {"armature": "Rig", "bone": "Tip"}, ctx)

    assert all_constraints["constraint_count"] == 2
    assert {constraint["bone"] for constraint in all_constraints["constraints"]} == {"Root", "Tip"}
    assert tip_constraints == {
        "armature": "Rig",
        "bone": "Tip",
        "constraint_count": 1,
        "constraints": [
            {
                "bone": "Tip",
                "name": "CopyTip",
                "type": "COPY_ROTATION",
                "influence": 1.0,
                "target": None,
                "subtarget": "",
                "mute": False,
            }
        ],
    }
    assert bpy.undo_pushes == []


def test_constraint_add_sets_name_influence_target_and_subtarget(env) -> None:
    ctx, bpy = env
    rig = FakeObj("Rig")
    rig.data.edit_bones.new("Tip")
    target = FakeObj("Target", type="EMPTY")
    bpy.add(rig)
    bpy.add(target)
    reg = build_default_registry()

    result = dispatch_on_main(
        reg,
        "rig.constraint_add",
        {
            "armature": "Rig",
            "bone": "Tip",
            "type": "COPY_LOCATION",
            "name": "CopyTarget",
            "target": "Target",
            "subtarget": "Socket",
            "influence": 0.75,
        },
        ctx,
    )

    constraint = rig.pose.bones.get("Tip").constraints.get("CopyTarget")
    assert constraint is not None
    assert constraint.type == "COPY_LOCATION"
    assert constraint.target is target
    assert constraint.subtarget == "Socket"
    assert constraint.influence == 0.75
    assert result["constraint"]["name"] == "CopyTarget"
    assert result["constraint"]["target"] == "Target"
    assert bpy.undo_pushes == ["mcp:rig.constraint_add"]


def test_constraint_remove_by_name(env) -> None:
    ctx, bpy = env
    rig = FakeObj("Rig")
    rig.data.edit_bones.new("Tip")
    rig.pose.bones.get("Tip").constraints.append(FakePoseConstraint("CopyTarget"))
    bpy.add(rig)
    reg = build_default_registry()

    result = dispatch_on_main(
        reg, "rig.constraint_remove", {"armature": "Rig", "bone": "Tip", "name": "CopyTarget"}, ctx
    )

    assert result["constraint_count"] == 0
    assert rig.pose.bones.get("Tip").constraints == []
    assert bpy.undo_pushes == ["mcp:rig.constraint_remove"]


def test_constraint_add_unsupported_type_raises_invalid_params(env) -> None:
    ctx, bpy = env
    rig = FakeObj("Rig")
    rig.data.edit_bones.new("Tip")
    bpy.add(rig)
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "rig.constraint_add", {"armature": "Rig", "bone": "Tip", "type": "NOPE"}, ctx)
    assert exc.value.code == INVALID_PARAMS
    assert bpy.undo_pushes == []


# -- vertex groups / skinning weights ---------------------------------------------


def test_router_contains_rig_vertex_group_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"rig.vertex_groups", "rig.vertex_group_create", "rig.assign_weights"} <= names


def test_vertex_groups_reports_groups_and_weights(env) -> None:
    ctx, bpy = env
    body = FakeObj("Body", type="MESH", data=FakeMesh(vertex_count=4))
    group = body.vertex_groups.new(name="Spine")
    group.add([0, 2], 0.5, "REPLACE")
    bpy.add(body)
    reg = build_default_registry()

    result = dispatch_on_main(reg, "rig.vertex_groups", {"mesh": "Body"}, ctx)

    assert result == {
        "mesh": "Body",
        "vertex_count": 4,
        "group_count": 1,
        "groups": [
            {
                "name": "Spine",
                "index": 0,
                "lock_weight": False,
                "vertices": [{"index": 0, "weight": 0.5}, {"index": 2, "weight": 0.5}],
            }
        ],
    }
    assert bpy.undo_pushes == []


def test_vertex_group_create_returns_report(env) -> None:
    ctx, bpy = env
    body = FakeObj("Body", type="MESH", data=FakeMesh(vertex_count=3))
    bpy.add(body)
    reg = build_default_registry()

    result = dispatch_on_main(reg, "rig.vertex_group_create", {"mesh": "Body", "name": "Arm"}, ctx)

    assert [group.name for group in body.vertex_groups] == ["Arm"]
    assert result["groups"][0]["name"] == "Arm"
    assert bpy.undo_pushes == ["mcp:rig.vertex_group_create"]


def test_assign_weights_parses_vertices_and_calls_group_add(env) -> None:
    ctx, bpy = env
    body = FakeObj("Body", type="MESH", data=FakeMesh(vertex_count=5))
    group = body.vertex_groups.new(name="Spine")
    bpy.add(body)
    reg = build_default_registry()

    result = dispatch_on_main(
        reg,
        "rig.assign_weights",
        {"mesh": "Body", "group": "Spine", "vertices": "1, 3,4", "weight": 0.75, "mode": "REPLACE"},
        ctx,
    )

    assert group.add_calls == [([1, 3, 4], 0.75, "REPLACE")]
    assigned = result["groups"][0]["vertices"]
    assert assigned == [{"index": 1, "weight": 0.75}, {"index": 3, "weight": 0.75}, {"index": 4, "weight": 0.75}]
    assert bpy.undo_pushes == ["mcp:rig.assign_weights"]


def test_assign_weights_invalid_vertex_index(env) -> None:
    ctx, bpy = env
    body = FakeObj("Body", type="MESH", data=FakeMesh(vertex_count=2))
    body.vertex_groups.new(name="Spine")
    bpy.add(body)
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(
            reg,
            "rig.assign_weights",
            {"mesh": "Body", "group": "Spine", "vertices": "8", "weight": 1.0},
            ctx,
        )
    assert exc.value.code == INVALID_PARAMS
    assert bpy.undo_pushes == []
