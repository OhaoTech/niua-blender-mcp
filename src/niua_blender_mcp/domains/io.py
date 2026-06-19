"""IO domain manifest: the niua -> Blender -> Godot asset seam.

Fully decoupled from niua: niua's generated assets are ordinary files consumed
through ``io.import``; Blender's output is an ordinary file consumed by niua-godot.
This domain knows nothing about either -- it just moves files in and out.

- ``io.import`` (mutates): import any supported file, format inferred from the
  extension by default; returns the names of the objects the import created
  (computed by diffing the scene before/after).
- ``io.export_gltf`` (read-only): Godot-ready glTF export with the knobs that
  matter for game pipelines (selection, GLB vs separate, apply modifiers, +Y up).
- ``io.export`` (read-only): generic export that routes to the right exporter.
- ``io.prepare_godot`` (mutates): apply transforms on one object then export it to
  GLB -- a convenience for "make this game-ready and hand it to Godot".

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

#: glTF container variants accepted by export_scene.gltf's ``export_format``.
GLTF_FORMATS = ["GLB", "GLTF_SEPARATE"]

#: Generic-export targets routed by io.export.
EXPORT_FORMATS = ["GLB", "FBX", "OBJ"]

SPECS = [
    ToolSpec(
        name="io.import",
        category="io",
        summary="Import a mesh/scene file; format inferred from the extension by default",
        command="io.import",
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
        name="io.export_gltf",
        category="io",
        summary="Export Godot-ready glTF (GLB or separate); optionally just a selection",
        command="io.export_gltf",
        params={
            "path": Str(required=True, summary="Output path (.glb or .gltf)"),
            "objects": Str(
                summary="Comma-separated object names to export; default = whole scene",
            ),
            "format": Enum(
                GLTF_FORMATS,
                default="GLB",
                summary="GLB (single binary) or GLTF_SEPARATE (.gltf + .bin + textures)",
            ),
            "apply_modifiers": Bool(default=True, summary="Apply modifiers on export"),
            "y_up": Bool(default=True, summary="+Y up axis (Godot/glTF convention)"),
        },
    ),
    ToolSpec(
        name="io.export",
        category="io",
        summary="Generic export: route to the right exporter for the chosen format",
        command="io.export",
        params={
            "path": Str(required=True, summary="Output path"),
            "format": Enum(
                EXPORT_FORMATS,
                default="GLB",
                summary="Export format; routes to glTF/FBX/OBJ",
            ),
            "objects": Str(
                summary="Comma-separated object names to export; default = whole scene",
            ),
        },
    ),
    ToolSpec(
        name="io.prepare_godot",
        category="io",
        summary="Apply transforms on an object, then export just it to Godot-ready GLB",
        command="io.prepare_godot",
        params={
            "object": Str(required=True, summary="Object to prepare and export"),
            "path": Str(required=True, summary="Output GLB path"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
