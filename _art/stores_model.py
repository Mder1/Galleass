"""Gun stores for the gunnery add-on's ammunition (user 2026-10-15: shared supplies per ship, loose powder ladled from
kegs, one station per battery): powder keg, ladle-rammer and shot garland, built parametrically, UV'd, exported for the
Modding Kit, plus review renders.

    blender -b --factory-startup --python stores_model.py -- ref/galleass_stores.blend ../AssetSources/export renders/stores

Meshes (materials = the guns' Kit materials):
- galleass_powder_keg: staved keg (~0.55 m) with iron hoops, the head lifted off and leaning against the body, black
  powder a hand below the rim (wood -> galleass_trim, iron -> galleass_iron, powder -> galleass_dark).
- galleass_ladle_<gun> / galleass_ladle_<gun>_charged: the period 'cucchiara' - a copper scoop (rolled sheet, 2/3 of
  a cylinder, a little narrower than the bore) on one end of an ash staff, the rammer head on the other; the charged one
  carries a heap of powder in the scoop (the carried item). Copper -> galleass_gun_bronze (plain misc strip).
  Frame = a Bannerlord weapon item's (vanilla push_fork: length along +Z, grip at the origin, butt ~0.22 L below):
  staff along +Z, scoop at +Z, ORIGIN ON THE STAFF A QUARTER OF ITS LENGTH FROM THE RAMMER END, sheet's open side -Y.
  (Built along +Y about the staff's middle, turned at the end of build_ladle.)
- galleass_shot_rack_<gun>: a shot garland - low box with a top board drilled in two rows; the balls are NOT in the
  mesh: their seat positions go to ref/galleass_stores.json ('racks') so the prefab places ball entities (and the
  add-on can empty the rack as the ship's shot runs low). Origin on the deck under the rack's centre, long side +X.
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:]
OUT_BLEND, OUT_FBX, RENDERS = argv[0], argv[1], (argv[2] if len(argv) > 2 else None)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gun_profiles as gp, gun_uv
import rope_geom as rg
from lod_util import make_lods

ROLE = {'wood': 'galleass_trim', 'iron': 'galleass_iron', 'dark': 'galleass_dark', 'copper': 'galleass_gun_bronze',
        'rope': 'galleass_rope', 'sack': 'galleass_sack'}
UV_S = {'galleass_iron': 0.5, 'galleass_trim': 0.135, 'galleass_dark': 0.135}
COL = {'wood': (0.36, 0.24, 0.14, 1), 'iron': (0.16, 0.16, 0.17, 1), 'dark': (0.03, 0.03, 0.03, 1), 'copper': (0.72, 0.42, 0.25, 1),
       'rope': (0.66, 0.55, 0.36, 1), 'sack': (0.70, 0.62, 0.46, 1)}

# calibres (bore, ball radius) and ladle sizes. The scoop is ~2.5 calibres long so it holds roughly a charge of 2/3 the
# ball's weight; the staff is shortened from the real (barrel-long) one so a man can carry it on deck.
BALL_R = {'culverin': 0.06, 'falcon': 0.038, 'falconet': 0.0265}          # = export_guns.py galleass_shot*
BORE = {'culverin': gp.CV['bore'], 'falcon': gp.FALCON['bore'], 'falconet': gp.FALCONET['bore'],
        'petriera': gp.FALCONET['bore']}                                    # (swivels: the falconet's bags)
STAFF = {'culverin': 3.0, 'falcon': 2.4, 'falconet': 1.8}
RACK = {'culverin': (2, 5), 'falcon': (2, 8), 'falconet': (2, 10)}        # rows, balls per row
# close-range shot (user 2026-10-15): small shot packed in bore-sized hemp bags, kept in wicker baskets at the falcon and
# falconet stations; (bag length, hex rings of bags in the basket's top layer)
BAG = {'falcon': (0.13, 1), 'falconet': (0.10, 2), 'petriera': (0.10, 2)}

for c in list(bpy.data.objects): bpy.data.objects.remove(c)
MATS = {}
for role, kit in ROLE.items():
    m = bpy.data.materials.get(kit) or bpy.data.materials.new(kit)
    m.diffuse_color = COL[role]; MATS[role] = m

def finish(bm, name, sharp=40):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for m in MATS.values(): me.materials.append(m)
    for p in me.polygons: p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(sharp))
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    return o

ROLES = list(ROLE)
def tag(bm, faces, role):
    i = ROLES.index(role)
    for f in faces: f.material_index = i

def lathe(bm, prof, role, axis='z', at=(0, 0, 0), segs=32, cap0=False, cap1=False, inside=False, arc=None, up=None):
    """Solid/shell of revolution: prof = [(h, r)] along the axis. arc = (a0, a1) for a partial sheet (radians)."""
    a0, a1 = arc if arc else (0.0, 2 * math.pi)
    n = segs if not arc else segs + 1
    rings = []
    for h, r in prof:
        row = []
        for k in range(n):
            a = a0 + (a1 - a0) * k / segs
            x, y = r * math.cos(a), r * math.sin(a)
            p = (x, y, h) if axis == 'z' else (x, h, y)            # 'y': the axis along Y, sheet in X/Z
            row.append(bm.verts.new(Vector(p) + Vector(at)))
        rings.append(row)
    faces = []
    for i in range(len(rings) - 1):
        for k in range(n if not arc else segs):
            kk = (k + 1) % n
            q = (rings[i][k], rings[i][kk], rings[i + 1][kk], rings[i + 1][k])
            faces.append(bm.faces.new(q if not inside else tuple(reversed(q))))
    caps = []
    if cap0 and not arc: caps.append((bm.faces.new(list(reversed(rings[0]))), -1 if prof[0][0] <= prof[-1][0] else 1))
    if cap1 and not arc: caps.append((bm.faces.new(rings[-1]), 1 if prof[-1][0] >= prof[0][0] else -1))
    # orient every face (in-game back faces are culled - user 2026-10-15: the keg was see-through): walls away from
    # the axis (towards it for an inside wall / the inner face of a sheet), caps along the axis away from the solid
    ax = Vector((0, 0, 1)) if axis == 'z' else Vector((0, 1, 0))
    flip = []
    hmid = (min(h for h, _ in prof) + max(h for h, _ in prof)) / 2
    for f in faces:
        c = f.calc_center_median() - Vector(at); f.normal_update()
        radial = c - ax * c.dot(ax)
        if radial.length < 1e-6: continue
        if up is not None:                                   # a surface seen from one side only (powder heap): all up / down
            if (f.normal.dot(ax) < 0) == up: flip.append(f)
        elif abs(f.normal.dot(radial.normalized())) < 0.3:   # flat ring (rim, hoop edge): up at the top, down below
            if (f.normal.dot(ax) < 0) != (c.dot(ax) < hmid): flip.append(f)
        elif (f.normal.dot(radial) < 0) != inside: flip.append(f)
    for f, sgn in caps:
        f.normal_update()
        if f.normal.dot(ax) * sgn < 0: flip.append(f)
    if flip: bmesh.ops.reverse_faces(bm, faces=flip)
    faces += [f for f, _ in caps]
    tag(bm, faces, role)
    return faces

def box(bm, x0, x1, y0, y1, z0, z1, role):
    r = bmesh.ops.create_cube(bm, size=1.0)
    for v in r['verts']:
        v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0), (y0 + y1) / 2 + v.co.y * (y1 - y0), (z0 + z1) / 2 + v.co.z * (z1 - z0)))
    tag(bm, list({f for v in r['verts'] for f in v.link_faces}), role)

def add_uvs(o):
    """Copper: the bronze atlas's plain misc strip; rope (wicker, sacking) keeps rope_geom's UVs on the laid-rope strip;
    everything else planar per face."""
    me = o.data
    uv = me.uv_layers[0] if me.uv_layers else me.uv_layers.new(name='UVMap')
    for poly in me.polygons:
        role = ROLES[poly.material_index]; n = poly.normal
        if role in ('rope', 'sack'):
            continue
        pts = [me.vertices[me.loops[li].vertex_index].co for li in poly.loop_indices]
        ax = max(range(3), key=lambda i: abs(n[i]))
        i, j = [k for k in range(3) if k != ax]
        for li, p in zip(poly.loop_indices, pts):
            if role == 'copper':
                uv.data[li].uv = gun_uv.misc_uv(p[i] * 0.5, p[j] * 0.5)
            else:
                s = UV_S.get(ROLE[role], 0.5)
                uv.data[li].uv = (p[i] * s, p[j] * s)
    col = me.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
    for d in col.data: d.color = (1, 1, 1, 1)
    # drop unused material slots (the Kit warns about them)
    used = sorted({p.material_index for p in me.polygons})
    idx = [used.index(p.material_index) for p in me.polygons]
    mats = [me.materials[i] for i in used]
    me.materials.clear()
    for m in mats: me.materials.append(m)
    for p, i in zip(me.polygons, idx): p.material_index = i

# ---------------------------------------------------------------- powder keg
def build_keg():
    bm = bmesh.new()
    H, Rb, Re, chime = 0.55, 0.205, 0.175, 0.025            # height, belly / end radius, staves past the head
    prof = [(0.0, Re), *[(H * t, Re + (Rb - Re) * math.sin(math.pi * t)) for t in [k / 12 for k in range(1, 12)]], (H, Re)]
    t = 0.018                                                # stave thickness
    lathe(bm, prof, 'wood', segs=28, cap0=True)
    lathe(bm, [(H, Re), (H, Re - t)], 'wood', segs=28)          # rim
    lathe(bm, [(h, r - t) for h, r in reversed(prof) if h >= H - 0.12] + [(H - 0.12, Re - t - 0.004)], 'wood', segs=28, inside=True)   # faces the axis
    # powder surface a hand below the rim (black grains), a low heap
    pz = H - 0.10
    # the powder meets the inner wall: its radius from the bulging profile at that height (a ring of floor showed
    # between powder and staves, user 2026-10-15), a few mm into the wall
    r_in = Re + (Rb - Re) * math.sin(math.pi * pz / H) - t + 0.004
    lathe(bm, [(pz, r_in), (pz + 0.012, r_in * 0.6), (pz + 0.02, 0.0)], 'dark', segs=28, up=True)
    # iron hoops: two near each end, one at the belly
    for hz in (0.05, 0.11, H - 0.11, H - 0.05, H * 0.5):
        r = Re + (Rb - Re) * math.sin(math.pi * hz / H)
        lathe(bm, [(hz - 0.015, r + 0.002), (hz - 0.015, r + 0.007), (hz + 0.015, r + 0.007), (hz + 0.015, r + 0.002)], 'iron', segs=28)
    # the head (lid), lifted off and leaning against the keg's side: a disc of boards with a batten and a grip
    lid = bmesh.new()
    lr = Re - 0.006
    lathe(lid, [(0.0, lr), (0.022, lr)], 'wood', segs=24, cap0=True, cap1=True)
    box(lid, -0.12, 0.12, -0.025, 0.025, 0.022, 0.04, 'wood')       # batten
    lid.verts.ensure_lookup_table()
    M = (Matrix.Translation((Rb + 0.01, 0.0, lr * math.cos(math.radians(20)) + 0.012)) @ Matrix.Rotation(math.radians(-70), 4, 'Y'))
    bmesh.ops.transform(lid, matrix=M, verts=lid.verts)
    tmp = bpy.data.meshes.new('tmp'); lid.to_mesh(tmp); lid.free(); bm.from_mesh(tmp); bpy.data.meshes.remove(tmp)
    return finish(bm, 'galleass_powder_keg')

# ---------------------------------------------------------------- ladle-rammer
def build_ladle(gun, charged):
    bm = bmesh.new()
    rb = BORE[gun] / 2 * 0.9                                 # scoop radius, a little under the bore
    L = STAFF[gun]
    sr = 0.018 if gun == 'culverin' else 0.016 if gun == 'falcon' else 0.014
    lathe(bm, [(-L / 2, sr), (L / 2, sr)], 'wood', axis='y', segs=10, cap0=True, cap1=True)          # staff
    # ladle head: a wooden block at the staff's end the sheet is nailed to
    hy = L / 2
    lathe(bm, [(hy, rb * 0.98), (hy + 0.05, rb * 0.98)], 'wood', axis='y', segs=16, cap0=True, cap1=True)
    # copper scoop: 2/3 of a cylinder, open side up (+Z), ~2.5 calibres long, a rounded lip
    ls = 2.5 * BORE[gun]
    a0, a1 = math.radians(150), math.radians(390)             # sheet round the bottom, open on top (angle from +X in X/Z)
    def arcprof(r):
        return [(hy + 0.05, r), (hy + 0.05 + ls, r)]
    lathe(bm, arcprof(rb), 'copper', axis='y', segs=14, arc=(a0, a1))
    lathe(bm, arcprof(rb - 0.0015), 'copper', axis='y', segs=14, arc=(a0, a1), inside=True)
    # rammer head on the other end (calcatoio)
    lathe(bm, [(-hy - 0.06 * (rb / 0.056) - 0.02, rb * 0.95), (-hy, rb * 0.95)], 'wood', axis='y', segs=16, cap0=True, cap1=True)
    if charged:                                              # a heaped scoopful of powder
        fill = []
        for k in range(9):
            y = hy + 0.05 + 0.01 + (ls - 0.02) * k / 8
            fill.append((y, rb * 0.92 * (1.0 - 0.15 * abs(k - 4) / 4)))
        bmh = bmesh.new()
        lathe(bmh, fill, 'dark', axis='y', segs=12, cap0=True, cap1=True)
        # flatten the heap's top just above the sheet's rim
        for v in bmh.verts:
            if v.co.z > rb * 0.35: v.co.z = rb * 0.35 + (v.co.z - rb * 0.35) * 0.3
        tmp = bpy.data.meshes.new('tmp'); bmh.to_mesh(tmp); bmh.free(); bm.from_mesh(tmp); bpy.data.meshes.remove(tmp)
    # item frame: grip a quarter of the staff from the rammer end, staff up (+Y -> +Z)
    for v in bm.verts:
        x, y, z = v.co.x, v.co.y + L / 4, v.co.z
        v.co.x, v.co.y, v.co.z = x, -z, y
    return finish(bm, 'galleass_ladle_%s%s' % (gun, '_charged' if charged else ''), sharp=50)

# ---------------------------------------------------------------- sponge-rammer and linstock (gunnery animations, 2026-10-20)
# Crew props for the custom clips: the sponge-rammer (scovolo / calcatoio) lies at each gun - the sponge swabs the bore
# before loading, the rammer end drives the ball home (the powder is rammed with the ladle's own rammer end). Sheepskin
# sponge a hair over the bore (it is pressed in) -> galleass_sack; staff and rammer head as the ladle's. Built straight
# in the ladle's item frame: staff along +Z, sponge at +Z, origin a quarter of the staff from the rammer end.
def build_sponge(gun):
    bm = bmesh.new()
    rb = BORE[gun] / 2 * 0.9
    L = STAFF[gun]
    sr = 0.018 if gun == 'culverin' else 0.016 if gun == 'falcon' else 0.014
    z0, z1 = -L / 4, 3 * L / 4
    lathe(bm, [(z0, sr), (z1, sr)], 'wood', segs=10, cap0=True, cap1=True)
    lathe(bm, [(z0 - 0.06 * (rb / 0.056) - 0.02, rb * 0.95), (z0, rb * 0.95)], 'wood', segs=16, cap0=True, cap1=True)
    # sponge: a fleece bolster on a wooden core, rounded at the head, bound to the staff by an iron collar
    rs, ls = BORE[gun] / 2 * 1.02, 1.8 * BORE[gun]
    lathe(bm, [(z1 - 0.01, sr * 1.4), (z1 + 0.012, sr * 1.4)], 'iron', segs=12, cap0=True, cap1=True)
    prof = [(z1 + 0.012, sr * 1.25), (z1 + 0.012 + 0.10 * ls, rs * 0.92), (z1 + 0.012 + 0.22 * ls, rs)]
    prof += [(z1 + 0.012 + ls * (0.78 + 0.22 * math.sin(math.pi / 2 * k / 4)), rs * math.cos(math.pi / 2 * k / 4.4)) for k in range(5)]
    fl = lathe(bm, prof, 'sack', segs=16, cap1=True)
    uv_sack(bm, fl, rs)
    return finish(bm, 'galleass_sponge_%s' % gun, sharp=50)

# linstock (buttafuoco): ash staff with an iron spike foot (stuck in the deck by the gun), an iron fork at the head with
# a clamp on each arm; the slow match is wound round the upper staff and clamped in the arms, the lit end on the +X arm
# (charred tip -> galleass_dark; the glow is an effect). Item frame: staff along +Z, origin a quarter from the foot.
LINSTOCK_L = 1.1
def build_linstock():
    bm = bmesh.new()
    L, sr = LINSTOCK_L, 0.015
    z0, z1 = -L / 4, 3 * L / 4
    lathe(bm, [(z0, sr), (z1, sr)], 'wood', segs=10, cap0=True, cap1=True)
    lathe(bm, [(z0 - 0.09, 0.0005), (z0 - 0.03, sr * 0.8), (z0 + 0.03, sr * 1.15), (z0 + 0.045, sr * 1.15)], 'iron', segs=10, cap1=True)
    lathe(bm, [(z1 - 0.035, sr * 1.2), (z1 + 0.015, sr * 1.2), (z1 + 0.03, sr * 0.7)], 'iron', segs=12, cap0=True, cap1=True)
    tips = []
    for sx in (1, -1):                                          # fork arms curving out and up, a clamp at each tip
        arm = [Vector((sx * x, 0, z1 + z)) for x, z in ((0.0, 0.02), (0.022, 0.045), (0.045, 0.085), (0.056, 0.13), (0.058, 0.16))]
        n0 = len(bm.faces); rg.rope(bm, rg.catmull(arm, 0.01), 0.0055, segs=8)
        bm.faces.ensure_lookup_table(); tag(bm, bm.faces[n0:], 'iron')
        tip = arm[-1]; tips.append(tip)
        box(bm, tip.x - 0.009, tip.x + 0.009, -0.009, 0.009, tip.z - 0.004, tip.z + 0.012, 'iron')
    rm = 0.0045                                                 # slow match: a thin loosely-laid cord
    za, zb, turns = z1 - 0.40, z1 - 0.07, 6.5
    helix = []
    for k in range(int(turns * 16) + 1):
        a = 2 * math.pi * k / 16
        helix.append(Vector(((sr + rm) * math.cos(a + math.pi), (sr + rm) * math.sin(a + math.pi), zb - (zb - za) * k / (turns * 16))))
    lit = tips[0]
    lead = [lit + Vector((0.004, 0, 0.035)), lit + Vector((0, 0, 0.004)), lit + Vector((-0.006, 0.006, -0.03)),
            Vector((0.036, 0.014, z1 + 0.06)), Vector((0.024, 0.022, z1 + 0.005)), Vector((-0.004, 0.026, z1 - 0.035)),
            Vector((-0.022, 0.012, zb + 0.012))]
    rope_part(bm, lambda: rg.rope(bm, rg.catmull(lead + helix, 0.012), rm, segs=6))
    spare = tips[1]                                             # the other end clamped in the -X arm, hanging a little
    rope_part(bm, lambda: rg.rope(bm, rg.catmull([spare + Vector((0, 0, 0.02)), spare + Vector((0, 0, -0.01)),
                                                  spare + Vector((0.006, 0.004, -0.05)), spare + Vector((0.012, 0.01, -0.09))], 0.01), rm, segs=6))
    # charred, glowing tip of the lit end
    lathe(bm, [(lit.z + 0.035, rm * 1.05), (lit.z + 0.05, rm * 1.0), (lit.z + 0.056, 0.0008)], 'dark', at=(lit.x + 0.004, 0, 0), segs=6)
    return finish(bm, 'galleass_linstock', sharp=50)

# ---------------------------------------------------------------- wicker basket + scattershot bags
def rope_part(bm, build):
    """Run a rope_geom builder and tag its new faces as rope."""
    bm.faces.ensure_lookup_table(); n0 = len(bm.faces)
    build()
    bm.faces.ensure_lookup_table()
    tag(bm, bm.faces[n0:], 'rope')

SACK_TILE = 0.30                                             # metres of cloth per texture repeat (coarse weave)
def uv_sack(bm, faces, R):
    """Cylindrical UVs on the tiling sacking (galleass_sack): u = arc length round the bag, v = height, both in
    texture repeats; the seam runs down the back (angle +-pi) and each face keeps its side of it."""
    uvl = rg.uv_layer(bm)
    for f in faces:
        c = f.calc_center_median(); ac = math.atan2(c.y, c.x)
        for l in f.loops:
            co = l.vert.co
            a = math.atan2(co.y, co.x) if co.xy.length > 1e-6 else ac
            if a - ac > math.pi: a -= 2 * math.pi
            if ac - a > math.pi: a += 2 * math.pi
            l[uvl].uv = (a * R / SACK_TILE, co.z / SACK_TILE)

BASKET_H, BASKET_R0, BASKET_R1, BASKET_FLOOR = 0.26, 0.19, 0.225, 0.12
def basket_r(z):
    return BASKET_R0 + (BASKET_R1 - BASKET_R0) * z / BASKET_H

def build_basket():
    bm = bmesh.new()
    n_st = 16
    for i in range(n_st):                                   # stakes
        a = 2 * math.pi * i / n_st
        pts = [Vector((basket_r(z) * math.cos(a), basket_r(z) * math.sin(a), z)) for z in (0.02, BASKET_H + 0.012)]
        rope_part(bm, lambda pts=pts: rg.rope(bm, pts, 0.006, segs=5))
    rows = 10
    for k in range(rows):                                   # weavers, in and out of the stakes, alternate rows
        z = 0.03 + k * (BASKET_H - 0.05) / (rows - 1)
        pts = []
        for j in range(49):
            a = 2 * math.pi * j / 48
            rr = basket_r(z) + 0.0065 * math.sin(a * n_st / 2 + k * math.pi)
            pts.append(Vector((rr * math.cos(a), rr * math.sin(a), z)))
        rope_part(bm, lambda pts=pts: rg.rope(bm, pts, 0.011, segs=5, caps=False))
    rim = [Vector((basket_r(BASKET_H) * math.cos(2 * math.pi * j / 48), basket_r(BASKET_H) * math.sin(2 * math.pi * j / 48),
                   BASKET_H + 0.006)) for j in range(49)]
    rope_part(bm, lambda: rg.rope(bm, rim, 0.013, segs=6, caps=False))
    for side in (-1, 1):                                    # two rope handles over the rim
        c = Vector((side * basket_r(BASKET_H), 0, BASKET_H))
        pts = [c + Vector((side * 0.01 * math.sin(math.pi * t), 0.07 * math.cos(math.pi * t), 0.07 * math.sin(math.pi * t)))
               for t in [k / 12 for k in range(13)]]
        rope_part(bm, lambda pts=pts: rg.rope(bm, pts, 0.009, segs=6))
    # bottom and the false floor the bags stand on (so they show at the rim)
    lathe(bm, [(0.0, BASKET_R0 + 0.004), (0.02, BASKET_R0 + 0.004)], 'wood', segs=24, cap0=True, cap1=True)
    lathe(bm, [(BASKET_FLOOR - 0.012, basket_r(BASKET_FLOOR) - 0.004), (BASKET_FLOOR, basket_r(BASKET_FLOOR) - 0.004)],
          'wood', segs=24, cap0=True, cap1=True)
    return finish(bm, 'galleass_shot_basket', sharp=60)

def build_bag(gun, seats):
    bm = bmesh.new()
    R = BORE[gun] / 2 * 0.92; Lb, rings = BAG[gun]
    # a soft sack: rounded bottom, a full body, shoulders falling in to a cinched neck and a short gathered tuft
    prof = [(0.0, 0.0), (0.006, R * 0.62), (0.018, R * 0.93), (0.035, R), (Lb * 0.62, R * 1.02), (Lb * 0.78, R * 0.93),
            (Lb * 0.88, R * 0.7), (Lb * 0.95, R * 0.45), (Lb, R * 0.34), (Lb + 0.006, R * 0.42), (Lb + 0.014, R * 0.5),
            (Lb + 0.02, R * 0.36), (Lb + 0.022, 0.0)]
    faces = lathe(bm, prof, 'sack', segs=16)
    # lumpy: the shot inside presses the cloth out unevenly; the tuft is crumpled
    for v in bm.verts:
        a = math.atan2(v.co.y, v.co.x)
        if v.co.xy.length < 1e-6:
            continue
        if 0.01 < v.co.z < Lb * 0.9:
            k = 1.0 + 0.07 * math.sin(5 * a + 31 * v.co.z) * math.sin(math.pi * v.co.z / (Lb * 0.9)) + 0.03 * math.sin(11 * a)
        elif v.co.z > Lb + 0.003:
            k = 1.0 + 0.25 * math.sin(6 * a)
        else:
            continue
        v.co.x *= k; v.co.y *= k
    uv_sack(bm, faces, R)
    rope_part(bm, lambda: rg.ring(bm, (0, 0, Lb - 0.002), (0, 0, 1), R * 0.38, 0.0035, segs=12, tube=4))   # tie
    o = finish(bm, 'galleass_scatter_bag_' + gun, sharp=70)
    pts = []                                                 # filled in by settle_bags() (rigid-body drop)
    seats[gun] = {'bags': pts, 'bag_r': round(R, 4), 'bag_len': Lb}
    return o

BAG_COUNT = {'falcon': 24, 'falconet': 40}                 # dropped; what stays in (heap <= rim + 0.10) is kept
def settle_bags(gun, basket, bag, seats):
    """Drop BAG_COUNT bags into the basket with Blender's rigid-body physics and keep where they come to rest (user
    2026-10-15: no bags clipping into each other, an organic heap). Seeded per calibre, so builds are stable. Seats
    [x, y, z, ex, ey, ez]: bag origin (bottom centre) and the prefab's rotation_euler (Mat3.GetEulerAngles)."""
    import random
    rnd = random.Random('drop/' + gun)
    sc = bpy.context.scene
    if sc.rigidbody_world is None:
        bpy.ops.rigidbody.world_add()
    rw = sc.rigidbody_world
    rw.substeps_per_frame = 20; rw.solver_iterations = 30
    rw.point_cache.frame_start, rw.point_cache.frame_end = 1, 200
    if rw.collection is None:
        rw.collection = bpy.data.collections.new('rbw')
    col = bpy.data.collections.new('drop_' + gun); sc.collection.children.link(col)
    bk = bpy.data.objects.new('drop_basket_' + gun, basket.data); col.objects.link(bk)
    rw.collection.objects.link(bk)
    bk.rigid_body.type = 'PASSIVE'; bk.rigid_body.collision_shape = 'MESH'; bk.rigid_body.collision_margin = 0.001
    # an invisible guard tube just inside the rim, a hand higher, keeps bouncing bags in during the drop only
    gb = bmesh.new()
    gr = basket_r(BASKET_H) - 0.012
    bmesh.ops.create_cone(gb, cap_ends=False, segments=32, radius1=gr, radius2=gr, depth=0.5,
                          matrix=Matrix.Translation((0, 0, BASKET_H + 0.12 - 0.25)))
    gm = bpy.data.meshes.new('guard'); gb.to_mesh(gm); gb.free()
    guard = bpy.data.objects.new('drop_guard', gm); col.objects.link(guard); rw.collection.objects.link(guard)
    guard.rigid_body.type = 'PASSIVE'; guard.rigid_body.collision_shape = 'MESH'; guard.rigid_body.collision_margin = 0.001
    R = BORE[gun] / 2 * 0.92; Lb = BAG[gun][0]
    # the rigid body's centre of mass is the object origin: the bag's own origin (its bottom) made every bag a
    # roly-poly that stood itself up - drop a copy centred on its middle, convert back afterwards
    zc = (Lb + 0.022) / 2
    dm = bag.data.copy(); dm.transform(Matrix.Translation((0, 0, -zc)))
    drops = []
    for i in range(BAG_COUNT[gun]):
        o = bpy.data.objects.new('drop_bag_%s_%d' % (gun, i), dm); col.objects.link(o)
        a, rr = rnd.uniform(-math.pi, math.pi), (BASKET_R0 - Lb * 0.6) * math.sqrt(rnd.random())
        o.location = (rr * math.cos(a), rr * math.sin(a), BASKET_FLOOR + 0.06 + i * (2.2 * R) * 0.35)
        o.rotation_euler = (rnd.uniform(-math.pi, math.pi), rnd.uniform(-math.pi, math.pi), rnd.uniform(-math.pi, math.pi))
        rw.collection.objects.link(o)
        rb = o.rigid_body
        rb.type = 'ACTIVE'; rb.collision_shape = 'CONVEX_HULL'; rb.mass = 2.0; rb.friction = 0.9
        rb.restitution = 0.0; rb.linear_damping = 0.8; rb.angular_damping = 0.9; rb.collision_margin = 0.001
        drops.append(o)
    for f in range(1, 201):
        sc.frame_set(f)
    pts = []
    for o in drops:
        M = o.matrix_world @ Matrix.Translation((0, 0, -zc))     # back to the bag's bottom-centre origin
        mid = M @ Vector((0, 0, zc))
        if M.translation.z < BASKET_FLOOR - 0.05 or mid.xy.length > BASKET_R1 or mid.z > BASKET_H + 0.10:
            continue                                         # fell out / through: leave it out
        s_, f_, u_ = M.col[0].xyz.normalized(), M.col[1].xyz.normalized(), M.col[2].xyz.normalized()
        ex = math.asin(max(-1.0, min(1.0, f_.z))); ey = math.atan2(-s_.z, u_.z); ez = math.atan2(-f_.x, f_.y)
        pts.append([round(v, 4) for v in (M.translation.x, M.translation.y, M.translation.z, ex, ey, ez)])
    seats[gun]['bags'] = pts
    bpy.data.collections.remove(col)
    for o in drops + [bk, guard]:
        bpy.data.objects.remove(o)
    bpy.data.meshes.remove(dm); bpy.data.meshes.remove(gm)
    print('SETTLE %s: %d of %d bags in the basket' % (gun, len(pts), BAG_COUNT[gun]))

