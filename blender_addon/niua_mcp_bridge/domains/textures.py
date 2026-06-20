"""Texture/image datablock handlers."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import NOT_FOUND, PRECONDITION, BridgeError


def _images(ctx: Ctx) -> Any:
    return ctx.bpy.data.images


def _image_report(image: Any) -> dict:
    colorspace = getattr(getattr(image, "colorspace_settings", None), "name", "")
    return {
        "name": getattr(image, "name", ""),
        "filepath": getattr(image, "filepath", ""),
        "size": [int(v) for v in list(getattr(image, "size", []) or [])],
        "source": getattr(image, "source", ""),
        "colorspace": colorspace,
    }


def _get_image(ctx: Ctx, name: str) -> Any:
    getter = getattr(_images(ctx), "get", None)
    image = getter(name) if callable(getter) else None
    if image is None:
        raise BridgeError(NOT_FOUND, f"image not found: {name}")
    return image


def load(ctx: Ctx, payload: dict) -> dict:
    path = str(payload.get("path", ""))
    try:
        image = _images(ctx).load(path)
    except Exception as exc:  # noqa: BLE001 - Blender raises RuntimeError for load failures
        raise BridgeError(PRECONDITION, f"could not load image: {exc}", {"path": path}) from exc
    name = payload.get("name")
    if isinstance(name, str) and name:
        image.name = name
    return _image_report(image)


def list_images(ctx: Ctx, payload: dict) -> dict:
    images = list(_images(ctx).values()) if hasattr(_images(ctx), "values") else list(_images(ctx) or [])
    return {"images": [_image_report(image) for image in images]}


def report(ctx: Ctx, payload: dict) -> dict:
    return _image_report(_get_image(ctx, str(payload.get("name", ""))))


COMMANDS = [
    Command("textures.load", load, mutates=True, feedback="viewport"),
    Command("textures.list", list_images, mutates=False),
    Command("textures.report", report, mutates=False),
]
