"""Placement of the five gun-store stations on the galleass (user 2026-10-15): forecastle ground floor (culverins),
forecastle platform rear (falconets), waist port + starboard (falcons), aft by the cabin door (stern chasers + cabin
falconets). Each station is a row: powder keg, shot rack(s), scattershot basket(s) (no ladles on deck, user
2026-10-15); a grid search per station
finds the clear spot nearest the preferred point, keeping clear of: the hull and masts, every gun's full sweep (run
out and recoiled, at both traverse limits) and its gunner's spot, the live and static gun ropes, and the prefab's deck
props (crates, piles, cleats, troop spots ...).

    blender -b ref/galleass_model.blend --python stores_layout.py -- ref/galleass_guns.blend ref/galleass_stations.json renders/stores

Needs ref/galleass_layout.json (prefab_layout.py on the installed prefab), ref/galleass_traverse.json,
ref/galleass_gun_ropes.json, ref/galleass_stores.json and AssetSources/export/galleass_gun_rigging.fbx.
Output: ref/galleass_stations.json - per station its items {mesh, pos, rot_z} in the ship frame, and the balls / bags
(rack / basket seats) per item - for build_prefab.py.

LOADER SPOTS (2026-10-16: the add-on's formula spots beside the guns were often off the navmesh - loaders stuck): per
gun the place its loader waits and loads at, nearest to beside the run-in muzzle, ON THE SHIP'S NAVMESH
(NavMeshPrefabs/galleass_ship_navmesh.bin, centre and a 0.2 m ring) and clear of the hull, masts, every gun's sweep and
gunner, deck props, the stores just placed and the other loaders (ropes allowed: a man may stand by a tackle) ->
ref/galleass_loader_spots.json {gun entity: {local: [x, y, yaw] in the gun's frame (yaw as Mat3.RotateAboutUp, the
man faces the gun), ship: [x, y, z]}} for the add-on (GalleassGunnery/src/make_gun_data.py).
"""
import bpy, bmesh, collections, json, math, os, sys
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index('--') + 1:]
GUNS_BLEND, OUT, RENDERS = argv[0], argv[1], (argv[2] if len(argv) > 2 else None)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model_geom, gun_layout, navmesh
G = model_geom.load()
L = G['Z_LIFT']
DIMS = gun_layout.load_dims()
PLACES = gun_layout.placements(G, DIMS)
TRAV = json.load(open(os.path.join(HERE, 'ref', 'galleass_traverse.json')))
ROPES = json.load(open(os.path.join(HERE, 'ref', 'galleass_gun_ropes.json')))
STORES = json.load(open(os.path.join(HERE, 'ref', 'galleass_stores.json')))
LAYOUT = json.load(open(os.path.join(HERE, 'ref', 'galleass_layout.json')))
RECOIL = {'culverin': 1.0, 'falcon': 0.8, 'falconet': 0.6}
MARGIN = 0.12                                              # free space round every store
Z_GD, Z_PL = G['Z_GUN_DECK'] + L, G['FC_Z_PLATFORM'] + L
Z_POOP = G['SC_Z_FLOOR'] + 0.12 + L
SWIVELS = gun_layout.swivel_placements(G)

# ---------------------------------------------------------------- obstacles
def world_bvh(objs):
    verts, polys = [], []
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        me = o.evaluated_get(dg).to_mesh(); mw = o.matrix_world; base = len(verts)
        verts += [mw @ v.co for v in me.vertices]; polys += [[base + i for i in p.vertices] for p in me.polygons]
        o.evaluated_get(dg).to_mesh_clear()
    return verts, polys

hull_objs = [o for o in bpy.data.objects if o.type == 'MESH' and
             (any(c.name == 'final' for c in o.users_collection) and o.name not in ('galleass_faction_paint', 'galleass_hull_plate')
              or o.name.startswith('mast_'))]
HV, HP = world_bvh(hull_objs)
HULL = BVHTree.FromPolygons(HV, HP)

with bpy.data.libraries.load(GUNS_BLEND, link=False) as (src, dst):
    dst.objects = [n for n in src.objects if n in ('galleass_culverin', 'galleass_falcon', 'galleass_falconet')]
GUNMESH = {}
for o in dst.objects:
    me = o.data
    GUNMESH[o.name[len('galleass_'):]] = ([v.co.copy() for v in me.vertices], [list(p.vertices) for p in me.polygons])