# ---------------------------------------------------------------- shot garland
def build_rack(gun, seats):
    r = BALL_R[gun]
    rows, per = RACK[gun]
    pitch = 2 * r + 0.035
    W = per * pitch + 0.06; D = rows * pitch + 0.05
    Ht = max(0.18, 2.2 * r + 0.06)                           # top board height
    tb = 0.04                                                # top board thickness
    hole = r * 0.8
    # the drilled top board on its own (an exact boolean wants one closed solid), then the frame joined to it
    bm = bmesh.new()
    box(bm, -W / 2, W / 2, -D / 2, D / 2, Ht - tb, Ht, 'wood')
    o = finish(bm, 'galleass_shot_rack_' + gun, sharp=30)
    cut = bmesh.new()
    pts = []
    for i in range(rows):
        for k in range(per):
            x = -W / 2 + 0.03 + pitch / 2 + k * pitch
            y = -D / 2 + 0.025 + pitch / 2 + i * pitch
            bmesh.ops.create_cone(cut, cap_ends=True, segments=16, radius1=hole, radius2=hole, depth=tb + 0.02,
                                  matrix=Matrix.Translation((x, y, Ht - tb / 2)))
            zc = Ht + math.sqrt(max(r * r - hole * hole, 0.0))   # ball resting on the hole's top edge
            pts.append([round(x, 4), round(y, 4), round(zc, 4)])
    cm = bpy.data.meshes.new('cut'); cut.to_mesh(cm); cut.free()
    co = bpy.data.objects.new('cut', cm); bpy.context.scene.collection.objects.link(co)
    md = o.modifiers.new('holes', 'BOOLEAN'); md.object = co; md.operation = 'DIFFERENCE'; md.solver = 'EXACT'
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier='holes')
    bpy.data.objects.remove(co); bpy.data.meshes.remove(cm)
    frame = bmesh.new()
    for x0, x1 in ((-W / 2, -W / 2 + 0.03), (W / 2 - 0.03, W / 2)):                 # end boards
        box(frame, x0, x1, -D / 2, D / 2, 0.0, Ht - tb, 'wood')
    for y0, y1 in ((-D / 2, -D / 2 + 0.025), (D / 2 - 0.025, D / 2)):               # side boards
        box(frame, -W / 2 + 0.03, W / 2 - 0.03, y0, y1, 0.04, Ht - tb, 'wood')
    box(frame, -W / 2 + 0.03, W / 2 - 0.03, -D / 2 + 0.025, D / 2 - 0.025, 0.0, 0.02, 'wood')   # floor board
    bm = bmesh.new(); bm.from_mesh(o.data)
    tmp = bpy.data.meshes.new('tmp'); frame.to_mesh(tmp); frame.free(); bm.from_mesh(tmp); bpy.data.meshes.remove(tmp)
    bm.to_mesh(o.data); bm.free()
    seats[gun] = {'balls': pts, 'size': [round(W, 3), round(D, 3), round(Ht, 3)], 'ball_r': r}
    return o

