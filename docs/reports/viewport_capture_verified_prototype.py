import bpy, hashlib, json, base64, os, tempfile

DIR = "/tmp/claude-1000/-home-frankyin-Desktop-lab-lab-niua-blender/b9bb9dd1-6c26-4913-8aab-2c600d1478d0/scratchpad"
RES = 320

suz = bpy.data.objects.get("TESTSUZ")
# select + activate so view_selected frames it
for o in bpy.data.objects:
    o.select_set(False)
suz.select_set(True)
bpy.context.view_layer.objects.active = suz

area = region = None
for win in bpy.context.window_manager.windows:
    for a in win.screen.areas:
        if a.type == "VIEW_3D":
            area = a
            region = next((r for r in a.regions if r.type == "WINDOW"), None)
    if area:
        break
area.spaces.active.shading.type = "SOLID"
area.spaces.active.overlay.show_overlays = False

scene = bpy.context.scene
scene.render.resolution_x = scene.render.resolution_y = RES
scene.render.image_settings.file_format = "PNG"

hashes = {}
for view in ("FRONT", "RIGHT", "TOP"):
    with bpy.context.temp_override(area=area, region=region):
        bpy.ops.view3d.view_axis(type=view)
        bpy.ops.view3d.view_selected()          # frame Suzanne
        path = os.path.join(tempfile.gettempdir(), f"vp_{view}.png")
        scene.render.filepath = path
        bpy.ops.render.opengl(write_still=True, view_context=True)  # capture the VIEWPORT (what you see)
    data = open(path, "rb").read()
    open(os.path.join(DIR, f"vp_{view}.png"), "wb").write(data)
    hashes[view] = hashlib.md5(data).hexdigest()[:8]

hashes["distinct_count"] = len(set(hashes[v] for v in ("FRONT", "RIGHT", "TOP")))
open(os.path.join(DIR, "viewport_capture_probe.json"), "w").write(json.dumps(hashes, indent=2))
print("[niua] viewport-capture probe done:", hashes)
