"""Pure token accounting: tool-by-tool (args+results+schemas) vs code-mode (SDK read once + summary)."""

from __future__ import annotations

from niua_blender_mcp.client import accounting


def test_tool_by_tool_exceeds_code_mode_and_ratio_is_correct():
    calls = [
        {"tool": "feedback.readiness", "arguments": {"object": "x"},
         "result": {"readiness": 0.5, "per_gate": [{"path": "a", "pass": False}] * 40}},
        {"tool": "mesh.tris_to_quads", "arguments": {"object": "x"}, "result": {"ok": True}},
    ]
    sdk_sources = {"mesh": "def tris_to_quads(...): ...\n", "feedback": "def readiness(...): ...\n"}
    tool_schemas = {"feedback.readiness": {"type": "object"}, "mesh.tris_to_quads": {"type": "object"}}
    summary = {"readiness_final": 0.7, "moves": []}
    out = accounting.token_accounting(calls, sdk_sources, tool_schemas, summary)
    assert out["n_calls"] == 2
    assert out["tool_by_tool_tokens"] > out["code_mode_tokens"]
    assert out["ratio"] == out["tool_by_tool_tokens"] / out["code_mode_tokens"]
    assert out["tool_by_tool_bytes"] > 0 and out["code_mode_bytes"] > 0
    assert "approx" in out["note"].lower()


def test_empty_run_does_not_divide_by_zero():
    out = accounting.token_accounting([], {}, {}, {})
    assert out["n_calls"] == 0
    assert out["ratio"] is None or out["ratio"] >= 0
