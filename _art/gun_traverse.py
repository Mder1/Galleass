"""Traverse limits of the 24 guns for the gunnery add-on: each gun turns about a vertical axis through its muzzle (the
crew levers the trail sideways with handspikes, the muzzle stays in the port). For every gun and direction the angle
grows in STEP_DEG steps until the gun - run out and fully recoiled (recoil happens along the turned axis) - hits the
hull, a mast or another gun; then neighbouring guns are checked against each other at their limits (both turned
towards each other) and the larger limit shrinks until they clear.

    blender -b ref/galleass_model.blend --python gun_traverse.py -- ref/galleass_guns.blend ref/galleass_traverse.json

Output per gun (prefab entity gun_<name>): pivot (gun frame) and min/max degrees, positive = counter-clockwise seen from
above (Blender +Z; the muzzle swings to the gun's left). The cascabel lashing (cast off in action) is not tested.
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
argv = sys.argv[sys.argv.index('--') + 1:]
GUNS_BLEND, OUT = argv[0], argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model_geom, gun_layout
G = model_geom.load()
DIMS = gun_layout.load_dims()
PLACES = gun_layout.placements(G, DIMS)
RECOIL = {'culverin': 1.0, 'falcon': 0.8, 'falconet': 0.6}    # GalleassGunnery config.xml defaults
STEP_DEG, MAX_DEG = 0.5, 10.0                          # "slightly" (user 2026-10-15)
# falcons (broadside + stern chasers, 0.9 m wide ports since 2026-10-15): they turn about the carriage's front (the
# wheels) so the muzzle sweeps across the wider port (user: use more of the port horizontally); others about the muzzle
MAX_DEG_KIND = {'falcon': 25.0}
def pivot_y(kind):
    d = DIMS['galleass_' + kind]
    return d['front_y'] if kind == 'falcon' else d['muzzle_y']
LIFT = 0.02                                                   # off the deck: wheels and runners stand on it
NEIGHBOUR_DIST = 7.0

with bpy.data.libraries.load(GUNS_BLEND, link=False) as (src, dst):
    dst.objects = [n for n in src.objects if n in ('galleass_culverin', 'galleass_falcon', 'galleass_falconet')]
GUN = {o.name: o for o in dst.objects}

def gun_polys(o):
    """(verts, polys) of the gun without the lashing (part 3), in the gun frame."""
    bm = bmesh.new(); bm.from_mesh(o.data)
    lay = bm.faces.layers.int.get('part')
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if lay is not None and f[lay] == 3], context='FACES')
    bmesh.ops.triangulate(bm, faces=bm.faces)
    verts = [v.co.copy() for v in bm.verts]
    bm.verts.index_update()
    polys = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    return verts, polys
MESH = {k: gun_polys(GUN['galleass_' + k]) for k in RECOIL}

def gun_matrix(g, deg, recoil):
    d = DIMS['galleass_' + g['kind']]
    piv = Vector((0.0, pivot_y(g['kind']), d['axis_h']))
    return (Matrix.Translation(Vector(g['pos']) + Vector((0, 0, LIFT))) @ Matrix.Rotation(g['rot_z'], 4, 'Z') @
            Matrix.Translation(piv) @ Matrix.Rotation(math.radians(deg), 4, 'Z') @ Matrix.Translation(-piv) @
            Matrix.Translation((0.0, -recoil, 0.0)))

def gun_bvh(g, deg, recoil):
    verts, polys = MESH[g['kind']]
    m = gun_matrix(g, deg, recoil)
    return BVHTree.FromPolygons([m @ v for v in verts], polys)

def world_bvh(objs):
    verts, polys = [], []
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        me = o.evaluated_get(dg).to_mesh()
        mw = o.matrix_world; base = len(verts)
        verts += [mw @ v.co for v in me.vertices]
        polys += [[base + i for i in p.vertices] for p in me.polygons]
        o.evaluated_get(dg).to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys)

hull_objs = [o for o in bpy.data.objects if o.type == 'MESH' and
             (any(c.name == 'final' for c in o.users_collection) and o.name not in ('galleass_faction_paint', 'galleass_hull_plate')
              or o.name.startswith('mast_'))]
HULL = world_bvh(hull_objs)
REST = {g['name']: gun_bvh(g, 0.0, 0.0) for g in PLACES}
print('traverse: %d hull objects, %d guns' % (len(hull_objs), len(PLACES)))

def clashes(g, deg, others):
    """Names of what the gun hits at deg, run out or recoiled (others: {name: bvh})."""
    hit = []
    for r in (0.0, RECOIL[g['kind']] * 0.5, RECOIL[g['kind']]):
        b = gun_bvh(g, deg, r)
        if b.overlap(HULL): hit.append('hull' + ('' if r == 0 else '(recoiled)'))
        for n, ob in others.items():
            if b.overlap(ob): hit.append(n)
        if hit:
            break
    return hit

res, base_hits = {}, {}
for g in PLACES:
    others = {n: b for n, b in REST.items() if n != g['name']}
    base = clashes(g, 0.0, others)
    if base:
        print('  %-18s ALREADY CLASHES at 0 deg: %s' % (g['name'], base))
    lim, why = {}, {}
    for sign in (1, -1):
        a = 0.0
        while a + STEP_DEG <= MAX_DEG_KIND.get(g['kind'], MAX_DEG) + 1e-6:
            h = clashes(g, sign * (a + STEP_DEG), others)
            if h and h != base:
                why[sign] = h; break
            a += STEP_DEG
        lim[sign] = a
    res[g['name']] = {'max': lim[1], 'min': -lim[-1], 'why': why}
    print('  %-18s -%4.1f .. +%4.1f   (%s | %s)' % (g['name'], lim[-1], lim[1], why.get(-1, 'free'), why.get(1, 'free')))

# pairs: both turned towards each other at their limits
byname = {g['name']: g for g in PLACES}
pairs = [(a, b) for a in byname for b in byname if a < b and
         (Vector(byname[a]['pos']) - Vector(byname[b]['pos'])).length < NEIGHBOUR_DIST]
changed = True
while changed:
    changed = False
    for an, bn in pairs:
        ga, gb = byname[an], byname[bn]
        for ka in ('min', 'max'):
            for kb in ('min', 'max'):
                da, db = res[an][ka], res[bn][kb]
                if da == 0 and db == 0:
                    continue
                hit = False
                for ra in (0.0, RECOIL[ga['kind']]):
                    for rb in (0.0, RECOIL[gb['kind']]):
                        if gun_bvh(ga, da, ra).overlap(gun_bvh(gb, db, rb)):
                            hit = True
                if hit:                                   # shrink the larger one
                    if abs(da) >= abs(db):
                        res[an][ka] = math.copysign(abs(da) - STEP_DEG, da)
                    else:
                        res[bn][kb] = math.copysign(abs(db) - STEP_DEG, db)
                    changed = True
                    print('  pair %s %s %+.1f / %s %s %+.1f -> shrunk' % (an, ka, da, bn, kb, db))

out = {}
for g in PLACES:
    d = DIMS['galleass_' + g['kind']]
    r = res[g['name']]
    out['gun_' + g['name']] = {'kind': g['kind'], 'pivot': [0.0, pivot_y(g['kind']), d['axis_h']],
                               'min_deg': r['min'], 'max_deg': r['max']}
json.dump(out, open(OUT, 'w'), indent=1)
print('TRAVERSE')
for n, v in out.items():
    print('  %-20s %-9s %+5.1f .. %+5.1f' % (n, v['kind'], v['min_deg'], v['max_deg']))
print('written', OUT)