# ---------------------------------------------------------------- falconet locker (2026-10-16)
# The forecastle platform has no room for a keg + rack + basket row (user: one tall locker with everything the
# falconets need, stacked): a shelf unit open to +Y (its front; it stands with its back to the platform's after edge),
# a small powder cask on the floor, a drilled shelf with the balls, a tray of scattershot bags on top. Ball and bag
# seats -> galleass_stores.json 'lockers' (the prefab places them, the add-on empties them with the ship's supply).
LOCKER = dict(W=0.50, D=0.38, H=1.25, t=0.022, z_ball=0.47, z_tray=0.82)
# swivel locker (2026-10-17, user: the poop swivels' loaders got stuck on the poop stairs): the same case on the poop
# without the ball shelf's holes (the swivels fire only shot): powder cask, a plain shelf, the tray of shot bags
def build_locker(gun, seats):
    W, D, H, t = LOCKER['W'], LOCKER['D'], LOCKER['H'], LOCKER['t']
    r = BALL_R.get(gun, 0.0); rows, per = (2, 5) if gun in BALL_R else (0, 0)
    pitch = 2 * r + 0.035
    # the drilled ball shelf first (exact boolean on one closed solid), the rest joined to it
    bm = bmesh.new()
    zb = LOCKER['z_ball']
    box(bm, -W / 2 + t, W / 2 - t, -D / 2 + t, D / 2, zb - 0.03, zb, 'wood')
    o = finish(bm, 'galleass_locker_' + gun, sharp=30)
    cut = bmesh.new(); balls = []
    hole = r * 0.8
    for i in range(rows):
        for k in range(per):
            x = (k - (per - 1) / 2) * pitch
            y = -D / 2 + t + 0.06 + i * pitch
            bmesh.ops.create_cone(cut, cap_ends=True, segments=16, radius1=hole, radius2=hole, depth=0.05,
                                  matrix=Matrix.Translation((x, y, zb - 0.015)))
            balls.append([round(x, 4), round(y, 4), round(zb + math.sqrt(max(r * r - hole * hole, 0.0)), 4)])
    cm = bpy.data.meshes.new('cut'); cut.to_mesh(cm); cut.free()
    if balls:
        co = bpy.data.objects.new('cut', cm); bpy.context.scene.collection.objects.link(co)
        md = o.modifiers.new('holes', 'BOOLEAN'); md.object = co; md.operation = 'DIFFERENCE'; md.solver = 'EXACT'
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier='holes')
        bpy.data.objects.remove(co)
    bpy.data.meshes.remove(cm)
    fr = bmesh.new()
    box(fr, -W / 2, -W / 2 + t, -D / 2, D / 2, 0.0, H, 'wood')                 # sides
    box(fr, W / 2 - t, W / 2, -D / 2, D / 2, 0.0, H, 'wood')
    box(fr, -W / 2 + t, W / 2 - t, -D / 2, -D / 2 + t, 0.0, H, 'wood')         # back
    box(fr, -W / 2, W / 2, -D / 2, D / 2, H - t, H, 'wood')                    # top
    box(fr, -W / 2 + t, W / 2 - t, -D / 2 + t, D / 2, 0.0, 0.03, 'wood')       # floor
    box(fr, -W / 2 + t, W / 2 - t, D / 2 - 0.02, D / 2, 0.03, 0.08, 'wood')    # kick board in front of the cask
    box(fr, -W / 2 + t, W / 2 - t, D / 2 - 0.02, D / 2, zb, zb + 0.04, 'wood') # lip in front of the balls
    zt = LOCKER['z_tray']
    box(fr, -W / 2 + t, W / 2 - t, -D / 2 + t, D / 2, zt - 0.025, zt, 'wood')  # tray floor
    box(fr, -W / 2 + t, W / 2 - t, D / 2 - 0.02, D / 2, zt, zt + 0.07, 'wood') # tray front board
    for hz in (0.62, 1.05):                                                    # iron straps round the case
        box(fr, -W / 2 - 0.004, -W / 2, -D / 2, D / 2, hz, hz + 0.03, 'iron')
        box(fr, W / 2, W / 2 + 0.004, -D / 2, D / 2, hz, hz + 0.03, 'iron')
    # small powder cask on the floor (open, powder a hand below the rim)
    ch, cR, cE = 0.36, 0.15, 0.13
    prof = [(0.0, cE), *[(ch * u, cE + (cR - cE) * math.sin(math.pi * u)) for u in [k / 10 for k in range(1, 10)]], (ch, cE)]
    cask = bmesh.new()
    lathe(cask, prof, 'wood', segs=24, cap0=True)
    lathe(cask, [(ch, cE), (ch, cE - 0.015)], 'wood', segs=24)
    lathe(cask, [(ch - 0.07, cE - 0.012), (ch - 0.065, (cE - 0.012) * 0.6), (ch - 0.06, 0.0)], 'dark', segs=24, up=True)
    for hz in (0.04, ch - 0.04, ch * 0.5):
        rr = cE + (cR - cE) * math.sin(math.pi * hz / ch)
        lathe(cask, [(hz - 0.012, rr + 0.002), (hz - 0.012, rr + 0.006), (hz + 0.012, rr + 0.006), (hz + 0.012, rr + 0.002)], 'iron', segs=24)
    cask.verts.ensure_lookup_table()
    bmesh.ops.translate(cask, vec=(0.0, 0.02, 0.03), verts=cask.verts)
    for part in (fr, cask):
        tmp = bpy.data.meshes.new('tmp'); part.to_mesh(tmp); part.free()
        bm = bmesh.new(); bm.from_mesh(o.data); bm.from_mesh(tmp); bm.to_mesh(o.data); bm.free(); bpy.data.meshes.remove(tmp)
    # bags lying across the tray (axis along x), two layers, the top layer in the gaps
    R = BORE[gun] / 2 * 0.92; Lb = BAG[gun][0] + 0.022
    bags = []
    nx = int((W - 2 * t) // (Lb + 0.01)); ny = int((D - t - 0.03) // (2 * R + 0.006))
    for layer in range(2):
        for i in range(nx):
            for j in range(ny - layer):
                x = -W / 2 + t + 0.005 + (Lb + 0.01) * i
                y = -D / 2 + t + R + 0.003 + (2 * R + 0.006) * (j + 0.5 * layer)
                z = zt + R * (1.0 + 1.6 * layer)
                bags.append([round(x, 4), round(y, 4), round(z, 4), 0.0, round(math.pi / 2, 4), 0.0])   # origin on the axis
    seats[gun] = {'balls': balls, 'bags': bags, 'size': [W, D, H], 'ball_r': r}
    return o

def export(o, lods=()):
    bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o
    for lo in lods: lo.select_set(True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT_FBX, o.name + '.fbx'), use_selection=True, object_types={'MESH'},
                             use_mesh_modifiers=True, mesh_smooth_type='FACE', use_tspace=False, axis_forward='Y',
                             axis_up='Z', apply_unit_scale=True, global_scale=1.0, bake_anim=False, path_mode='STRIP',
                             add_leaf_bones=False)
    print('EXPORT %-34s tris %6d  materials %s' % (o.name + '.fbx', sum(len(p.vertices) - 2 for p in o.data.polygons),
                                                    [m.name for m in o.data.materials]))

