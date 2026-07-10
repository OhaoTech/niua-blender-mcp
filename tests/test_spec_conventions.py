"""Spec-lint: THE parameter convention, written once and enforced against every ToolSpec.

THE CONVENTION (single source of truth -- edit this docstring and the constants
below deliberately, never ad hoc):

1. Multi-value object/element params are STRING params with a plural name
   ("objects", "vertices", "edges", "indices", "maps") taking a COMMA-SEPARATED
   string; their summary/description must say "comma-separated" so an agent
   cannot guess the encoding wrong.
2. "JSON array string" params are a FROZEN legacy exception on the RNA-passthrough
   quartet only (JSON_ARRAY_ALLOWLIST). New tools must not add JSON-string params:
   use a real array param (kind="array") or rule 1's comma-separated string.
3. Every param carries at least a summary or a description.
4. Defaults type-match their kind; enum defaults are members of choices.

Generated-tier specs mirror live Blender RNA verbatim and are exempt (their
conventions are Blender's, not ours).
"""

from __future__ import annotations

from niua_blender_mcp.domains import build_router

MULTI_VALUE_NAMES = {"objects", "vertices", "edges", "indices", "maps"}

#: Frozen legacy exception (rule 2): the RNA-passthrough quartet's 'select' param.
JSON_ARRAY_ALLOWLIST = {
    ("capabilities.invoke", "select"),
    ("rna.call_operator", "select"),
    ("ui.operator_poll", "select"),
    ("ui.operator_invoke", "select"),
}


def _curated_params():
    for spec in build_router().specs():
        if spec.tier == "generated":
            continue
        for pname, param in spec.params.items():
            yield spec, pname, param


def _doc(param) -> str:
    return (param.summary + " " + param.description).lower()


def test_multi_value_string_params_document_comma_separated() -> None:
    bad = [
        f"{spec.name}.{pname}"
        for spec, pname, param in _curated_params()
        if param.kind == "string"
        and pname in MULTI_VALUE_NAMES
        and (spec.name, pname) not in JSON_ARRAY_ALLOWLIST
        and "comma" not in _doc(param)
    ]
    assert not bad, f"multi-value string params must document 'comma-separated': {bad}"


def test_json_array_string_params_are_frozen_to_the_allowlist() -> None:
    found = {
        (spec.name, pname)
        for spec, pname, param in _curated_params()
        if "json array" in _doc(param)
    }
    assert found <= JSON_ARRAY_ALLOWLIST, (
        f"new JSON-array-string params are banned (rule 2): {sorted(found - JSON_ARRAY_ALLOWLIST)}"
    )


def test_every_param_is_documented() -> None:
    bad = [
        f"{spec.name}.{pname}"
        for spec, pname, param in _curated_params()
        if not param.summary and not param.description
    ]
    assert not bad, f"params without any summary/description: {bad}"


def test_defaults_type_match_kind() -> None:
    bad = []
    for spec, pname, param in _curated_params():
        default = param.default
        if default is None:
            continue
        ok = True
        if param.kind == "boolean":
            ok = isinstance(default, bool)
        elif param.kind == "integer":
            ok = isinstance(default, int) and not isinstance(default, bool)
        elif param.kind == "number":
            ok = isinstance(default, (int, float)) and not isinstance(default, bool)
        elif param.kind == "string":
            ok = isinstance(default, str)
        elif param.kind == "enum":
            ok = default in (param.choices or ())
        elif param.kind == "array":
            ok = isinstance(default, (list, tuple))
        if not ok:
            bad.append(f"{spec.name}.{pname} ({param.kind} default {default!r})")
    assert not bad, f"defaults that don't match their kind: {bad}"