OV, OP = [], []                                            # everything else, as one BVH
def add_mesh(verts, polys):
    base = len(OV); OV.extend(verts); OP.extend([[base + i for i in p] for p in polys])
def add_box(c, hx, hy, z0, z1, rot=0.0):
    ca, sa = math.cos(rot), math.sin(rot)
    pts = [Vector((c[0] + ca * x - sa * y, c[1] + sa * x + ca * y, z)) for z in (z0, z1) for x, y in
           ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))]
    add_mesh(pts, [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]])
def add_tube(a, b, r):
    a, b = Vector(a), Vector(b); d = b - a
    if d.length < 1e-6: return
    rot = d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=r, radius2=r, depth=d.length,
                                            matrix=Matrix.Translation((a + b) / 2) @ rot)
    add_mesh([v.co.copy() for v in bm.verts], [[v.index for v in f.verts] for f in bm.faces]); bm.free()

GUN_RANGES = {}                                             # gun -> (sweep p0, p1, rest p0, p1) in OP
GUNNER_RANGES = []                                          # the formula gunner boxes (stations keep clear of them)
for g in PLACES:                                            # gun sweeps + gunner spots
    d = DIMS['galleass_' + g['kind']]; t = TRAV['gun_' + g['name']]
    sw0 = len(OP); rest = recoiled = None
    piv = Vector((0.0, t['pivot'][1], 0.0))
    verts, polys = GUNMESH[g['kind']]
    for deg in (t['min_deg'], 0.0, t['max_deg']):
        for r in (0.0, RECOIL[g['kind']]):
            M = (Matrix.Translation(Vector(g['pos'])) @ Matrix.Rotation(g['rot_z'], 4, 'Z') @ Matrix.Translation(piv) @
                 Matrix.Rotation(math.radians(deg), 4, 'Z') @ Matrix.Translation(-piv) @ Matrix.Translation((0, -r, 0)))
            r0 = len(OP)
            add_mesh([M @ v for v in verts], polys)
            if deg == 0.0 and r == 0.0: rest = (r0, len(OP))
            if deg == 0.0 and r > 0.0: recoiled = (r0, len(OP))
        Mg = (Matrix.Translation(Vector(g['pos'])) @ Matrix.Rotation(g['rot_z'], 4, 'Z') @ Matrix.Translation(piv) @
              Matrix.Rotation(math.radians(deg), 4, 'Z') @ Matrix.Translation(-piv))
        gp = Mg @ Vector((d['half_w'] + 0.30, d['cascabel_y'] + 0.25, 0.0))
        b0 = len(OP); add_box(gp, 0.35, 0.35, gp.z + 0.02, gp.z + 1.7); GUNNER_RANGES.append((b0, len(OP)))
    GUN_RANGES['gun_' + g['name']] = (sw0, len(OP), rest, recoiled)
for sw in SWIVELS:                                          # swivel gunners' working areas (build_prefab SW_AREA)
    a = sw['rot_z']; ca_, sa_ = math.cos(a), math.sin(a)
    c = (sw['pos'][0] + ca_ * 0.0 - sa_ * (-0.75), sw['pos'][1] + sa_ * 0.0 + ca_ * (-0.75))
    add_box(c, 1.2, 0.85, sw['deck_z'] + 0.02, sw['deck_z'] + 1.7, a)
ROPE_P0 = len(OP)
for r in ROPES['ropes']:                                    # live ropes (rest position, fat)
    add_tube(r['start'], r['end'], 0.06)
ROPE_P1 = len(OP)
rig_fbx = os.path.join(HERE, '..', 'AssetSources', 'export', 'galleass_gun_rigging.fbx')
before = set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=rig_fbx)
for o in set(bpy.data.objects) - before:                    # static rigging: ringbolts, blocks, heaps
    if o.type == 'MESH' and '_lod' not in o.name:
        v, p = world_bvh([o]); add_mesh(v, p)
    o.hide_render = True
GUNPARTS = ('quoin', 'lashing', 'fuse', 'barrel', 'gun_', 'block_', 'rope_', 'gunner')
props = 0
for e in LAYOUT:                                            # the prefab's deck props
    z = e['pos'][2]
    near = min(abs(z - Z_GD), abs(z - Z_PL), abs(z - Z_POOP))
    name = e.get('name', '')
    if near > 0.6 or any(name.startswith(p) for p in GUNPARTS) or any(t in ('gun_store', 'store_ball', 'store_bag') for t in e['tags']):
        continue                                            # (the stores themselves, once in the prefab)
    # (crew standing spots are no obstacle since 2026-10-16: build_prefab.py moves them off the stores and the gun
    # crews' places - counting them here kept the platform guns from getting places at all)
    if (e.get('meshes') or 'barrier' in name) and not name.startswith('sp_troop'):   # (spots carry an editor icon mesh)
        add_box(e['pos'], 0.4, 0.4, z + 0.02, z + 1.2); props += 1
