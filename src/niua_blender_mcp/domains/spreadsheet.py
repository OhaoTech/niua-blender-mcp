"""Spreadsheet GUI-parity tool specs."""

from __future__ import annotations

from ..kernel import Int, Str, ToolSpec

_COMMON_PARAMS = {
    "object": Str(default="", summary="Object name; defaults to the active object"),
    "component": Str(default="", summary="Geometry domain/component: POINT, EDGE, FACE, or CORNER"),
}

SPECS = [
    ToolSpec(
        name="spreadsheet.report",
        category="spreadsheet",
        summary="Report spreadsheet editor state and object table shape",
        command="spreadsheet.report",
        params=_COMMON_PARAMS,
    ),
    ToolSpec(
        name="spreadsheet.columns",
        category="spreadsheet",
        summary="List spreadsheet columns derived from object geometry attributes",
        command="spreadsheet.columns",
        params=_COMMON_PARAMS,
    ),
    ToolSpec(
        name="spreadsheet.rows",
        category="spreadsheet",
        summary="Return paginated spreadsheet rows derived from object geometry attributes",
        command="spreadsheet.rows",
        params={
            **_COMMON_PARAMS,
            "limit": Int(default=100, minimum=0, summary="Maximum rows to return"),
            "offset": Int(default=0, minimum=0, summary="Row offset"),
        },
    ),
]
