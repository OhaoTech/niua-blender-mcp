"""Generate the committed Blender capability manifest. Run INSIDE Blender:

    blender --background --python scripts/gen_manifest.py

Walks bpy.ops via RNA and writes src/niua_blender_mcp/manifest/blender_5_1.json.
The server reads that JSON offline (it never imports this script or bpy).
"""

from __future__ import annotations

import json
import os

import bpy  # available only inside Blender

SKIP = {"wm", "screen", "file", "ui", "console", "preferences", "niua"}

# Curated category -> craft domain + tier-2 allowlist. Extend as coverage grows.
DOMAINS = {
    "modeling": {
        "categories": ["mesh", "object", "transform"],
        "allowlist": [
            "mesh.subdivide",
            "mesh.bevel",
            "mesh.extrude_region_move",
            "mesh.inset",
            "mesh.loopcut_slide",
            "mesh.merge",
            "mesh.tris_convert_to_quads",
            "mesh.quads_convert_to_tris",
            "mesh.normals_make_consistent",
            "mesh.remove_doubles",
        ],
    },
    "uv": {
        "categories": ["uv"],
        "allowlist": ["uv.unwrap", "uv.smart_project", "uv.pack_islands", "uv.seams_from_islands"],
    },
    "shading": {
        "categories": ["node", "material"],
        "allowlist": ["material.new"],
    },
    "modifiers": {
        "categories": ["object"],
        "allowlist": ["object.modifier_add", "object.modifier_apply", "object.shade_smooth", "object.shade_flat"],
    },
}


def _prop(p):
    entry = {"type": getattr(p, "type", "")}
    if entry["type"] == "ENUM":
        entry["enum"] = [e.identifier for e in getattr(p, "enum_items", [])]
        default = getattr(p, "default", None)
        if default is not None:
            entry["default"] = default
        return entry
    default = getattr(p, "default", None)
    if default is not None:
        entry["default"] = default
    hard_min, hard_max = getattr(p, "hard_min", None), getattr(p, "hard_max", None)
    if hard_min is not None:
        entry["min"] = hard_min
    if hard_max is not None:
        entry["max"] = hard_max
    entry["array_length"] = int(getattr(p, "array_length", 0) or 0)
    if getattr(p, "is_required", False):
        entry["required"] = True
    return entry


def _operators():
    ops = bpy.ops
    out = {}
    for cat in dir(ops):
        if cat.startswith("_") or cat in SKIP:
            continue
        try:
            module = getattr(ops, cat)
        except Exception:
            continue
        for name in dir(module):
            if name.startswith("_"):
                continue
            try:
                rna = getattr(module, name).get_rna_type()
            except Exception:
                continue
            desc = (getattr(rna, "description", "") or "").strip()
            if not desc:
                continue
            props = {}
            for p in getattr(rna, "properties", []):
                ident = getattr(p, "identifier", "")
                if ident in ("", "rna_type"):
                    continue
                props[ident] = _prop(p)
            out[f"{cat}.{name}"] = {
                "category": cat,
                "label": getattr(rna, "bl_label", "") or getattr(rna, "name", "") or "",
                "description": desc,
                "properties": props,
            }
    return out


def main():
    manifest = {
        "blender_version": bpy.app.version_string,
        "generated_by": "scripts/gen_manifest.py",
        "operators": _operators(),
        "domains": DOMAINS,
    }
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(here, "..", "src", "niua_blender_mcp", "manifest")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "blender_5_1.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=True)
    print(f"wrote {out_path}: {len(manifest['operators'])} operators")


if __name__ == "__main__":
    main()
