"""Galleass standing rigging (re-rig phase 2, user 2026-10-13): shrouds ABAFT each mast with tackles, and the tie
tackle (ghinda) at the mast foot. Static, one mesh galleass_standing_rigging (+ _lod1.._lod3) in the ship's frame;
build_prefab.py places it in torch_holder (tag galleass_standing_rigging). No collision (crew walk through ropes).

    blender -b ref/galleass_model.blend --python standing_rig.py -- ref/galleass_layout.json ref/galleass_guns.blend ../AssetSources/export renders/standing

Venetian galley practice (sartie): a few shrouds a side from a pendant collar at the masthead, each set up with a
tackle (two blocks) to a ringbolt on the side, the hauling part belayed / heaped on deck. The vanilla lateen yard
swings -5..170 deg round its mast, so shrouds only go aft (user choice: abaft the yard, measure the crossings,
accept rare clipping): each shroud reports how much of the yard's yaw range brings the yard within YARD_CLEAR of it.

The tie (amante): build_prefab.py turns a vanilla rope into the yard -> calcese part (it follows the yard); here the
calcese -> deck part: down the far side of the mast to a tackle hooked to an eyebolt by the mast foot.
Masts and yards come from the built prefab's layout (prefab_layout.py); the calcese from mast_dims.py.
"""
import bpy, bmesh, json, math, os, random, sys
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index('--') + 1:]
LAYOUT, GUNS_BLEND, OUT = argv[:3]
RENDERS = argv[3] if len(argv) > 3 else None
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model_geom, gun_layout, mast_dims as MD
import rope_geom as rg

G = model_geom.load()
LIFT = G['Z_LIFT']
rows = json.load(open(LAYOUT))
CLEAR = 0.02
YARD_CLEAR = 0.35                      # yard (~0.15 radius) + shroud + margin

# per mast: rig in the prefab, deck it stands on (world z), where its shrouds' feet go on the side bulwark (world y,
# in the free stretches between the gunports and their gun tackles: ports at y -8.8/-3.4/2.1/7.5/12.9, +-1.4 m kept
# clear), shroud rope radius
MASTS = {
    'main':   dict(rig='lateen_sail_large_nested', size='large', deck=G['Z_GUN_DECK'] + LIFT, feet=(3.9, 0.3, -1.6), r=0.020, tie_eye=(-0.3, -0.95)),
    'fore':   dict(rig='lateen_sail_medium_nested', size='medium', deck=G['FC_Z_PLATFORM'] + LIFT, feet=(16.8, 15.0), r=0.018, tie_eye=(-0.55, 0.55)),
    'mizzen': dict(rig='lateen_sail_small_nested', size='small', deck=G['Z_GUN_DECK'] + LIFT, feet=(-14.6, -16.0), r=0.017, tie_eye=(-0.45, -0.5)),   # (user 2026-10-27: at -0.95 aft the eyebolt sat 0.15 m inside the cabin front)
}
FOOT_Z = G['Z_GUN_DECK'] + LIFT + 0.75          # ringbolts on the gun deck bulwark's inner face

def row(rig, name):
    return next(r for r in rows if rig in r['path'] and r['name'] == name)

def frame_of(r):
    M = Matrix(r['mat']).to_4x4(); M.translation = Vector(r['pos'])
    return M

# ---------------------------------------------------------------- obstacles: hull + masts + guns
with bpy.data.libraries.load(GUNS_BLEND, link=False) as (src, dst):
    dst.objects = [n for n in src.objects if n.startswith('galleass_') and not n.endswith('_fuse')]
GUN = {o.name: o for o in dst.objects}
for g in gun_layout.placements(G, gun_layout.load_dims()):
    o = bpy.data.objects.new('sr_' + g['name'], GUN['galleass_' + g['kind']].data); bpy.context.scene.collection.objects.link(o)
    o.location = g['pos']; o.rotation_euler = (0, 0, g['rot_z'])
bpy.context.view_layer.update()

