"""Tier-2 code generation: committed manifest -> typed ToolSpecs.

Each allowlisted operator becomes a named craft tool (e.g. modeling.subdivide).
Generated specs carry the real operator idname in `command`; the server packs the
validated typed args and routes them through capabilities.invoke (see server.py).
The router drops any generated name that collides with a curated tool.
"""

from __future__ import annotations

from ..kernel import Bool, Enum, Float, Int, Str, ToolSpec
from ..manifest import Manifest, load_manifest

_UNBOUNDED = 1e30  # treat |hard_min/max| >= this as "no bound"


def _bound(v):
    if v is None:
        return None
    try:
        return None if abs(float(v)) >= _UNBOUNDED else v
    except (TypeError, ValueError):
        return None


def _param(pinfo: dict):
    ptype = pinfo.get("type", "")
    if ptype == "ENUM":
        choices = pinfo.get("enum", [])
        if not choices:
            return None
        return Enum(choices, default=pinfo.get("default"))
    if ptype == "INT":
        return Int(default=pinfo.get("default"), minimum=_bound(pinfo.get("min")), maximum=_bound(pinfo.get("max")))
    if ptype == "FLOAT":
        return Float(default=pinfo.get("default"), minimum=_bound(pinfo.get("min")), maximum=_bound(pinfo.get("max")))
    if ptype == "BOOLEAN":
        return Bool(default=pinfo.get("default"))
    if ptype == "STRING":
        return Str(default=pinfo.get("default"))
    return None  # POINTER / COLLECTION / unknown -> skip


def generate_specs(manifest: Manifest | None = None) -> list[ToolSpec]:
    m = manifest or load_manifest()
    specs: list[ToolSpec] = []
    for domain in m.domains.values():
        for idname in domain.allowlist:
            op = m.operators.get(idname)
            if op is None:
                continue
            op_name = idname.split(".", 1)[1]
            params = {}
            for pid, pinfo in op.properties.items():
                if int(pinfo.get("array_length", 0) or 0) > 1:
                    continue  # arrays not supported yet
                param = _param(pinfo)
                if param is not None:
                    params[pid] = param
            specs.append(
                ToolSpec(
                    name=f"{domain.name}.{op_name}",
                    category=domain.name,
                    summary=(op.description.split(".")[0] or op.label or op_name)[:160],
                    command=idname,  # real operator idname; server routes via capabilities.invoke
                    params=params,
                    mutates=True,
                    feedback="viewport",
                    tier="generated",
                )
            )
    return specs
