"""The capabilities meta-domain: the agent's discoverability front door.

domains / search / describe / invoke. At runtime these answer from the LIVE
Blender RNA (always correct for the running version) by reusing the introspection
and rna_exec handlers. The server-side committed manifest is used for code
generation and offline tests, not for runtime answers. rna.* names remain as
aliases (their COMMANDS still register) so existing callers keep working.
"""

from __future__ import annotations

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, BridgeError
from .introspection import _iter_operators, rna_describe, rna_search
from .rna_exec import call_operator


def domains(ctx: Ctx, payload: dict) -> dict:
    # Group the live operator categories the agent may drive. Mirrors rna_search's
    # category surface; coverage detail comes from the committed manifest offline.
    cats: dict[str, int] = {}
    for _idname, cat, _label, _desc in _iter_operators(ctx.bpy, None):
        cats[cat] = cats.get(cat, 0) + 1
    return {"domains": [{"name": c, "reachable_count": n} for c, n in sorted(cats.items())]}


def search(ctx: Ctx, payload: dict) -> dict:
    # Reuse the live RNA search; accept an optional 'domain' alias for 'category'.
    if payload.get("domain") and not payload.get("category"):
        payload = {**payload, "category": payload["domain"]}
    return rna_search(ctx, payload)


def describe(ctx: Ctx, payload: dict) -> dict:
    idn = payload.get("id")
    if not isinstance(idn, str) or not idn:
        raise BridgeError(INVALID_PARAMS, "id is required, e.g. 'mesh.bevel'")
    return rna_describe(ctx, {"path": f"op:{idn}"})


def invoke(ctx: Ctx, payload: dict) -> dict:
    return call_operator(ctx, payload)


COMMANDS = [
    Command("capabilities.domains", domains, mutates=False),
    Command("capabilities.search", search, mutates=False),
    Command("capabilities.describe", describe, mutates=False),
    Command("capabilities.invoke", invoke, mutates=True, feedback="viewport"),
]