KEEP = json.load(open(os.path.join(HERE, 'ref', 'galleass_keepclear.json')))     # build_prefab.py: stair landings
KEEP_P0 = len(OP)
for x0, x1, y0, y1, z in KEEP['stair_clear']:
    add_box(((x0 + x1) / 2, (y0 + y1) / 2), (x1 - x0) / 2, (y1 - y0) / 2, z + 0.02, z + 1.7)
KEEP_P1 = len(OP)
OBST = BVHTree.FromPolygons(OV, OP)
OBST_NR = BVHTree.FromPolygons(OV, OP[:ROPE_P0] + OP[ROPE_P1:])     # without the live ropes (loader spots)
# pickup points may stand in the walkways (a man takes his item and goes): no ropes, no keep-clear lanes
OBST_PK = BVHTree.FromPolygons(OV, [p for i, p in enumerate(OP) if not (ROPE_P0 <= i < ROPE_P1 or KEEP_P0 <= i < KEEP_P1)])
print('LAYOUT obstacles: hull %d polys, others %d polys (%d props)' % (len(HP), len(OP), props))

# ---------------------------------------------------------------- stations
racks, baskets = STORES['racks'], STORES['baskets']
KEG_R = STORES['keg']['radius']; BASK_R = STORES['basket']['radius']; STAFF = STORES['staff']
HEADROOM = 2.0                                             # a store must leave standing room above it (no stairs over it)
LOCKERS = STORES.get('lockers', {})
def items_for(kinds):
    """Row of footprints along local x: keg, racks, baskets - or a single locker ('locker_<gun>': all in one)."""
    if kinds and kinds[0].startswith('locker_'):
        k = kinds[0][len('locker_'):]
        w, d, h = LOCKERS[k]['size']
        return [{'name': kinds[0], 'mesh': 'galleass_' + kinds[0], 'local': (0.0, 0.0), 'hx': w / 2, 'hy': d / 2, 'h': HEADROOM}]
    row = [('keg', 'galleass_powder_keg', KEG_R + 0.06, KEG_R)]
    for k in kinds:
        w, d, h = racks[k]['size']; row.append(('rack_' + k, 'galleass_shot_rack_' + k, w / 2, d / 2))
    for k in kinds:
        if k in baskets: row.append(('basket_' + k, 'galleass_shot_basket', BASK_R, BASK_R))
    items, x = [], 0.0
    depth = max(hy for _, _, _, hy in row)
    for name, mesh, hx, hy in row:
        items.append({'name': name, 'mesh': mesh, 'local': (x + hx, 0.0), 'hx': hx, 'hy': hy, 'h': HEADROOM})
        x += 2 * hx + 0.12
    cx = (x - 0.12) / 2
    for it in items:                                        # centre the row
        it['local'] = (it['local'][0] - cx, it['local'][1])
    return items

fc_R = G['fc_radius'](G['FC_Z_PLATFORM'])
gy = [G['gunport_y'](i) for i in range(G['GUNPORTS_PER_SIDE'])]
cv_trail = max(g['pos'][1] + DIMS['galleass_culverin']['rear_y'] - 1.0 for g in PLACES if g['kind'] == 'culverin')
STATIONS = [
    # name, guns served, deck z, preferred (x, y), search box (x0, x1, y0, y1)
    ('fc_lower', ['culverin'], Z_GD, (0.0, (G['FC_Y_BACK'] + cv_trail) / 2), (-fc_R, fc_R, G['FC_Y_BACK'] + 0.05, cv_trail)),
    ('fc_platform', ['locker_falconet'], Z_PL, (0.0, G['FC_Y_BACK'] + 0.5), (-fc_R, fc_R, G['FC_Y_BACK'] + 0.1, G['FC_CY'] + 1.0)),
    ('waist_port', ['falcon'], Z_GD, (-2.2, (gy[1] + gy[2]) / 2), (-4.2, -0.6, gy[0] - 1.0, gy[-1] + 1.0)),
    ('waist_starboard', ['falcon'], Z_GD, (2.2, (gy[1] + gy[2]) / 2), (0.6, 4.2, gy[0] - 1.0, gy[-1] + 1.0)),
    # the foremost broadside falcons walked 8-14 m to the waist stations (user 2026-10-16): a third falcon station on
    # the centre line between the two foremost pairs, serving both sides
    ('fore_waist', ['falcon'], Z_GD, (0.0, (gy[3] + gy[4]) / 2), (-2.5, 2.5, gy[3] - 0.5, gy[4] + 0.5)),
    ('aft', ['falcon', 'falconet'], Z_GD, (2.0, G['SC_Y_FORE'] + 1.2), (-4.2, 4.2, G['SC_Y_FORE'] + 0.2, G['SC_Y_FORE'] + 4.0)),
    # the poop swivels (user 2026-10-17: their loaders got stuck on the poop stairs): a swivel locker on the poop's
    # centre line between their two pairs
    ('poop', ['locker_petriera'], Z_POOP, (0.0, sum(gun_layout.swivel_poop_y(G)) / 2), (-1.6, 1.6, -22.5, -16.0)),
]

