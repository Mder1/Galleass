"""Preview of the galleass's current rigs in the model (re-rig phase 0): the vanilla lateen masts and yards placed with
the world frames of our built prefab (prefab_layout.py -> ref/galleass_layout.json), the rigs' simple ropes as
lines (rest pose), the sail free bones and the rail cleats (knot points) as markers.

    python3 prefab_layout.py ../AssetPackages/nested_prefabs_packed.xml,../../NavalDLC/AssetPackages/nested_prefabs_packed.xml galleass_ship_nested ref/galleass_layout.json
    blender -b ref/galleass_model.blend --python rig_preview.py -- ref/galleass_layout.json ref/rig renders/rig_now [out.blend]

Meshes come from NavalDLC sails.tpac (tpac_tools/mesh_extract.py -> ref/rig/*.obj, Bannerlord frame: x right,
y forward, z up).
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index('--') + 1:]
LAYOUT, MESHDIR, OUT = argv[:3]
SAVE = argv[3] if len(argv) > 3 else None
os.makedirs(OUT, exist_ok=True)
rows = json.load(open(LAYOUT))

def mat(color, name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = color
    return m

M_ROPE = mat((0.9, 0.75, 0.3, 1), 'pv_rope_static')
M_YARD = mat((0.95, 0.25, 0.2, 1), 'pv_rope_yard')
M_DYN = mat((0.3, 0.6, 1.0, 1), 'pv_rope_dyn')
M_KNOT = mat((0.1, 0.9, 0.2, 1), 'pv_knot')
M_BONE = mat((1.0, 0.1, 1.0, 1), 'pv_bone')
coll = bpy.data.collections.new('rig_now'); bpy.context.scene.collection.children.link(coll)

_mesh_cache = {}
def obj_mesh(name):
    if name in _mesh_cache:
        return _mesh_cache[name]
    path = os.path.join(MESHDIR, name + '.obj')
    if not os.path.exists(path):
        return None
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path, forward_axis='Y', up_axis='Z')
    new = [o for o in set(bpy.data.objects) - before]
    # keep LOD0 only (sub-meshes .0 are LOD0 pieces? mesh_extract writes one object per sub-mesh)
    keep = [o for o in new if o.type == 'MESH']
    bm = bmesh.new()
    for o in keep:
        if o.name.split('.')[-1] in ('0', '1') or len(keep) <= 2:
            me = o.data.copy(); me.transform(o.matrix_world); bm.from_mesh(me); bpy.data.meshes.remove(me)
    for o in new:
        bpy.data.objects.remove(o)
    me = bpy.data.meshes.new('pv_' + name); bm.to_mesh(me); bm.free()
    _mesh_cache[name] = me
    return me

def place(row, meshname, color=None):
    me = obj_mesh(meshname)
    if me is None:
        print('PV missing mesh', meshname); return
    o = bpy.data.objects.new(row['name'], me); coll.objects.link(o)
    m3 = Matrix(row['mat'])
    M = m3.to_4x4(); M.translation = Vector(row['pos'])
    o.matrix_world = M
    if color: o.color = color

def line(a, b, m, r=0.03):
    a, b = Vector(a), Vector(b)
    d = b - a
    if d.length < 1e-4: return
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=r, depth=d.length, location=(a + b) / 2)
    o = bpy.context.active_object
    o.rotation_euler = d.to_track_quat('Z', 'Y').to_euler()
    o.data.materials.append(m)
    for c in o.users_collection: c.objects.unlink(o)
    coll.objects.link(o)

def marker(p, m, r=0.12):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=r, location=p)
    o = bpy.context.active_object; o.data.materials.append(m)
    for c in o.users_collection: c.objects.unlink(o)
    coll.objects.link(o)

# masts and yards (MASTS_BLEND=ref/galleass_masts.blend: our masts from mast_model.py instead of the vanilla ones)
OUR_MASTS = {}
if os.environ.get('MASTS_BLEND'):
    with bpy.data.libraries.load(os.environ['MASTS_BLEND'], link=False) as (src, dst):
        dst.meshes = [n for n in src.meshes if n.startswith('galleass_mast_') and '_lod' not in n]
    OUR_MASTS = {m.name.replace('galleass_mast_', 'ship_mast_lateen_a_'): m for m in dst.meshes}
    _mesh_cache.update(OUR_MASTS)
for r in rows:
    if '/sail_holder/' not in r['path']:
        continue
    for mn in r['meshes']:
        if mn.startswith('galleass_mast_'):                   # our masts in the prefab: their vanilla stand-in
            mn = mn.replace('galleass_mast_', 'ship_mast_lateen_a_')
        if mn.startswith('ship_mast_lateen') or mn.startswith('ship_yard_lateen'):
            place(r, mn)
        elif os.environ.get('FITTINGS') and os.path.exists(os.path.join(MESHDIR, mn + '.obj')):
            place(r, mn)                                      # vanilla fittings (bands, pegs, pulleys, rope piles)
# ropes: walk rows in order; a simple_rope_nested owns the following rope_start / rope_end rows
cur = None; ropes = []
for r in rows:
    if '/sail_holder/' not in r['path']:
        continue
    if 'simple_rope' in r['tags'] or r['name'] == 'simple_rope_nested':
        cur = {'path': r['path'], 'start': None, 'end': None, 'yard': set()}; ropes.append(cur); continue
    if cur and r['path'].rsplit('/', 1)[0] == cur['path'] and r['name'] in ('rope_start', 'rope_end'):
        key = 'start' if r['name'] == 'rope_start' else 'end'
        cur[key] = r['pos']
        if 'attached_to_yard' in r['tags']: cur['yard'].add(key)
n = 0
for c in ropes:
    if c['start'] and c['end']:
        line(c['start'], c['end'], M_YARD if c['yard'] else M_ROPE); n += 1
print('PV ropes drawn', n, 'of', len(ropes))
for r in rows:
    if 'knot_point' in r['tags']:
        marker(r['pos'], M_KNOT, 0.08)
    if 'free_bone' in r['tags']:
        marker(r['pos'], M_BONE, 0.25)
        print('PV free bone', r['path'].split('/sail_holder/')[1].split('/')[0], r['name'], r['pos'], r['tags'])

if SAVE:
    bpy.ops.wm.save_as_mainfile(filepath=SAVE, copy=True)

sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'MATERIAL'
sc.display.shading.show_cavity = True
for o in bpy.data.objects:
    if o.name in ('galleass_faction_paint', 'galleass_hull_plate'): o.hide_render = True
cam = bpy.data.objects.new('pv_cam', bpy.data.cameras.new('pv_cam')); sc.collection.objects.link(cam); sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = 1800, 1100
def shot(fname, loc, tgt, lens=30, ortho=None):
    cam.location = loc
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
    else: cam.data.type = 'PERSP'; cam.data.lens = lens
    sc.render.filepath = os.path.join(OUT, fname); bpy.ops.render.render(write_still=True)
shot('now_side.png', (60, 2, 16), (0, 2, 16), ortho=70)
shot('now_top.png', (0, 2, 90), (0, 2.001, 0), ortho=70)
shot('now_front.png', (0, 70, 16), (0, 0, 16), ortho=40)
shot('now_persp.png', (28, 38, 26), (0, 0, 12), lens=28)
shot('now_deck.png', (7, -24, 10), (0, 10, 6), lens=24)
if os.environ.get('FITTINGS'):
    def foot(mast, dz_cam, look):
        mm = next(r for r in rows if mast in r['path'] and r['name'] == 'mast_mesh')
        c = Vector(mm['pos']) + Matrix(mm['mat']) @ Vector((0, 0, dz_cam))
        return c
    for rig, tag in (('lateen_sail_large_nested', 'main'), ('lateen_sail_medium_nested', 'fore'), ('lateen_sail_small_nested', 'mizzen')):
        mm = next(r for r in rows if rig in r['path'] and r['name'] == 'mast_mesh')
        M = Matrix(mm['mat'])
        for k, zz in enumerate((5.5, 9.0)):
            c = Vector(mm['pos']) + M @ Vector((0, 0, zz if tag != 'fore' else zz - 3.0))
            shot('foot_%s_%d.png' % (tag, k), c + Vector((-2.2, -2.0, 0.6)), c, lens=35)
            shot('foot_%s_%d_b.png' % (tag, k), c + Vector((2.0, 2.2, 0.4)), c, lens=35)
print('PV done')
