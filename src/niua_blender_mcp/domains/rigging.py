"""Rigging domain manifest: armatures + skinning.

An armature is the skeleton; its bones live in ``armature.data.edit_bones`` and are only
editable while the armature object is in EDIT mode (the kernel context resolver guarantees
this via ``ctx.ensure(mode="EDIT")``). ``rig.add_armature`` creates the skeleton object,
``rig.add_bone`` / ``rig.set_bone_transform`` author edit bones, ``rig.list_bones`` is a
read-only inspection of the skeleton, and ``rig.parent_with_auto_weights`` binds a mesh to
the armature with automatic weights (object-mode ``parent_set`` type=ARMATURE_AUTO).
"""

from __future__ import annotations

from ..kernel import Enum, Str, ToolSpec, Vec3

SPECS = [
    ToolSpec(
        name="rig.add_armature",
        category="rigging",
        summary="Create a new armature (skeleton) object",
        command="rig.add_armature",
        params={
            "name": Str(summary="Name for the new armature object"),
            "location": Vec3(summary="World location of the armature [x, y, z]"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="rig.add_bone",
        category="rigging",
        summary="Add an edit bone to an armature (head/tail in armature-local space)",
        command="rig.add_bone",
        params={
            "armature": Str(required=True, summary="Armature object to add the bone to"),
            "name": Str(required=True, summary="Name for the new bone"),
            "head": Vec3(summary="Bone head position [x, y, z] (defaults to origin)"),
            "tail": Vec3(summary="Bone tail position [x, y, z] (defaults to +Z unit)"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="rig.set_bone_transform",
        category="rigging",
        summary="Set an existing bone's head and/or tail position",
        command="rig.set_bone_transform",
        params={
            "armature": Str(required=True, summary="Armature object owning the bone"),
            "bone": Str(required=True, summary="Name of the bone to move"),
            "head": Vec3(summary="New bone head position [x, y, z]"),
            "tail": Vec3(summary="New bone tail position [x, y, z]"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="rig.parent_with_auto_weights",
        category="rigging",
        summary="Parent a mesh to an armature with automatic skinning weights",
        command="rig.parent_with_auto_weights",
        params={
            "mesh": Str(required=True, summary="Mesh object to skin"),
            "armature": Str(required=True, summary="Armature object to bind the mesh to"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="rig.list_bones",
        category="rigging",
        summary="List an armature's bones with head/tail positions (read-only)",
        command="rig.list_bones",
        params={
            "armature": Str(required=True, summary="Armature object to inspect"),
        },
    ),
    ToolSpec(
        name="rig.report",
        category="rigging",
        summary="Report rest bones, pose bones, constraints, and child meshes",
        command="rig.report",
        params={
            "armature": Str(required=True, summary="Armature object to inspect"),
        },
    ),
    ToolSpec(
        name="rig.pose_report",
        category="rigging",
        summary="Report pose bone transforms and constraints",
        command="rig.pose_report",
        params={
            "armature": Str(required=True, summary="Armature object to inspect"),
            "bone": Str(summary="Optional pose bone name to inspect"),
        },
    ),
    ToolSpec(
        name="rig.set_pose_bone",
        category="rigging",
        summary="Set a pose bone's location, Euler rotation, and/or scale",
        command="rig.set_pose_bone",
        params={
            "armature": Str(required=True, summary="Armature object owning the pose bone"),
            "bone": Str(required=True, summary="Pose bone to edit"),
            "location": Vec3(summary="Pose bone location [x, y, z]"),
            "rotation": Vec3(summary="Euler rotation in radians [x, y, z]"),
            "scale": Vec3(summary="Pose bone scale [x, y, z]"),
            "rotation_mode": Enum(
                ["XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"],
                summary="Euler rotation mode; defaults to XYZ when rotation is provided",
            ),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="rig.clear_pose",
        category="rigging",
        summary="Clear all pose bone transforms back to rest values",
        command="rig.clear_pose",
        params={
            "armature": Str(required=True, summary="Armature object whose pose to clear"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
