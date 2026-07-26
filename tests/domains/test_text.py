"""Text Editor GUI-parity domain tests (fake-bpy)."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import INVALID_PARAMS, NOT_FOUND, BridgeError


class FakeText:
    def __init__(self, name: str, body: str = "", filepath: str = "") -> None:
        self.name = name
        self._body = body
        self.filepath = filepath
        self.is_dirty = bool(body)
        self.is_modified = False
        self.is_in_memory = not bool(filepath)
        self.use_module = False
        self.indentation = "TABS"

    def as_string(self) -> str:
        return self._body

    def from_string(self, body: str) -> None:
        self._body = body
        self.is_dirty = True

    def write(self, body: str) -> None:
        self._body += body
        self.is_dirty = True

    def clear(self) -> None:
        self._body = ""
        self.is_dirty = True


class FakeTexts(list):
    def get(self, name: str):
        return next((text for text in self if text.name == name), None)

    def new(self, name: str):
        text = FakeText(name)
        self.append(text)
        return text

    def load(self, filepath: str):
        body = Path(filepath).read_text(encoding="utf-8")
        text = FakeText(Path(filepath).name, body, filepath)
        self.append(text)
        return text

    def remove(self, text: FakeText) -> None:
        super().remove(text)


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.texts = FakeTexts()
        self.undo_pushes: list[str] = []

        class _EdOps:
            @staticmethod
            def undo_push(message: str = "", **kw):
                self.undo_pushes.append(message)

        self.ops = types.SimpleNamespace(ed=_EdOps())

    @property
    def data(self):
        return types.SimpleNamespace(texts=self.texts)


@pytest.fixture()
def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_text_editor_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {
        "text.list",
        "text.create",
        "text.open",
        "text.read",
        "text.write",
        "text.append",
        "text.save",
        "text.remove",
    } <= names


def test_create_list_read_write_append_save_and_remove(env, tmp_path) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    created = dispatch_on_main(reg, "text.create", {"name": "Script", "body": "print(1)\\n"}, ctx)
    assert created["name"] == "Script"
    assert created["line_count"] == 1
    assert bpy.undo_pushes == ["mcp:text.create"]

    listed = dispatch_on_main(reg, "text.list", {}, ctx)
    assert listed["text_count"] == 1
    assert listed["texts"][0]["name"] == "Script"

    read = dispatch_on_main(reg, "text.read", {"name": "Script"}, ctx)
    assert read["body"] == "print(1)\\n"

    written = dispatch_on_main(reg, "text.write", {"name": "Script", "body": "x = 1\\n"}, ctx)
    assert written["body"] == "x = 1\\n"

    appended = dispatch_on_main(reg, "text.append", {"name": "Script", "body": "y = 2\\n"}, ctx)
    assert appended["body"] == "x = 1\\ny = 2\\n"

    save_path = tmp_path / "script.py"
    saved = dispatch_on_main(reg, "text.save", {"name": "Script", "path": str(save_path)}, ctx)
    assert saved["path"] == str(save_path)
    assert save_path.read_text(encoding="utf-8") == "x = 1\\ny = 2\\n"

    removed = dispatch_on_main(reg, "text.remove", {"name": "Script"}, ctx)
    assert removed["removed"] == "Script"
    assert dispatch_on_main(reg, "text.list", {}, ctx)["text_count"] == 0


def test_open_text_from_file_can_rename(env, tmp_path) -> None:
    ctx, _bpy = env
    path = tmp_path / "source.py"
    path.write_text("print('hi')\\n", encoding="utf-8")
    reg = build_default_registry()

    opened = dispatch_on_main(reg, "text.open", {"path": str(path), "name": "Opened"}, ctx)

    assert opened["name"] == "Opened"
    assert opened["filepath"] == str(path)
    assert opened["body"] == "print('hi')\\n"


def test_missing_path_and_text_fail_without_undo(env) -> None:
    ctx, bpy = env
    reg = build_default_registry()

    with pytest.raises(BridgeError) as path_exc:
        dispatch_on_main(reg, "text.open", {"path": "/no/such/file.py"}, ctx)

    with pytest.raises(BridgeError) as text_exc:
        dispatch_on_main(reg, "text.read", {"name": "Missing"}, ctx)

    with pytest.raises(BridgeError) as save_exc:
        dispatch_on_main(reg, "text.save", {"name": "Missing"}, ctx)

    assert path_exc.value.code == INVALID_PARAMS
    assert text_exc.value.code == NOT_FOUND
    assert save_exc.value.code == NOT_FOUND
    assert bpy.undo_pushes == []
