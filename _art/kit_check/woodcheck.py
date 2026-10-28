"""Render an FBX with a proxy of the ship plank texture on trim/dark (grain along U, 14 planks across V with dark gap
lines at v = -0.001 + k/14) and a UV grid on everything else: shows grain direction, stretching and gap lines across
parts. Two views -> <out>_0.png, <out>_1.png.

    blender -b --python woodcheck.py -- AssetSources/export/galleass_culverin.fbx /tmp/x/culverin_new
"""
import bpy, sys, math, random
import numpy as np
from mathutils import Vector
fbx, out = sys.argv[sys.argv.index('--') + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
N = 1024
# proxy of the ship wood: grain streaks along U, 14 planks across V with dark gaps at v = -0.001 + k/14
v = (np.arange(N) + 0.5) / N; u = (np.arange(N) + 0.5) / N
rng = np.random.default_rng(1)
streak = np.interp(v, np.linspace(0, 1, 300), rng.random(300))
plank = np.floor((v + 0.001) * 14); tint = rng.random(15)[plank.astype(int) % 15]
base = 0.35 + 0.25 * streak[:, None] + 0.15 * tint[:, None] + 0.05 * np.sin(u * 40)[None, :]
gap = (((v + 0.001) * 14) % 1 < 0.04)[:, None]
r = np.where(gap, 0.05, base); g = np.where(gap, 0.03, base * 0.65); b = np.where(gap, 0.02, base * 0.35)
px = np.stack([r * np.ones((N, N)), g * np.ones((N, N)), b * np.ones((N, N)), np.ones((N, N))], -1)
wood = bpy.data.images.new('wood', N, N); wood.pixels.foreach_set(px.astype(np.float32).ravel())
grid = bpy.data.images.new('grid', 512, 512); grid.generated_type = 'UV_GRID'
def mat(img):
    m = bpy.data.materials.new(img.name); m.use_nodes = True
    t = m.node_tree.nodes.new('ShaderNodeTexImage'); t.image = img
    m.node_tree.links.new(t.outputs['Color'], m.node_tree.nodes['Principled BSDF'].inputs['Base Color']); return m
mw, mg = mat(wood), mat(grid)
obs = []
for o in list(bpy.data.objects):
    if o.type != 'MESH' or '_lod' in o.name or o.name.startswith('bo_'):
        bpy.data.objects.remove(o); continue
    for i, m in enumerate(o.data.materials):
        o.data.materials[i] = mw if m and m.name.split('.')[0] in ('galleass_trim', 'galleass_dark') else mg
    obs.append(o)
pts = [o.matrix_world @ v.co for o in obs for v in o.data.vertices]
lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
c = (lo + hi) / 2; rr = (hi - lo).length / 2
sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'TEXTURE'; sc.display.shading.light = 'STUDIO'
sc.render.resolution_x, sc.render.resolution_y = 600, 450
cam = bpy.data.objects.new('c', bpy.data.cameras.new('c')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 40
for k, d in enumerate((Vector((1.0, -1.2, 1.1)), Vector((-1.1, 0.9, 0.7)))):
    cam.location = c + d.normalized() * rr * 2.4
    cam.rotation_euler = (c - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = f'{out}_{k}.png'; bpy.ops.render.render(write_still=True)
