"""Deterministic token accounting for the code-mode win — pure, offline, no tokenizer dep.

approx_tokens(x) = ceil(len(json_or_str(x)) / 4), the standard rough estimate; raw byte
counts are reported alongside. Both are labelled approximate. Tool-by-tool charges every
call's arguments + FULL result (what would flow into an agent's context) plus the schema
cost of the distinct tools held; code-mode charges the touched SDK source read once plus
the single returned summary — intermediates never enter context.
"""

from __future__ import annotations

import json
import math
from typing import Any


def _text(x: Any) -> str:
    if isinstance(x, str):
        return x
    try:
        return json.dumps(x, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(x)


def _bytes(x: Any) -> int:
    return len(_text(x).encode("utf-8"))


def approx_tokens(x: Any) -> int:
    return math.ceil(len(_text(x)) / 4)


def token_accounting(calls: list[dict], sdk_sources: dict[str, str],
                     tool_schemas: dict[str, dict], summary: Any) -> dict:
    tbt_tokens = sum(approx_tokens(c.get("arguments", {})) + approx_tokens(c.get("result"))
                     for c in calls)
    tbt_tokens += sum(approx_tokens(s) for s in tool_schemas.values())
    tbt_bytes = sum(_bytes(c.get("arguments", {})) + _bytes(c.get("result")) for c in calls)
    tbt_bytes += sum(_bytes(s) for s in tool_schemas.values())

    cm_tokens = sum(approx_tokens(src) for src in sdk_sources.values()) + approx_tokens(summary)
    cm_bytes = sum(_bytes(src) for src in sdk_sources.values()) + _bytes(summary)

    ratio = (tbt_tokens / cm_tokens) if cm_tokens else None
    return {
        "tool_by_tool_tokens": tbt_tokens,
        "code_mode_tokens": cm_tokens,
        "ratio": ratio,
        "tool_by_tool_bytes": tbt_bytes,
        "code_mode_bytes": cm_bytes,
        "n_calls": len(calls),
        "note": "approx tokens = ceil(chars/4); bytes are utf-8; both approximate",
    }
