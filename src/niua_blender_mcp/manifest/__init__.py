"""Offline loader for the committed Blender capability manifest.

The manifest is generated inside Blender (scripts/gen_manifest.py) and committed
as JSON. The server reads it here without ever importing bpy, so it works on
machines with no Blender install. Powers capabilities.search/describe (tier 3)
and the tier-2 code generator.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache

_DEFAULT = os.path.join(os.path.dirname(__file__), "blender_5_1.json")


@dataclass(frozen=True)
class OperatorInfo:
    idname: str
    category: str
    label: str
    description: str
    properties: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DomainInfo:
    name: str
    categories: list[str]
    allowlist: list[str]


def _score(query: str, *fields: str) -> int:
    """Mirror introspection._score: exact > prefix > substring, identifying-field-first."""
    if not query:
        return 1
    q = query.lower()
    best = 0
    for weight, fld in zip((100, 60, 30), fields):
        f = (fld or "").lower()
        if not f:
            continue
        if f == q:
            best = max(best, weight + 5)
        elif f.startswith(q):
            best = max(best, weight + 3)
        elif q in f:
            best = max(best, weight)
    return best


@dataclass
class Manifest:
    version: str
    operators: dict[str, OperatorInfo]
    domains: dict[str, DomainInfo]

    def describe(self, idname: str) -> dict | None:
        op = self.operators.get(idname)
        if op is None:
            return None
        return {
            "id": op.idname,
            "category": op.category,
            "label": op.label,
            "description": op.description,
            "properties": op.properties,
        }

    def search(self, query: str, *, kind: str = "any", domain: str | None = None, limit: int = 30) -> list[dict]:
        cats = set(self.domains[domain].categories) if domain and domain in self.domains else None
        allowlisted = {idname for info in self.domains.values() for idname in info.allowlist}
        scored: list[tuple[int, dict]] = []
        if kind in ("operator", "any"):
            for op in self.operators.values():
                if cats is not None and op.category not in cats:
                    continue
                s = _score(query, op.idname, op.label, op.description)
                if op.idname in allowlisted:
                    s += 10
                if s:
                    scored.append(
                        (
                            s,
                            {
                                "kind": "operator",
                                "idname": op.idname,
                                "category": op.category,
                                "label": op.label,
                                "description": op.description,
                            },
                        )
                    )
        scored.sort(key=lambda it: (-it[0], it[1].get("idname", "")))
        return [rec for _, rec in scored[: max(1, int(limit))]]


@lru_cache(maxsize=4)
def load_manifest(path: str | None = None) -> Manifest:
    with open(path or _DEFAULT, encoding="utf-8") as fh:
        raw = json.load(fh)
    operators = {
        idn: OperatorInfo(
            idname=idn,
            category=o.get("category", ""),
            label=o.get("label", ""),
            description=o.get("description", ""),
            properties=o.get("properties", {}),
        )
        for idn, o in raw.get("operators", {}).items()
    }
    domains = {
        name: DomainInfo(name=name, categories=list(d.get("categories", [])), allowlist=list(d.get("allowlist", [])))
        for name, d in raw.get("domains", {}).items()
    }
    return Manifest(version=raw.get("blender_version", ""), operators=operators, domains=domains)
