import bpy, gpu, hashlib, json, os, struct, zlib, mathutils
from niua_mcp_bridge.core import capture as cap

DIR = "/tmp/claude-1000/-home-frankyin-Desktop-lab-lab-niua-blender/b9bb9dd1-6c26-4913-8aab-2c600d1478d0/scratchpad"
RES = 320

name = "GPU2CONE"
o = bpy.data.objects.get(name)
if o is None:
    bpy.ops.mesh.primitive_cone_add()
    o = bpy.context.active_object
    o.name = name
bpy.context.view_layer.update()
center, size = cap.scene_bbox(bpy, name)
cam = cap._ensure_capture_camera(bpy)

space = region = None
for win in bpy.context.window_manager.windows:
    for area in win.screen.areas:
        if area.type == "VIEW_3D":
            space = area.spaces.active
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            break
    if space:
        break

if hasattr(space, "shading"):
    space.shading.type = "SOLID"


def png_bytes(w, h, flat):
    stride = w * 4
    rows = [b"\x00" + bytes(flat[y * stride:(y + 1) * stride]) for y in range(h - 1, -1, -1)]
    raw = b"".join(rows)
    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def view_matrix_from_frame(frame):
    # PURE-COMPUTED from the frame (no cam.matrix_world read -> not stale)
    loc = mathutils.Vector(frame["location"])
    rot = mathutils.Euler(frame["rotation_euler"], "XYZ").to_matrix().to_4x4()
    cam_world = mathutils.Matrix.Translation(loc) @ rot
    return cam_world.inverted()


offscreen = gpu.types.GPUOffScreen(RES, RES)
dg = bpy.context.evaluated_depsgraph_get()
hashes = {}
for view in ("front", "right", "top", "persp"):
    frame = cap.view_camera(center, size, view)
    view_matrix = view_matrix_from_frame(frame)
    # projection from camera DATA (data props read immediately, unlike deferred transforms)
    if frame["type"] == "ORTHO":
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = frame.get("ortho_scale", 2.0)
    else:
        cam.data.type = "PERSP"
    proj_matrix = cam.calc_matrix_camera(dg, x=RES, y=RES)
    offscreen.draw_view3d(bpy.context.scene, bpy.context.view_layer, space, region,
                          view_matrix, proj_matrix, do_color_management=False)
    with offscreen.bind():
        buf = gpu.state.active_framebuffer_get().read_color(0, 0, RES, RES, 4, 0, "UBYTE")
    buf.dimensions = RES * RES * 4
    png = png_bytes(RES, RES, list(buf))
    open(os.path.join(DIR, f"gpu2_{view}.png"), "wb").write(png)
    hashes[view] = hashlib.md5(png).hexdigest()[:8]
offscreen.free()

hashes["front_eq_right"] = hashes["front"] == hashes["right"]     # cone: expect TRUE
hashes["top_distinct"] = hashes["top"] not in (hashes["front"], hashes["persp"])  # expect TRUE
hashes["distinct_count"] = len(set(hashes[v] for v in ("front", "right", "top", "persp")))
open(os.path.join(DIR, "gpu_offscreen_probe2.json"), "w").write(json.dumps(hashes, indent=2))
