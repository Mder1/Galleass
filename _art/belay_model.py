"""Belaying fittings for the galleass's running rigging (user 2026-10-18: galley-style pin rails and bitts instead of the
vanilla cleats spread along the cap rail), built parametrically, UV'd, exported for the Modding Kit.

    blender -b --factory-startup --python belay_model.py -- ref/galleass_belay.blend ../AssetSources/export [renders/belay]

Meshes (material galleass_trim = oak, galleass_iron = bolts / straps):
- galleass_pinrail_<n> (n = 3, 4): a pin board - an oak doubling plank laid on a cap rail (waist bulwark, forecastle
  parapet) with n turned belaying pins through it. ORIGIN ON THE CAP'S TOP CENTRE LINE, plank along +-Y.
- galleass_bitts_<n> (n = 3): two square posts with a crossbar and n pins through it, free-standing on a deck.
  ORIGIN ON THE DECK under the middle, crossbar along +-Y. With a convex collision body bo_galleass_bitts_<n>.
The pins' rope points (a hand above the bar, where the fall is turned round the pin) go to ref/galleass_belay_pins.json
in each fitting's frame; the prefab puts one knot_point there per pin (the game ties braces and sheets to the nearest).
Every pin carries crossing belaying turns round its shank (material galleass_rope, rope_geom UVs) centred on that point,
as vanilla's cleats carry their knot mesh (knot_point_a_1): the game's rope then runs into the turns (user 2026-10-27:
the falls ended bare at the pins).
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
OUT_BLEND, OUT_FBX, RENDERS = argv[0], argv[1], (argv[2] if len(argv) > 2 else None)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rope_geom as rg

ROLE = {'wood': 'galleass_trim', 'iron': 'galleass_iron', 'rope': 'galleass_rope'}
UV_S = {'galleass_trim': 0.135, 'galleass_iron': 0.5}
COL = {'wood': (0.36, 0.24, 0.14, 1), 'iron': (0.16, 0.16, 0.17, 1), 'rope': (0.80, 0.72, 0.55, 1)}
ROLES = list(ROLE)

PIN_SPACING = 0.20
PIN = [(-0.20, 0.014), (-0.02, 0.016), (-0.02, 0.026), (0.0, 0.026), (0.01, 0.019), (0.10, 0.017), (0.13, 0.021),
       (0.15, 0.020), (0.16, 0.012), (0.165, 0.0)]                    # turned pin: (z above the bar top, radius)
ROPE_DZ = 0.06                                                          # rope point above the bar top
TURNS = dict(r=0.016, n=4, half_h=0.02, gap=0.0, zc=0.06)               # belaying turns: rope radius, crossing turns, half their
                                                                        # tilt height, play off the pin, centre above the bar
BOARD = dict(width=0.24, thick=0.05)                                    # pin board on the cap rail
BITTS = dict(post=0.14, height=1.0, bar_z=0.78, bar_h=0.11, bar_d=0.12, cap=0.04)

for c in list(bpy.data.objects): bpy.data.objects.remove(c)
MATS = {}
for role, kit in ROLE.items():
    m = bpy.data.materials.get(kit) or bpy.data.materials.new(kit)
    m.diffuse_color = COL[role]; MATS[role] = m

def tag(faces, role):
    for f in faces: f.material_index = ROLES.index(role)

def box(bm, x0, x1, y0, y1, z0, z1, role='wood'):
    r = bmesh.ops.create_cube(bm, size=1.0)
    for v in r['verts']:
        v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0), (y0 + y1) / 2 + v.co.y * (y1 - y0), (z0 + z1) / 2 + v.co.z * (z1 - z0)))
    tag(list({f for v in r['verts'] for f in v.link_faces}), role)

def lathe(bm, prof, at, segs=12, role='wood'):
    """Closed solid of revolution about +Z at 'at': prof = [(z, r)], r 0 at an end closes it in a point."""
    rings = []
    for z, r in prof:
        if r <= 0:
            rings.append([bm.verts.new(Vector(at) + Vector((0, 0, z)))])
        else:
            rings.append([bm.verts.new(Vector(at) + Vector((r * math.cos(2 * math.pi * k / segs), r * math.sin(2 * math.pi * k / segs), z)))
                          for k in range(segs)])
    faces = []
    for a, b in zip(rings, rings[1:]):
        for k in range(segs):
            kk = (k + 1) % segs
            if len(a) == 1: faces.append(bm.faces.new((a[0], b[k], b[kk])))
            elif len(b) == 1: faces.append(bm.faces.new((a[k], a[kk], b[0])))
            else: faces.append(bm.faces.new((a[k], a[kk], b[kk], b[k])))
    if len(rings[0]) > 1: faces.append(bm.faces.new(list(reversed(rings[0]))))
    if len(rings[-1]) > 1: faces.append(bm.faces.new(rings[-1]))
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    tag(faces, role)

def bolt(bm, x, y, z, axis='x', r=0.012, l=0.012):
    seg = 8
    vs0, vs1 = [], []
    for k in range(seg):
        a = 2 * math.pi * k / seg
        u, w = r * math.cos(a), r * math.sin(a)
        if axis == 'x':
            vs0.append(bm.verts.new((x, y + u, z + w))); vs1.append(bm.verts.new((x + l, y + u, z + w)))
        else:
            vs0.append(bm.verts.new((x + u, y + w, z))); vs1.append(bm.verts.new((x + u, y + w, z + l)))
    fs = [bm.faces.new(vs0[::-1]), bm.faces.new(vs1)]
    for k in range(seg):
        kk = (k + 1) % seg
        fs.append(bm.faces.new((vs0[k], vs0[kk], vs1[kk], vs1[k])))
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    tag(fs, 'iron')

def finish(bm, name):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for m in MATS.values(): me.materials.append(m)
    for p in me.polygons: p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(40))
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    return o

def belay_turns(bm, y, z0):
    """Figure-of-eight turns of the fall round the pin at y whose bar top is z0: n turns round the shank, each a loop
    tilted the other way (z = centre +- h sin(angle): they cross on the near and far side), a little further out each
    turn so they lie on each other; the end tucked under the last turn, down to the bar."""
    r, h = TURNS['r'], TURNS['half_h']
    zc = z0 + TURNS['zc']                       # round ROPE_DZ, thick enough to hide the game's rope end (user 2026-10-27)
    R0 = max(rr for zz, rr in PIN if 0.0 < zz < 0.11) + r + TURNS['gap']   # round the shank, clear of it
    pts = []
    steps = 12
    for k in range(TURNS['n']):
        s = 1 if k % 2 == 0 else -1
        R = R0 + 0.2 * r * k
        for i in range(steps):
            a = 2 * math.pi * (k + i / steps)
            pts.append(Vector((R * math.cos(a), y + R * math.sin(a), zc + s * h * math.sin(a))))
    R = R0 + 0.2 * r * TURNS['n']
    pts.append(Vector((R, y, zc)))
    pts.append(Vector((R + 0.006, y + 0.02, z0 + r + 0.012)))           # the tail laid down on the bar
    pts.append(Vector((R + 0.01, y + 0.06, z0 + r)))
    n0 = len(bm.faces)
    rg.rope(bm, rg.catmull(pts, 0.02), r, segs=6)            # ~550 tris a pin (56 pins aboard)
    bm.faces.ensure_lookup_table()
    tag(bm.faces[n0:], 'rope')

def pin_ys(n):
    return [PIN_SPACING * (i - (n - 1) / 2) for i in range(n)]

def build_pinrail(n, pins):
    """Pin board on a cap rail: an oak doubling plank laid along the rail, nailed down, the pins through plank and
    rail (galley sides were too low for a rail on the inner face: a fall from a yard out over the side would cut
    through the cap - rig_check, 2026-10-18). ORIGIN ON THE CAP RAIL'S TOP CENTRE LINE, plank along +-Y."""
    bm = bmesh.new()
    w, t = BOARD['width'], BOARD['thick']
    L = n * PIN_SPACING + 0.16
    box(bm, -w / 2, w / 2, -L / 2, L / 2, 0.0, t)
    for s in (-1, 1):                                                        # spikes at the ends
        for k in (-1, 1):
            bolt(bm, k * w * 0.3, s * (L / 2 - 0.04), t, 'z', r=0.011, l=0.006)   # nail / spike heads
    for y in pin_ys(n):
        lathe(bm, [(z + t, r) for z, r in PIN], (0.0, y, 0.0))
        belay_turns(bm, y, t)
    name = 'galleass_pinrail_%d' % n
    pins[name] = [[0.0, round(y, 4), round(t + ROPE_DZ, 4)] for y in pin_ys(n)]
    return finish(bm, name)

