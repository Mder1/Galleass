"""Galleass model generator (hull and superstructure, no masts/sails/oars: those are vanilla prefabs).

blender -b --python galleass_model.py -- <out.blend> <render dir>

Ship frame as in vanilla War Sails ships: bow +Y, starboard +X, up +Z, waterline z = 0, metres.
Dimensions come from the 1/400 drawing (ref/galleass_drawing.jpg, 17.9 px/m) scaled by
K_LEN = 1.15 along the ship and vertically, and K_WID = 1.0 across (keeps the 12 m footprint).
Drawing px -> ship: y = (px_x - 469) / 17.9 * K_LEN, z = (742 - px_y) / 17.9 * K_LEN.

Every part is created with a material ROLE; at the end parts are merged into one object per role
(galleass_<role>) so the Modding Kit import gets a few meshes with one material each. The rudder
stays separate (it rotates in game).
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:]
OUT_BLEND, RENDER_DIR = argv[0], argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
K_LEN, K_WID = 1.15, 1.0
PX_M = 17.9

# ================================================================= main dimensions
Y_STERN_WL, Y_STEM_WL = -25.0, 25.0     # waterline ends
Z_KEEL = -2.5                            # flat keel midships
HB_WL = 4.55 * K_WID                     # max half beam (at Z_MAXB)
Z_MAXB = 0.4
HB_TOP = 4.45 * K_WID                    # half beam at the hull top (slight tumblehome)
Z_HULL_TOP = 0.9                         # top of the hull shell midships (rowing level above)

Z_GUN_DECK = 2.3                         # gun deck floor (rowing level below it is closed)
Z_BULWARK_TOP = 3.7
Y_GUNDECK_AFT, Y_GUNDECK_FORE = -14.5, 18.6
HB_DECK = 4.45 * K_WID                   # gun deck / bulwark half width (outer face)

OUTRIGGER_HW = 6.2 * K_WID               # rowing frame (apostis) half width
Y_OUTR_AFT, Y_OUTR_FORE = -17.6, 20.6
Z_OUTR_LOW, Z_OUTR_RAIL = 1.0, 1.7

# closed rowing level: oar ports in the side planking (unmanned oars rest on the outrigger rail)
OARS_PER_SIDE = 16
OAR_Y_AFT, OAR_Y_FORE = -16.5, 17.5
OARPORT_W, OARPORT_Z0, OARPORT_Z1 = 0.32, 1.25, 1.6

# broadside gunports in the gun-deck bulwark (cannons)
GUNPORTS_PER_SIDE = 5
GP_SILL, GP_TOP, GP_W = 2.85, 3.45, 0.6

# forecastle: tapered horseshoe, five gun embrasures on the upper tier (0, +-45, +-90 deg)
FC_CY = 21.6                             # centre of the round front
FC_R_BASE, FC_R_TOP = 4.35 * K_WID, 4.15 * K_WID
FC_Y_BACK = 18.6
FC_Z_BASE = 2.15
FC_Z_PLATFORM, FC_Z_PARAPET, FC_Z_RAIL = 3.9, 5.3, 6.0
FC_EMB_SILL, FC_EMB_TOP, FC_EMB_W = 4.3, 5.0, 0.8
FC_GUN_DEGS = (-90, -45, 0, 45, 90)
FC_LOWER_PORT_DEGS = (-40, 0, 40)        # round decorative ports on the lower tier
FC_STAIR_X = 2.4                         # centre line of the two stairs up to the platform

# sterncastle: cabin with windows, poop deck with turned balustrade, awning frame, lantern
SC_Y_AFT, SC_Y_FORE = -24.0, -14.5
SC_Z_FLOOR = 5.3                         # poop deck
SC_Z_RAIL = 6.45
SC_AWNING_Y = (-23.4, -18.6)            # aft hoop clears the stern lantern
SC_Z_AWNING = 8.7
SC_STAIR_X = 3.25                        # centre line of the two stairs up to the poop
LANTERN_Y = -24.15                       # on the poop deck, just inside the aft rail

# masts (vanilla lateen rigs go here later): mizzen, main, fore
MASTS = {'mizzen': -13.7, 'main': 5.5, 'fore': 22.5}
# bow slot: vanilla rams (ram_01..08) as on the meditheavy (scale 1.9, at the waterline), shifted from the
# meditheavy's waterline stem (y 18.46) to ours (y 25.0). The adaptor sheath is shown only with a ram fitted.
RAM_FWD, RAM_DOWN = 0.0, 0.0             # same relation to the waterline stem as on the meditheavy
RAM_POS, RAM_SCALE = (0.0, -10.74 + (Y_STEM_WL - 18.46) + RAM_FWD, 1.18 - RAM_DOWN), 1.9
ADAPTOR_Y0, ADAPTOR_Z = 21.5, (-1.7, 1.9)

ROLES = {                                 # role -> blockout colour (real materials are set up in the Kit)
    'hull':  (0.42, 0.28, 0.17),          # hull planking (below the rowing level)
    'paint': (0.55, 0.13, 0.10),          # painted upper works
    'deck':  (0.72, 0.60, 0.42),
    'trim':  (0.22, 0.15, 0.10),          # rails, wales, mouldings, frames
    'gilt':  (0.85, 0.66, 0.25),          # carved/gilded decoration
    'iron':  (0.20, 0.20, 0.22),
    'dark':  (0.03, 0.03, 0.03),          # port/window interiors
    'glass': (0.95, 0.80, 0.45),          # lantern panes (emissive in game)
}

# ================================================================= scene helpers
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
COLL = {}
def coll(name):
    if name not in COLL:
        c = bpy.data.collections.new(name); sc.collection.children.link(c); COLL[name] = c
    return COLL[name]

MATS = {}
for role, rgb in ROLES.items():
    m = bpy.data.materials.new('galleass_' + role); m.diffuse_color = (*rgb, 1); MATS[role] = m

PARTS = []                                # (object, role)
def obj_from_bm(bm, name, role, collection='parts', smooth=False):
    if smooth:
        for f in bm.faces: f.smooth = True
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); coll(collection).objects.link(o)
    me.materials.append(MATS[role])
    if collection == 'parts':
        PARTS.append((o, role))
    return o

def box(name, x0, x1, y0, y1, z0, z1, role, collection='parts'):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts:
        v.co = Vector((x0 if v.co.x < 0 else x1, y0 if v.co.y < 0 else y1, z0 if v.co.z < 0 else z1))
    return obj_from_bm(bm, name, role, collection)

def cutter_box(cx, cy, cz, sx, sy, sz, rot_z=0.0):
    o = box('cut', -sx / 2, sx / 2, -sy / 2, sy / 2, -sz / 2, sz / 2, 'dark', 'cutters')
    o.location = (cx, cy, cz); o.rotation_euler = (0, 0, rot_z)
    return o

def cutter_cyl(cx, cy, cz, r, depth, axis_rot):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=r, radius2=r, depth=depth)
    o = obj_from_bm(bm, 'cut', 'dark', 'cutters')
    o.location = (cx, cy, cz); o.rotation_euler = axis_rot
    return o

def subtract(target, cutters):
    for i, c in enumerate(cutters):
        m = target.modifiers.new(f'cut{i}', 'BOOLEAN'); m.object = c; m.operation = 'DIFFERENCE'
        m.solver = 'EXACT'

def lathe(name, profile, role, at=(0, 0, 0), segs=8, cap=True):
    """Revolve [(r, z)] around the local Z axis, placed at `at`."""
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        rings.append([bm.verts.new((at[0] + r * math.cos(2 * math.pi * i / segs),
                                    at[1] + r * math.sin(2 * math.pi * i / segs), at[2] + z)) for i in range(segs)])
    for a, b in zip(rings, rings[1:]):
        for i in range(segs):
            bm.faces.new((a[i], a[(i + 1) % segs], b[(i + 1) % segs], b[i]))
    if cap:
        bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, name, role, smooth=True)

def sweep(name, pts, radii, role, segs=8, square=False, cap=True):
    """Tube along a polyline (parallel-transported frames); square=True gives a beam."""
    pts = [Vector(p) for p in pts]
    if not isinstance(radii, (list, tuple)):
        radii = [radii] * len(pts)
    tangents = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]; b = pts[min(i + 1, len(pts) - 1)]
        tangents.append((b - a).normalized())
    ref = Vector((1, 0, 0)) if abs(tangents[0].x) < 0.9 else Vector((0, 0, 1))
    n = (ref - tangents[0] * ref.dot(tangents[0])).normalized()
    bm = bmesh.new(); rings = []
    k = 4 if square else segs
    for i, (p, t) in enumerate(zip(pts, tangents)):
        n = (n - t * n.dot(t)).normalized()
        bnorm = t.cross(n)
        ring = []
        for j in range(k):
            a = 2 * math.pi * j / k + (math.pi / 4 if square else 0)
            ring.append(bm.verts.new(p + (n * math.cos(a) + bnorm * math.sin(a)) * radii[i]))
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for j in range(k):
            bm.faces.new((a[j], a[(j + 1) % k], b[(j + 1) % k], b[j]))
    if cap:
        bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, name, role, smooth=not square)

def spiral(c, r0, r1, a0, a1, n=24, plane='YZ'):
    """Points of a flat spiral (volute) around centre c in the given plane."""
    out = []
    for i in range(n + 1):
        t = i / n; a = a0 + (a1 - a0) * t; r = r0 + (r1 - r0) * t
        u, v = r * math.cos(a), r * math.sin(a)
        out.append((c[0], c[1] + u, c[2] + v) if plane == 'YZ' else (c[0] + u, c[1], c[2] + v))
    return out

def smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0), 1); return t * t * (3 - 2 * t)

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

# ================================================================= hull shape
BOW_PROFILE = [(14.0, Z_KEEL), (17.4, -2.3), (21.3, -1.67), (23.8, -0.84), (25.0, 0.0), (25.2, 1.2), (25.3, 2.4)]
STERN_PROFILE = [(14.0, Z_KEEL), (21.1, -2.25), (23.1, -1.93), (24.3, -1.16), (25.0, 0.0), (25.25, 1.6), (25.4, 3.3)]

def z_bottom(y):
    """Keel / stem / stern profile (side view), from drawing points (stern mirrored to +y)."""
    return pchip(BOW_PROFILE, y) if y >= 0 else pchip(STERN_PROFILE, -y)

def z_top(y):
    """Top of the hull shell: low midships, rising under the castles at the ends."""
    fore = smoothstep(15.0, 19.5, y) * (FC_Z_BASE - Z_HULL_TOP)
    aft = smoothstep(-13.0, -19.5, y) * (FC_Z_BASE - Z_HULL_TOP)
    return Z_HULL_TOP + fore + aft

def half_beam(y, top):
    """Planform: fine at the waterline, full at the top so the round forecastle sits on the bow."""
    if y >= 0:
        t = y / (Y_STEM_WL + (0.3 if top else 0.0)); p = 4.5 if top else 2.4
    else:
        t = -y / (-Y_STERN_WL + (0.4 if top else 0.0)); p = 3.0 if top else 2.2
    t = min(t, 1.0)
    return (HB_TOP if top else HB_WL) * max(1 - t ** p, 0.0) ** 0.5

def section(y, n=28):
    """Wall-sided galley section: flat floor, firm bilge, near-vertical sides (front view)."""
    zt = z_top(y)
    zb = min(z_bottom(y), zt - 0.15)          # the ends: keel line must stay below the hull top
    hb_b, hb_t = half_beam(y, False), half_beam(y, True)
    zm = min(max(Z_MAXB, zb + 0.05), zt - 0.05)
    pts = []
    for i in range(n + 1):
        u = i / n
        z = zb + (zt - zb) * (1 - math.cos(u * math.pi)) / 2
        if z <= zm:
            s = (zm - z) / max(zm - zb, 1e-4)
            w = hb_b * max(1 - s ** 3.4, 0) ** (1 / 3.4)
        else:
            w = hb_b + (hb_t - hb_b) * (z - zm) / max(zt - zm, 1e-4)
        pts.append((w, z))
    return pts

def hull_x_at(y, z):
    """Half width of the hull surface at (y, z) (for placing wales/fittings on the shell)."""
    sec = section(y, 60)
    for (w0, z0), (w1, z1) in zip(sec, sec[1:]):
        if z0 <= z <= z1:
            return w0 + (w1 - w0) * (z - z0) / max(z1 - z0, 1e-6)
    return sec[-1][0]

def build_hull():
    ys = []
    n_st = 110
    y0, y1 = -25.2, 25.2
    for i in range(n_st + 1):
        t = i / n_st
        ys.append(y0 + (y1 - y0) * (0.5 - 0.5 * math.cos(t * math.pi)))
    bm = bmesh.new()
    rings = []
    for y in ys:
        sec = section(y)
        ring = [bm.verts.new((-w, y, z)) for w, z in reversed(sec)] + [bm.verts.new((w, y, z)) for w, z in sec[1:]]
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for i in range(len(a) - 1):
            bm.faces.new((a[i], a[i + 1], b[i + 1], b[i]))
    for ring, flip in ((rings[0], True), (rings[-1], False)):
        bm.faces.new(ring if flip else list(reversed(ring)))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, 'hull_shell', 'hull', smooth=True)

def wale(name, z_fn, y0, y1, thick=0.09, height=0.18, n=80, role='trim'):
    """Strake running along the hull surface on both sides at height z_fn(y)."""
    for side in (-1, 1):
        pts = []
        for i in range(n + 1):
            y = y0 + (y1 - y0) * i / n
            z = z_fn(y)
            pts.append((side * (hull_x_at(y, z) + thick * 0.5), y, z))
        sweep(f'{name}_{side}', pts, max(thick, height) * 0.5, role, square=True)

# ================================================================= rowing level and gun deck
def build_rowing_level():
    """Closed planking from the hull top to the gun deck, one oar port per bay (rowers hidden)."""
    for side in (-1, 1):
        s = 'stbd' if side > 0 else 'port'
        for i in range(OARS_PER_SIDE):
            ya = OAR_Y_AFT + (OAR_Y_FORE - OAR_Y_AFT) * i / OARS_PER_SIDE
            yb = OAR_Y_AFT + (OAR_Y_FORE - OAR_Y_AFT) * (i + 1) / OARS_PER_SIDE
            yc = (ya + yb) / 2
            w = half_beam(yc, True)
            x0, x1 = sorted((side * w, side * (w - 0.15)))
            z0, z1 = Z_HULL_TOP - 0.1, Z_GUN_DECK - 0.15
            pa, pb = yc - OARPORT_W / 2, yc + OARPORT_W / 2
            box('row_wall', x0, x1, ya, yb, z0, OARPORT_Z0, 'paint')
            box('row_wall', x0, x1, ya, yb, OARPORT_Z1, z1, 'paint')
            box('row_wall', x0, x1, ya, pa, OARPORT_Z0, OARPORT_Z1, 'paint')
            box('row_wall', x0, x1, pb, yb, OARPORT_Z0, OARPORT_Z1, 'paint')
            # port frame (proud of the planking) and a dark back so the hole doesn't show the void
            fx0, fx1 = sorted((side * (w + 0.04), side * w))
            for (ya2, yb2, za, zb) in ((pa - 0.06, pb + 0.06, OARPORT_Z0 - 0.06, OARPORT_Z0),
                                       (pa - 0.06, pb + 0.06, OARPORT_Z1, OARPORT_Z1 + 0.06),
                                       (pa - 0.06, pa, OARPORT_Z0, OARPORT_Z1), (pb, pb + 0.06, OARPORT_Z0, OARPORT_Z1)):
                box('oarport_frame', fx0, fx1, ya2, yb2, za, zb, 'trim')
            bx0, bx1 = sorted((side * (w - 0.45), side * (w - 0.5)))
            box('oarport_back', bx0, bx1, pa - 0.05, pb + 0.05, OARPORT_Z0 - 0.05, OARPORT_Z1 + 0.05, 'dark')
    # deck under the rowing level, only so the oar ports show a floor
    box('row_deck', -HB_WL + 0.6, HB_WL - 0.6, OAR_Y_AFT, OAR_Y_FORE, 0.15, 0.25, 'dark')

def gunport_y(i):
    span = (Y_GUNDECK_FORE - 3.0) - (Y_GUNDECK_AFT + 3.0)
    return Y_GUNDECK_AFT + 3.0 + span * (i + 0.5) / GUNPORTS_PER_SIDE

def build_gun_deck():
    box('gun_deck', -HB_DECK + 0.05, HB_DECK - 0.05, Y_GUNDECK_AFT, Y_GUNDECK_FORE, Z_GUN_DECK - 0.15, Z_GUN_DECK, 'deck')
    for side in (-1, 1):
        s = 'stbd' if side > 0 else 'port'
        x0, x1 = sorted((side * HB_DECK, side * (HB_DECK - 0.2)))
        bw = box(f'bulwark_{s}', x0, x1, Y_GUNDECK_AFT, Y_GUNDECK_FORE, Z_GUN_DECK - 0.15, Z_BULWARK_TOP, 'paint')
        cuts = []
        for i in range(GUNPORTS_PER_SIDE):
            y = gunport_y(i)
            cuts.append(cutter_box(side * (HB_DECK - 0.1), y, (GP_SILL + GP_TOP) / 2, 0.8, GP_W, GP_TOP - GP_SILL))
            # gilded wreath around the port (the drawing's rosettes) and a sill
            fx = side * (HB_DECK + 0.03)
            ring = []
            for k in range(17):
                a = 2 * math.pi * k / 16
                ring.append((fx, y + 0.48 * math.cos(a), (GP_SILL + GP_TOP) / 2 + 0.42 * math.sin(a)))
            sweep('gunport_wreath', ring, 0.05, 'gilt', segs=6, cap=False)
            box('gunport_sill', *sorted((side * HB_DECK, side * (HB_DECK + 0.08))), y - GP_W / 2 - 0.05,
                y + GP_W / 2 + 0.05, GP_SILL - 0.06, GP_SILL, 'trim')
        subtract(bw, cuts)
        # cap rail, rub rail at deck level and a moulding between
        box('cap_rail', *sorted((side * (HB_DECK + 0.06), side * (HB_DECK - 0.26))), Y_GUNDECK_AFT, Y_GUNDECK_FORE,
            Z_BULWARK_TOP, Z_BULWARK_TOP + 0.1, 'trim')
        box('rub_rail', *sorted((side * (HB_DECK + 0.1), side * (HB_DECK - 0.02))), OAR_Y_AFT - 0.5, OAR_Y_FORE + 0.5,
            Z_GUN_DECK - 0.3, Z_GUN_DECK - 0.1, 'trim')
        box('moulding', *sorted((side * (HB_DECK + 0.05), side * HB_DECK)), Y_GUNDECK_AFT, Y_GUNDECK_FORE,
            GP_TOP + 0.08, GP_TOP + 0.14, 'gilt')
        # stanchions inside the bulwark
        for k in range(int((Y_GUNDECK_FORE - Y_GUNDECK_AFT) / 1.6) + 1):
            y = Y_GUNDECK_AFT + 0.3 + k * 1.6
            if any(abs(y - gunport_y(i)) < 0.6 for i in range(GUNPORTS_PER_SIDE)):
                continue
            box('stanchion', *sorted((side * (HB_DECK - 0.2), side * (HB_DECK - 0.32))), y - 0.07, y + 0.07,
                Z_GUN_DECK, Z_BULWARK_TOP, 'trim')
    # hatches (gratings) and mast partners
    for y in (-6.5, 12.0):
        box('hatch_coaming', -0.9, 0.9, y - 0.75, y + 0.75, Z_GUN_DECK, Z_GUN_DECK + 0.2, 'trim')
        box('hatch_grating', -0.8, 0.8, y - 0.65, y + 0.65, Z_GUN_DECK + 0.05, Z_GUN_DECK + 0.18, 'dark')
        for k in range(7):
            yy = y - 0.6 + k * 0.2
            box('grating_bar', -0.8, 0.8, yy - 0.03, yy + 0.03, Z_GUN_DECK + 0.15, Z_GUN_DECK + 0.2, 'trim')
    for name, y in MASTS.items():
        z = Z_GUN_DECK if name != 'fore' else FC_Z_PLATFORM
        lathe(f'mast_partner_{name}', [(0.62, 0), (0.62, 0.12), (0.5, 0.3), (0.5, 0.32)], 'trim', at=(0, y, z), segs=10)

def build_outriggers():
    for side in (-1, 1):
        s = 'stbd' if side > 0 else 'port'
        X = side * OUTRIGGER_HW
        box(f'outrigger_rail_{s}', X - 0.12, X + 0.12, Y_OUTR_AFT, Y_OUTR_FORE, Z_OUTR_RAIL - 0.22, Z_OUTR_RAIL, 'trim')
        box(f'outrigger_low_{s}', X - 0.09, X + 0.09, Y_OUTR_AFT, Y_OUTR_FORE, Z_OUTR_LOW, Z_OUTR_LOW + 0.15, 'trim')
        n = 12
        for i in range(n):
            y = Y_OUTR_AFT + 0.5 + (Y_OUTR_FORE - Y_OUTR_AFT - 1) * i / (n - 1)
            xh = side * (half_beam(y, True) - 0.05)
            box('outrigger_bracket', *sorted((xh, X)), y - 0.12, y + 0.12, Z_OUTR_RAIL - 0.42, Z_OUTR_RAIL - 0.22, 'trim')
            sweep('outrigger_strut', [(X, y, Z_OUTR_LOW + 0.05), (xh, y, Z_OUTR_LOW - 0.35)], 0.07, 'trim', square=True)
            box('outrigger_post', X - 0.07, X + 0.07, y - 0.07, y + 0.07, Z_OUTR_LOW, Z_OUTR_RAIL, 'trim')
        # thole pins where the unmanned oars rest
        for i in range(OARS_PER_SIDE):
            y = OAR_Y_AFT + (OAR_Y_FORE - OAR_Y_AFT) * (i + 0.5) / OARS_PER_SIDE
            lathe('thole', [(0.04, 0), (0.04, 0.22), (0.0, 0.25)], 'trim', at=(X, y + 0.14, Z_OUTR_RAIL), segs=6)
        # carved scroll brackets closing the frame at both ends (front view of the drawing)
        for yend in (Y_OUTR_FORE, Y_OUTR_AFT):
            # outer face of what stands there: forecastle side forward, sterncastle side aft
            z_end = Z_GUN_DECK + 0.45
            xw = side * (fc_radius(z_end) if yend > 0 else sc_hw(yend))
            # volute wound around a centre above the rail end, leaving it at the bottom heading inboard
            cz, n = Z_OUTR_RAIL + 0.28, 20
            pts = []
            for i in range(n + 1):
                t = i / n
                a = math.radians(450 - 540 * t)               # 1.5 turns, ends at -90 deg (bottom)
                r = 0.07 + 0.21 * t
                pts.append((X + side * r * math.cos(a), yend, cz + r * math.sin(a)))
            for t in (0.25, 0.5, 0.75, 1.0):                   # S curve up and inboard to the castle side
                x = X + (xw - X) * t
                z = Z_OUTR_RAIL + 0.07 + (z_end - Z_OUTR_RAIL - 0.07) * (3 * t * t - 2 * t ** 3)
                pts.append((x, yend, z))
            sweep('outrigger_scroll', pts, [0.045 + 0.05 * min(i / n, 1) for i in range(len(pts))], 'trim', segs=8)

# ================================================================= forecastle
def horseshoe(r, n=48):
    """Plan outline: straight sides from FC_Y_BACK to FC_CY, semicircle in front (port -> bow -> starboard)."""
    pts = [(-r, FC_Y_BACK)]
    for i in range(n + 1):
        a = math.pi - math.pi * i / n
        pts.append((r * math.cos(a), FC_CY + r * math.sin(a)))
    pts.append((r, FC_Y_BACK))
    return pts

def fc_radius(z):
    t = (z - FC_Z_BASE) / (FC_Z_RAIL - FC_Z_BASE)
    return FC_R_BASE + (FC_R_TOP - FC_R_BASE) * t

def horseshoe_wall(name, z0, z1, wall, role):
    bm = bmesh.new()
    o0, o1 = horseshoe(fc_radius(z0)), horseshoe(fc_radius(z1))
    i0, i1 = horseshoe(fc_radius(z0) - wall), horseshoe(fc_radius(z1) - wall)
    def layer(pts, z): return [bm.verts.new((x, y, z)) for x, y in pts]
    ob, ot, ib, it = layer(o0, z0), layer(o1, z1), layer(i0, z0), layer(i1, z1)
    for i in range(len(o0) - 1):
        bm.faces.new((ob[i], ob[i + 1], ot[i + 1], ot[i]))
        bm.faces.new((ib[i + 1], ib[i], it[i], it[i + 1]))
        bm.faces.new((ot[i], ot[i + 1], it[i + 1], it[i]))
        bm.faces.new((ib[i], ib[i + 1], ob[i + 1], ob[i]))
    for a, b, c, d in ((ob[0], ot[0], it[0], ib[0]), (ib[-1], it[-1], ot[-1], ob[-1])):
        bm.faces.new((a, b, c, d))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, name, role)

def horseshoe_slab(name, r, z0, z1, role):
    bm = bmesh.new()
    pts = horseshoe(r)
    bot = [bm.verts.new((x, y, z0)) for x, y in pts]; top = [bm.verts.new((x, y, z1)) for x, y in pts]
    bm.faces.new(list(reversed(bot))); bm.faces.new(top)
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, name, role)

def fc_point(deg, r, back=0.0):
    """Point on the forecastle outline at bearing deg (0 = ahead, +90 = starboard)."""
    if abs(deg) >= 90:
        return (math.copysign(r, deg), FC_CY - back)
    a = math.radians(90 - deg)
    return (r * math.cos(a), FC_CY + r * math.sin(a))

def stairs(name, x0, x1, y_bottom, z_bottom, y_top, z_top, role='trim', step=0.25):
    """Straight stair (treads + two stringers + hand rail posts); runs from y_bottom to y_top."""
    n = max(int(round((z_top - z_bottom) / step)), 2)
    dy, dz = (y_top - y_bottom) / n, (z_top - z_bottom) / n
    for i in range(n):
        y = y_bottom + dy * (i + 0.5); z = z_bottom + dz * (i + 1)
        box(f'{name}_tread', x0, x1, *sorted((y - abs(dy) * 0.55, y + abs(dy) * 0.55)), z - 0.06, z, 'deck')
    for x in (x0, x1):
        sweep(f'{name}_stringer', [(x, y_bottom, z_bottom + 0.05), (x, y_top, z_top - 0.05)], 0.08, role, square=True)
        sweep(f'{name}_handrail', [(x, y_bottom, z_bottom + 0.95), (x, y_top, z_top + 0.95)], 0.04, role, segs=6)
        for t in (0.0, 0.5, 1.0):
            y = y_bottom + (y_top - y_bottom) * t; z = z_bottom + (z_top - z_bottom) * t
            box(f'{name}_post', x - 0.04, x + 0.04, y - 0.04, y + 0.04, z, z + 0.95, role)

def build_forecastle():
    lower = horseshoe_wall('fc_lower', FC_Z_BASE, FC_Z_PLATFORM, 0.35, 'paint')
    # planking between the last oar bay and the forecastle (hull top is still low there)
    for side in (-1, 1):
        w = half_beam((OAR_Y_FORE + FC_Y_BACK) / 2, True)
        box('row_wall_fore', *sorted((side * w, side * (w - 0.15))), OAR_Y_FORE, FC_Y_BACK + 0.3,
            Z_HULL_TOP - 0.1, FC_Z_BASE, 'paint')
    cuts = []
    for deg in FC_LOWER_PORT_DEGS:
        x, y = fc_point(deg, fc_radius(2.95))
        a = math.radians(90 - deg)
        cuts.append(cutter_cyl(x, y, 2.95, 0.22, 1.2, (math.pi / 2, 0, a - math.pi / 2)))
        ring = [(x + 0.04 * math.cos(a) + (0.32 * math.cos(t)) * -math.sin(a),
                 y + 0.04 * math.sin(a) + (0.32 * math.cos(t)) * math.cos(a), 2.95 + 0.32 * math.sin(t))
                for t in [2 * math.pi * k / 16 for k in range(17)]]
        sweep('fc_port_wreath', ring, 0.05, 'gilt', segs=6, cap=False)
    subtract(lower, cuts)
    horseshoe_slab('fc_floor_low', fc_radius(FC_Z_BASE) - 0.3, Z_GUN_DECK - 0.15, Z_GUN_DECK, 'deck')
    horseshoe_slab('fc_platform', fc_radius(FC_Z_PLATFORM) - 0.05, FC_Z_PLATFORM - 0.15, FC_Z_PLATFORM, 'deck')
    par = horseshoe_wall('fc_parapet', FC_Z_PLATFORM, FC_Z_PARAPET, 0.35, 'paint')
    cuts = []
    for deg in FC_GUN_DEGS:
        x, y = fc_point(deg, fc_radius(FC_EMB_SILL), back=0.6)
        a = math.radians(90 - deg) if abs(deg) < 90 else (0.0 if deg > 0 else math.pi)
        cuts.append(cutter_box(x, y, (FC_EMB_SILL + FC_EMB_TOP) / 2, 1.6, FC_EMB_W, FC_EMB_TOP - FC_EMB_SILL, a))
        # gun position marker (cannon goes here later)
        r_in = fc_radius(FC_Z_PLATFORM) - 1.8
        gx, gy = fc_point(deg, r_in, back=0.6)
        box(f'fc_gun_{deg:+d}', gx - 0.1, gx + 0.1, gy - 0.1, gy + 0.1, FC_Z_PLATFORM, FC_Z_PLATFORM + 0.3, 'dark', 'markers')
    subtract(par, cuts)
    # mouldings: band at the platform level and cap of the parapet, top rail on posts
    horseshoe_wall('fc_band_low', FC_Z_BASE - 0.12, FC_Z_BASE + 0.05, -0.08, 'trim')
    horseshoe_wall('fc_band_mid', FC_Z_PLATFORM - 0.1, FC_Z_PLATFORM + 0.06, -0.06, 'gilt')
    horseshoe_wall('fc_cap', FC_Z_PARAPET, FC_Z_PARAPET + 0.1, 0.45, 'trim')
    pts = horseshoe(fc_radius(FC_Z_RAIL) - 0.2, n=30)
    for x, y in pts[1:-1]:
        lathe('fc_rail_baluster', [(0.06, 0), (0.09, 0.15), (0.05, 0.35), (0.08, 0.55), (0.06, 0.7)], 'trim',
              at=(x, y, FC_Z_PARAPET + 0.1), segs=6)
    for i in range(len(pts) - 1):
        (xa, ya), (xb, yb) = pts[i], pts[i + 1]
        sweep('fc_top_rail', [(xa, ya, FC_Z_RAIL - 0.05), (xb, yb, FC_Z_RAIL - 0.05)], 0.06, 'trim', square=True)
    # rail along the open back edge of the platform, gaps where the stairs arrive
    r = fc_radius(FC_Z_PLATFORM) - 0.35
    yb = FC_Y_BACK + 0.05
    for x0, x1 in ((-r, -FC_STAIR_X - 0.5), (-FC_STAIR_X + 0.5, FC_STAIR_X - 0.5), (FC_STAIR_X + 0.5, r)):
        sweep('fc_back_rail', [(x0, yb, FC_Z_PLATFORM + 0.95), (x1, yb, FC_Z_PLATFORM + 0.95)], 0.05, 'trim', square=True)
        n = max(int(round((x1 - x0) / 0.6)), 1)
        for k in range(n + 1):
            x = x0 + (x1 - x0) * k / n
            box('fc_back_post', x - 0.04, x + 0.04, yb - 0.04, yb + 0.04, FC_Z_PLATFORM, FC_Z_PLATFORM + 0.98, 'trim')
    # stairs from the gun deck up to the platform, one per side behind the forecastle
    for side in (-1, 1):
        x = side * FC_STAIR_X
        stairs(f'fc_stairs_{side}', x - 0.5, x + 0.5, FC_Y_BACK - 3.0, Z_GUN_DECK, FC_Y_BACK, FC_Z_PLATFORM)

# ================================================================= sterncastle
def sc_hw(y):
    return half_beam(y, True) + 0.02

def tapered_block(name, ya, yb, z0, z1, hw_fn, role, n=16, grow=0.0):
    """Block whose half width follows hw_fn(y); z0 may be a function of y (bottom following the hull)."""
    bm = bmesh.new(); rings = []
    for i in range(n + 1):
        y = ya + (yb - ya) * i / n; w = hw_fn(y) + grow
        zb = z0(y) if callable(z0) else z0
        rings.append([bm.verts.new(c) for c in ((-w, y, zb), (w, y, zb), (w, y, z1), (-w, y, z1))])
    for a, b in zip(rings, rings[1:]):
        for i in range(4):
            bm.faces.new((a[i], a[(i + 1) % 4], b[(i + 1) % 4], b[i]))
    bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, name, role)

def side_strip(name, ya, yb, z0, z1, out, thick, role, n=16):
    """Strip on both sides of the sterncastle following its taper (mouldings, window bands)."""
    for side in (-1, 1):
        bm = bmesh.new(); rings = []
        for i in range(n + 1):
            y = ya + (yb - ya) * i / n; w = sc_hw(y)
            xo, xi = side * (w + out), side * (w + out - thick)
            rings.append([bm.verts.new(c) for c in ((xi, y, z0), (xo, y, z0), (xo, y, z1), (xi, y, z1))])
        for a, b in zip(rings, rings[1:]):
            for i in range(4):
                bm.faces.new((a[i], a[(i + 1) % 4], b[(i + 1) % 4], b[i]))
        bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        obj_from_bm(bm, f'{name}_{side}', role)

def build_sterncastle():
    body = tapered_block('sc_body', SC_Y_AFT, SC_Y_FORE, lambda y: z_top(y) - 0.1, SC_Z_FLOOR, sc_hw, 'paint')
    # cap over the hull end behind the cabin (the hull shell is open on top)
    tapered_block('stern_cap', -25.25, SC_Y_AFT + 0.05, FC_Z_BASE - 0.25, FC_Z_BASE, lambda y: half_beam(y, True) + 0.02, 'hull')
    cuts = []
    # cabin door and two windows in the front bulkhead
    cuts.append(cutter_box(0, SC_Y_FORE, Z_GUN_DECK + 1.0, 1.1, 0.6, 2.0))
    for x in (-2.2, 2.2):
        cuts.append(cutter_box(x, SC_Y_FORE, 4.3, 0.6, 0.6, 0.6))
    # side windows (the drawing's band of small arched windows)
    nwin = 6
    for side in (-1, 1):
        for i in range(nwin):
            y = SC_Y_AFT + 1.0 + (SC_Y_FORE - SC_Y_AFT - 2.0) * (i + 0.5) / nwin
            cuts.append(cutter_box(side * sc_hw(y), y, 4.75, 0.6, 0.5, 0.55))
            box('sc_window_back', *sorted((side * (sc_hw(y) - 0.25), side * (sc_hw(y) - 0.3))), y - 0.3, y + 0.3, 4.4, 5.1, 'dark')
            # arch over each window
            arch = [(side * (sc_hw(y) + 0.03), y + 0.3 * math.cos(t), 5.02 + 0.22 * math.sin(t))
                    for t in [math.pi * k / 10 for k in range(11)]]
            sweep('sc_window_arch', arch, 0.04, 'gilt', segs=6, cap=False)
    for x in (-2.2, 2.2):
        box('sc_front_window_back', x - 0.35, x + 0.35, SC_Y_FORE - 0.35, SC_Y_FORE - 0.3, 3.95, 4.65, 'dark')
    box('sc_door_back', -0.6, 0.6, SC_Y_FORE - 0.6, SC_Y_FORE - 0.55, Z_GUN_DECK, Z_GUN_DECK + 2.05, 'dark')
    subtract(body, cuts)
    # mouldings: above the bulwark line, under the windows, under the poop deck
    for z0, z1, role in ((Z_BULWARK_TOP, Z_BULWARK_TOP + 0.12, 'trim'), (4.35, 4.45, 'gilt'), (SC_Z_FLOOR - 0.12, SC_Z_FLOOR, 'trim')):
        side_strip('sc_moulding', SC_Y_AFT, SC_Y_FORE, z0, z1, 0.06, 0.12, role)
    # poop deck and turned balustrade
    tapered_block('poop_deck', SC_Y_AFT - 0.3, SC_Y_FORE + 0.25, SC_Z_FLOOR, SC_Z_FLOOR + 0.12, sc_hw, 'deck', grow=0.12)
    baluster = [(0.05, 0), (0.07, 0.08), (0.045, 0.25), (0.085, 0.5), (0.05, 0.75), (0.07, 0.85), (0.05, 0.9)]
    zb = SC_Z_FLOOR + 0.12
    hb = SC_Z_RAIL - zb - 0.1
    prof = [(r, z * hb / 0.9) for r, z in baluster]
    for side in (-1, 1):
        n = int((SC_Y_FORE - SC_Y_AFT) / 0.32)
        for i in range(n + 1):
            y = SC_Y_AFT + (SC_Y_FORE - SC_Y_AFT) * i / n
            x = side * (sc_hw(y) + 0.02)
            if i % 6 == 0:                              # big posts with gilded finials
                box('sc_post', x - 0.09, x + 0.09, y - 0.09, y + 0.09, zb, SC_Z_RAIL + 0.1, 'trim')
                lathe('sc_finial', [(0.09, 0), (0.06, 0.04), (0.11, 0.12), (0.08, 0.22), (0.0, 0.3)], 'gilt',
                      at=(x, y, SC_Z_RAIL + 0.1), segs=8)
            else:
                lathe('sc_baluster', prof, 'trim', at=(x, y, zb), segs=6)
        rail = [(side * (sc_hw(SC_Y_AFT + (SC_Y_FORE - SC_Y_AFT) * k / 16) + 0.02),
                 SC_Y_AFT + (SC_Y_FORE - SC_Y_AFT) * k / 16, SC_Z_RAIL - 0.05) for k in range(17)]
        sweep('sc_rail', rail, 0.07, 'trim', square=True)
    w = sc_hw(SC_Y_AFT)
    for i in range(int(2 * w / 0.32) + 1):
        x = -w + i * 0.32
        lathe('sc_baluster', prof, 'trim', at=(x, SC_Y_AFT, zb), segs=6)
    sweep('sc_rail_aft', [(-w, SC_Y_AFT, SC_Z_RAIL - 0.05), (w, SC_Y_AFT, SC_Z_RAIL - 0.05)], 0.07, 'trim', square=True)
    # forward rail of the poop with a gap for the stairs
    wf = sc_hw(SC_Y_FORE) + 0.02
    for x0, x1 in ((-wf, -SC_STAIR_X - 0.5), (-SC_STAIR_X + 0.5, SC_STAIR_X - 0.5), (SC_STAIR_X + 0.5, wf)):
        sweep('sc_rail_fore', [(x0, SC_Y_FORE, SC_Z_RAIL - 0.05), (x1, SC_Y_FORE, SC_Z_RAIL - 0.05)], 0.07, 'trim', square=True)
        n = max(int((x1 - x0) / 0.32), 1)
        for k in range(1, n):
            lathe('sc_baluster', prof, 'trim', at=(x0 + (x1 - x0) * k / n, SC_Y_FORE, zb), segs=6)
        for x in (x0, x1):
            box('sc_post', x - 0.09, x + 0.09, SC_Y_FORE - 0.09, SC_Y_FORE + 0.09, zb, SC_Z_RAIL + 0.1, 'trim')
    # awning frame (tendalino) over the after part of the poop
    ya, yb = SC_AWNING_Y
    aw = lambda y: sc_hw(y) + 0.02                     # on the balustrade line
    for y in (ya, (ya + yb) / 2, yb):
        for side in (-1, 1):
            x = side * aw(y)
            sweep('awning_post', [(x, y, SC_Z_RAIL - 0.1), (x, y, SC_Z_AWNING + 0.05)], 0.06, 'trim', segs=6)
            box('awning_post_cap', x - 0.08, x + 0.08, y - 0.08, y + 0.08, SC_Z_AWNING - 0.06, SC_Z_AWNING + 0.06, 'trim')
        arc = [(-aw(y) * math.cos(t), y, SC_Z_AWNING + 0.6 * math.sin(t)) for t in [math.pi * k / 12 for k in range(13)]]
        sweep('awning_hoop', arc, 0.05, 'trim', segs=6, cap=False)
    for side in (-1, 1):
        sweep('awning_rail', [(side * aw(y), y, SC_Z_AWNING) for y in (ya, (ya + yb) / 2, yb)], 0.05, 'trim', segs=6)
    sweep('awning_ridge', [(0, ya, SC_Z_AWNING + 0.6), (0, yb, SC_Z_AWNING + 0.6)], 0.05, 'trim', segs=6)
    # stern lantern on its post
    lathe('lantern_post', [(0.12, 0), (0.12, 3.6), (0.2, 3.7), (0.2, 3.8)], 'trim', at=(0, LANTERN_Y, SC_Z_FLOOR), segs=8)
    zl = SC_Z_FLOOR + 3.8
    lathe('lantern_body', [(0.25, 0), (0.45, 0.25), (0.45, 1.55), (0.3, 1.75), (0.0, 1.8)], 'gilt', at=(0, LANTERN_Y, zl), segs=8)
    lathe('lantern_glass', [(0.47, 0.35), (0.47, 1.45)], 'glass', at=(0, LANTERN_Y, zl), segs=8, cap=False)
    sweep('lantern_cross_v', [(0, LANTERN_Y, zl + 1.8), (0, LANTERN_Y, zl + 2.6)], 0.04, 'gilt', segs=6)
    sweep('lantern_cross_h', [(-0.18, LANTERN_Y, zl + 2.35), (0.18, LANTERN_Y, zl + 2.35)], 0.04, 'gilt', segs=6)
    # stairs from the gun deck up to the poop, running aft along both sides of the cabin front
    run = (SC_Z_FLOOR - Z_GUN_DECK) / math.tan(math.radians(40))
    for side in (-1, 1):
        x = side * SC_STAIR_X
        stairs(f'sc_stairs_{side}', x - 0.5, x + 0.5, SC_Y_FORE + run, Z_GUN_DECK, SC_Y_FORE, SC_Z_FLOOR + 0.12)

# ================================================================= stem, spur, stern post, rudder
def build_ends():
    # stem post from the keel up to the forecastle base
    stem = [(0, y, pchip(BOW_PROFILE, y) + 0.05) for y in (21.5, 23.0, 24.2, 24.9, 25.15, 25.28)] + [(0, 25.35, 2.3)]
    sweep('stem', stem, 0.2, 'trim', square=True)
    # keel batten along the bottom
    sweep('keel', [(0, y, z_bottom(y) - 0.08) for y in [-23.5 + 47 * i / 40 for i in range(41)]], 0.12, 'trim', square=True)
    # stern post rising and curling aft into a volute (the drawing's carved stern piece)
    sp = [(0, y, pchip(STERN_PROFILE, -y) + 0.05) for y in (-21.5, -23.0, -24.2, -24.9, -25.2)]
    sp += [(0, -25.35, 1.6), (0, -25.45, 3.3), (0, -25.6, 5.0), (0, -26.0, 6.2), (0, -26.6, 6.9)]
    sweep('stern_post', sp, 0.2, 'trim', square=True)
    vol = spiral((0, -26.6, 6.45), 0.45, 0.12, math.pi / 2, math.pi / 2 - 1.7 * math.pi, n=24)
    sweep('stern_volute', vol, [0.17 - 0.1 * i / 24 for i in range(25)], 'gilt', segs=8)
    # small quarter volutes on both sides of the stern (drawing: the twin scrolls)
    for side in (-1, 1):
        x = side * (sc_hw(SC_Y_AFT) - 0.2)
        q = spiral((x, SC_Y_AFT - 0.35, SC_Z_RAIL + 0.15), 0.3, 0.08, -math.pi / 2, -math.pi / 2 + 1.6 * math.pi, n=18)
        sweep('quarter_volute', [(x, SC_Y_AFT - 0.1, SC_Z_FLOOR)] + q, 0.06, 'gilt', segs=6)

def build_ram_adaptor():
    """Sheath over the lower bow that carries the vanilla rams (slot 'platform', like adaptor_meditheavy).
    A shell 6 cm proud of the hull from ADAPTOR_Y0 to the stem, plus a chock in front of the stem where
    the ram's rear end sits. Separate object: it is only visible while a ram is fitted."""
    bm = bmesh.new()
    z0, z1 = ADAPTOR_Z
    ny, nz = 24, 14
    rings = []
    for i in range(ny + 1):
        y = ADAPTOR_Y0 + (Y_STEM_WL + 0.2 - ADAPTOR_Y0) * i / ny
        zlo = max(z0, z_bottom(y) + 0.02)
        ring = []
        for j in range(nz + 1):
            z = zlo + (z1 - zlo) * j / nz
            w = hull_x_at(y, z) + 0.06
            ring.append((w, y, z))
        rings.append(ring)
    def strip(side):
        vs = [[bm.verts.new((side * x, y, z)) for x, y, z in ring] for ring in rings]
        for a, b in zip(vs, vs[1:]):
            for j in range(nz):
                f = (a[j], b[j], b[j + 1], a[j + 1]) if side > 0 else (a[j], a[j + 1], b[j + 1], b[j])
                bm.faces.new(f)
    strip(1); strip(-1)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.02)
    o = obj_from_bm(bm, 'galleass_ram_adaptor', 'trim', 'final', smooth=True)
    # chock: tapered block on the stem's fore face, waterline level, where the ram butts on
    chock = sweep('ram_chock', [(0, Y_STEM_WL - 0.4, 0.4), (0, Y_STEM_WL + 0.7, 0.4)], [0.75, 0.6], 'trim', square=True)
    band = sweep('ram_chock_band', [(0, Y_STEM_WL + 0.25, 0.4), (0, Y_STEM_WL + 0.45, 0.4)], 0.67, 'iron', square=True)
    for part in (chock, band):                       # move them out of the merged hull into the adaptor group
        PARTS[:] = [(p, r) for p, r in PARTS if p is not part]
        for c in part.users_collection: c.objects.unlink(part)
        coll('final').objects.link(part); part.name = 'galleass_ram_adaptor_' + part.name
    return o