objs, seats, bag_seats = [], {}, {}
objs.append(build_keg())
objs.append(build_basket())
for g in ('falcon', 'falconet'):
    objs.append(build_bag(g, bag_seats))
for g in ('falcon', 'falconet'):
    settle_bags(g, bpy.data.objects['galleass_shot_basket'], bpy.data.objects['galleass_scatter_bag_' + g], bag_seats)
for g in ('culverin', 'falcon', 'falconet'):
    objs.append(build_ladle(g, False)); objs.append(build_ladle(g, True))
    objs.append(build_rack(g, seats))
    objs.append(build_sponge(g))
objs.append(build_linstock())
lockers = {}
objs.append(build_locker('falconet', lockers))
objs.append(build_locker('petriera', lockers))
os.makedirs(OUT_FBX, exist_ok=True)
# LODs for what stands in the ship (performance pass 2026-10-27: 146 bags, the baskets, kegs, racks and lockers had none
# - the same ~143k triangles at every distance); the carried tools (ladles, sponges, linstock) stay single
STORE_LODS = ('galleass_powder_keg', 'galleass_shot_basket', 'galleass_scatter_bag_', 'galleass_shot_rack_', 'galleass_locker_')
for o in objs:
    add_uvs(o); o.data.name = o.name
    export(o, make_lods(o) if o.name.startswith(STORE_LODS) else ())

