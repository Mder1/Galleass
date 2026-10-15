"""Ship-side gun rigging (user 2026-10-13): for every one of the 24 guns, the breeching from the gun to two ringbolts
beside its port, and (falcons, falconets) a side tackle each side from the carriage's side ring to a ringbolt further
out, in the run-out position: the breeching hangs slack, the tackle falls are taut.

LIVE ROPES (user 2026-10-15: "ropes like the sails'"): the parts that must follow the gun (breechings, tackle falls,
the running block on the carriage) are no longer mesh. They go to ref/galleass_gun_ropes.json and build_prefab.py
makes them vanilla rope entities (rope_segment between a static start and an end, ship_ropes material) plus a block
entity on the gun; the gunnery add-on re-points every rope end at an attachment entity on the gun (or barrel), so the
ropes follow recoil, traverse and elevation. Static still, one mesh in the ship's frame galleass_gun_rigging
(+ _lod1.._lod3, tag galleass_gun_rigging): ringbolts, the standing blocks with their strops, hauling parts and their
deck heaps. galleass_tackle_block.fbx = the running block (+ its strop) in its own frame (y = towards the carriage
ring), scaled per gun.

    blender -b ref/galleass_model.blend --python gun_rigging.py -- ref/galleass_guns.blend ../AssetSources/export renders/rig

The ringbolts are found by ray casts from beside each gun along its heading onto the inner wall; bolt spacing and height
are searched so no rope passes through the hull, a mast, its own gun or a neighbour (clearance = rope radius + 1.5 cm).
The gun anchors (end of the breeching legs round the cascabel, the side rings) come from cannon_model.py via
ref/galleass_guns.json ('rig'). Materials: rope -> galleass_rope (vanilla ship_ropes texture, laid-rope strip),
ringbolts -> galleass_iron, blocks -> galleass_trim. No collision (crew walk through ropes, like vanilla rigging).
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index('--') + 1:]
GUNS_BLEND, OUT, RENDERS = argv[0], argv[1], (argv[2] if len(argv) > 2 else None)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model_geom, gun_layout, json
import rope_geom as rg

G = model_geom.load()
DIMS = gun_layout.load_dims()
PLACES = gun_layout.placements(G, DIMS)
CLEAR = 0.015

# ---------------------------------------------------------------- scene: hull + guns as obstacles
with bpy.data.libraries.load(GUNS_BLEND, link=False) as (src, dst):
    dst.objects = [n for n in src.objects if n.startswith('galleass_')]
GUN = {o.name: o for o in dst.objects}
coll = bpy.data.collections.new('rig_guns'); bpy.context.scene.collection.children.link(coll)

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
placed = []
for g in PLACES:
    src = GUN['galleass_' + g['kind']]
    o = bpy.data.objects.new('rig_' + g['name'], src.data); coll.objects.link(o)
    o.location = g['pos']; o.rotation_euler = (0, 0, g['rot_z'])
    placed.append((g, o))
bpy.context.view_layer.update()
HULL = world_bvh(hull_objs)
GUNS_BVH = world_bvh([o for _, o in placed])

LAST_CLASH = []
OTHER_ROPES = []                                          # (points, radius) of ropes already laid at this gun side

def rope_dist(p, poly):
    from mathutils.geometry import intersect_point_line
    best = 1e9
    for a, b in zip(poly, poly[1:]):
        q, f = intersect_point_line(p, a, b)
        q = a if f < 0 else (b if f > 1 else q)
        best = min(best, (p - q).length)
    return best

def clear_of(pts, r, skip0=0.06, skip1=0.06):
    """True if every rope point (except the first/last few cm) keeps r + CLEAR from hull, guns and the ropes in
    OTHER_ROPES (user 2026-10-13: the breeching ran through the tackle block)."""
    L = 0.0; total = sum((b - a).length for a, b in zip(pts, pts[1:]))
    lim = r + CLEAR
    for a, b in zip(pts, pts[1:]):
        n = max(int((b - a).length / 0.02), 1)
        for k in range(n):
            p = a.lerp(b, k / n); s = L + (b - a).length * k / n
            if s < skip0 or s > total - skip1:
                continue
            for nm, bvh in (('hull', HULL), ('guns', GUNS_BVH)):
                hit = bvh.find_nearest(p, lim)
                if hit[0] is not None:
                    LAST_CLASH[:] = [nm, s, total, tuple(round(c, 3) for c in p), tuple(round(c, 3) for c in hit[0])]
                    return False
            for poly, r2 in OTHER_ROPES:
                if rope_dist(p, poly) < r + r2 + 0.012:
                    LAST_CLASH[:] = ['rope', s, total, tuple(round(c, 3) for c in p)]
                    return False
        L += (b - a).length
    return True

# RIG_DEBUG=<gun name>,<side> prints why that gun side's candidates fail ('WHY' lines)
DEBUG = os.environ.get('RIG_DEBUG', '').split(',') if os.environ.get('RIG_DEBUG') else None
if DEBUG: DEBUG = (DEBUG[0], int(DEBUG[1]))
def wall_hit(origin, d, maxd=4.0):
    """Ray onto the hull; returns (point, normal) when it meets a wall facing back at us."""
    loc, nor, _, dist = HULL.ray_cast(origin, d, maxd)
    if loc is None:
        return None
    if nor.dot(d) > 0:
        nor = -nor
    if nor.dot(d) > -0.6 or abs(nor.z) > 0.5:            # not a wall square to the gun
        return None
    if GUNS_BVH.ray_cast(origin, d, dist)[0] is not None:   # a gun in the way
        return None
    return loc, nor

# ---------------------------------------------------------------- rigging per gun
def frame(g):
    M = Matrix.Translation(Vector(g['pos'])) @ Matrix.Rotation(g['rot_z'], 4, 'Z')
    return M, (M.to_3x3() @ Vector((0, 1, 0))).normalized(), (M.to_3x3() @ Vector((1, 0, 0))).normalized()

def bolt_search(g, s, anchor, r, d_pref, d_range, h_pref, sags, make_path, skip0=0.06):
    """Search the wall bolt (lateral offset d from the gun's axis, height h above the floor) and the sag so the rope
    from 'anchor' clears everything. make_path(anchor, ring_point, sag) -> rope points."""
    M, f, rt = frame(g)
    floor = g['pos'][2]
    cands = sorted(((d, h) for d in d_range for h in (h_pref, h_pref + 0.1, h_pref - 0.1, h_pref + 0.2, h_pref + 0.3, h_pref + 0.45)),
                   key=lambda dh: abs(dh[0] - d_pref) + 0.6 * abs(dh[1] - h_pref))
    for d, h in cands:
        o = Vector(g['pos']) + rt * (s * d) + Vector((0, 0, h))
        o = o - f * 0.4                                    # start behind the gun's trunnions' line
        hit = wall_hit(o, f)
        if hit is None:
            if DEBUG and g['name'] == DEBUG[0] and s == DEBUG[1]:
                loc, nor, _, dist = HULL.ray_cast(o, f, 4.0)
                gl = GUNS_BVH.ray_cast(o, f, 4.0)
                print('WHY nohit d %.2f h %.2f hull %s n %s dist %s gun %s' % (d, h, loc and tuple(round(c, 2) for c in loc),
                      nor and tuple(round(c, 2) for c in nor), dist and round(dist, 2), gl[0] and round(gl[3], 2)))
            continue
        W, N = hit
        ring_pt = W + N * 0.075 + Vector((0, 0, -0.035))    # bottom of the bolt's ring
        for sag in sags:
            pts = make_path(anchor, ring_pt, sag)
            if clear_of(pts, r, skip0=skip0):
                return W, N, pts
            if DEBUG and g['name'] == DEBUG[0] and s == DEBUG[1]:
                print('WHY', g['name'], 'd %.2f h %.2f sag %.2f' % (d, h, sag), LAST_CLASH)
    return None

def ringbolt(bm_iron, W, N, scale=1.0):
    rg.eyebolt(bm_iron, W, N, 0.045 * scale, 0.012 * scale)
    side = N.cross(Vector((0, 0, 1))).normalized()
    rg.ring(bm_iron, W + N * 0.06 * scale - Vector((0, 0, 0.04 * scale)) + Vector((0, 0, 0.0)), side,
            0.04 * scale, 0.008 * scale, segs=8, tube=4, role_uv='iron')

def build(level):
    """level 0..3: rope sides 6/5/4/3; rings + blocks dropped at 3."""
    segs = (5, 4, 3, 3)[level]
    bms = {'rope': bmesh.new(), 'iron': bmesh.new(), 'wood': bmesh.new()}
    report = []
    for g, o in placed:
        M, f, rt = frame(g)
        rig = DIMS['galleass_' + g['kind']]['rig']
        ah = DIMS['galleass_' + g['kind']]['axis_h']
        r_b = rig['rope_r']
        k = r_b / 0.016                                     # scale of bolts / blocks with the gun
        for s in (-1, 1):
            # breeching: from the leg's end beside the base ring (or the sledge's front ring) to the wall, slack
            bp = rig['breech']['p']
            Rb = rig['breech']['ring_r']
            a_loc = Vector((s * bp[0], bp[1] + Rb * 0.6, bp[2] - Rb * 0.6))   # through the ring's fore-lower side
            A = M @ a_loc
            def breech_path(a, ring_pt, sag):
                pts = rg.sag_span(a, ring_pt, sag, n=12)
                return pts
            res = bolt_search(g, s, A, r_b, d_pref=0.45 + 0.10 * k, d_range=[0.30 + 0.05 * i for i in range(22)],
                              h_pref=ah - 0.20, sags=(0.14, 0.10, 0.06, 0.03), make_path=breech_path,
                              skip0=0.12 if Rb else 0.06)
            if res is None:
                report.append('%s side %+d: NO breeching path' % (g['name'], s)); continue
            W, N, pts = res
            if level < 3: ringbolt(bms['iron'], W, N, max(k, 0.75))
            OTHER_ROPES[:] = [(pts, r_b)]                  # the tackle must keep clear of this side's breeching
            if level == 0:                                  # live rope: wall ring -> leg end (barrel) / sledge ring
                span = (pts[-1] - pts[0]).length
                sag = max(0.0, max(((pts[0] + (pts[-1] - pts[0]) * (i / (len(pts) - 1))) - q).z for i, q in enumerate(pts)))
                on_barrel = not Rb                          # falcons: the legs hug the barrel; culverin: sledge ring
                LIVE.append({'gun': 'gun_' + g['name'], 'name': 'breech_%+d' % s, 'start': list(pts[-1]),
                             'end': list(A), 'end_local': list(a_loc), 'on_barrel': on_barrel,
                             'radius': r_b, 'loose': round(max(0.02, 8 * sag * sag / (3 * max(span, 0.1))), 4)})
            report.append('%s side %+d: breeching to bolt %.2f m out' % (g['name'], s, (W - Vector(g['pos'])).dot(rt) * s))
            # side tackle (wheeled carriages): ring on the cheek -> wall bolt further out; two blocks, three falls
            if rig['tackle'] is None:
                continue
            tp = rig['tackle']['p']; R = rig['tackle']['ring_r']
            T = M @ Vector((s * tp[0], tp[1] + R * 0.6, tp[2] + R * 0.2))   # hooked in the ring's fore side, above the tyre
            r_t = r_b * 0.6
            bl = 0.15 * k
            def tackle_path(a, ring_pt, sag):
                return [a, ring_pt]
            res = bolt_search(g, s, T, r_t * 3, d_pref=1.0 + 0.2 * k, d_range=[0.7 + 0.05 * i for i in range(16)],
                              h_pref=ah + 0.15, sags=(0.0,), make_path=tackle_path, skip0=0.12)
            if res is None:
                report.append('%s side %+d: NO tackle path' % (g['name'], s)); continue
            W2, N2, _ = res
            ring_pt = W2 + N2 * 0.075 - Vector((0, 0, 0.035))
            d = (T - ring_pt).normalized()
            b1 = ring_pt + d * (0.05 + bl / 2)              # standing block hooked to the wall bolt
            b2 = T - d * (0.05 + bl / 2)                    # running block hooked to the carriage ring
            up = d.cross(Vector((0, 0, 1)))
            up = (up if up.length > 1e-6 else Vector((1, 0, 0))).normalized()
            if level < 3:
                ringbolt(bms['iron'], W2, N2, max(k, 0.75))
                rg.block(bms['wood'], b1, d, up, bl, bl * 0.62, bl * 0.42)    # standing block (static)
                rg.rope(bms['rope'], [ring_pt, b1 - d * bl * 0.45], r_t, segs=segs)
            off = up.cross(d).normalized()
            Minv = M.inverted(); R3 = Minv.to_3x3()
            if level == 0:                                  # running block on the carriage ring: an entity on the gun
                LIVE_BLOCKS.append({'gun': 'gun_' + g['name'], 'name': 'block_%+d' % s, 'pos_local': list(Minv @ b2),
                                    'along_local': list((R3 @ d).normalized()), 'across_local': list((R3 @ up).normalized()),
                                    'scale': k})
            for j, o2 in enumerate((-1.2, 0.0, 1.2)):      # falls between the sheaves: live ropes
                q0 = b1 + off * o2 * r_t * 1.8 + d * bl * 0.3
                q1 = b2 + off * o2 * r_t * 1.8 - d * bl * 0.3
                if level == 0:
                    LIVE.append({'gun': 'gun_' + g['name'], 'name': 'fall_%+d_%d' % (s, j), 'start': list(q0),
                                 'end': list(q1), 'end_local': list(Minv @ q1), 'on_barrel': False,
                                 'radius': r_t, 'loose': 0.005})
            # hauling part: from the standing block down to the deck, left in a loose heap inboard of the bolt
            floor = g['pos'][2]
            inb = Vector((N2.x, N2.y, 0)).normalized()          # N2 faces back into the ship
            import random
            jr = random.Random('%s/%d/pos' % (g['name'], s))       # each heap lies a little differently
            along = Vector((-inb.y, inb.x, 0))
            cc = Vector((b1.x, b1.y, floor)) + inb * (0.24 + 0.10 * k + jr.uniform(-0.05, 0.08)) \
                 + along * jr.uniform(-0.12, 0.12)
            start = (cc - Vector((b1.x, b1.y, cc.z)))
            start = Vector((-start.x, -start.y, 0)).normalized() if start.length > 1e-6 else inb
            coil = rg.heap_points(cc, r_t, seed='%s/%d' % (g['name'], s), scale=k, step=0.035 if level == 0 else 0.09,
                                  start_dir=start)
            drop = rg.catmull([b1 - off * r_t * 2.5, (b1 + coil[0]) / 2 + inb * 0.05 + Vector((0, 0, 0.05)), coil[0]],
                              0.08)
            rg.rope(bms['rope'], drop[:-1] + coil, r_t, segs=max(segs - 2, 3))
            if DEBUG and g['name'] == DEBUG[0] and s == DEBUG[1] and level == 0:
                hit = HULL.ray_cast(cc + Vector((0, 0, 2)), Vector((0, 0, -1)), 5)
                print('WHY coil', tuple(round(c, 3) for c in cc), 'floor hit', hit[0] and tuple(round(c, 3) for c in hit[0]),
                      'b1', tuple(round(c, 3) for c in b1), 'n coil', len(coil))
            report.append('%s side %+d: tackle to bolt %.2f m out' % (g['name'], s, (W2 - Vector(g['pos'])).dot(rt) * s))
    return bms, report

MAT = {'rope': 'galleass_rope', 'iron': 'galleass_iron', 'wood': 'galleass_trim'}

def to_object(bms, name):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    order = list(bms)
    for i, key in enumerate(order):
        tmp = bpy.data.meshes.new('tmp'); bms[key].to_mesh(tmp); bms[key].free()
        n0 = len(bm.faces)
        bm.from_mesh(tmp); bpy.data.meshes.remove(tmp)
        bm.faces.ensure_lookup_table()
        for fc in bm.faces[n0:]:
            fc.material_index = i
    bm.to_mesh(me); bm.free()
    for key in order:
        m = bpy.data.materials.get(MAT[key]) or bpy.data.materials.new(MAT[key])
        me.materials.append(m)
    for p in me.polygons: p.use_smooth = True
    col = me.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
    for d in col.data: d.color = (1, 1, 1, 1)
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    return o

LIVE, LIVE_BLOCKS = [], []
objs = []
for lvl in range(4):
    bms, report = build(lvl)
    o = to_object(bms, 'galleass_gun_rigging' + ('' if lvl == 0 else '_lod%d' % lvl))
    objs.append(o)
    if lvl == 0:
        for line in report: print('RIG', line)
    print('RIG level %d: %d tris' % (lvl, sum(len(p.vertices) - 2 for p in o.data.polygons)))

os.makedirs(OUT, exist_ok=True)
bpy.ops.object.select_all(action='DESELECT')
for x in objs: x.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, 'galleass_gun_rigging.fbx'), use_selection=True,
                         object_types={'MESH'}, use_mesh_modifiers=True, mesh_smooth_type='FACE', use_tspace=False,
                         axis_forward='Y', axis_up='Z', apply_unit_scale=True, global_scale=1.0, bake_anim=False,
                         path_mode='STRIP', add_leaf_bones=False)
print('RIG exported', os.path.join(OUT, 'galleass_gun_rigging.fbx'))
pz = {k: v['elev']['pivot_z'] for k, v in DIMS.items()}
for r in LIVE:                                              # barrel ends in the barrel's frame (origin on the trunnions)
    if r['on_barrel']:
        kind = 'galleass_' + next(g['kind'] for g in PLACES if 'gun_' + g['name'] == r['gun'])
        r['end_local'][2] -= pz[kind]
json.dump({'ropes': LIVE, 'blocks': LIVE_BLOCKS}, open(os.path.join(HERE, 'ref', 'galleass_gun_ropes.json'), 'w'), indent=1)
print('RIG live: %d ropes, %d running blocks -> ref/galleass_gun_ropes.json' % (len(LIVE), len(LIVE_BLOCKS)))

# the running block in its own frame: y = 'along' (towards the carriage ring), x = 'across' (sheave axis), scale 1 =
# a falcon's block (bl 0.15); its strop runs on to the ring (0.05 beyond the block's end)
bl = 0.15
bmw, bmr = bmesh.new(), bmesh.new()
rg.block(bmw, Vector((0, 0, 0)), Vector((0, 1, 0)), Vector((1, 0, 0)), bl, bl * 0.62, bl * 0.42)
rg.rope(bmr, [Vector((0, bl * 0.45, 0)), Vector((0, bl / 2 + 0.05, 0))], 0.016 * 0.6, segs=5)
blk = to_object({'wood': bmw, 'rope': bmr}, 'galleass_tackle_block')
bpy.ops.object.select_all(action='DESELECT'); blk.select_set(True); bpy.context.view_layer.objects.active = blk
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, 'galleass_tackle_block.fbx'), use_selection=True,
                         object_types={'MESH'}, use_mesh_modifiers=True, mesh_smooth_type='FACE', use_tspace=False,
                         axis_forward='Y', axis_up='Z', apply_unit_scale=True, global_scale=1.0, bake_anim=False,
                         path_mode='STRIP', add_leaf_bones=False)
print('RIG exported galleass_tackle_block.fbx: %d tris' % sum(len(p.vertices) - 2 for p in blk.data.polygons))

# ---------------------------------------------------------------- check renders
if RENDERS:
    os.makedirs(RENDERS, exist_ok=True)
    for x in objs[1:]: x.hide_render = True
    for o in bpy.data.objects:
        if o.name in ('galleass_faction_paint', 'galleass_hull_plate') or o.name in GUN: o.hide_render = True
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'MATERIAL'
    sc.display.shading.show_cavity = True; sc.display.shading.show_shadows = False
    for name, colr in (('galleass_rope', (0.75, 0.62, 0.42, 1)), ('galleass_iron', (0.12, 0.12, 0.13, 1))):
        m = bpy.data.materials.get(name)
        if m: m.diffuse_color = colr
    cam = bpy.data.objects.new('rig_cam', bpy.data.cameras.new('rig_cam')); sc.collection.objects.link(cam); sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
    def shot(fname, loc, tgt, lens=30):
        cam.location = loc; cam.data.lens = lens
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(RENDERS, fname); bpy.ops.render.render(write_still=True)
    L = G['Z_LIFT']; zgd = G['Z_GUN_DECK'] + L; zfc = G['FC_Z_PLATFORM'] + L
    y2 = G['gunport_y'](2)
    shot('rig_broadside.png', (2.0, y2 - 3.0, zgd + 2.6), (5.2, y2, zgd + 0.4), 28)
    shot('rig_broadside_top.png', (4.5, y2, zgd + 4.5), (4.5, y2 + 0.01, zgd), 30)
    shot('rig_fc_platform.png', (0.0, 16.5, zfc + 4.0), (0.0, 21.5, zfc), 26)
    shot('rig_fc_lower.png', (1.3, 16.2, zgd + 1.9), (0.0, 23.0, zgd + 0.5), 22)
    shot('rig_cabin.png', (0.0, -16.5, zgd + 2.2), (0.0, -22.5, zgd + 0.3), 20)
    sp = Vector(next(g for g in PLACES if g['name'] == 'fa_stern_+1')['pos'])
    shot('rig_stern_chaser.png', sp + Vector((-0.4, 0.6, 2.6)), sp + Vector((0.0, -0.3, 0.3)), 16)
    bp = Vector(next(g for g in PLACES if g['name'] == 'fa_bs_2_+1')['pos'])
    shot('rig_heap_close.png', bp + Vector((0.2, 0.2, 1.3)), bp + Vector((0.95, 1.0, 0.0)), 35)
    shot('rig_heap_close2.png', bp + Vector((0.2, -0.2, 1.3)), bp + Vector((0.95, -1.0, 0.0)), 35)
    shot('rig_cross.png', bp + Vector((-0.6, -0.9, 1.0)), bp + Vector((0.6, 0.3, 0.75)), 28)
    print('RIG renders in', RENDERS)
