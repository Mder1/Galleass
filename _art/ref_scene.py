"""Reference scene: vanilla meditheavy hull (LOD0) + the galleass drawing as a scaled side-view
plane, rendered orthographic for a proportion check.
blender -b --python ref_scene.py -- <scale k> <out.blend> <side.png> <top.png>

Drawing calibration (ref/galleass_drawing.jpg, 1/400): 17.9 px/m, waterline at y=742 px,
stern post at x=80 px, stem at x=858 px (waterline), ram tip at x=956 px.
Galleass waterline midpoint is put at ship y=0, waterline at z=0, bow = +Y (as in vanilla ships).
"""
import bpy, sys, math, os
argv = sys.argv[sys.argv.index('--') + 1:]
k = float(argv[0]); out_blend, side_png, top_png = argv[1:4]
here = os.path.dirname(os.path.abspath(__file__))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

# --- meditheavy LOD0 (sub-meshes .0-.3)
bpy.ops.wm.obj_import(filepath=os.path.join(here, 'ref/meditheavy/ship_meditheavy.obj'), forward_axis='Y', up_axis='Z')
for o in list(sc.objects):
    if o.type == 'MESH' and o.name.split('.')[-1] not in ('0', '1', '2', '3'):
        bpy.data.objects.remove(o)
medit = [o for o in sc.objects if o.type == 'MESH']
red = bpy.data.materials.new('medit_red'); red.diffuse_color = (0.85, 0.15, 0.1, 1)
for o in medit:
    o.color = (0.85, 0.15, 0.1, 1)
    o.data.materials.clear(); o.data.materials.append(red)

# --- drawing plane (side view part only)
PX_M, WL_Y, STERN_X, STEM_X = 17.9, 742.0, 80.0, 858.0
crop = (20, 150, 1080, 800)          # x0, y0, x1, y1 in px
img = bpy.data.images.load(os.path.join(here, 'ref/galleass_drawing.jpg'))
W, H = img.size
mid_x = (STERN_X + STEM_X) / 2
def to_ship(px, py):                 # drawing px -> ship (y, z) in metres, scaled by k
    return ((px - mid_x) / PX_M * k, (WL_Y - py) / PX_M * k)
(y0, z0), (y1, z1) = to_ship(crop[0], crop[3]), to_ship(crop[2], crop[1])
bpy.ops.mesh.primitive_plane_add()
pl = bpy.context.object; pl.name = 'drawing_side'
me = pl.data
# plane in the YZ plane at x = -12 (behind the hull for a camera at +X, bow to the right)
coords = [(-12, y0, z0), (-12, y1, z0), (-12, y0, z1), (-12, y1, z1)]
for v, c in zip(me.vertices, coords):
    v.co = c
uv = me.uv_layers.active.data
u0, u1 = crop[0] / W, crop[2] / W
v0, v1 = 1 - crop[3] / H, 1 - crop[1] / H
for loop in me.loops:
    c = me.vertices[loop.vertex_index].co
    uv[loop.index].uv = (u0 if abs(c.y - y0) < 1e-4 else u1, v0 if abs(c.z - z0) < 1e-4 else v1)
mat = bpy.data.materials.new('drawing'); mat.use_nodes = True
tex = mat.node_tree.nodes.new('ShaderNodeTexImage'); tex.image = img
bsdf = mat.node_tree.nodes['Principled BSDF']
mat.node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
me.materials.append(mat)

# --- planned galleass footprint (top view): hull beam 5.9 m and outriggers 10.6 m in the drawing
def rect(name, half_w, ya, yb, z, col):
    bpy.ops.mesh.primitive_plane_add()
    o = bpy.context.object; o.name = name
    for v, c in zip(o.data.vertices, [(-half_w, ya, z), (half_w, ya, z), (-half_w, yb, z), (half_w, yb, z)]):
        v.co = c
    o.color = col
    return o
stern_y, stem_y = to_ship(STERN_X, 0)[0], to_ship(STEM_X, 0)[0]
ram_y = to_ship(956, 0)[0]
rect('galleass_outriggers', 10.6 / 2 * k, stern_y + 3 * k, stem_y - 4 * k, 3.2, (0.1, 0.4, 0.9, 1))
rect('galleass_hull', 5.9 / 2 * k, stern_y, stem_y, 3.3, (0.1, 0.8, 0.3, 1))
rect('galleass_ram', 0.4 * k, stem_y, ram_y, 3.4, (0.9, 0.7, 0.1, 1))

# --- render setup (workbench, object colours, ortho)
sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading
sh.light = 'FLAT'; sh.color_type = 'TEXTURE'
sc.render.resolution_x, sc.render.resolution_y = 2000, 1000
sc.render.film_transparent = False
sc.world = bpy.data.worlds.new('w'); sc.world.color = (1, 1, 1)

cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam)
cam.data.type = 'ORTHO'; sc.camera = cam

def render(path, loc, rot, scale, color_type, xray):
    cam.location = loc; cam.rotation_euler = rot; cam.data.ortho_scale = scale
    sh.color_type = color_type
    sh.show_xray = xray; sh.xray_alpha = 0.45
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)

# side: camera at +X looking -X (bow +Y to the right), drawing behind the semi-transparent red hull
render(side_png, (40, 3, 8), (math.radians(90), 0, math.radians(90)), 72, 'TEXTURE', True)
# top: hide drawing, show footprint over the hull
pl.hide_render = True
for o in medit: o.color = (0.85, 0.15, 0.1, 1)
sh.color_type = 'OBJECT'
render(top_png, (0, 3, 60), (0, 0, math.radians(90)), 72, 'OBJECT', True)  # bow to the right
pl.hide_render = False
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
