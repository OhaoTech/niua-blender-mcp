"""IO domain manifest: import/export ordinary Blender asset files.

This domain knows nothing about consumers or game engines. It moves files in and
out of Blender. Format is always data, not a product-specific tool name.

- ``io.import`` (mutates): import any supported file, format inferred from extension
  by default; returns the names of imported objects.
- ``io.export`` (read-only): generic export with format, selection, and common flags.
- ``io.prepare_asset`` (mutates): optionally apply transforms on one object, then
  export just that object.

Operator ids (verified against Blender 5.1.1):
  GLTF/GLB: import_scene.gltf / export_scene.gltf
  OBJ:      wm.obj_import      / wm.obj_export
  FBX:      import_scene.fbx   / export_scene.fbx
  STL:      wm.stl_import      / wm.stl_export
  USD:      wm.usd_import      / wm.usd_export
  PLY:      wm.ply_import      / wm.ply_export
  DAE:      wm.collada_import  / wm.collada_export
  ABC:      wm.alembic_import  / wm.alembic_export
"""

from __future__ import annotations

from ..kernel import Bool, Enum, Str, ToolSpec

#: Importable formats. AUTO infers from the file extension (see EXT_TO_FORMAT in the
#: add-on handler). The rest force a specific importer.
IMPORT_FORMATS = ["AUTO", "GLTF", "GLB", "OBJ", "FBX", "STL", "USD", "PLY", "DAE", "ABC"]

#: Generic-export targets routed by io.export.
EXPORT_FORMATS = ["AUTO", "GLB", "GLTF_SEPARATE", "FBX", "OBJ"]

SPECS = [
    ToolSpec(
        name="io.import",
        category="io",
        summary="Import a mesh/scene file; format inferred from the extension by default",
        command="io.import",
        timeout_tier="heavy",
        params={
            "path": Str(required=True, summary="Absolute path to the file to import"),
            "format": Enum(
                IMPORT_FORMATS,
                default="AUTO",
                summary="Importer to use; AUTO infers it from the file extension",
            ),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="io.export",
        category="io",
        summary="Export the scene or selected objects; format can be inferred from the path",
        command="io.export",
        timeout_tier="heavy",
        params={
            "path": Str(required=True, summary="Output path"),
            "format": Enum(
                EXPORT_FORMATS,
                default="AUTO",
                summary="AUTO infers from extension; otherwise GLB, GLTF_SEPARATE, FBX, or OBJ",
            ),
            "objects": Str(
                summary="Comma-separated object names to export; default = whole scene",
            ),
            "apply_modifiers": Bool(default=True, summary="Apply modifiers where supported"),
            "y_up": Bool(default=True, summary="+Y up axis for formats that support it"),
        },
    ),
    ToolSpec(
        name="io.prepare_asset",
        category="io",
        summary="Optionally apply transforms on one object, then export just that object",
        command="io.prepare_asset",
        timeout_tier="heavy",
        params={
            "object": Str(required=True, summary="Object to prepare"),
            "path": Str(required=True, summary="Output path"),
            "format": Enum(
                EXPORT_FORMATS,
                default="AUTO",
                summary="AUTO infers from extension; otherwise GLB, GLTF_SEPARATE, FBX, or OBJ",
            ),
            "apply_transforms": Bool(default=True, summary="Apply location/rotation/scale before export"),
            "apply_modifiers": Bool(default=True, summary="Apply modifiers where supported"),
            "y_up": Bool(default=True, summary="+Y up axis for formats that support it"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