def world_bvh(objs):
    verts, polys = [], []
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        me = o.evaluated_get(dg).to_mesh(); mw = o.matrix_world; base = len(verts)
        verts += [mw @ v.co for v in me.vertices]; polys += [[base + i for i in p.vertices] for p in me.polygons]
        o.evaluated_get(dg).to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys)

HULL = world_bvh([o for o in bpy.data.objects if o.type == 'MESH' and any(c.name == 'final' for c in o.users_collection)
                  and o.name not in ('galleass_faction_paint', 'galleass_hull_plate')])
GUNS = world_bvh([o for o in bpy.data.objects if o.name.startswith('sr_')])

def clear_of(pts, r, skip0=0.1, skip1=0.1):
    total = sum((b - a).length for a, b in zip(pts, pts[1:])); L = 0.0
    for a, b in zip(pts, pts[1:]):
        n = max(int((b - a).length / 0.03), 1)
        for k in range(n):
            p = a.lerp(b, k / n); s = L + (b - a).length * k / n
            if skip0 < s < total - skip1:
                for bvh in (HULL, GUNS):
                    if bvh.find_nearest(p, r + CLEAR)[0] is not None:
                        return False
        L += (b - a).length
    return True

def seg_dist(a0, a1, b0, b1):
    """Shortest distance between segments a0a1 and b0b1 (sampled, robust enough here)."""
    from mathutils.geometry import intersect_line_line
    best = 1e9
    for k in range(41):
        p = a0.lerp(a1, k / 40)
        d = b1 - b0; t = max(0.0, min(1.0, (p - b0).dot(d) / max(d.length_squared, 1e-9)))
        best = min(best, (p - (b0 + d * t)).length)
    return best

def yard_sweep(mast, shroud_pts):
    """Fraction of the yard's yaw range (both senses tried: -5..170 and -170..5; the worse is reported) in which the
    yard comes within YARD_CLEAR of the shroud."""
    rig = MASTS[mast]['rig']
    yaw = row(rig, 'yaw_rotation_entity')
    c = Vector(yaw['pos']); ax = Vector(Matrix(yaw['mat']).col[2]).normalized()
    f0, b0 = Vector(row(rig, 'yard_bone_fore')['pos']), Vector(row(rig, 'yard_bone_back')['pos'])
    worst = 0.0
    for sense in (1, -1):
        hits = 0; n = 0
        for deg in range(-5, 171, 5):
            R = Matrix.Rotation(math.radians(sense * deg), 3, ax)
            f = c + R @ (f0 - c); b = c + R @ (b0 - c)
            d = min(seg_dist(f, b, p, q) for p, q in zip(shroud_pts, shroud_pts[1:]))
            hits += d < YARD_CLEAR; n += 1
        worst = max(worst, hits / n)
    return worst

def wall_hit(o, d, maxd=9.0):
    loc, nor, _, dist = HULL.ray_cast(o, d, maxd)
    if loc is None: return None
    if nor.dot(d) > 0: nor = -nor
    if abs(nor.z) > 0.5: return None
    return loc, nor

def ringbolt(bms, W, N, k=1.0):
    rg.eyebolt(bms['iron'], W, N, 0.045 * k, 0.012 * k)
    side = N.cross(Vector((0, 0, 1)))
    side = side.normalized() if side.length > 1e-6 else Vector((1, 0, 0))
    rg.ring(bms['iron'], W + N * 0.06 * k - Vector((0, 0, 0.04 * k)), side, 0.04 * k, 0.008 * k, segs=8, tube=4, role_uv='iron')

FALL = 0.8                                             # tackle falls + hauling part, x the tackle's rope (user 2026-10-27:
                                                       # at 0.6 the heap looked thinner than the three falls it leaves)
HALYARD_R = 0.020                                      # the vanilla flag halyard (sail_rope_pile vector_argument_w)
HEAP_H = 0.13                                          # heaps no higher than the old thin ones (thick rope: fewer loops)

