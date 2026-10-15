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
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index('--') + 1:]
GUNS_BLEND, OUT, RENDERS = argv[0], argv[1], (argv[2] if len(argv) > 2 else None)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model_geom, gun_layout
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

for g in PLACES:                                            # gun sweeps + gunner spots
    d = DIMS['galleass_' + g['kind']]; t = TRAV['gun_' + g['name']]
    piv = Vector((0.0, t['pivot'][1], 0.0))
    verts, polys = GUNMESH[g['kind']]
    for deg in (t['min_deg'], 0.0, t['max_deg']):
        for r in (0.0, RECOIL[g['kind']]):
            M = (Matrix.Translation(Vector(g['pos'])) @ Matrix.Rotation(g['rot_z'], 4, 'Z') @ Matrix.Translation(piv) @
                 Matrix.Rotation(math.radians(deg), 4, 'Z') @ Matrix.Translation(-piv) @ Matrix.Translation((0, -r, 0)))
            add_mesh([M @ v for v in verts], polys)
        Mg = (Matrix.Translation(Vector(g['pos'])) @ Matrix.Rotation(g['rot_z'], 4, 'Z') @ Matrix.Translation(piv) @
              Matrix.Rotation(math.radians(deg), 4, 'Z') @ Matrix.Translation(-piv))
        gp = Mg @ Vector((d['half_w'] + 0.30, d['cascabel_y'] + 0.25, 0.0))
        add_box(gp, 0.35, 0.35, gp.z + 0.02, gp.z + 1.7)
for r in ROPES['ropes']:                                    # live ropes (rest position, fat)
    add_tube(r['start'], r['end'], 0.06)
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
    near = min(abs(z - Z_GD), abs(z - Z_PL))
    name = e.get('name', '')
    if near > 0.6 or any(name.startswith(p) for p in GUNPARTS):
        continue
    if e.get('meshes') or name.startswith('sp_troop') or 'barrier' in name:
        rad = 0.25 if name.startswith('sp_troop') else 0.4
        add_box(e['pos'], rad, rad, z + 0.02, z + 1.2); props += 1
OBST = BVHTree.FromPolygons(OV, OP)
print('LAYOUT obstacles: hull %d polys, others %d polys (%d props)' % (len(HP), len(OP), props))

# ---------------------------------------------------------------- stations
racks, baskets = STORES['racks'], STORES['baskets']
KEG_R = STORES['keg']['radius']; BASK_R = STORES['basket']['radius']; STAFF = STORES['staff']
HEADROOM = 2.0                                             # a store must leave standing room above it (no stairs over it)
def items_for(kinds):
    """Row of footprints along local x: keg, racks, baskets."""
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
    ('fc_platform', ['falconet'], Z_PL, (0.0, G['FC_Y_BACK'] + 0.5), (-fc_R, fc_R, G['FC_Y_BACK'] + 0.1, G['FC_CY'] + 1.0)),
    ('waist_port', ['falcon'], Z_GD, (-2.2, (gy[1] + gy[2]) / 2), (-4.2, -0.6, gy[0] - 1.0, gy[-1] + 1.0)),
    ('waist_starboard', ['falcon'], Z_GD, (2.2, (gy[1] + gy[2]) / 2), (0.6, 4.2, gy[0] - 1.0, gy[-1] + 1.0)),
    ('aft', ['falcon', 'falconet'], Z_GD, (2.0, G['SC_Y_FORE'] + 1.2), (-4.2, 4.2, G['SC_Y_FORE'] + 0.2, G['SC_Y_FORE'] + 4.0)),
]

def on_deck(x, y, z):
    hit = HULL.ray_cast(Vector((x, y, z + 0.5)), Vector((0, 0, -1)), 1.0)
    return hit[0] is not None and abs(hit[0].z - z) < 0.06

def clear(items, cx, cy, rot, z, box):
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
    return not b.overlap(HULL) and not b.overlap(OBST)

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
        for rot in (0.0, math.pi / 2, math.pi, -math.pi / 2):
            if clear(items, x, y, rot, z, (x0, x1, y0, y1)):
                found = (x, y, rot); break
        if found: break
    if not found:
        print('LAYOUT %-16s NO CLEAR SPOT in its area' % name); continue
    x, y, rot = found
    ca, sa = math.cos(rot), math.sin(rot)
    st = {'name': name, 'guns': kinds, 'z': z, 'pos': [round(x, 3), round(y, 3), round(z, 3)], 'rot_z': round(rot, 4), 'items': []}
    for it in items:
        lx, ly = it['local']
        p = [round(x + ca * lx - sa * ly, 4), round(y + sa * lx + ca * ly, 4), round(z, 4)]
        e = {'name': it['name'], 'mesh': it['mesh'], 'pos': p, 'rot_z': round(rot, 4)}
        k = it['name'].split('_', 1)[1] if '_' in it['name'] else None
        if it['name'].startswith('rack_'): e['balls'] = racks[k]['balls']; e['ball_mesh'] = 'galleass_shot' + ('' if k == 'culverin' else '_' + k)
        if it['name'].startswith('basket_'): e['bags'] = baskets[k]['bags']; e['bag_mesh'] = 'galleass_scatter_bag_' + k
        st['items'].append(e)
    out.append(st)
    print('LAYOUT %-16s at (%.2f, %.2f, %.2f) rot %3.0f deg, %.2f m from the preferred spot' % (
        name, x, y, z, math.degrees(rot), math.hypot(x - pref[0], y - pref[1])))
json.dump(out, open(OUT, 'w'), indent=1)
print('LAYOUT written', OUT)

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
