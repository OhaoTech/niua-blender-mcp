from __future__ import annotations

import base64
import io

import pytest

from niua_mcp_bridge.core import silhouette as sil
from niua_mcp_bridge.domains import build_default_registry, finishing_feedback as fb
from niua_mcp_bridge.finishing import preservation_ledger as ledger

# Reuse the shared fake-bpy env + cube fixtures. (Note: "tests" has no __init__.py --
# pytest's rootdir insertion makes the sibling module importable as "domains.fake_bpy",
# not "tests.domains.fake_bpy".)
from domains.fake_bpy import _CUBE_QUADS, _CUBE_VERTS, FakeMesh, FakeObj, env  # noqa: F401


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
    assert rec["checkpoint_label"] == "mcp:intake"
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


def test_preservation_requires_intake_baseline(env) -> None:
    from niua_mcp_bridge.errors import BridgeError
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    with pytest.raises(BridgeError):
        fb.preservation(ctx, {"object": "Cube"})


def test_preservation_identical_is_one(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(sil, "render_preservation_views", _render_stub([[1, 1], [1, 0]]))
    fb.capture_intake(ctx, {"object": "Cube"})
    out = fb.preservation(ctx, {"object": "Cube"})
    assert out["available"] is True
    assert out["preservation"] == 1.0
    assert out["preservation_pass"] is True
    assert out["threshold"] == 0.85
    assert out["bbox_delta"]["changed"] is False


def test_preservation_flags_damage_below_floor(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(sil, "render_preservation_views", _render_stub([[1, 1], [1, 0]]))
    fb.capture_intake(ctx, {"object": "Cube"})
    # Current form collapses to a quarter of the frame -> IoU well below floor.
    monkeypatch.setattr(sil, "render_preservation_views", _render_stub([[1, 0], [0, 0]]))
    out = fb.preservation(ctx, {"object": "Cube"})
    assert out["available"] is True
    assert out["preservation"] < 0.85
    assert out["preservation_pass"] is False


def test_preservation_uniform_scale_visible_in_bbox_delta(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(sil, "render_preservation_views", _render_stub([[1, 1], [1, 0]], size=(2.0, 2.0, 2.0)))
    fb.capture_intake(ctx, {"object": "Cube"})
    # Same silhouette shape, but the object is half the size -> bbox_delta flags it.
    monkeypatch.setattr(sil, "render_preservation_views", _render_stub([[1, 1], [1, 0]], size=(1.0, 1.0, 1.0)))
    out = fb.preservation(ctx, {"object": "Cube"})
    assert out["bbox_delta"]["changed"] is True
    assert abs(out["bbox_delta"]["scale_ratio"] - 0.5) < 1e-9


def test_preservation_unmeasured_when_intake_headless(env, monkeypatch) -> None:
    ctx, bpy = env
    bpy.add(FakeObj("Cube", data=FakeMesh(verts=_CUBE_VERTS, polys=_CUBE_QUADS)))
    monkeypatch.setattr(sil, "render_preservation_views",
                        lambda bpy, name, **kw: {"available": False, "reason": "headless"})
    fb.capture_intake(ctx, {"object": "Cube"})
    out = fb.preservation(ctx, {"object": "Cube"})
    assert out["available"] is False  # unmeasured, not a false failure


def test_preservation_command_registered_readonly() -> None:
    cmd = build_default_registry().get("feedback.preservation")
    assert cmd is not None and cmd.mutates is False and cmd.feedback is None