def off_cabin(pts, r):
    """Heaps on the gun deck stay clear of the cabin front (user 2026-10-27: the mizzen tie's heap lay in it): shift the
    points forward by what they lack."""
    inside = [p.y for p in pts if abs(p.x) < G['sc_hw'](G['SC_Y_FORE']) + 0.1 and p.z < G['SC_Z_FLOOR'] + LIFT]
    lack = (G['SC_Y_FORE'] + r + 0.04) - min(inside) if inside else 0.0
    return [p + Vector((0, lack, 0)) for p in pts] if lack > 0 else pts

def tackle(bms, top, bottom, r, segs, level, seed, deck_z, inboard):
    """Two blocks between 'top' (the shroud's end) and 'bottom' (the ring), three falls, hauling part to a heap."""
    d = (bottom - top).normalized()
    bl = 0.17
    b1 = top + d * (bl / 2)
    b2 = bottom - d * (0.05 + bl / 2)
    up = d.cross(Vector((0, 0, 1)))
    up = up.normalized() if up.length > 1e-6 else Vector((1, 0, 0))
    off = up.cross(d).normalized()
    if level < 3:
        for cc in (b1, b2):
            rg.block(bms['wood'], cc, d, up, bl, bl * 0.62, bl * 0.42)
        rg.rope(bms['rope'], [b2 + d * bl * 0.45, bottom], r * 0.7, segs=segs)
    for o2 in (-1.2, 0.0, 1.2):
        rg.rope(bms['rope'], [b1 + off * o2 * r * 1.6 + d * bl * 0.3, b2 + off * o2 * r * 1.6 - d * bl * 0.3], r * FALL,
                segs=max(segs - 1, 3))
    if level < 3:                                      # hauling part, belayed and heaped on deck inboard
        rr = random.Random(seed)
        cc = Vector((b2.x, b2.y, deck_z)) + inboard * (0.35 + rr.uniform(0, 0.15)) + \
             Vector((-inboard.y, inboard.x, 0)) * rr.uniform(-0.15, 0.15)
        start = Vector((-(cc - b2).x, -(cc - b2).y, 0))
        heap = off_cabin(rg.heap_points(cc, r * FALL, seed=seed, scale=1.1, step=0.035 if level == 0 else 0.09, max_h=HEAP_H,
                                        start_dir=start.normalized() if start.length > 1e-6 else None), r * FALL)
        drop = rg.catmull([b2 - off * r * 2.2, (b2 + heap[0]) / 2 + inboard * 0.05 + Vector((0, 0, 0.05)), heap[0]], 0.08)
        rg.rope(bms['rope'], drop[:-1] + heap, r * FALL, segs=max(segs - 2, 3))
    return b1