def on_deck(x, y, z):
    hit = HULL.ray_cast(Vector((x, y, z + 0.5)), Vector((0, 0, -1)), 1.0)
    return hit[0] is not None and abs(hit[0].z - z) < 0.06

def clear(items, cx, cy, rot, z, box, placed=None):
    ca, sa = math.cos(rot), math.sin(rot)
    bv, bp = [], []
    x0, x1, y0, y1 = box
    for it in items:
        lx, ly = it['local']; x, y = cx + ca * lx - sa * ly, cy + sa * lx + ca * ly
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            return False                                    # every store inside the station's area
        hx, hy = it['hx'] + MARGIN, it['hy'] + MARGIN
        for px, py in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy), (0, 0)):
            if not on_deck(x + ca * px - sa * py, y + sa * px + ca * py, z):
                return False
        base = len(bv)
        bv += [Vector((x + ca * px - sa * py, y + sa * px + ca * py, zz)) for zz in (z + 0.03, z + it['h'])
               for px, py in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))]
        bp += [[base + i for i in f] for f in ([0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7])]
    b = BVHTree.FromPolygons(bv, bp)
    return not b.overlap(HULL) and not b.overlap(OBST) and not (placed and b.overlap(placed))

out = []
for name, kinds, z, pref, (x0, x1, y0, y1) in STATIONS:
    items = items_for(kinds)
    cands = []
    step = 0.1
    nx, ny = int((x1 - x0) / step) + 1, int((y1 - y0) / step) + 1
    for i in range(nx):
        for j in range(ny):
            x, y = x0 + i * step, y0 + j * step
            cands.append(((x - pref[0]) ** 2 + (y - pref[1]) ** 2, x, y))
    cands.sort()
    found = None
    for _, x, y in cands:
        for rot in ((0.0,) if kinds[0].startswith('locker_') else (0.0, math.pi / 2, math.pi, -math.pi / 2)):
            if clear(items, x, y, rot, z, (x0, x1, y0, y1)):     # (a locker's open front faces the bow)
                found = (x, y, rot); break
        if found: break
    single = {}
    if not found:
        # no room for the row (2026-10-16: forecastle platform - mast, cleat, stair landings): each store on its own,
        # nearest to the preferred point, clear of the others already placed
        pv, pp = [], []
        for it in items:
            one = dict(it, local=(0.0, 0.0))
            for _, cx, cy in cands:
                hit = None
                for rot in (0.0, math.pi / 2):
                    if clear([one], cx, cy, rot, z, (x0, x1, y0, y1), BVHTree.FromPolygons(pv, pp) if pp else None):
                        hit = (cx, cy, rot); break
                if hit: break
            if not hit:
                print('LAYOUT %-16s %s: NO CLEAR SPOT' % (name, it['name'])); continue
            single[it['name']] = hit
            hx, hy = it['hx'] + MARGIN, it['hy'] + MARGIN
            ca_, sa_ = math.cos(hit[2]), math.sin(hit[2]); base = len(pv)
            pv += [Vector((hit[0] + ca_ * px - sa_ * py, hit[1] + sa_ * px + ca_ * py, zz)) for zz in (z + 0.03, z + it['h'])
                   for px, py in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))]
            pp += [[base + i for i in f] for f in ([0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7])]
        if not single:
            print('LAYOUT %-16s NO CLEAR SPOT in its area' % name); continue
        found = (pref[0], pref[1], 0.0)
    x, y, rot = found
    ca, sa = math.cos(rot), math.sin(rot)
    st = {'name': name, 'guns': kinds, 'z': z, 'pos': [round(x, 3), round(y, 3), round(z, 3)], 'rot_z': round(rot, 4), 'items': []}
    for it in items:
        if single and it['name'] not in single:
            continue
        lx, ly = it['local']
        p = [round(x + ca * lx - sa * ly, 4), round(y + sa * lx + ca * ly, 4), round(z, 4)]
        r_ = rot
        if single:
            p = [round(single[it['name']][0], 4), round(single[it['name']][1], 4), round(z, 4)]; r_ = single[it['name']][2]
        e = {'name': it['name'], 'mesh': it['mesh'], 'pos': p, 'rot_z': round(r_, 4)}
        k = it['name'].split('_', 1)[1] if '_' in it['name'] else None
        if it['name'].startswith('rack_'): e['balls'] = racks[k]['balls']; e['ball_mesh'] = 'galleass_shot' + ('' if k == 'culverin' else '_' + k)
        if it['name'].startswith('basket_'): e['bags'] = baskets[k]['bags']; e['bag_mesh'] = 'galleass_scatter_bag_' + k
        if it['name'].startswith('locker_'):
            e['balls'] = LOCKERS[k]['balls']; e['ball_mesh'] = 'galleass_shot_' + k
            e['bags'] = LOCKERS[k]['bags']; e['bag_mesh'] = 'galleass_scatter_bag_' + ('falconet' if k == 'petriera' else k)
        st['items'].append(e)
    out.append(st)
    if single:
        print('LAYOUT %-16s stores placed one by one: %s' % (name, ', '.join('%s (%.2f, %.2f, %3.0f deg)' % (k, v[0], v[1], math.degrees(v[2])) for k, v in single.items())))
    else:
        print('LAYOUT %-16s at (%.2f, %.2f, %.2f) rot %3.0f deg, %.2f m from the preferred spot' % (
            name, x, y, z, math.degrees(rot), math.hypot(x - pref[0], y - pref[1])))
