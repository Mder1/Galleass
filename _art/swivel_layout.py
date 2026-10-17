"""Swivel guns (petriere da mascolo, user 2026-10-17) on the galleass's rails: traverse and elevation limits, clash
check of the gunners' steps, review renders.

    blender -b ref/galleass_model.blend --python swivel_layout.py -- ref/galleass_guns.blend ref/galleass_swivels.json [<render dir>] [<out.blend>]

Each swivel (gun_layout.swivel_placements) turns about its pin (vertical through the origin) and tilts about the
trunnions (x axis at axis_h). Its moving parts (yoke, barrel, chamber, wedge - not the mount block on the rail) are
swept against the hull ('final' + masts), the other guns (at rest and at their traverse limits), their live ropes,
the static gun rigging and the standing rigging (AssetSources/export FBX). Traverse: outward-facing rest, then
STEP_DEG steps each way up to MAX_TRAV at the lowest, level and highest elevation; elevation: at heading 0. Output per
swivel (prefab entity gun_<name>): pos, heading, min/max traverse (+ = CCW from above, as galleass_traverse.json),
min/max elevation.
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
argv = sys.argv[sys.argv.index('--') + 1:]
GUNS_BLEND, OUT = argv[0], argv[1]
RENDERS = argv[2] if len(argv) > 2 else None
SAVE = argv[3] if len(argv) > 3 else None
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model_geom, gun_layout
G = model_geom.load()
DIMS = gun_layout.load_dims()
PLACES = gun_layout.placements(G, DIMS)
SWIVELS = gun_layout.swivel_placements(G, **json.loads(os.environ.get('SWIVEL_YS', '{}')))
TRAV = json.load(open(os.path.join(HERE, 'ref', 'galleass_traverse.json')))
ROPES = json.load(open(os.path.join(HERE, 'ref', 'galleass_gun_ropes.json')))
RECOIL = {'culverin': 1.0, 'falcon': 0.8, 'falconet': 0.6}
STEP_DEG, MAX_TRAV = 1.0, float(os.environ.get('SWIVEL_MAX_TRAV', 80.0))
# the gunner walks round the pin with the tail (~1.2 m out): on a waist step (1.5 m long) +-45 keeps him on it; on the
# poop deck +-60 keeps him off the awning posts by the rail
CAP_STEP, CAP_DECK = 45.0, 60.0
PE = DIMS['galleass_petriera']
AH = PE['axis_h']; EMIN, EMAX = PE['elev']['min_deg'], PE['elev']['max_deg']

with bpy.data.libraries.load(GUNS_BLEND, link=False) as (src, dst):
    dst.objects = [n for n in src.objects if n.startswith('galleass_')]
GUN = {o.name: o for o in dst.objects}

def polys_of(o, keep=lambda grp: True):
    bm = bmesh.new(); bm.from_mesh(o.data)
    lay = bm.faces.layers.int.get('part')
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if lay is not None and not keep(f[lay])], context='FACES')
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.verts.index_update()
    res = ([v.co.copy() for v in bm.verts], [[v.index for v in f.verts] for f in bm.faces])
    bm.free()
    return res
# swivel: yoke (4) turns with the traverse; barrel (1), chamber (5), wedge (6) also tilt; the fuse rides the chamber
YOKE = polys_of(GUN['galleass_petriera'], lambda g: g == 4)
TILT = polys_of(GUN['galleass_petriera'], lambda g: g in (1, 5, 6))

def swivel_parts(sw, trav, elev):
    """World matrices of the yoke and the tilting parts."""
    base = Matrix.Translation(Vector(sw['pos'])) @ Matrix.Rotation(sw['rot_z'], 4, 'Z') @ Matrix.Rotation(math.radians(trav), 4, 'Z')
    tilt = base @ Matrix.Translation((0, 0, AH)) @ Matrix.Rotation(math.radians(elev), 4, 'X') @ Matrix.Translation((0, 0, -AH))
    return base, tilt

def swivel_bvh(sw, trav, elev):
    base, tilt = swivel_parts(sw, trav, elev)
    v, p = [base @ x for x in YOKE[0]], list(YOKE[1])
    n = len(v); v += [tilt @ x for x in TILT[0]]; p += [[n + i for i in q] for q in TILT[1]]
    return BVHTree.FromPolygons(v, p)

# ---------------------------------------------------------------- obstacles
def world_polys(objs):
    verts, polys = [], []
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        me = o.evaluated_get(dg).to_mesh()
        mw = o.matrix_world; base = len(verts)
        verts += [mw @ v.co for v in me.vertices]
        polys += [[base + i for i in p.vertices] for p in me.polygons]
        o.evaluated_get(dg).to_mesh_clear()
    return verts, polys

hull_objs = [o for o in bpy.data.objects if o.type == 'MESH' and
             (any(c.name == 'final' for c in o.users_collection) and o.name not in ('galleass_faction_paint', 'galleass_hull_plate')
              or o.name.startswith('mast_'))]
HULL = BVHTree.FromPolygons(*world_polys(hull_objs))
HULL_BY = {o.name: BVHTree.FromPolygons(*world_polys([o])) for o in hull_objs}

OBJ = {}                                                   # name -> (verts, polys) of the other obstacles
def add(name, verts, polys):
    v, p = OBJ.setdefault(name, ([], []))
    b = len(v); v.extend(verts); p.extend([[b + i for i in q] for q in polys])
GMESH = {k: polys_of(GUN['galleass_' + k], lambda g: g != 3) for k in RECOIL}
for g in PLACES:                                           # big guns: rest, traverse limits, recoiled
    t = TRAV['gun_' + g['name']]; piv = Vector((0.0, t['pivot'][1], 0.0))
    for deg in (t['min_deg'], 0.0, t['max_deg']):
        for r in (0.0, RECOIL[g['kind']]):
            M = (Matrix.Translation(Vector(g['pos'])) @ Matrix.Rotation(g['rot_z'], 4, 'Z') @ Matrix.Translation(piv) @
                 Matrix.Rotation(math.radians(deg), 4, 'Z') @ Matrix.Translation(-piv) @ Matrix.Translation((0, -r, 0)))
            add('gun ' + g['name'], [M @ v for v in GMESH[g['kind']][0]], GMESH[g['kind']][1])
def tube(a, b, r):
    a, b = Vector(a), Vector(b); d = b - a
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=r, radius2=r, depth=d.length,
                                            matrix=Matrix.Translation((a + b) / 2) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4())
    res = ([v.co.copy() for v in bm.verts], [[v.index for v in f.verts] for f in bm.faces]); bm.free()
    return res
for r in ROPES['ropes']:
    if (Vector(r['end']) - Vector(r['start'])).length > 1e-4:
        add('gun ropes', *tube(r['start'], r['end'], 0.04))
for fbx, label in (('galleass_gun_rigging.fbx', 'gun rigging'), ('galleass_standing_rigging.fbx', 'standing rigging')):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=os.path.join(HERE, '..', 'AssetSources', 'export', fbx))
    for o in set(bpy.data.objects) - before:
        if o.type == 'MESH' and '_lod' not in o.name:
            add(label, *world_polys([o]))
        o.hide_render = True; o.hide_set(True)
OBST = {n: BVHTree.FromPolygons(v, p) for n, (v, p) in OBJ.items()}
print('SWIVELS: %d hull objects, obstacles %s' % (len(hull_objs), ', '.join(sorted({n.split(' ')[0] for n in OBST}))))

def clashes(sw, trav, elev, others):
    b = swivel_bvh(sw, trav, elev)
    hit = ['hull ' + n for n, o in HULL_BY.items() if b.overlap(o)] if b.overlap(HULL) else []
    hit += [n for n, o in OBST.items() if b.overlap(o)]
    hit += [n for n, o in others.items() if b.overlap(o)]
    return hit

res = {}
REST = {sw['name']: swivel_bvh(sw, 0.0, 0.0) for sw in SWIVELS}
for sw in SWIVELS:
    others = {'swivel ' + n: b for n, b in REST.items() if n != sw['name']}
    base = clashes(sw, 0.0, 0.0, others)
    if base:
        print('  %-14s CLASHES AT REST: %s' % (sw['name'], base))
    el = {}
    for sign, lim in ((-1, EMIN), (1, EMAX)):
        a = 0.0
        while abs(a) + 1.0 <= abs(lim) + 1e-6 and not clashes(sw, 0.0, a + sign, others):
            a += sign
        el[sign] = a
    tr, why = {}, {}
    cap = min(MAX_TRAV, CAP_STEP if sw['step'] else CAP_DECK)
    for sign in (1, -1):
        a = 0.0
        while a + STEP_DEG <= cap + 1e-6:
            h = set()
            for e in (0.0, el[1]):
                h |= set(clashes(sw, sign * (a + STEP_DEG), e, others))
            if h - set(base):
                why[sign] = sorted(h); break
            a += STEP_DEG
        tr[sign] = a
    # lowest elevation per traverse angle (swung along the rail the barrel meets it sooner)
    dep = []
    for t in range(-int(tr[-1]) // 5 * 5, int(tr[1]) + 1, 5):
        a = 0.0
        while a - 1.0 >= EMIN - 1e-6 and not clashes(sw, float(t), a - 1.0, others):
            a -= 1.0
        dep.append([float(t), a])
    res[sw['name']] = dict(sw, min_deg=-tr[-1], max_deg=tr[1], elev_min=el[-1], elev_max=el[1], depression=dep)
    print('  %-14s traverse -%4.0f .. +%4.0f   elevation %+3.0f .. %+3.0f   (%s | %s)' % (
        sw['name'], tr[-1], tr[1], el[-1], el[1], why.get(-1, 'free'), why.get(1, 'free')))
    print('      lowest elevation by traverse: ' + ' '.join('%+d:%+d' % (t, a) for t, a in dep))

# the gunners' steps: footprint boxes vs the hull above the deck, the big guns' sweeps, their ropes
STEP = GUN['galleass_petriera_step']
SV, SP = polys_of(STEP)
for sw in SWIVELS:
    if not sw['step']:
        continue
    M = Matrix.Translation((sw['pos'][0], sw['pos'][1], sw['deck_z'] + 0.005)) @ Matrix.Rotation(sw['rot_z'], 4, 'Z')
    b = BVHTree.FromPolygons([M @ v for v in SV], SP)
    hit = [n for n, o in OBST.items() if b.overlap(o)]
    hull = b.overlap(HULL)
    print('  step %-9s %s%s' % (sw['name'], 'hull: %d face pairs (stanchions / wall?) ' % len(hull) if hull else '',
                                ', '.join(hit) or 'clear'))

json.dump(res, open(OUT, 'w'), indent=1)
print('written', OUT)

# ---------------------------------------------------------------- preview
coll = bpy.data.collections.new('swivel_preview'); bpy.context.scene.collection.children.link(coll)
def place(src, name, M):
    o = bpy.data.objects.new(name, src.data); coll.objects.link(o); o.matrix_world = M
    return o
for g in PLACES:
    M = Matrix.Translation(Vector(g['pos'])) @ Matrix.Rotation(g['rot_z'], 4, 'Z')
    place(GUN['galleass_' + g['kind']], 'gun_' + g['name'], M)
for sw in SWIVELS:
    r = res[sw['name']]
    M = Matrix.Translation(Vector(sw['pos'])) @ Matrix.Rotation(sw['rot_z'], 4, 'Z')
    place(GUN['galleass_petriera'], 'gun_' + sw['name'], M)
    place(GUN['galleass_petriera_fuse'], 'gun_' + sw['name'] + '_fuse', M)
    if sw['stand']:
        place(GUN['galleass_petriera_stand'], 'stand_' + sw['name'], M)
    if sw['step']:
        place(STEP, 'step_' + sw['name'], Matrix.Translation((sw['pos'][0], sw['pos'][1], sw['deck_z'])) @ Matrix.Rotation(sw['rot_z'], 4, 'Z'))
if SAVE:
    bpy.ops.wm.save_as_mainfile(filepath=SAVE, copy=True)
    print('saved', SAVE)
if RENDERS:
    os.makedirs(RENDERS, exist_ok=True)
    for o in GUN.values(): o.hide_render = True
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'MATERIAL'
    sc.display.shading.show_cavity = True; sc.display.shading.show_shadows = True
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.name in ('galleass_faction_paint', 'galleass_hull_plate'):
            o.hide_render = True
    cam = bpy.data.objects.new('sw_cam', bpy.data.cameras.new('sw_cam')); sc.collection.objects.link(cam); sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
    def shot(fname, loc, tgt, lens=30):
        cam.location = loc
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        cam.data.lens = lens
        sc.render.filepath = os.path.join(RENDERS, fname)
        bpy.ops.render.render(write_still=True)
    for sw in SWIVELS:
        if sw['name'].endswith('+1'):
            p = Vector(sw['pos']); s = 1
            inward = Vector((-math.sin(math.radians(sw['heading'])), -math.cos(math.radians(sw['heading'])), 0))
            shot('sw_%s.png' % sw['name'], p + inward * 3.2 + Vector((0, -1.6, 0.9)), p + inward * 0.5 - Vector((0, 0, 0.4)), lens=26)
    shot('sw_waist_overview.png', (0.0, -16.0, 11.0), (5.0, 2.0, 4.6), lens=24)
    shot('sw_poop_overview.png', (-1.5, -12.5, 10.5), (2.5, -20.0, 7.6), lens=26)
    shot('sw_poop_stand.png', (0.6, -17.2, 8.3), (3.3, -19.6, 7.3), lens=28)