def build(level):
    segs = (6, 5, 4, 3)[level]
    bms = {'rope': bmesh.new(), 'iron': bmesh.new(), 'wood': bmesh.new()}
    report = []
    for mast, sp in MASTS.items():
        mm = frame_of(next(r for r in rows if sp['rig'] in r['path'] and r['name'] == 'mast_mesh'))
        dims = MD.MASTS[sp['size']]
        c0, c1 = MD.calcese_span(dims)
        hx, hy = MD.calcese_half(dims)
        z_head = c0 - 0.30
        head_c = mm @ Vector((0, 0, z_head))
        r_m = MD.rad(dims, z_head)
        # pendant collar round the masthead where the shrouds hang
        if level < 3:
            ax = (mm.to_3x3() @ Vector((0, 0, 1))).normalized()
            for k in range(2):
                rg.ring(bms['rope'], mm @ Vector((0, 0, z_head - 0.05 * k)), ax, r_m + sp['r'] * 0.9, sp['r'],
                        segs=16, tube=5)
        foot_c = mm @ Vector((0, 0, (sp['deck'] - mm.translation.z)))
        for s in (-1, 1):
            for i, fy in enumerate(sp['feet']):
                done = False
                for dy in (0.0, 0.3, -0.3, 0.6, -0.6):
                    o = Vector((s * 4.8, fy + dy, FOOT_Z))
                    hit = wall_hit(o, Vector((s, 0, 0)), maxd=2.5)
                    if hit is None or GUNS.ray_cast(o, Vector((s, 0, 0)), 2.5)[0] is not None: continue
                    W, N = hit
                    ring_pt = W + N * 0.075 - Vector((0, 0, 0.035))
                    head = head_c + Vector((s * (r_m + sp['r']), 0, 0))
                    top = ring_pt + (head - ring_pt).normalized() * 1.5      # upper block 1.5 m up the shroud
                    if not clear_of([head, top, ring_pt], sp['r'] * 3, skip0=0.3, skip1=0.25):
                        continue
                    sweep = yard_sweep(mast, [head, top])
                    if level < 3: ringbolt(bms, W, N)
                    b1 = tackle(bms, top, ring_pt, sp['r'], segs, level, '%s/%d/%d' % (mast, s, i), G['Z_GUN_DECK'] + LIFT,
                                Vector((N.x, N.y, 0)).normalized())
                    rg.rope(bms['rope'], [head, b1 - (b1 - head).normalized() * 0.08], sp['r'], segs=segs)
                    aft = head_c.y - W.y
                    report.append('%-6s side %+d shroud %d: foot y %.2f (%.1f m aft of the head), bolt (%.2f, %.2f, %.2f), '
                                  'yard near it %.0f%% of its swing' % (mast, s, i, W.y, aft, W.x, W.y, W.z, sweep * 100))
                    done = True
                    break
                if not done:
                    report.append('%-6s side %+d shroud %d: NO clear path' % (mast, s, i))
        # tie tackle: the tie leaves the calcese's lower sheave on the far side (-x), down to a tackle at the mast foot
        zt = MD.sheaves(dims)[0] - 0.05
        t0 = mm @ Vector((-(hx + 0.03), 0, zt))
        zb = sp['deck'] - mm.translation.z                       # mast-local z of the deck (approx, rake small)
        # clear of the mast lanterns (build_prefab: main/mizzen arms out to +-x 0.75 at deck + 3.2, fore arm aft):
        # main/mizzen tackle aft of the mast, fore tackle forward on the platform (aft of it is the platform's edge:
        # the heap lay on the rail post, user 2026-10-13)
        ex, ey = sp['tie_eye']
        eye = mm @ Vector((ex, ey, zb)); eye.z = sp['deck']
        upper = mm @ Vector((ex, ey * 0.8, zb + 2.4))
        rope_r = sp['r'] * 1.25
        if level < 3:
            rg.eyebolt(bms['iron'], eye, Vector((0, 0, 1)), 0.04, 0.014)
            rg.ring(bms['iron'], eye + Vector((0, 0, 0.065)), Vector((1, 0, 0)), 0.045, 0.009, segs=8, tube=4, role_uv='iron')
        b1 = tackle(bms, upper, eye + Vector((0, 0, 0.11)), rope_r * 0.8, segs, level, '%s/tie' % mast, sp['deck'],
                    (Vector((eye.x, eye.y, 0)) - Vector((foot_c.x, foot_c.y, 0))).normalized())
        # the tie runs into the upper block (it stopped 10 cm above it, user 2026-10-13), as the shrouds do
        rg.rope(bms['rope'], [t0, b1 - (b1 - t0).normalized() * 0.05], rope_r, segs=segs)
        report.append('%-6s tie: calcese (%.2f, %.2f, %.2f) -> tackle -> eyebolt (%.2f, %.2f, %.2f)' % (mast, *t0, *eye))
        # flag halyard's hauling end: the vanilla rope stops at HALYARD_FOOT (build_prefab.py), heaped from there
        if level < 3:
            hx_, hy_ = MD.HALYARD_FOOT[sp['size']]
            foot = mm @ Vector((hx_, hy_, zb)); foot.z = sp['deck'] + MD.HALYARD_DZ
            out = Vector((foot.x - foot_c.x, foot.y - foot_c.y, 0)).normalized()
            hp = off_cabin(rg.heap_points(Vector((foot.x, foot.y, sp['deck'])) + out * 0.16, HALYARD_R, seed='%s/halyard' % mast,
                                          scale=1.0, step=0.035 if level == 0 else 0.09, start_dir=-out, max_h=HEAP_H), HALYARD_R)
            rg.rope(bms['rope'], rg.catmull([foot, (foot + hp[0]) / 2 + Vector((0, 0, 0.02)), hp[0]], 0.04)[:-1] + hp,
                    HALYARD_R, segs=max(segs - 2, 3))
    return bms, report