def build_bitts(n, pins):
    bm = bmesh.new()
    p, H, bz, bh, bd = BITTS['post'], BITTS['height'], BITTS['bar_z'], BITTS['bar_h'], BITTS['bar_d']
    L = n * PIN_SPACING + 0.10                                                # clear span between the posts
    for s in (-1, 1):
        yc = s * (L / 2 + p / 2)
        box(bm, -p / 2, p / 2, yc - p / 2, yc + p / 2, 0.0, H - BITTS['cap'])
        lathe(bm, [(H - BITTS['cap'], p * 0.62), (H - 0.01, p * 0.55), (H, 0.0)], (0, yc, 0.0), segs=12)   # rounded post head
        bolt(bm, -bd / 2 - 0.012, yc, bz - bh / 2, 'x', r=0.013, l=bd + 0.024)  # bolt through post + bar
    box(bm, -bd / 2, bd / 2, -L / 2 - p, L / 2 + p, bz - bh, bz)               # crossbar, through both posts
    for y in pin_ys(n):
        lathe(bm, PIN, (0.0, y, bz))
        belay_turns(bm, y, bz)
    name = 'galleass_bitts_%d' % n
    pins[name] = [[0.0, round(y, 4), round(bz + ROPE_DZ, 4)] for y in pin_ys(n)]
    return finish(bm, name)

