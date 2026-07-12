"""Session replay log: mutating tool calls -> JSONL via server-dispatch middleware."""

from __future__ import annotations

import json

from niua_blender_mcp.bridge import BridgeError
from niua_blender_mcp.kernel.errors import NOT_FOUND
from niua_blender_mcp.server import create_server
from niua_blender_mcp.session_log import ENV_VAR, SessionLog, from_env, summarize_result


class RecordingBridge:
    def __init__(self, result=None, raises=None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.result = result if result is not None else {"ok": True}
        self.raises = raises

    def call(self, command: str, payload: dict, timeout: float | None = None) -> dict:
        self.calls.append((command, payload))
        if self.raises is not None:
            raise self.raises
        return dict(self.result)


def entries(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_mutating_call_is_logged(tmp_path) -> None:
    log_path = tmp_path / "session.jsonl"
    server = create_server(bridge=RecordingBridge(result={"name": "Hero"}), session_log=SessionLog(log_path))
    server._tools_call({"name": "scene.create_object", "arguments": {"type": "CUBE", "name": "Hero"}})
    (entry,) = entries(log_path)
    assert entry["tool"] == "scene.create_object"
    assert entry["ok"] is True
    assert entry["arguments"]["type"] == "CUBE"
    assert entry["duration_ms"] >= 0
    assert entry["summary"]["name"] == "Hero"
    assert entry["ts"]


def test_read_only_call_is_not_logged(tmp_path) -> None:
    log_path = tmp_path / "session.jsonl"
    server = create_server(bridge=RecordingBridge(), session_log=SessionLog(log_path))
    server._tools_call({"name": "scene.info", "arguments": {}})
    assert not log_path.exists()


def test_failed_mutation_is_logged_with_error_summary(tmp_path) -> None:
    log_path = tmp_path / "session.jsonl"
    bridge = RecordingBridge(raises=BridgeError(NOT_FOUND, "object not found: Ghost"))
    server = create_server(bridge=bridge, session_log=SessionLog(log_path))
    server._tools_call({"name": "scene.set_transform", "arguments": {"object": "Ghost"}})
    (entry,) = entries(log_path)
    assert entry["ok"] is False
    assert entry["summary"]["code"] == NOT_FOUND


def test_thumbnail_captured_from_feedback_attachment(tmp_path) -> None:
    log_path = tmp_path / "session.jsonl"
    result = {"name": "Hero", "_feedback": {"available": True, "data": "QkFTRTY0"}}
    server = create_server(bridge=RecordingBridge(result=result), session_log=SessionLog(log_path))
    server._tools_call({"name": "scene.create_object", "arguments": {"type": "CUBE"}})
    (entry,) = entries(log_path)
    assert entry["thumbnail"] == "QkFTRTY0"


def test_summarize_result_is_scalar_only_and_image_free() -> None:
    summary = summarize_result(
        {"name": "Hero", "count": 3, "data": "HUGEBASE64", "_feedback": {"data": "x"}, "nested": {"a": 1}}
    )
    assert summary == {"count": 3, "name": "Hero"}


def test_from_env_toggles_the_middleware(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert from_env() is None
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "s.jsonl"))
    log = from_env()
    assert log is not None and log.path.name == "s.jsonl"


def test_no_summary_or_thumbnail_work_when_logging_is_off(monkeypatch) -> None:
    """Zero-cost off: summarize/thumbnail must not even be CALLED with no session log."""
    import niua_blender_mcp.server as server_mod

    def boom(*args, **kwargs):
        raise AssertionError("must not run when logging is off")

    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setattr(server_mod, "summarize_result", boom)
    monkeypatch.setattr(server_mod.NiuaBlenderMCP, "_session_thumbnail", staticmethod(boom))
    server = create_server(bridge=RecordingBridge(result={"name": "Hero"}))
    out = server._tools_call({"name": "scene.create_object", "arguments": {"type": "CUBE"}})
    assert out["isError"] is False


def test_logging_failure_never_breaks_a_dispatch(tmp_path) -> None:
    class ExplodingLog(SessionLog):
        def record(self, **kwargs) -> None:
            raise OSError("disk full")

    server = create_server(
        bridge=RecordingBridge(result={"name": "Hero"}), session_log=ExplodingLog(tmp_path / "s.jsonl")
    )
    out = server._tools_call({"name": "scene.create_object", "arguments": {"type": "CUBE"}})
    assert out["isError"] is False
    assert out["structuredContent"]["name"] == "Hero"


def test_giant_string_argument_is_truncated_and_keys_are_capped(tmp_path) -> None:
    log = SessionLog(tmp_path / "s.jsonl")
    arguments = {"code": "x" * 5000, **{f"k{i}": i for i in range(30)}}
    log.record(tool="t", arguments=arguments, duration_ms=1.0, ok=True, summary={})
    (entry,) = entries(log.path)
    code = entry["arguments"]["code"]
    assert code.endswith("…[truncated]")
    assert len(code) == 500 + len("…[truncated]")
    assert len(entry["arguments"]) == 16