# collision (2026-10-16, user: the stores had none): one light convex hull per store mesh, 'bo_' + its name, physics
# material wood (as the guns' bodies); the balls and bags lie inside their rack's / basket's hull
def body(o):
    bm = bmesh.new()
    for v in o.data.vertices: bm.verts.new(v.co)
    bmesh.ops.convex_hull(bm, input=bm.verts)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    if len(bm.faces) > 60:
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(12), verts=bm.verts, edges=bm.edges)
        bmesh.ops.triangulate(bm, faces=bm.faces)
    name = 'bo_' + o.name
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    me.materials.append(bpy.data.materials.get('wood') or bpy.data.materials.new('wood'))
    bo = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(bo)
    return bo
for o in [x for x in objs if x.name == 'galleass_powder_keg' or x.name.startswith(('galleass_shot_rack_', 'galleass_shot_basket', 'galleass_locker_'))]:
    export(body(o))
json.dump({'racks': seats, 'baskets': bag_seats, 'lockers': lockers, 'basket': {'height': BASKET_H, 'radius': BASKET_R1}, 'keg': {'height': 0.55, 'radius': 0.205}, 'staff': STAFF, 'ball_r': BALL_R},
          open(os.path.join(HERE, 'ref', 'galleass_stores.json'), 'w'), indent=1)