def add_uvs(o):
    me = o.data
    uv = me.uv_layers[0] if me.uv_layers else me.uv_layers.new(name='UVMap')
    for poly in me.polygons:
        n = poly.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        i, j = [k for k in range(3) if k != ax]
        if ROLES[poly.material_index] == 'rope':
            continue
        s = UV_S[ROLE[ROLES[poly.material_index]]]
        for li in poly.loop_indices:
            p = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (p[i] * s, p[j] * s)
    col = me.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
    for d in col.data: d.color = (1, 1, 1, 1)
    used = sorted({p.material_index for p in me.polygons})
    idx = [used.index(p.material_index) for p in me.polygons]
    mats = [me.materials[i] for i in used]
    me.materials.clear()
    for m in mats: me.materials.append(m)
    for p, i in zip(me.polygons, idx): p.material_index = i

def export(o):
    bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT_FBX, o.name + '.fbx'), use_selection=True, object_types={'MESH'},
                             use_mesh_modifiers=True, mesh_smooth_type='FACE', use_tspace=False, axis_forward='Y',
                             axis_up='Z', apply_unit_scale=True, global_scale=1.0, bake_anim=False, path_mode='STRIP',
                             add_leaf_bones=False)
    print('EXPORT %-30s tris %6d  materials %s' % (o.name + '.fbx', sum(len(p.vertices) - 2 for p in o.data.polygons),
                                                    [m.name for m in o.data.materials]))

def body(o):
    """Collision for the bitts: one box over posts and bar (a man walks round them)."""
    xs, ys, zs = zip(*[v.co for v in o.data.vertices])
    bm = bmesh.new()
    box(bm, min(xs), max(xs), min(ys), max(ys), 0.0, max(zs))
    name = 'bo_' + o.name
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    me.materials.append(bpy.data.materials.get('wood') or bpy.data.materials.new('wood'))
    bo = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(bo)
    return bo

pins = {}
objs = [build_pinrail(3, pins), build_pinrail(4, pins), build_bitts(3, pins)]
os.makedirs(OUT_FBX, exist_ok=True)
for o in objs:
    add_uvs(o); o.data.name = o.name
    export(o)
for o in [x for x in objs if x.name.startswith('galleass_bitts_')]:
    export(body(o))
json.dump({'pins': pins, 'board': BOARD, 'bitts': BITTS, 'pin_spacing': PIN_SPACING},
          open(os.path.join(HERE, 'ref', 'galleass_belay_pins.json'), 'w'), indent=1)

if RENDERS:
    os.makedirs(RENDERS, exist_ok=True)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'MATERIAL'
    sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = 1400, 900
    for i, o in enumerate(objs):
        o.location = (-0.1 if 'pinrail' in o.name else 0.8, -1.0 + (i % 2) * 1.4, 0.0 if 'bitts' in o.name else 1.5)
    for o in [x for x in bpy.data.objects if x.name.startswith('bo_')]:
        o.hide_render = True
    wall = bpy.data.meshes.new('wall'); bm = bmesh.new(); box(bm, -0.2, 0.0, -1.8, 1.4, 0.0, 1.5); bm.to_mesh(wall); bm.free()
    w = bpy.data.objects.new('wall', wall); sc.collection.objects.link(w)
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    def shot(fname, loc, tgt, lens=35):
        cam.location = loc; cam.data.lens = lens
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(RENDERS, fname); bpy.ops.render.render(write_still=True)
    shot('belay_all.png', (3.2, -2.8, 2.0), (0.4, -0.3, 0.7), 35)
    shot('belay_pinrail.png', (1.3, -1.6, 1.5), (0.1, -1.0, 0.95), 45)
    shot('belay_bitts.png', (2.2, 0.2, 1.4), (0.8, 0.4, 0.7), 45)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print('belay done')
