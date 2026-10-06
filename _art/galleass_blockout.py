"""Galleass hull blockout (shape only, no UVs/materials yet).

blender -b --python galleass_blockout.py -- <out.blend> <render dir>

Ship frame as in vanilla War Sails ships: bow +Y, starboard +X, up +Z, waterline z = 0, metres.
Dimensions come from the 1/400 drawing (ref/galleass_drawing.jpg, 17.9 px/m) scaled by
K_LEN = 1.15 along the ship and vertically, and K_WID = 1.0 across (keeps the 12 m footprint).
Drawing px -> ship: y = (px_x - 469) / 17.9 * K_LEN, z = (742 - px_y) / 17.9 * K_LEN.
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
OUT_BLEND, RENDER_DIR = argv[0], argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
K_LEN, K_WID = 1.15, 1.0
PX_M = 17.9

# ---------------------------------------------------------------- main dimensions
Y_STERN_WL, Y_STEM_WL = -25.0, 25.0     # waterline ends
Z_KEEL = -2.5                            # flat keel midships
HB_WL = 4.55 * K_WID                     # max half beam (at Z_MAXB)
Z_MAXB = 0.3
HB_TOP = 4.40 * K_WID                    # half beam at the hull top (slight tumblehome)
Z_HULL_TOP = 0.9                         # top of the hull planking midships (rowing frame above)

Z_ROW_DECK = 0.25                        # rowers' deck (under the gun deck)
Z_GUN_DECK = 2.3                         # gun deck floor
Z_BULWARK_TOP = 3.7
Y_GUNDECK_AFT, Y_GUNDECK_FORE = -14.5, 18.6
HB_DECK = 4.45 * K_WID                   # gun deck / bulwark half width

OUTRIGGER_HW = 6.2 * K_WID               # rowing frame (apostis) half width
Y_OUTR_AFT, Y_OUTR_FORE = -17.6, 20.6
Z_OUTR_LOW, Z_OUTR_RAIL = 1.0, 1.7

# forecastle: horseshoe, five gun embrasures on the upper tier (0, +-45, +-90 deg)
FC_CY, FC_R = 21.6, 4.25 * K_WID         # centre of the round front, radius
FC_Y_BACK = 18.6
FC_Z_PLATFORM, FC_Z_PARAPET, FC_Z_RAIL = 3.9, 5.3, 6.2
FC_EMB_SILL, FC_EMB_TOP, FC_EMB_W = 4.3, 5.0, 0.8

# sterncastle (poop)
SC_Y_AFT, SC_Y_FORE = -24.0, -14.5
SC_Z_FLOOR, SC_Z_RAIL = 4.7, 5.9

# closed rowing level: oar ports in the side planking (oars rest on the outrigger rail)
OARS_PER_SIDE = 16
OAR_Y_AFT, OAR_Y_FORE = -16.5, 17.5
OARPORT_W, OARPORT_Z0, OARPORT_Z1 = 0.32, 1.25, 1.6

# broadside gunports in the gun-deck bulwark
GUNPORTS_PER_SIDE = 5
GP_SILL, GP_TOP, GP_W = 2.85, 3.45, 0.6

# masts (vanilla lateen rigs go here later): mizzen, main, fore
MASTS = {'mizzen': (-13.7, 21.0), 'main': (5.5, 34.8), 'fore': (22.5, 24.5)}
RAM = ((25.0, 2.0), (31.3, 2.0))         # spur from the stem to the tip (y, z)

def px(x, y):
    return ((x - 469) / PX_M * K_LEN, (742 - y) / PX_M * K_LEN)

# ---------------------------------------------------------------- helpers
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
COLL = {}
def coll(name):
    if name not in COLL:
        c = bpy.data.collections.new(name); sc.collection.children.link(c); COLL[name] = c
    return COLL[name]

def mat(name, rgb):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1)
    return m
M_HULL = mat('blk_hull', (0.45, 0.30, 0.18))
M_DECK = mat('blk_deck', (0.70, 0.58, 0.40))
M_WORK = mat('blk_upperworks', (0.62, 0.20, 0.15))
M_FRAME = mat('blk_frame', (0.25, 0.18, 0.12))
M_MARK = mat('blk_marker', (0.1, 0.5, 0.9))
M_GUN = mat('blk_gunport', (0.05, 0.05, 0.05))

def obj_from_bm(bm, name, material, collection='hull'):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); coll(collection).objects.link(o)
    me.materials.append(material)
    for p in me.polygons: p.use_smooth = False
    return o

def box(name, x0, x1, y0, y1, z0, z1, material, collection='hull'):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts:
        v.co = Vector((x0 if v.co.x < 0 else x1, y0 if v.co.y < 0 else y1, z0 if v.co.z < 0 else z1))
    return obj_from_bm(bm, name, material, collection)

def smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0), 1); return t * t * (3 - 2 * t)

# ---------------------------------------------------------------- hull loft
def pchip(pts, x):
    """Monotone cubic through (x, y) points (no overshoot, smooth joins); clamped outside."""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    if x <= xs[0]: return ys[0]
    if x >= xs[-1]: return ys[-1]
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [d[0]] + [0.0] * (n - 2) + [d[-1]]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] > 0:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    m[0] = 0.0                                   # flat keel run-in
    i = max(j for j in range(n - 1) if xs[j] <= x)
    t = (x - xs[i]) / h[i]
    h00, h10, h01, h11 = 2*t**3 - 3*t**2 + 1, t**3 - 2*t**2 + t, -2*t**3 + 3*t**2, t**3 - t**2
    return h00 * ys[i] + h10 * h[i] * m[i] + h01 * ys[i + 1] + h11 * h[i] * m[i + 1]

BOW_PROFILE = [(14.0, Z_KEEL), (17.4, -2.3), (21.3, -1.67), (23.8, -0.84), (25.0, 0.0), (25.2, 1.2), (25.3, 2.4)]
STERN_PROFILE = [(14.0, Z_KEEL), (21.1, -2.25), (23.1, -1.93), (24.3, -1.16), (25.0, 0.0), (25.25, 1.6), (25.4, 3.3)]

def z_bottom(y):
    """Keel / stem / stern profile (side view), from drawing points (stern mirrored to +y)."""
    return pchip(BOW_PROFILE, y) if y >= 0 else pchip(STERN_PROFILE, -y)

def z_top(y):
    """Hull planking top: low midships, rising into the castles at the ends."""
    fore = smoothstep(14.0, 19.0, y) * (Z_GUN_DECK + 0.2 - Z_HULL_TOP)
    aft = smoothstep(-13.0, -20.0, y) * (Z_GUN_DECK + 1.0 - Z_HULL_TOP)
    return Z_HULL_TOP + fore + aft

def half_beam(y, top):
    """Planform: fine at the waterline, full at the top so the round forecastle sits on the bow."""
    if y >= 0:
        t = y / (Y_STEM_WL + (0.3 if top else 0.0)); p = 4.5 if top else 2.4
    else:
        t = -y / (-Y_STERN_WL + (0.4 if top else 0.0)); p = 3.0 if top else 2.2
    t = min(t, 1.0)
    return (HB_TOP if top else HB_WL) * max(1 - t ** p, 0.0) ** 0.5

def section(y, n=24):
    zb, zt = z_bottom(y), z_top(y)
    hb_b, hb_t = half_beam(y, False), half_beam(y, True)
    zm = min(max(Z_MAXB, zb + 0.05), zt - 0.05)
    pts = []
    for i in range(n + 1):
        u = i / n
        z = zb + (zt - zb) * (1 - math.cos(u * math.pi)) / 2      # cosine spacing
        if z <= zm:
            s = (zm - z) / max(zm - zb, 1e-4)
            w = hb_b * max(1 - s ** 2.6, 0) ** (1 / 2.6)              # U section, flat-ish floor
        else:
            w = hb_b + (hb_t - hb_b) * (z - zm) / max(zt - zm, 1e-4)
        pts.append((w, z))
    return pts

def build_hull():
    ys = []
    n_st = 90
    y0, y1 = -25.35, 25.25
    for i in range(n_st + 1):
        t = i / n_st
        ys.append(y0 + (y1 - y0) * (0.5 - 0.5 * math.cos(t * math.pi)))   # denser at the ends
    bm = bmesh.new()
    rings = []
    for y in ys:
        sec = section(y)
        ring = [bm.verts.new((-w, y, z)) for w, z in reversed(sec)] + [bm.verts.new((w, y, z)) for w, z in sec[1:]]
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for i in range(len(a) - 1):
            bm.faces.new((a[i], a[i + 1], b[i + 1], b[i]))
    # close the ends (stem/stern posts get their own pieces)
    for ring, flip in ((rings[0], True), (rings[-1], False)):
        f = bm.faces.new(ring if flip else list(reversed(ring)))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, 'galleass_hull', M_HULL)

def build_post(name, pts, half_t=0.15):
    """Thin extruded profile (stem / stern post) from a list of (y, z)."""
    bm = bmesh.new()
    L = [bm.verts.new((-half_t, y, z)) for y, z in pts]
    R = [bm.verts.new((half_t, y, z)) for y, z in pts]
    for i in range(len(pts) - 1):
        bm.faces.new((L[i], L[i + 1], R[i + 1], R[i]))
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.35)
    return obj_from_bm(bm, name, M_FRAME)

# ---------------------------------------------------------------- upper works
def build_decks():
    box('row_deck', -HB_WL + 0.4, HB_WL - 0.4, -17.0, 17.5, Z_ROW_DECK - 0.1, Z_ROW_DECK, M_DECK)
    box('gun_deck', -HB_DECK, HB_DECK, Y_GUNDECK_AFT, Y_GUNDECK_FORE, Z_GUN_DECK - 0.15, Z_GUN_DECK, M_DECK)
    # bulwarks with gunports cut by boolean
    for side in (-1, 1):
        x0, x1 = sorted((side * HB_DECK, side * (HB_DECK - 0.2)))
        b = box(f'bulwark_{"stbd" if side > 0 else "port"}', x0, x1, Y_GUNDECK_AFT, Y_GUNDECK_FORE,
                Z_GUN_DECK, Z_BULWARK_TOP, M_WORK)
        span = (Y_GUNDECK_FORE - 2.5) - (Y_GUNDECK_AFT + 2.5)
        for i in range(GUNPORTS_PER_SIDE):
            y = Y_GUNDECK_AFT + 2.5 + span * (i + 0.5) / GUNPORTS_PER_SIDE
            cut = box(f'gp_cut', x0 - 0.3, x1 + 0.3, y - GP_W / 2, y + GP_W / 2, GP_SILL, GP_TOP, M_GUN, 'cutters')
            mod = b.modifiers.new('port', 'BOOLEAN'); mod.object = cut; mod.operation = 'DIFFERENCE'
            mark = box(f'gunport_{"stbd" if side > 0 else "port"}_{i}', side * HB_DECK - 0.05, side * HB_DECK + 0.05,
                       y - 0.05, y + 0.05, GP_SILL + 0.05, GP_SILL + 0.15, M_MARK, 'markers')
        # closed rowing level: planking from the hull top to the gun deck, one oar port per bay
        # (rowers stay hidden, as in the drawing). Each bay is built from 4 pieces around the port.
        bays = OARS_PER_SIDE
        for i in range(bays):
            ya = OAR_Y_AFT + (OAR_Y_FORE - OAR_Y_AFT) * i / bays
            yb = OAR_Y_AFT + (OAR_Y_FORE - OAR_Y_AFT) * (i + 1) / bays
            yc = (ya + yb) / 2
            w = half_beam(yc, True)
            x0, x1 = sorted((side * w, side * (w - 0.15)))
            z0, z1 = Z_HULL_TOP - 0.1, Z_GUN_DECK - 0.15
            pa, pb = yc - OARPORT_W / 2, yc + OARPORT_W / 2
            box('row_wall', x0, x1, ya, yb, z0, OARPORT_Z0, M_WORK)
            box('row_wall', x0, x1, ya, yb, OARPORT_Z1, z1, M_WORK)
            box('row_wall', x0, x1, ya, pa, OARPORT_Z0, OARPORT_Z1, M_WORK)
            box('row_wall', x0, x1, pb, yb, OARPORT_Z0, OARPORT_Z1, M_WORK)
            box(f'oarport_{"stbd" if side > 0 else "port"}_{i}', side * w - 0.05, side * w + 0.05,
                yc - 0.05, yc + 0.05, OARPORT_Z0, OARPORT_Z0 + 0.1, M_MARK, 'markers')

def build_outriggers():
    for side in (-1, 1):
        s = 'stbd' if side > 0 else 'port'
        # outer rail (oar tholes) and lower stringer
        box(f'outrigger_rail_{s}', side * OUTRIGGER_HW - 0.12, side * OUTRIGGER_HW + 0.12,
            Y_OUTR_AFT, Y_OUTR_FORE, Z_OUTR_RAIL - 0.2, Z_OUTR_RAIL, M_FRAME)
        box(f'outrigger_low_{s}', side * OUTRIGGER_HW - 0.1, side * OUTRIGGER_HW + 0.1,
            Y_OUTR_AFT, Y_OUTR_FORE, Z_OUTR_LOW, Z_OUTR_LOW + 0.15, M_FRAME)
        # brackets from the hull out to the rail
        for i in range(12):
            y = Y_OUTR_AFT + 0.5 + (Y_OUTR_FORE - Y_OUTR_AFT - 1) * i / 11
            x0, x1 = sorted((side * (HB_TOP - 0.1), side * OUTRIGGER_HW))
            box('outrigger_bracket', x0, x1, y - 0.12, y + 0.12, Z_OUTR_RAIL - 0.35, Z_OUTR_RAIL - 0.15, M_FRAME)
            box('outrigger_post', side * OUTRIGGER_HW - 0.08, side * OUTRIGGER_HW + 0.08, y - 0.08, y + 0.08,
                Z_OUTR_LOW, Z_OUTR_RAIL, M_FRAME)

def horseshoe_outline(r, n=40):
    """Plan outline: straight sides from FC_Y_BACK to FC_CY, semicircle in front."""
    pts = [(-r, FC_Y_BACK)]
    for i in range(n + 1):
        a = math.pi - math.pi * i / n          # from port (180 deg) over the bow to starboard (0 deg)
        pts.append((r * math.cos(a), FC_CY + r * math.sin(a)))
    pts.append((r, FC_Y_BACK))
    return pts

def build_forecastle():
    def ring_solid(name, r_out, wall, z0, z1, material):
        bm = bmesh.new()
        outer = horseshoe_outline(r_out); inner = horseshoe_outline(r_out - wall)
        def layer(pts, z): return [bm.verts.new((x, y, z)) for x, y in pts]
        ob, ot, ib, it = layer(outer, z0), layer(outer, z1), layer(inner, z0), layer(inner, z1)
        for i in range(len(outer) - 1):
            bm.faces.new((ob[i], ob[i + 1], ot[i + 1], ot[i]))
            bm.faces.new((ib[i + 1], ib[i], it[i], it[i + 1]))
            bm.faces.new((ot[i], ot[i + 1], it[i + 1], it[i]))
            bm.faces.new((ib[i], ib[i + 1], ob[i + 1], ob[i]))
        for a, b, c, d in ((ob[0], ot[0], it[0], ib[0]), (ib[-1], it[-1], ot[-1], ob[-1])):
            bm.faces.new((a, b, c, d))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return obj_from_bm(bm, name, material)

    def disc(name, r, z0, z1, material):
        bm = bmesh.new()
        pts = horseshoe_outline(r)
        bot = [bm.verts.new((x, y, z0)) for x, y in pts]; top = [bm.verts.new((x, y, z1)) for x, y in pts]
        bm.faces.new(list(reversed(bot))); bm.faces.new(top)
        for i in range(len(pts)):
            j = (i + 1) % len(pts)
            bm.faces.new((bot[i], bot[j], top[j], top[i]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return obj_from_bm(bm, name, material)

    # lower tier (solid base, round decorative ports later) and the open gun platform above it
    ring_solid('forecastle_lower', FC_R, 0.35, Z_GUN_DECK - 0.15, FC_Z_PLATFORM, M_WORK)
    disc('forecastle_platform', FC_R - 0.05, FC_Z_PLATFORM - 0.15, FC_Z_PLATFORM, M_DECK)
    par = ring_solid('forecastle_parapet', FC_R, 0.35, FC_Z_PLATFORM, FC_Z_PARAPET, M_WORK)
    for deg in (-90, -45, 0, 45, 90):
        a = math.radians(90 - deg)                     # 0 deg = straight ahead (+Y)
        dx, dy = math.cos(a), math.sin(a)
        cx, cy = FC_R * dx, FC_CY + FC_R * dy
        if abs(deg) == 90:                              # abeam guns sit on the straight sides
            cy = FC_CY - 0.2
        cut = box('emb_cut', -FC_EMB_W / 2, FC_EMB_W / 2, -0.8, 0.8, FC_EMB_SILL, FC_EMB_TOP, M_GUN, 'cutters')
        cut.location = (cx, cy, 0); cut.rotation_euler = (0, 0, a - math.pi / 2)
        mod = par.modifiers.new(f'emb{deg}', 'BOOLEAN'); mod.object = cut; mod.operation = 'DIFFERENCE'
        m = box(f'fc_gun_{deg:+d}', -0.1, 0.1, -0.1, 0.1, FC_Z_PLATFORM, FC_Z_PLATFORM + 0.4, M_MARK, 'markers')
        m.location = (cx - dx * 1.6, cy - dy * 1.6, 0)
    # open railing posts above the parapet
    pts = horseshoe_outline(FC_R - 0.15, n=28)
    for x, y in pts[1:-1:2]:
        box('fc_rail_post', x - 0.06, x + 0.06, y - 0.06, y + 0.06, FC_Z_PARAPET, FC_Z_RAIL, M_FRAME)
    ring_solid('forecastle_rail', FC_R - 0.05, 0.2, FC_Z_RAIL - 0.12, FC_Z_RAIL, M_FRAME)

def tapered_block(name, ya, yb, z0, z1, hw_fn, material, n=16, grow=0.0):
    """Block whose half width follows hw_fn(y) between ya and yb (castle bodies on a tapering hull)."""
    bm = bmesh.new()
    rings = []
    for i in range(n + 1):
        y = ya + (yb - ya) * i / n
        w = hw_fn(y) + grow
        rings.append([bm.verts.new(c) for c in ((-w, y, z0), (w, y, z0), (w, y, z1), (-w, y, z1))])
    for a, b in zip(rings, rings[1:]):
        for i in range(4):
            bm.faces.new((a[i], a[(i + 1) % 4], b[(i + 1) % 4], b[i]))
    bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, name, material)

def build_sterncastle():
    hw = lambda y: half_beam(y, True)
    tapered_block('sterncastle_body', SC_Y_AFT, SC_Y_FORE, Z_GUN_DECK - 0.15, SC_Z_FLOOR, hw, M_WORK, grow=0.05)
    tapered_block('poop_deck', SC_Y_AFT - 0.3, SC_Y_FORE + 0.2, SC_Z_FLOOR, SC_Z_FLOOR + 0.12, hw, M_DECK, grow=0.15)
    for side in (-1, 1):
        for i in range(11):
            y = SC_Y_AFT + (SC_Y_FORE - SC_Y_AFT) * i / 10
            x = side * (hw(y) + 0.05)
            box('balustre', x - 0.05, x + 0.05, y - 0.05, y + 0.05, SC_Z_FLOOR, SC_Z_RAIL, M_FRAME)
    for side in (-1, 1):                               # side rails, one straight piece per baluster bay
        for i in range(10):
            ya = SC_Y_AFT + (SC_Y_FORE - SC_Y_AFT) * i / 10
            yb = SC_Y_AFT + (SC_Y_FORE - SC_Y_AFT) * (i + 1) / 10
            x = side * (hw((ya + yb) / 2) + 0.05)
            box('poop_rail', x - 0.07, x + 0.07, ya, yb, SC_Z_RAIL - 0.1, SC_Z_RAIL, M_FRAME)
    w = hw(SC_Y_AFT) + 0.05
    box('poop_rail_aft', -w, w, SC_Y_AFT - 0.07, SC_Y_AFT + 0.07, SC_Z_RAIL - 0.1, SC_Z_RAIL, M_FRAME)

def build_spur_and_posts():
    (ya, za), (yb, zb) = RAM
    bm = bmesh.new()
    prof = [(ya - 1.0, 0.45), (ya, 0.45), (yb - 1.2, 0.25), (yb, 0.02)]
    rings = []
    for y, r in prof:
        z = za + (zb - za) * (y - ya) / (yb - ya)
        rings.append([bm.verts.new((r * math.cos(t), y, z + r * math.sin(t))) for t in [i * math.pi / 4 for i in range(8)]])
    for a, b in zip(rings, rings[1:]):
        for i in range(8):
            bm.faces.new((a[i], a[(i + 1) % 8], b[(i + 1) % 8], b[i]))
    bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj_from_bm(bm, 'spur', M_FRAME)
    # stern post rising and curling aft, stem head
    stern = [(-25.0, -0.5), (-25.25, 1.6), (-25.4, 3.3), (-25.6, 5.0), (-26.2, 6.4), (-27.0, 7.0), (-27.4, 6.6)]
    build_post('stern_post', stern)
    build_post('stem', [(24.6, -1.2), (25.0, 0.0), (25.3, 1.4), (25.4, 2.6)])

def build_markers():
    for name, (y, h) in MASTS.items():
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.35, radius2=0.18, depth=h)
        for v in bm.verts: v.co.z += h / 2; v.co.y += y
        o = obj_from_bm(bm, f'mast_{name}', M_MARK, 'markers')

# ---------------------------------------------------------------- build
hull = build_hull()
build_decks(); build_outriggers(); build_forecastle(); build_sterncastle(); build_spur_and_posts(); build_markers()
coll('cutters').hide_render = True; coll('cutters').hide_viewport = True

# ---------------------------------------------------------------- reference planes
def ref_plane(name, crop, map_fn, plane, offset):
    img = bpy.data.images.load(os.path.join(HERE, 'ref/galleass_drawing.jpg'), check_existing=True)
    W, H = img.size
    (a0, b0), (a1, b1) = map_fn(crop[0], crop[3]), map_fn(crop[2], crop[1])
    bpy.ops.mesh.primitive_plane_add()
    o = bpy.context.object; o.name = name
    for c in o.users_collection: c.objects.unlink(o)
    coll('reference').objects.link(o)
    corners = [(a0, b0), (a1, b0), (a0, b1), (a1, b1)]       # primitive plane vertex order
    for v, (a, b) in zip(o.data.vertices, corners):
        v.co = (offset, a, b) if plane == 'YZ' else (a, offset, b)
    uv = o.data.uv_layers.active.data
    for loop in o.data.loops:
        a, b = corners[loop.vertex_index]
        uv[loop.index].uv = ((crop[0] if a == a0 else crop[2]) / W, 1 - (crop[3] if b == b0 else crop[1]) / H)
    m = bpy.data.materials.new(name); m.use_nodes = True
    t = m.node_tree.nodes.new('ShaderNodeTexImage'); t.image = img
    m.node_tree.links.new(t.outputs['Color'], m.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    o.data.materials.append(m)
    return o

side_ref = ref_plane('ref_side', (20, 150, 1080, 800), lambda x, y: px(x, y), 'YZ', -14)
# front section: centre line at px x 1281, same vertical calibration (waterline 744.5 in that view)
front_ref = ref_plane('ref_front', (1140, 600, 1420, 800),
                      lambda x, y: ((x - 1281) / PX_M * K_WID, (744.5 - y) / PX_M * K_LEN), 'XZ', -40)

# ---------------------------------------------------------------- renders
sc.render.engine = 'BLENDER_WORKBENCH'
shd = sc.display.shading
shd.light = 'STUDIO'; shd.color_type = 'MATERIAL'
sc.render.resolution_x, sc.render.resolution_y = 2000, 1000
sc.world = bpy.data.worlds.new('w'); sc.world.color = (0.9, 0.9, 0.92)
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam

def shot(fname, loc, rot, ortho=None, xray=False, refs=(), res=(2000, 1000), color='MATERIAL'):
    for r in (side_ref, front_ref):
        r.hide_render = r not in refs
    cam.location = loc; cam.rotation_euler = [math.radians(a) for a in rot]
    if ortho:
        cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
    else:
        cam.data.type = 'PERSP'; cam.data.lens = 35
    shd.show_xray = xray; shd.xray_alpha = 0.6
    shd.color_type = 'TEXTURE' if refs else color
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = os.path.join(RENDER_DIR, fname)
    bpy.ops.render.render(write_still=True)

os.makedirs(RENDER_DIR, exist_ok=True)
for o in coll('hull').objects:                 # texture mode shows material colour for untextured objects
    pass
shot('blk_side_overlay.png', (40, 3, 8), (90, 0, 90), ortho=72, xray=True, refs=(side_ref,))
shot('blk_side.png', (40, 3, 8), (90, 0, 90), ortho=72)
shot('blk_top.png', (0, 3, 80), (0, 0, 90), ortho=72)
shot('blk_front_overlay.png', (0, 60, 6), (90, 0, 180), ortho=22, xray=True, refs=(front_ref,), res=(1200, 1000))
shot('blk_persp.png', (32, 52, 22), (68, 0, 148))
shot('blk_persp_aft.png', (-30, -48, 16), (75, 0, -32))
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print('blockout done')
