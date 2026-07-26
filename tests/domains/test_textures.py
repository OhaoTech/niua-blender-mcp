from __future__ import annotations

import sys
import types

import pytest

from niua_blender_mcp.domains import build_router
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import NOT_FOUND, BridgeError


class FakeImage:
    def __init__(self, name: str, filepath: str = "") -> None:
        self.name = name
        self.filepath = filepath
        self.size = [64, 32]
        self.source = "FILE"
        self.colorspace_settings = types.SimpleNamespace(name="sRGB")


class FakeImages(dict):
    def __init__(self) -> None:
        super().__init__()
        self.loaded = []

    def load(self, path: str) -> FakeImage:
        name = path.rsplit("/", 1)[-1] or "Image"
        image = FakeImage(name, path)
        self[name] = image
        self.loaded.append(path)
        return image


class FakeBpy(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("bpy")
        self.images = FakeImages()
        self.undo_pushes = []
        self.data = types.SimpleNamespace(images=self.images)

        bpy = self

        class EdOps:
            def undo_push(self, message="", **kwargs):
                bpy.undo_pushes.append(message)

        self.ops = types.SimpleNamespace(ed=EdOps())


def env(monkeypatch):
    bpy = FakeBpy()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    return Ctx(bpy), bpy


def test_router_contains_texture_tools() -> None:
    names = {spec.name for spec in build_router().specs()}
    assert {"textures.load", "textures.list", "textures.report"} <= names


def test_load_image_datablock_with_optional_name(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    reg = build_default_registry()

    out = dispatch_on_main(reg, "textures.load", {"path": "/tmp/albedo.png", "name": "Albedo"}, ctx)

    assert out["name"] == "Albedo"
    assert out["filepath"] == "/tmp/albedo.png"
    assert bpy.images.loaded == ["/tmp/albedo.png"]
    assert bpy.undo_pushes == ["mcp:textures.load"]


def test_list_and_report_images(monkeypatch) -> None:
    ctx, bpy = env(monkeypatch)
    bpy.images["Albedo"] = FakeImage("Albedo", "/tmp/albedo.png")
    reg = build_default_registry()

    listed = dispatch_on_main(reg, "textures.list", {}, ctx)
    reported = dispatch_on_main(reg, "textures.report", {"name": "Albedo"}, ctx)

    assert listed["images"] == [
        {"name": "Albedo", "filepath": "/tmp/albedo.png", "size": [64, 32], "source": "FILE", "colorspace": "sRGB"}
    ]
    assert reported == {"name": "Albedo", "filepath": "/tmp/albedo.png", "size": [64, 32], "source": "FILE", "colorspace": "sRGB"}


def test_report_missing_image_not_found(monkeypatch) -> None:
    ctx, _bpy = env(monkeypatch)
    reg = build_default_registry()

    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(reg, "textures.report", {"name": "Missing"}, ctx)
    assert exc.value.code == NOT_FOUND
