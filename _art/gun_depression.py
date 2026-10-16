"""Depression check of the 24 guns (2026-10-16, user: falcons to -10 deg, falconets to -15 deg so they still hit close
ships): for every gun the barrel (part 1) is turned muzzle-down about its trunnion axis in STEP_DEG steps, at the
gun's traverse limits and centred (run out - recoiled, the muzzle is well inside), and tested against the hull (port
sills, linings, walls) and against its own carriage (part 0; the trunnion region is left out - it sits in the cheeks'
notches). Reports per gun the lowest clear angle and what stops it. Also runs the quoin solver to the target.

    blender -b ref/galleass_model.blend --python gun_depression.py -- ref/galleass_guns.blend [target_falcon target_falconet target_culverin]
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
argv = sys.argv[sys.argv.index('--') + 1:]
GUNS_BLEND = argv[0]
TARGET = {'falcon': -10.0, 'falconet': -15.0, 'culverin': -3.0}
if len(argv) >= 4:
    TARGET = {'falcon': float(argv[1]), 'falconet': float(argv[2]), 'culverin': float(argv[3])}
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model_geom, gun_layout
G = model_geom.load()
DIMS = gun_layout.load_dims()
PLACES = gun_layout.placements(G, DIMS)
TRAV = json.load(open(os.path.join(HERE, 'ref', 'galleass_traverse.json')))
GUNS = json.load(open(os.path.join(HERE, 'ref', 'galleass_guns.json')))
STEP_DEG = 0.5
LIFT = 0.02

with bpy.data.libraries.load(GUNS_BLEND, link=False) as (src, dst):
    dst.objects = [n for n in src.objects if n in ('galleass_culverin', 'galleass_falcon', 'galleass_falconet')]
GUN = {o.name[len('galleass_'):]: o for o in dst.objects}

def parts(o):
    """{part: (verts, tris)} in the gun frame; barrel without the trunnion region (it sits in the cheeks' notches)."""
    bm = bmesh.new(); bm.from_mesh(o.data)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    lay = bm.faces.layers.int.get('part')
    out = {}
    for f in bm.faces:
        p = f[lay] if lay is not None else 0
        c = f.calc_center_median()
        if p == 1 and abs(c.y) < 0.14 and abs(c.x) > 0.10:
            continue                                          # trunnions
        vs, ts = out.setdefault(p, ([], []))
        base = len(vs)
        vs.extend(v.co.copy() for v in f.verts)
        ts.append([base, base + 1, base + 2])
    bm.free()
    return out
PARTS = {k: parts(o) for k, o in GUN.items()}

def world_bvh(objs):
    verts, polys = [], []
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        me = o.evaluated_get(dg).to_mesh(); mw = o.matrix_world; base = len(verts)
        verts += [mw @ v.co for v in me.vertices]; polys += [[base + i for i in p.vertices] for p in me.polygons]
        o.evaluated_get(dg).to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys)
hull_objs = [o for o in bpy.data.objects if o.type == 'MESH' and
             (any(c.name == 'final' for c in o.users_collection) and o.name not in ('galleass_faction_paint', 'galleass_hull_plate')
              or o.name.startswith('mast_'))]
HULL = world_bvh(hull_objs)

def gun_frame(g, trav):
    t = TRAV['gun_' + g['name']]
    piv = Vector((0.0, t['pivot'][1], 0.0))
    return (Matrix.Translation(Vector(g['pos']) + Vector((0, 0, LIFT))) @ Matrix.Rotation(g['rot_z'], 4, 'Z') @
            Matrix.Translation(piv) @ Matrix.Rotation(math.radians(trav), 4, 'Z') @ Matrix.Translation(-piv))

def barrel_bvh(g, trav, elev):
    pz = GUNS['galleass_' + g['kind']]['elev']['pivot_z']
    E = Matrix.Translation((0, 0, pz)) @ Matrix.Rotation(math.radians(elev), 4, 'X') @ Matrix.Translation((0, 0, -pz))
    M = gun_frame(g, trav) @ E
    vs, ts = PARTS[g['kind']][1]
    return BVHTree.FromPolygons([M @ v for v in vs], ts)

def carriage_bvh(g, trav):
    M = gun_frame(g, trav)
    vs, ts = PARTS[g['kind']][0]
    return BVHTree.FromPolygons([M @ v for v in vs], ts)

print('DEPRESSION targets', TARGET)
summary = {}
for g in PLACES:
    t = TRAV['gun_' + g['name']]
    lowest, why = 0.0, None
    base_c = {tr: len(barrel_bvh(g, tr, 0.0).overlap(carriage_bvh(g, tr))) for tr in (t['min_deg'], 0.0, t['max_deg'])}
    e = 0.0
    while e - STEP_DEG >= TARGET[g['kind']] - 1e-6:
        e2 = e - STEP_DEG
        hit = None
        for tr in (t['min_deg'], 0.0, t['max_deg']):
            b = barrel_bvh(g, tr, e2)
            if b.overlap(HULL):
                hit = 'hull/port at traverse %+.1f' % tr; break
            if not os.environ.get('NO_CARRIAGE') and len(b.overlap(carriage_bvh(g, tr))) > base_c[tr]:
                hit = 'own carriage'; break
        if hit:
            why = hit; break
        e = e2
    lowest = e
    summary.setdefault(g['kind'], []).append(lowest)
    print('DEPRESSION %-16s %-9s clear down to %+5.1f  %s' % (g['name'], g['kind'], lowest, ('stopped by ' + why) if why else '(target reached)'))
for k, v in summary.items():
    print('DEPRESSION %-9s worst %+5.1f (target %+.1f)' % (k, max(v), TARGET[k]))

# quoin: can it lift the breech that far?
import gun_elevation as gel
print('DEPRESSION quoin params', {k: gel.QUOIN['galleass_' + k] for k in TARGET})
