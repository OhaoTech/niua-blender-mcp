#!/usr/bin/env python3
"""Render a session JSONL log (niua_blender_mcp.session_log) into standalone HTML.

    python scripts/session_report.py <session.jsonl> [-o report.html]

The gallery that earned trust, as a standing artifact: every mutating call in order,
with status, duration, arguments, result summary, and the viewport thumbnail when one
was recorded. Zero dependencies; thumbnails are inlined base64.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
from pathlib import Path

_BASE64_RE = re.compile(r"[A-Za-z0-9+/=\n]+")
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class _Entries(list):
    """List of log entries that remembers how many malformed lines were skipped."""

    skipped: int = 0


def load_entries(path: str | Path) -> list[dict]:
    entries = _Entries()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            entries.skipped += 1
            continue
        if not isinstance(entry, dict):
            entries.skipped += 1
            continue
        entries.append(entry)
    return entries


def _is_png_thumbnail(value: object) -> bool:
    """True only for a base64 string that decodes to bytes with the PNG magic prefix."""
    if not isinstance(value, str) or not _BASE64_RE.fullmatch(value):
        return False
    try:
        raw = base64.b64decode(value)
    except (ValueError, TypeError):
        return False
    return raw.startswith(_PNG_MAGIC)


def _duration_ms(entry: dict) -> float | None:
    """The parsed duration, or None if 'duration_ms' isn't numeric -- callers decide
    how to render/aggregate a missing value instead of crashing the whole report."""
    try:
        return float(entry.get("duration_ms", 0.0))
    except (TypeError, ValueError):
        return None


def _duration_cell(entry: dict) -> str:
    """Defensive like the thumbnail path: a malformed log must render '?', never crash
    the whole report."""
    ms = _duration_ms(entry)
    return "?" if ms is None else f"{ms:.0f} ms"


def _row(index: int, entry: dict) -> str:
    thumb = ""
    if entry.get("thumbnail"):
        if _is_png_thumbnail(entry["thumbnail"]):
            alt = html.escape(str(entry.get("tool", "")))
            src = html.escape(entry["thumbnail"])  # belt and braces: validated AND escaped
            thumb = f'<img src="data:image/png;base64,{src}" alt="{alt}" style="max-width:220px">'
        else:
            thumb = "(invalid thumbnail)"
    ok = bool(entry.get("ok"))
    return (
        "<tr>"
        f"<td>{index}</td>"
        f"<td><code>{html.escape(str(entry.get('tool', '')))}</code></td>"
        f"<td class=\"{'ok' if ok else 'fail'}\">{'ok' if ok else 'FAILED'}</td>"
        f"<td>{_duration_cell(entry)}</td>"
        f"<td><code>{html.escape(json.dumps(entry.get('arguments', {})))}</code></td>"
        f"<td><code>{html.escape(json.dumps(entry.get('summary', {})))}</code></td>"
        f"<td>{thumb}</td>"
        "</tr>"
    )


def render_html(entries: list[dict], title: str = "Niua session report") -> str:
    ok_count = sum(1 for e in entries if e.get("ok"))
    total_ms = sum(ms for e in entries if (ms := _duration_ms(e)) is not None)
    skipped = getattr(entries, "skipped", 0)
    skipped_note = f" &middot; {skipped} malformed lines skipped" if skipped else ""
    rows = "".join(_row(i, e) for i, e in enumerate(entries, 1))
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #ccc; padding: 6px 10px; vertical-align: top; text-align: left; }}
.ok {{ color: #2a7; }} .fail {{ color: #c33; font-weight: bold; }}
</style></head>
<body>
<h1>{html.escape(title)}</h1>
<p>{len(entries)} mutating calls &middot; {ok_count} ok &middot; {len(entries) - ok_count} failed &middot; {total_ms:.0f} ms total{skipped_note}</p>
<table>
<tr><th>#</th><th>tool</th><th>status</th><th>duration</th><th>arguments</th><th>result</th><th>view</th></tr>
{rows}
</table>
</body></html>
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render a session JSONL log to an HTML replay report.")
    ap.add_argument("log", help="path to the session .jsonl written by the MCP server")
    ap.add_argument("-o", "--out", default="", help="output .html path (default: alongside the log)")
    args = ap.parse_args(argv)
    log = Path(args.log)
    out = Path(args.out) if args.out else log.with_suffix(".html")
    entries = load_entries(log)
    out.write_text(render_html(entries, title=f"Niua session report — {log.name}"), encoding="utf-8")
    print(f"wrote {out} ({len(entries)} calls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