json.dump(out, open(OUT, 'w'), indent=1)
print('LAYOUT written', OUT)

# ---------------------------------------------------------------- loader spots
NV, _, NF = navmesh.read(os.path.join(HERE, '..', 'NavMeshPrefabs', 'galleass_ship_navmesh.bin'))
# only the main edge-connected piece counts (a face reached only across a corner is no way for the game)
_par = list(range(len(NF)))
def _find(a):
    while _par[a] != a:
        _par[a] = _par[_par[a]]; a = _par[a]
    return a
_bye = {}
for _i, (_vs, _, _) in enumerate(NF):
    for _k in range(len(_vs)):
        _bye.setdefault((min(_vs[_k], _vs[(_k + 1) % len(_vs)]), max(_vs[_k], _vs[(_k + 1) % len(_vs)])), []).append(_i)
for _l in _bye.values():
    for _j in _l[1:]: _par[_find(_j)] = _find(_l[0])
_cnt = {}
for _i in range(len(NF)): _cnt[_find(_i)] = _cnt.get(_find(_i), 0) + 1
_MAIN = max(_cnt, key=_cnt.get)
NF_MAIN = [f for i, f in enumerate(NF) if _find(i) == _MAIN]
# spatial index (0.5 m buckets): the padded fine navmesh has ~4400 faces, scanning them all per point took hours
_BUCKET = {}
for _f in NF_MAIN:
    _xs = [NV[v][0] for v in _f[0]]; _ys = [NV[v][1] for v in _f[0]]
    for _bx in range(int(math.floor(min(_xs) / 0.5)), int(math.floor(max(_xs) / 0.5)) + 1):
        for _by in range(int(math.floor(min(_ys) / 0.5)), int(math.floor(max(_ys) / 0.5)) + 1):
            _BUCKET.setdefault((_bx, _by), []).append(_f)
def on_nav(x, y, z):
    return any((fz := navmesh.face_z(NV, vs, x, y)) is not None and abs(fz - z) < 0.3
               for vs, _, _ in _BUCKET.get((int(math.floor(x / 0.5)), int(math.floor(y / 0.5))), ()))
# a man's place may lie just off the padded navmesh (it is padded by ~ a body radius round every obstacle): his centre
# gets within 0.3 m and his body reaches the rest
def near_nav(x, y, z, r=0.3):
    if on_nav(x, y, z):
        return True
    return any(on_nav(x + rr * math.cos(k * math.pi / 4), y + rr * math.sin(k * math.pi / 4), z) for rr in (0.15, r) for k in range(8))
