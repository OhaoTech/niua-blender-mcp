"""Server-side tool manifest: the ToolSpecs exposed to the agent.

Command names must mirror the add-on's command registry (a parity test guards this).
The server validates arguments against these specs before dispatching over the bridge.
"""

from __future__ import annotations

from ..kernel import Enum, Router, Str, ToolSpec, Vec3

PRIMITIVE_TYPES = ["CUBE", "SPHERE", "PLANE", "CYLINDER", "CONE", "EMPTY"]

SCENE = [
    ToolSpec(
        name="scene.info",
        category="scene",
        summary="Summarize the current scene (objects, materials)",
        command="scene.info",
    ),
    ToolSpec(
        name="scene.create_object",
        category="scene",
        summary="Create a primitive object in the scene",
        command="scene.create_object",
        params={
            "type": Enum(PRIMITIVE_TYPES, required=True, summary="Primitive type"),
            "name": Str(summary="Optional object name"),
            "location": Vec3(summary="World location [x, y, z]"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="scene.set_transform",
        category="scene",
        summary="Set an object's location/rotation/scale",
        command="scene.set_transform",
        params={
            "object": Str(required=True, summary="Object name"),
            "location": Vec3(summary="World location [x, y, z]"),
            "rotation": Vec3(summary="Euler rotation in radians [x, y, z]"),
            "scale": Vec3(summary="Scale [x, y, z]"),
        },
        mutates=True,
        feedback="viewport",
    ),
]

INTROSPECTION = [
    ToolSpec(
        name="rna.describe",
        category="introspection",
        summary="Describe a Blender operator or type via RNA (e.g. 'op:mesh.bevel', 'type:Object')",
        command="rna.describe",
        params={"path": Str(required=True, summary="'op:<cat>.<name>' or 'type:<TypeName>'")},
    ),
]

FEEDBACK = [
    ToolSpec(
        name="feedback.capture",
        category="feedback",
        summary="Render the current view to a PNG the agent can see",
        command="feedback.capture",
        params={"mode": Enum(["viewport"], default="viewport", summary="Capture mode")},
    ),
]

SYSTEM = [
    ToolSpec(
        name="system.execute_python",
        category="system",
        summary="Run Python inside Blender (disabled unless explicitly enabled)",
        command="system.execute_python",
        params={"code": Str(required=True, summary="Python source to exec")},
        mutates=True,
    ),
]


def build_router() -> Router:
    router = Router()
    router.add(SCENE)
    router.add(INTROSPECTION)
    router.add(FEEDBACK)
    router.add(SYSTEM)
    return router
