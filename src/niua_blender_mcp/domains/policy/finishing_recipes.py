"""Finishing recipe specs (server side): the typed surface for the policy recipes.

Mirrors ``niua_mcp_bridge.domains.policy.finishing_recipes`` on the add-on. See that
module for why these tools are policy rather than interface, and ``..policy`` for why
they live in a package that the wheel excludes.

``tests/test_parity.py`` keeps this file and its add-on twin naming the same four tools.
"""

from __future__ import annotations

from ...kernel import Bool, Enum, Float, Int, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="object.lod_create",
        category="object",
        summary="Create a decimated LOD duplicate using a generic Asset_LOD# naming convention",
        command="object.lod_create",
        params={
            "object": Str(required=True, summary="Source mesh object"),
            "name": Str(default="", summary="Optional LOD object name; default is <object>_LOD<level>"),
            "level": Int(default=1, minimum=1, maximum=8, summary="LOD level number"),
            "ratio": Float(default=0.5, minimum=0.01, maximum=1.0, summary="Decimate ratio for the LOD mesh"),
            "apply": Bool(default=False, summary="Apply the decimate modifier immediately"),
        },
        mutates=True,
        feedback="viewport",
    ),

    ToolSpec(
        name="object.collision_proxy_create",
        category="object",
        summary="Create a simple collision proxy around an object's bounds using a generic Asset_COL naming convention",
        command="object.collision_proxy_create",
        params={
            "object": Str(required=True, summary="Source object to bound"),
            "name": Str(default="", summary="Optional proxy name; default is <object>_COL"),
            "shape": Enum(["BOX"], default="BOX", summary="Proxy shape"),
            "margin": Float(default=0.0, minimum=0.0, summary="Extra size added around the source bounds"),
        },
        mutates=True,
        feedback="viewport",
    ),

    ToolSpec(
        name="object.collision_hulls_create",
        category="object",
        summary="Create split box collision hulls across an object's bounds using generic Asset_COL_## names",
        command="object.collision_hulls_create",
        params={
            "object": Str(required=True, summary="Source object to bound"),
            "name_prefix": Str(default="", summary="Optional proxy prefix; default is <object>_COL"),
            "count": Int(default=2, minimum=2, maximum=16, summary="Number of hull boxes to create"),
            "axis": Enum(["LONGEST", "X", "Y", "Z"], default="LONGEST", summary="Axis used to split the bounds"),
            "margin": Float(default=0.0, minimum=0.0, summary="Extra size added around each hull"),
        },
        mutates=True,
        feedback="viewport",
    ),

    ToolSpec(
        name="object.retopo",
        category="object",
        summary="Retopologize a mesh to a face budget (voxel+decimate, or decimate-only when voxel is unsafe)",
        command="object.retopo",
        params={
            "object": Str(required=True, summary="Mesh object to retopologize"),
            "target_faces": Int(required=True, minimum=1, summary="Target quad face count"),
            "voxel_size": Float(default=0.0, minimum=0.0, summary="Voxel size for the cleanup pass; 0 = auto from bbox"),
            "adaptivity": Float(default=0.0, minimum=0.0, maximum=1.0, summary="Voxel adaptivity (0 = uniform)"),
            "mode": Str(default="auto", summary="auto | decimate — auto skips voxel on multi-island/high non-manifold meshes"),
            "preserve_sharp": Bool(default=True, summary="Reserved for API compatibility; unused now that quadriflow has been dropped"),
            "preserve_boundary": Bool(default=True, summary="Reserved for API compatibility; unused now that quadriflow has been dropped"),
        },
        mutates=True,
        feedback="viewport",
        timeout_tier="heavy",
    ),
]
