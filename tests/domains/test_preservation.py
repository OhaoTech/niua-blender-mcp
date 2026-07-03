from __future__ import annotations

import base64
import io

import pytest

from niua_mcp_bridge.core import preservation_ledger as ledger
from niua_mcp_bridge.core import silhouette as sil
from niua_mcp_bridge.domains import build_default_registry, feedback as fb

# Reuse the fake-bpy env + cube fixtures from the existing pipeline domain tests. (Note:
# "tests" has no __init__.py -- pytest's rootdir insertion makes the sibling module
# importable as "domains.test_pipeline", not "tests.domains.test_pipeline".)
from domains.test_pipeline import _CUBE_QUADS, _CUBE_VERTS, FakeMesh, FakeObj, env  # noqa: F401


@pytest.fixture(autouse=True)
def _reset_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _rgba(rows):
    from PIL import Image

    h, w = len(rows), len(rows[0])
    img = Image.new("RGBA", (w, h))
    img.putdata([(200, 200, 210, 255) if v else (240, 240, 240, 0) for r in rows for v in r])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _render_stub(rows, size=(2.0, 2.0, 2.0)):
    data = _rgba(rows)
    frame = {"center": (0.0, 0.0, 0.0), "size": size}

    def _fn(bpy, obj_name, *, frame=None, views=ledger.PRESERVATION_VIEWS, res=256):
        used = frame or {"center": (0.0, 0.0, 0.0), "size": size}
        return {
            "available": True,
            "res": res,
            "frame": used,
            "measured": {"center": (0.0, 0.0, 0.0), "size": size},
            "images": [{"view": v, "data": data} for v in views],
        }

    return _fn


def test_capture_intake_writes_ledger(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(sil, "render_preservation_views", _render_stub([[1, 1], [1, 0]]))
    out = fb.capture_intake(ctx, {"object": "Cube"})
    assert out["available"] is True
    rec = ledger.get_intake("Cube")
    assert set(rec["masks"]) == {"front", "right", "top"}
    assert rec["checkpoint_label"] == "niua:intake"
    assert rec["size"] == (2.0, 2.0, 2.0)


def test_capture_intake_fails_closed_on_nonseparable(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(sil, "render_preservation_views", _render_stub([[1, 1], [1, 1]]))  # all-full
    out = fb.capture_intake(ctx, {"object": "Cube"})
    assert out["available"] is False
    assert ledger.get_intake("Cube")["available"] is False


def test_capture_intake_headless_degrades(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(
        sil, "render_preservation_views",
        lambda bpy, name, **kw: {"available": False, "reason": "headless"},
    )
    out = fb.capture_intake(ctx, {"object": "Cube"})
    assert out["available"] is False


def test_capture_intake_command_registered_readonly() -> None:
    cmd = build_default_registry().get("feedback.capture_intake")
    assert cmd is not None and cmd.mutates is False and cmd.feedback is None
