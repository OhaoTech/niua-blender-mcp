"""session_report.py: JSONL session log -> standalone HTML replay report."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from niua_blender_mcp.session_log import SessionLog

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "session_report.py"

# base64 of the PNG magic bytes (\x89PNG\r\n\x1a\n) — a minimal valid thumbnail payload.
PNG_THUMB = "iVBORw0KGgo="


def _load_module():
    spec = importlib.util.spec_from_file_location("session_report", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_fixture(path: Path) -> None:
    log = SessionLog(path)
    log.record(tool="scene.create_object", arguments={"type": "CUBE"}, duration_ms=12.5,
               ok=True, summary={"name": "Cube"}, thumbnail=PNG_THUMB)
    log.record(tool="scene.set_transform", arguments={"object": "Ghost"}, duration_ms=3.0,
               ok=False, summary={"code": "not_found"})


def test_load_entries_round_trips_the_log(tmp_path) -> None:
    module = _load_module()
    _write_fixture(tmp_path / "s.jsonl")
    entries = module.load_entries(tmp_path / "s.jsonl")
    assert [e["tool"] for e in entries] == ["scene.create_object", "scene.set_transform"]


def test_render_html_shows_calls_failures_and_thumbnails(tmp_path) -> None:
    module = _load_module()
    _write_fixture(tmp_path / "s.jsonl")
    html_text = module.render_html(module.load_entries(tmp_path / "s.jsonl"))
    assert "scene.create_object" in html_text
    assert f"data:image/png;base64,{PNG_THUMB}" in html_text
    assert "FAILED" in html_text
    assert "2 mutating calls" in html_text
    assert html_text.lstrip().startswith("<!doctype html>")


def test_main_writes_the_report_next_to_the_log(tmp_path) -> None:
    module = _load_module()
    _write_fixture(tmp_path / "s.jsonl")
    assert module.main([str(tmp_path / "s.jsonl")]) == 0
    out = tmp_path / "s.html"
    assert out.exists()
    assert "scene.set_transform" in out.read_text(encoding="utf-8")


def test_poisoned_thumbnail_cannot_escape_the_img_attribute(tmp_path) -> None:
    """A log entry with an attribute-breaking 'thumbnail' must never reach the DOM raw."""
    module = _load_module()
    payload = '"><script>alert(1)</script>'
    log = SessionLog(tmp_path / "s.jsonl")
    log.record(tool="scene.create_object", arguments={}, duration_ms=1.0,
               ok=True, summary={}, thumbnail=payload)
    html_text = module.render_html(module.load_entries(tmp_path / "s.jsonl"))
    assert "<script" not in html_text
    assert payload not in html_text
    assert "(invalid thumbnail)" in html_text


def test_non_png_base64_thumbnail_is_rejected(tmp_path) -> None:
    """Base64 that does not decode to PNG magic is not embedded as an image."""
    module = _load_module()
    log = SessionLog(tmp_path / "s.jsonl")
    log.record(tool="scene.create_object", arguments={}, duration_ms=1.0,
               ok=True, summary={}, thumbnail="QkFTRTY0")  # b"BASE64", not a PNG
    html_text = module.render_html(module.load_entries(tmp_path / "s.jsonl"))
    assert "data:image/png" not in html_text
    assert "(invalid thumbnail)" in html_text


def test_malformed_lines_are_skipped_and_counted(tmp_path) -> None:
    """Truncated JSON and non-dict lines are skipped; the report says how many."""
    module = _load_module()
    path = tmp_path / "s.jsonl"
    log = SessionLog(path)
    log.record(tool="scene.create_object", arguments={"type": "CUBE"}, duration_ms=12.5,
               ok=True, summary={"name": "Cube"})
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"ts": "2026-07-10", "tool": "scene.set_tra\n')  # truncated JSON
        fh.write('"just a bare string"\n')  # valid JSON, not a dict
    entries = module.load_entries(path)
    assert [e["tool"] for e in entries] == ["scene.create_object"]
    html_text = module.render_html(entries)
    assert html_text.count("<tr>") == 2  # header + exactly 1 data row
    assert "2 malformed lines skipped" in html_text