MAT = {'rope': 'galleass_rope', 'iron': 'galleass_iron', 'wood': 'galleass_trim'}
def to_object(bms, name):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    order = list(bms)
    for i, key in enumerate(order):
        tmp = bpy.data.meshes.new('tmp'); bms[key].to_mesh(tmp); bms[key].free()
        n0 = len(bm.faces); bm.from_mesh(tmp); bpy.data.meshes.remove(tmp)
        bm.faces.ensure_lookup_table()
        for fc in bm.faces[n0:]: fc.material_index = i
    bm.to_mesh(me); bm.free()
    for key in order:
        me.materials.append(bpy.data.materials.get(MAT[key]) or bpy.data.materials.new(MAT[key]))
    for p in me.polygons: p.use_smooth = True
    col = me.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
    for d in col.data: d.color = (1, 1, 1, 1)
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    return o

objs = []
for lvl in range(4):
    bms, report = build(lvl)
    objs.append(to_object(bms, 'galleass_standing_rigging' + ('' if lvl == 0 else '_lod%d' % lvl)))
    if lvl == 0:
        for line in report: print('SR', line)
    print('SR level %d: %d tris' % (lvl, sum(len(p.vertices) - 2 for p in objs[-1].data.polygons)))
os.makedirs(OUT, exist_ok=True)
bpy.ops.object.select_all(action='DESELECT')
for x in objs: x.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, 'galleass_standing_rigging.fbx'), use_selection=True,
                         object_types={'MESH'}, use_mesh_modifiers=True, mesh_smooth_type='FACE', use_tspace=False,
                         axis_forward='Y', axis_up='Z', apply_unit_scale=True, global_scale=1.0, bake_anim=False,
                         path_mode='STRIP', add_leaf_bones=False)
print('SR exported')

if RENDERS:
    os.makedirs(RENDERS, exist_ok=True)
    for x in objs[1:]: x.hide_render = True
    for o in bpy.data.objects:
        if o.name in ('galleass_faction_paint', 'galleass_hull_plate') or o.name in GUN: o.hide_render = True
    # our masts + vanilla yards from the layout, as in rig_preview.py
    if os.environ.get('MASTS_BLEND'):
        with bpy.data.libraries.load(os.environ['MASTS_BLEND'], link=False) as (src, dst):
            dst.meshes = [n for n in src.meshes if n.startswith('galleass_mast_') and '_lod' not in n]
        mesh = {m.name: m for m in dst.meshes}
        for r in rows:
            for mn in r['meshes']:
                if mn in mesh:
                    o = bpy.data.objects.new('pv_' + mn, mesh[mn]); bpy.context.scene.collection.objects.link(o)
                    o.matrix_world = frame_of(r)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'MATERIAL'; sc.display.shading.show_cavity = True
    for name, colr in (('galleass_rope', (0.75, 0.62, 0.42, 1)), ('galleass_iron', (0.12, 0.12, 0.13, 1))):
        m = bpy.data.materials.get(name)
        if m: m.diffuse_color = colr
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = 1700, 1100
    def shot(fname, loc, tgt, lens=28, ortho=None):
        cam.location = loc; cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        if ortho: cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
        else: cam.data.type = 'PERSP'; cam.data.lens = lens
        sc.render.filepath = os.path.join(RENDERS, fname); bpy.ops.render.render(write_still=True)
    shot('sr_side.png', (60, 2, 16), (0, 2, 16), ortho=70)
    shot('sr_persp.png', (26, -30, 24), (0, 4, 10), lens=26)
    shot('sr_front.png', (0, 60, 18), (0, 0, 16), ortho=34)
    shot('sr_main_foot.png', (3.5, 0.5, 6.0), (0, 5.0, 4.0), lens=26)
    shot('sr_main_rail.png', (0.0, 4.0, 6.5), (5.5, 1.0, 4.4), lens=28)
    print('SR renders in', RENDERS)