def box_polys(c, hx, hy, z0, z1, rot=0.0):
    ca, sa = math.cos(rot), math.sin(rot)
    v = [Vector((c[0] + ca * x - sa * y, c[1] + sa * x + ca * y, z)) for z in (z0, z1) for x, y in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))]
    return v, [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
taken_v, taken_p = [], []                                   # stores + loaders placed so far
def take(v, p):
    base = len(taken_v); taken_v.extend(v); taken_p.extend([[base + i for i in f] for f in p])
for st in out:
    for it in st['items']:
        fp = next(i for i in items_for(st['guns']) if i['name'] == it['name'])
        take(*box_polys(it['pos'], fp['hx'] + MARGIN, fp['hy'] + MARGIN, st['z'] + 0.03, st['z'] + 1.2, it['rot_z']))
MAN = 0.32                                                  # half a man's footprint (body capsule radius 0.37)
MEN = []                                                    # (x, y, z) of every place for a man so far (coincident
def apart(x, y, z, pickup=False):                           # boxes do not count as overlapping in a BVH test)
    # pickup points may crowd each other (men queue at the stores), never a gunner's or loader's place
    return all(abs(z - mz) > 1.0 or math.hypot(x - mx, y - my_) >= 2 * MAN for mx, my_, mz, pk in MEN if not (pickup and pk))
def man_clear(x, y, z, taken, pickup=False):
    if not apart(x, y, z, pickup):
        return False
    if not near_nav(x, y, z):
        return False
    bv, bp = box_polys((x, y), MAN, MAN, z + 0.05, z + 1.75)
    b = BVHTree.FromPolygons(bv, bp)
    return not (b.overlap(HULL) or b.overlap(OBST_PK if pickup else OBST_NR) or (taken and b.overlap(taken)))

# gunner places (2026-10-16: the forecastle culverins' formula places beside the breech lay under a neighbour's
# recoiled trail - cut out of the navmesh, the centre culverin was never manned): nearest to beside the breech on its
# right (then its left), on the navmesh, clear of the hull, the OTHER guns' sweeps, this gun at rest, the stores and
# the men placed so far -> ref/galleass_gunner_spots.json {gun: {local: [x, y, 0] (faces the muzzle), ship}}
_gunner_idx = set(i for a, b in GUNNER_RANGES for i in range(a, b))
_rope_idx = set(range(ROPE_P0, ROPE_P1))
_base_idx = [i for i in range(len(OP)) if i not in _gunner_idx and i not in _rope_idx]
gunners = {}
for g in PLACES:
    name = 'gun_' + g['name']
    d = DIMS['galleass_' + g['kind']]
    sw0, sw1, rest, recoiled = GUN_RANGES[name]
    B = BVHTree.FromPolygons(OV, [OP[i] for i in _base_idx if not (sw0 <= i < sw1)] + OP[rest[0]:rest[1]] + OP[recoiled[0]:recoiled[1]])
    hw, cy = d['half_w'], d['cascabel_y']
    o, rz, z = g['pos'], g['rot_z'], g['pos'][2]
    ca, sa = math.cos(rz), math.sin(rz)
    taken = BVHTree.FromPolygons(taken_v, taken_p) if taken_p else None
    cands = []
    rc = RECOIL[g['kind']]
    y_lo = d['rear_y'] - rc - 1.2                         # (fallback: behind the gun, clear of its recoil - the
    for i in range(int(2 * (hw + 1.2) / 0.1) + 1):         # centre culverin's sides are walled in by its neighbours)
        for j in range(int((cy + 1.2 - y_lo) / 0.1) + 1):
            lx, ly = -(hw + 1.2) + 0.1 * i, y_lo + 0.1 * j
            cands.append((min(math.hypot(lx - (hw + 0.3), ly - (cy + 0.25)), math.hypot(lx + (hw + 0.3), ly - (cy + 0.25)) + 0.15), lx, ly))
    cands.sort()
    found = None
    dbg = collections.Counter() if name in os.environ.get('DBG_GUNNER', '').split(',') else None
    for cost, lx, ly in cands:
        x, y = o[0] + ca * lx - sa * ly, o[1] + sa * lx + ca * ly
        if not near_nav(x, y, z):
            if dbg is not None: dbg['nav'] += 1
            continue
        bv, bp = box_polys((x, y), MAN, MAN, z + 0.05, z + 1.75)
        b = BVHTree.FromPolygons(bv, bp)
        if not apart(x, y, z) or b.overlap(HULL) or b.overlap(B) or (taken and b.overlap(taken)):
            if dbg is not None:
                dbg['apart' if not apart(x, y, z) else 'hull' if b.overlap(HULL) else 'guns/props' if b.overlap(B) else 'taken'] += 1
            continue
        found = (lx, ly, x, y, cost); break
    if not found:
        print('GUNNER %-24s NO SPOT%s' % (name, (' (rejected: %s)' % dict(dbg)) if dbg is not None else '')); continue
    lx, ly, x, y, cost = found
    MEN.append((x, y, z, False))
    gunners[name] = {'local': [round(lx, 3), round(ly, 3), 0.0], 'ship': [round(x, 3), round(y, 3), round(z, 3)]}
    take(*box_polys((x, y), MAN, MAN, z + 0.05, z + 1.75))
    if cost > 0.05:
        print('GUNNER %-24s local (%5.2f, %5.2f), %.2f m from beside the breech' % (name, lx, ly, cost))
json.dump(gunners, open(os.path.join(HERE, 'ref', 'galleass_gunner_spots.json'), 'w'), indent=1)
print('GUNNER written ref/galleass_gunner_spots.json: %d of %d guns' % (len(gunners), len(PLACES)))

# store pickup points (2 per store, where a man stands to take powder / a ball / a bag): nearest to in front of and
# behind the store, on the navmesh, outside every gun's sweep and gunner, clear of the stores; in the store's frame,
# facing it -> stations json item 'pickup': [[x, y, yaw], [x, y, yaw]]
for st in out:
    z = st['z']
    for it in st['items']:
        fp = next(i for i in items_for(st['guns']) if i['name'] == it['name'])
        rz = it['rot_z']; ca, sa = math.cos(rz), math.sin(rz)
        prefs = [(0.0, fp['hy'] + 0.40)] if it['name'].startswith('locker_') else [(0.0, -(fp['hy'] + 0.40)), (0.0, fp['hy'] + 0.40)]
        cands = []
        for i in range(-12, 13):
            for j in range(-12, 13):
                lx, ly = 0.1 * i, 0.1 * j
                if abs(lx) < fp['hx'] + MARGIN + MAN and abs(ly) < fp['hy'] + MARGIN + MAN:
                    continue                                   # on the store
                if abs(lx) > fp['hx'] + 0.9 or abs(ly) > fp['hy'] + 0.9:
                    continue                                   # out of arm's reach
                if it['name'].startswith('locker_') and ly < fp['hy']:
                    continue                                   # a locker opens to its front (+y) only
                cands.append((min(math.hypot(lx - px, ly - py) for px, py in prefs), lx, ly))
        cands.sort()
        got = []
        taken = BVHTree.FromPolygons(taken_v, taken_p)
        for cost, lx, ly in cands:
            x, y = it['pos'][0] + ca * lx - sa * ly, it['pos'][1] + sa * lx + ca * ly
            if any(math.hypot(lx - gx, ly - gy) < 0.6 for gx, gy, _ in got) or not man_clear(x, y, z, taken, pickup=True):
                continue
            got.append((round(lx, 3), round(ly, 3), round(math.atan2(lx, -ly), 4)))
            if len(got) == 2: break
        for lx, ly, _ in got:
            MEN.append((it['pos'][0] + ca * lx - sa * ly, it['pos'][1] + sa * lx + ca * ly, z, True))
            take(*box_polys((it['pos'][0] + ca * lx - sa * ly, it['pos'][1] + sa * lx + ca * ly), MAN, MAN, z + 0.05, z + 1.75))
        it['pickup'] = [list(g) for g in got]
        print('PICKUP %-16s %-15s %d points %s' % (st['name'], it['name'], len(got), got))
json.dump(out, open(OUT, 'w'), indent=1)

spots = {}
for g in PLACES:
    d = DIMS['galleass_' + g['kind']]
    hw, my, ry, rc = d['half_w'], d['muzzle_y'], d['rear_y'], RECOIL[g['kind']]
    prefs = [(-(hw + 0.40), my - rc - 0.30), (hw + 0.40, my - rc - 0.30)]
    o, rz, z = g['pos'], g['rot_z'], g['pos'][2]
    ca, sa = math.cos(rz), math.sin(rz)
    taken = BVHTree.FromPolygons(taken_v, taken_p) if taken_p else None
    cands = []
    wx = hw + 2.4                                              # (a cramped platform needs the wide window)
    for i in range(int(2 * wx / 0.1) + 1):
        for j in range(int((my + 0.6 - (ry - rc - 2.0)) / 0.1) + 1):   # back to 2 m behind the recoiled trail
            lx, ly = -wx + 0.1 * i, ry - rc - 2.0 + 0.1 * j
            cost = min(math.hypot(lx - px, ly - py) for px, py in prefs)
            cands.append((cost, lx, ly))
    cands.sort()
    found = None
    for cost, lx, ly in cands:
        x, y = o[0] + ca * lx - sa * ly, o[1] + sa * lx + ca * ly
        if not man_clear(x, y, z, taken):
            continue
        found = (lx, ly, x, y, cost); break
    name = 'gun_' + g['name']
    if not found:
        print('LOADER %-24s NO SPOT' % name); continue
    lx, ly, x, y, cost = found
    yaw = -math.pi / 2 if lx < 0 else math.pi / 2           # faces the gun (f = +x on its left, -x on its right)
    MEN.append((x, y, z, False))
    spots[name] = {'local': [round(lx, 3), round(ly, 3), round(yaw, 4)], 'ship': [round(x, 3), round(y, 3), round(z, 3)]}
    take(*box_polys((x, y), MAN, MAN, z + 0.05, z + 1.75))
    print('LOADER %-24s local (%5.2f, %5.2f) ship (%6.2f, %6.2f, %.2f), %.2f m from the preferred spot' % (name, lx, ly, x, y, z, cost))
json.dump(spots, open(os.path.join(HERE, 'ref', 'galleass_loader_spots.json'), 'w'), indent=1)
print('LOADER written ref/galleass_loader_spots.json: %d of %d guns' % (len(spots), len(PLACES)))

# ---------------------------------------------------------------- preview: footprints in the model
if RENDERS:
    os.makedirs(RENDERS, exist_ok=True)
    mat = bpy.data.materials.new('store'); mat.diffuse_color = (0.9, 0.2, 0.1, 1)
    for st in out:
        for it in st['items']:
            hx = next(i['hx'] for i in items_for(st['guns']) if i['name'] == it['name'])
            hy = next(i['hy'] for i in items_for(st['guns']) if i['name'] == it['name'])
            h = 0.6
            bpy.ops.mesh.primitive_cube_add(size=1)
            o = bpy.context.active_object; o.scale = (2 * hx, 2 * hy, h)
            o.location = (it['pos'][0], it['pos'][1], st['z'] + h / 2); o.rotation_euler = (0, 0, it['rot_z'])
            o.data.materials.append(mat)
    lmat = bpy.data.materials.new('loader'); lmat.diffuse_color = (0.1, 0.8, 0.2, 1)
    for sp in spots.values():
        bpy.ops.mesh.primitive_cube_add(size=1)
        o = bpy.context.active_object; o.scale = (2 * MAN, 2 * MAN, 1.7)
        o.location = (sp['ship'][0], sp['ship'][1], sp['ship'][2] + 0.85); o.data.materials.append(lmat)
    # guns in place for context
    for g in PLACES:
        src = bpy.data.objects['galleass_' + g['kind']]
        o = bpy.data.objects.new('pv_' + g['name'], src.data); bpy.context.scene.collection.objects.link(o)
        o.location = g['pos']; o.rotation_euler = (0, 0, g['rot_z'])
    for o in bpy.data.objects:
        if o.name in ('galleass_faction_paint', 'galleass_hull_plate') or o.name in ('galleass_culverin', 'galleass_falcon', 'galleass_falconet'):
            o.hide_render = True
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'MATERIAL'; sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = 1400, 1000
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    def shot(fname, loc, tgt, lens=28):
        cam.location = loc; cam.data.lens = lens
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(RENDERS, fname); bpy.ops.render.render(write_still=True)
    for st in out:
        x, y, z = st['pos']
        side = 1.0 if st['name'] == 'aft' else -1.0          # aft: look from forward (the poop rail is in the way)
        shot('station_%s.png' % st['name'], (x * 0.5 + 0.01, y + side * 4.0, z + 5.0), (x, y, z), 26)
    shot('stations_top.png', (0.0, 0.0, 70.0), (0.0, 0.001, 0.0), 40)
print('layout done')
