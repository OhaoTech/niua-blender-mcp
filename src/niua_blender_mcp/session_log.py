"""Session replay log: JSONL middleware for every mutating tool call.

Interface-layer observability: what happened, with what arguments, how long it took,
whether it worked, and (when the tool attached a viewport capture) what it looked
like. scripts/session_report.py renders a log into the before/after HTML gallery.
Enabled by pointing NIUA_BLENDER_MCP_SESSION_LOG at a file path; off otherwise.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENV_VAR = "NIUA_BLENDER_MCP_SESSION_LOG"

_MAX_SUMMARY_FIELDS = 8
_SKIP_KEYS = {"data", "images", "_feedback"}  # image payloads never belong in a summary

_MAX_ARGUMENT_KEYS = 16
_MAX_ARGUMENT_CHARS = 500


def _bound_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Bounded view of call arguments: capped key count, truncated string values."""
    bounded: dict[str, Any] = {}
    for key in list(arguments)[:_MAX_ARGUMENT_KEYS]:
        value = arguments[key]
        if isinstance(value, str) and len(value) > _MAX_ARGUMENT_CHARS:
            value = value[:_MAX_ARGUMENT_CHARS] + "…[truncated]"
        bounded[key] = value
    return bounded


def summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    """Small scalar-only view of a tool result (no image payloads, no nesting)."""
    summary: dict[str, Any] = {}
    for key in sorted(result):
        if key in _SKIP_KEYS:
            continue
        value = result[key]
        if isinstance(value, str):
            summary[key] = value[:120]
        elif isinstance(value, (int, float, bool)) or value is None:
            summary[key] = value
        if len(summary) >= _MAX_SUMMARY_FIELDS:
            break
    return summary


class SessionLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record(
        self,
        *,
        tool: str,
        arguments: dict[str, Any],
        duration_ms: float,
        ok: bool,
        summary: dict[str, Any],
        thumbnail: str | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "arguments": _bound_arguments(arguments),
            "duration_ms": round(duration_ms, 1),
            "ok": ok,
            "summary": summary,
        }
        if thumbnail:
            entry["thumbnail"] = thumbnail
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")


def from_env(environ: dict[str, str] | None = None) -> SessionLog | None:
    path = (os.environ if environ is None else environ).get(ENV_VAR)
    return SessionLog(path) if path else None
