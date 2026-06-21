"""Video Sequencer GUI-parity domain manifest."""

from __future__ import annotations

from ..kernel import Int, Str, ToolSpec

SPECS = [
    ToolSpec(
        name="sequencer.report",
        category="sequencer",
        summary="Report sequence strips in the active scene",
        command="sequencer.report",
        params={},
    ),
    ToolSpec(
        name="sequencer.strip_add",
        category="sequencer",
        summary="Add a sequence strip",
        command="sequencer.strip_add",
        params={
            "type": Str(required=True, summary="Strip type, e.g. COLOR, TEXT, MOVIE, SOUND"),
            "name": Str(default="", summary="Optional strip name"),
            "frame_start": Int(default=1, minimum=1, summary="Start frame"),
            "channel": Int(default=1, minimum=1, summary="Sequencer channel"),
            "path": Str(default="", summary="File path for movie or sound strips"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="sequencer.strip_remove",
        category="sequencer",
        summary="Remove a sequence strip by name",
        command="sequencer.strip_remove",
        params={"name": Str(required=True, summary="Strip name")},
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="sequencer.strip_set",
        category="sequencer",
        summary="Set one RNA property on a sequence strip",
        command="sequencer.strip_set",
        params={
            "name": Str(required=True, summary="Strip name"),
            "property": Str(required=True, summary="Strip RNA property identifier"),
            "value": Str(required=True, summary="New value as JSON"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="sequencer.modifiers",
        category="sequencer",
        summary="List strip modifiers on a sequence strip",
        command="sequencer.modifiers",
        params={"name": Str(required=True, summary="Strip name")},
    ),
    ToolSpec(
        name="sequencer.modifier_add",
        category="sequencer",
        summary="Add a strip modifier to a sequence strip",
        command="sequencer.modifier_add",
        params={
            "name": Str(required=True, summary="Strip name"),
            "type": Str(required=True, summary="Modifier type, e.g. BRIGHT_CONTRAST"),
            "modifier_name": Str(default="", summary="Optional modifier name"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="sequencer.modifier_set",
        category="sequencer",
        summary="Set one RNA property on a strip modifier",
        command="sequencer.modifier_set",
        params={
            "name": Str(required=True, summary="Strip name"),
            "modifier": Str(required=True, summary="Modifier name"),
            "property": Str(required=True, summary="Modifier RNA property identifier"),
            "value": Str(required=True, summary="New value as JSON"),
        },
        mutates=True,
        feedback="viewport",
    ),
    ToolSpec(
        name="sequencer.modifier_remove",
        category="sequencer",
        summary="Remove a strip modifier",
        command="sequencer.modifier_remove",
        params={
            "name": Str(required=True, summary="Strip name"),
            "modifier": Str(required=True, summary="Modifier name"),
        },
        mutates=True,
        feedback="viewport",
    ),
]