def build_rudder():
    """Sternpost rudder, separate object with its origin on the hinge (rotates in game)."""
    bm = bmesh.new()
    top, bot = Vector((0, -25.45, 2.6)), Vector((0, -25.25, -2.2))
    prof = [(0.0, 0.0), (0.9, 0.2), (1.25, 1.2), (1.25, 3.4), (0.4, 4.6), (0.0, 4.8)]   # (aft offset, height)
    axis = (top - bot).normalized()
    aft = Vector((0, -1, 0))
    vs = []
    for d, h in prof:
        p = bot + axis * h + aft * d
        vs.append((bm.verts.new(p + Vector((0.09, 0, 0))), bm.verts.new(p - Vector((0.09, 0, 0)))))
    for (a0, a1), (b0, b1) in zip(vs, vs[1:]):
        bm.faces.new((a0, b0, b1, a1))
    bm.faces.new([v[0] for v in vs]); bm.faces.new([v[1] for v in reversed(vs)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = obj_from_bm(bm, 'galleass_rudder', 'trim', 'final')
    o.data.transform(Matrix.Translation(-bot)); o.location = bot
    return o

# ================================================================= markers (not exported)
def build_markers():
    for name, y in MASTS.items():
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.35, radius2=0.18, depth=20)
        z0 = Z_GUN_DECK if name != 'fore' else FC_Z_PLATFORM
        for v in bm.verts: v.co.z += 10 + z0; v.co.y += y
        obj_from_bm(bm, f'mast_{name}', 'dark', 'markers')

# ================================================================= build
build_hull()
wale('wale_low', lambda y: 0.35, -21.0, 21.0, height=0.16)
wale('wale_top', lambda y: z_top(y) - 0.05, -19.5, 19.5, height=0.2)
build_rowing_level(); build_gun_deck(); build_outriggers()
build_forecastle(); build_sterncastle(); build_ends(); build_markers()
rudder = build_rudder()
adaptor = build_ram_adaptor()
coll('cutters').hide_render = True; coll('cutters').hide_viewport = True

# apply booleans and merge parts into one object per material role
dg = bpy.context.evaluated_depsgraph_get()
by_role = {}
for o, role in PARTS:
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    me.transform(o.matrix_world)
    by_role.setdefault(role, []).append(me)
for role, meshes in by_role.items():
    bm = bmesh.new()
    for me in meshes:
        bm.from_mesh(me); bpy.data.meshes.remove(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    obj_from_bm(bm, f'galleass_{role}', role, 'final')
coll('parts').hide_render = True; coll('parts').hide_viewport = True
tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in coll('final').objects)
print('triangles (final):', tris)

# ================================================================= reference planes + renders
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

def px(x, y):
    return ((x - 469) / PX_M * K_LEN, (742 - y) / PX_M * K_LEN)

side_ref = ref_plane('ref_side', (20, 150, 1080, 800), lambda x, y: px(x, y), 'YZ', -14)
front_ref = ref_plane('ref_front', (1140, 600, 1420, 800),
                      lambda x, y: ((x - 1281) / PX_M * K_WID, (744.5 - y) / PX_M * K_LEN), 'XZ', -40)

sc.render.engine = 'BLENDER_WORKBENCH'
shd = sc.display.shading
shd.light = 'STUDIO'; shd.color_type = 'MATERIAL'; shd.show_cavity = True; shd.cavity_type = 'WORLD'
shd.show_shadows = True
sc.world = bpy.data.worlds.new('w'); sc.world.color = (0.9, 0.9, 0.92)
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam

def shot(fname, loc, rot, ortho=None, xray=False, refs=(), res=(2000, 1000), lens=35):
    for r in (side_ref, front_ref):
        r.hide_render = r not in refs
    cam.location = loc; cam.rotation_euler = [math.radians(a) for a in rot]
    if ortho:
        cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
    else:
        cam.data.type = 'PERSP'; cam.data.lens = lens
    shd.show_xray = xray; shd.xray_alpha = 0.6
    shd.color_type = 'TEXTURE' if refs else 'MATERIAL'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = os.path.join(RENDER_DIR, fname)
    bpy.ops.render.render(write_still=True)

# preview only: vanilla rams in the bow slot with the planned transform (not exported)
PREVIEW_RAMS = {}
for rid in ('ram_01', 'ram_05', 'ram_06'):
    bpy.ops.wm.obj_import(filepath=os.path.join(HERE, f'ref/meditheavy/{rid}.obj'), forward_axis='Y', up_axis='Z')
    objs = []
    for o in list(bpy.context.selected_objects):
        for c in o.users_collection: c.objects.unlink(o)
        if o.name.split('.')[-1] not in ('0', '1', '2'):
            bpy.data.objects.remove(o); continue
        coll('preview').objects.link(o); objs.append(o)
        o.location = RAM_POS; o.scale = (RAM_SCALE,) * 3
        o.data.materials.clear(); o.data.materials.append(MATS['iron'])
    PREVIEW_RAMS[rid] = objs

def show_ram(rid):
    for k, objs in PREVIEW_RAMS.items():
        for o in objs: o.hide_render = (k != rid)
show_ram('ram_05')

def look(fname, loc, target, lens=35, res=(1400, 1000)):
    d = Vector(target) - Vector(loc)
    cam.location = loc; cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    cam.data.type = 'PERSP'; cam.data.lens = lens
    shd.show_xray = False; shd.color_type = 'MATERIAL'
    for r in (side_ref, front_ref): r.hide_render = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = os.path.join(RENDER_DIR, fname)
    bpy.ops.render.render(write_still=True)

os.makedirs(RENDER_DIR, exist_ok=True)
coll('markers').hide_render = True
shot('mdl_side_overlay.png', (40, 3, 8), (90, 0, 90), ortho=72, xray=True, refs=(side_ref,))
shot('mdl_side.png', (40, 3, 8), (90, 0, 90), ortho=72)
shot('mdl_top.png', (0, 3, 80), (0, 0, 90), ortho=72)
shot('mdl_front_overlay.png', (0, 60, 5), (90, 0, 180), ortho=20, xray=True, refs=(front_ref,), res=(1200, 1000))
shot('mdl_persp.png', (30, 48, 18), (70, 0, 148))
shot('mdl_persp_aft.png', (-26, -44, 14), (75, 0, -32))
shot('mdl_bow_close.png', (13, 38, 8.5), (78, 0, 150), lens=30)
shot('mdl_stern_close.png', (-12, -34, 9.5), (78, 0, -25), lens=30)
shot('mdl_deck.png', (0, -11, 8.5), (72, 0, 0), lens=24)
# close-ups for checking joins
for rid in ('ram_01', 'ram_05', 'ram_06', None):
    show_ram(rid)
    tag = rid or 'none'
    look(f'chk_bow_{tag}.png', (14, 27, 1.2), (0, 26.5, 0.8), lens=30)
look('chk_bow_ram_front.png', (9, 35, 3), (0, 26, 0.5), lens=28)
show_ram('ram_05')
look('chk_poop_corner.png', (-6.5, -27.5, 8.5), (-3.0, -23.5, 6.0), lens=30)
look('chk_awning.png', (2.5, -16.5, 10.5), (0, -21.0, 8.4), lens=30)
look('chk_sc_stairs.png', (5.5, -9.5, 7.5), (3.2, -14.3, 5.8), lens=30)
look('chk_fc_stairs.png', (5.0, 13.0, 5.5), (2.4, 18.4, 4.0), lens=30)
look('chk_scroll_fore.png', (10.5, 23.5, 3.2), (5.5, 20.6, 2.0), lens=30)
look('chk_scroll_aft.png', (10.5, -20.5, 3.2), (5.5, -17.6, 2.0), lens=30)
look('chk_stern_under.png', (-6, -28, 0.5), (-2.5, -22, 2.5), lens=28)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print('model done')