# ---------------------------------------------------------------- review renders
if RENDERS:
    os.makedirs(RENDERS, exist_ok=True)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'MATERIAL'
    sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
    # lay out: keg, racks with balls, ladles on the floor
    x = 0.0
    lay = {}
    keg = bpy.data.objects['galleass_powder_keg']; keg.location = (-1.2, 0.6, 0); lay['keg'] = keg
    for i, g in enumerate(('culverin', 'falcon', 'falconet')):
        rk = bpy.data.objects['galleass_shot_rack_' + g]; rk.location = (0.0, 1.0 - i * 0.7, 0)
        bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=14, v_segments=9, radius=BALL_R[g])
        bme = bpy.data.meshes.new('ball_' + g); bm.to_mesh(bme); bm.free(); bme.materials.append(MATS['iron'])
        for p in seats[g]['balls']:
            b = bpy.data.objects.new('ball', bme); sc.collection.objects.link(b)
            b.location = (p[0], p[1] + 1.0 - i * 0.7, p[2])
        for k, ch in enumerate((False, True)):
            ld = bpy.data.objects['galleass_ladle_%s%s' % (g, '_charged' if ch else '')]
            ld.location = (1.9 + 0.25 * k + i * 0.6, 0.2 - STAFF[g] / 4, 0.03); ld.rotation_euler = (math.radians(-90), 0, 0)
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    def shot(fname, loc, tgt, lens=35):
        cam.location = loc; cam.data.lens = lens
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(RENDERS, fname); bpy.ops.render.render(write_still=True)
    for i, g in enumerate(('falcon', 'falconet')):                  # two filled baskets
        bk = bpy.data.objects['galleass_shot_basket'] if i == 0 else bpy.data.objects.new('basket2', bpy.data.objects['galleass_shot_basket'].data)
        if i: sc.collection.objects.link(bk)
        bk.location = (-1.0 + i * 0.6, -0.6, 0)
        bag = bpy.data.objects['galleass_scatter_bag_' + g]; bag.location = (-0.7 + i * 0.6, -1.1, 0)
        for p in bag_seats[g]['bags']:
            b = bpy.data.objects.new('bag', bag.data); sc.collection.objects.link(b)
            b.location = (p[0] - 1.0 + i * 0.6, p[1] - 0.6, p[2])
            b.rotation_mode = 'YXZ'; b.rotation_euler = (p[3], p[4], p[5])     # R = Rz Rx Ry = Bannerlord ApplyEulerAngles
    shot('stores_all.png', (1.0, -3.8, 2.6), (0.6, 0.4, 0.2), 30)
    shot('stores_baskets.png', (-0.7, -1.9, 1.0), (-0.7, -0.6, 0.15), 45)
    shot('stores_bag.png', (-0.55, -1.45, 0.3), (-0.7, -1.1, 0.07), 70)
    shot('stores_keg.png', (-1.2 + 0.9, 0.6 - 0.9, 0.95), (-1.2, 0.6, 0.35), 50)
    shot('stores_racks.png', (0.0, -1.6, 1.3), (0.0, 0.4, 0.1), 40)
    shot('stores_ladles.png', (2.6, -1.4, 0.8), (2.6, 1.6, 0.0), 45)
    for i, g in enumerate(('culverin', 'falcon', 'falconet')):          # sponge-rammers and the linstock on the floor
        sp = bpy.data.objects['galleass_sponge_' + g]
        sp.location = (4.0 + i * 0.35, 0.2 - STAFF[g] / 4, BORE[g] / 2); sp.rotation_euler = (math.radians(-90), 0, 0)
    ls = bpy.data.objects['galleass_linstock']; ls.location = (5.2, 0.2, 0.0); ls.rotation_euler = (0, 0, 0)
    shot('stores_tools.png', (4.6, -1.6, 1.2), (4.6, 1.0, 0.2), 40)
    shot('stores_sponges.png', (4.85, 2.25, 0.45), (4.35, 1.35, 0.05), 40)
    shot('stores_linstock.png', (5.6, 0.2 - 0.5, 0.95), (5.2, 0.2, 0.74), 55)
    shot('stores_scoops.png', (3.0, 2.1, 0.45), (2.6, 1.7, 0.03), 50)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print('stores done')
