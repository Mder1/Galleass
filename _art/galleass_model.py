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
OAR_Y_AFT, OAR_Y_FORE = -14.3, 17.5       # first port just forward of the sterncastle front (-14.5)
OARPORT_W, OARPORT_Z0, OARPORT_Z1 = 0.3, 1.12, 1.42      # in the wings' outer face (port above the water: oars slope down)
# rowing-level wings (drawing's front section): the hull flares out above the waterline into a broad sponson
# upper hull (drawing's front + side views): above the waterline the hull flares out (curved cove) into a wide box
# whose outer wall carries the oar ports (low) and the gunports (high); the forecastle tower and the cabin are
# narrower and stand at its ends
WING_HW = 6.2 * K_WID                     # outer wall half width
WING_Y0, WING_Y1 = -17.6, 20.6            # extent along the ship (side view's band)
WING_Z0, WING_Z_FACE = -0.5, 0.95         # flare leaves the hull (just below the waterline) / outer wall foot

# broadside gunports in the gun-deck bulwark (cannons)
GUNPORTS_PER_SIDE = 5
GP_SILL, GP_TOP, GP_W = 2.85, 3.45, 0.6
WREATH_RY, WREATH_RZ = 0.56, 0.5           # gilded ring round each gunport (clears the sill ends)

# forecastle: tapered horseshoe, five gun embrasures on the upper tier (0, +-45, +-90 deg)
FC_CY = 21.6                             # centre of the round front
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
# cabin windows: opening z, arch rise; arch top (+ tube) stays below the deck-line moulding at SC_Z_FLOOR - 0.12
SCW_Z0, SCW_Z1, SCW_ARCH = 4.4, 4.88, 0.18
# cabin door beside the mizzen mast (the mast at y -13.7 stands on the centreline 0.8 m in front of the bulkhead)
SC_DOOR_X, SC_DOOR_W = 1.35, 1.0
SC_FWIN_X = 2.35                         # front windows, outboard of the door
SC_WALL = 0.2                             # cabin wall thickness (cabin interior is walk-in)
SC_AWIN_X = 1.25                          # small windows either side of the stern door
SC_EWIN_Z = 4.6                           # front/stern windows: at side-window height, above the window band
BALC_RY = 1.3                             # stern balcony depth (apex reaches the stern post's face); width = cabin's
BALC_INSET = 0.08                         # balustrade set in from the floor edge
BALC_Z_BOT = FC_Z_BASE - 0.3              # plate reaches below the hull top: it closes the hull end behind the cabin
POOP_INSET = 0.06                         # poop balustrade line inside the deck edge (posts never overhang)
SC_STAIR_X = 3.25                        # centre line of the two stairs up to the poop
LANTERN_Y = -24.15                       # on the poop deck, just inside the aft rail

# masts (vanilla lateen rigs go here later): mizzen, main, fore
MASTS = {'mizzen': -13.7, 'main': 5.5, 'fore': 22.5}
# bow: no ram slot (user 2026-10-06). A carved beak under the forecastle front carries the vanilla figureheads
# (figurehead slot). Figurehead pivot/tilt/scale as on the meditheavy (rotation x -0.85 rad, scale 0.85/0.92/0.92).
FIG_POS = (0.0, 26.7, 1.75)
FIG_ROT_X = -0.85
FIG_SCALE = (0.95, 1.05, 1.05)                    # vanilla 0.85/0.92/0.92 x ~1.12 (bigger ship)

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
    bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=r, radius2=r, depth=depth)
    o = obj_from_bm(bm, 'cut', 'dark', 'cutters')
    o.location = (cx, cy, cz); o.rotation_euler = axis_rot
    return o

def _basis(c, n):
    """Matrix mapping local (X = along the wall, Y = outward normal n, Z = up) to world at point c."""
    n = Vector(n).normalized(); z = Vector((0, 0, 1)); u = n.cross(z).normalized()
    m = Matrix.Identity(4)
    for i in range(3):
        m[i][0], m[i][1], m[i][2], m[i][3] = u[i], n[i], z[i], c[i]
    return m

def lining(name, c, n, w, h, d, lip=0.02, t=0.04, sill_out=0.0, role='trim', curve_r=None):
    """Timber lining of a rectangular opening: jambs, head and sill boards through the wall (depth d), with a
    small lip proud of the outer face; sill_out makes the sill project as a ledge. c = opening centre on the
    outer face, n = outward normal, w/h = cut width/height. Boards sit inside the cut (no overlap with wall)."""
    M = _basis(c, n)
    def lbox(x0, x1, y0, y1, z0, z1):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1)
        for v in bm.verts:
            v.co = M @ Vector((x0 if v.co.x < 0 else x1, y0 if v.co.y < 0 else y1, z0 if v.co.z < 0 else z1))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        obj_from_bm(bm, name, role)
    # the same 2 cm lip shows outside AND inside; on a curved (round) wall the boards are lengthened by the
    # wall's sag over half the opening width, so the lip is the same at the edges as in the middle
    sag_o = sag_i = 0.0
    if curve_r:
        u = w / 2
        sag_o = curve_r - math.sqrt(curve_r ** 2 - u * u)
        ri = curve_r - d
        sag_i = (curve_r - math.sqrt(ri * ri - u * u)) - d
    y0, y1 = -d - sag_i - lip, lip
    lbox(-w / 2, -w / 2 + t, y0, y1, -h / 2 + t, h / 2 - t)             # jambs
    lbox(w / 2 - t, w / 2, y0, y1, -h / 2 + t, h / 2 - t)
    lbox(-w / 2, w / 2, y0, y1, h / 2 - t, h / 2)                       # head
    lbox(-w / 2, w / 2, y0, y1, -h / 2, -h / 2 + t)                     # sill board, frame width
    if sill_out:                                                         # projecting ledge: outside only
        lbox(-w / 2 - 0.05, w / 2 + 0.05, -sag_o, lip + sill_out, -h / 2 - 0.02, -h / 2 + t)

def round_lining(name, c, n, r, d, lip=0.02, t=0.03, role='trim'):
    """Round timber sleeve lining a round port through a wall of depth d."""
    o = lathe(name, [(r, -d - 0.01), (r, lip), (r - t, lip), (r - t, -d - 0.01), (r, -d - 0.01)], role,
              segs=32, cap=False)
    nn = Vector(n).normalized(); z = Vector((0, 0, 1)); u = nn.cross(z).normalized()
    m = Matrix.Identity(4)                                # lathe axis (local Z) -> n
    for i in range(3):
        m[i][0], m[i][1], m[i][2], m[i][3] = u[i], z[i], nn[i], c[i]
    o.data.transform(m)
    return o

def wall_normal(hw_fn, y, side):
    """Outward horizontal normal of a side wall x = side * hw_fn(y) (accounts for the taper)."""
    d = (hw_fn(y + 0.01) - hw_fn(y - 0.01)) / 0.02
    return Vector((side, -d, 0)).normalized()

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

def sweep(name, pts, radii, role, segs=8, square=False, cap=True, closed=False):
    """Tube along a polyline (parallel-transported frames); square=True gives a beam.
    closed=True: pts is a loop (last point may repeat the first); the tube is joined seamlessly."""
    pts = [Vector(p) for p in pts]
    if closed:
        if (pts[0] - pts[-1]).length < 1e-6:
            pts = pts[:-1]
        cap = False
    if not isinstance(radii, (list, tuple)):
        radii = [radii] * len(pts)
    tangents = []
    for i in range(len(pts)):
        if closed:
            a = pts[i - 1]; b = pts[(i + 1) % len(pts)]
        else:
            a = pts[max(i - 1, 0)]; b = pts[min(i + 1, len(pts) - 1)]
        tangents.append((b - a).normalized())
    ref = Vector((1, 0, 0)) if abs(tangents[0].x) < 0.9 else Vector((0, 0, 1))
    n = (ref - tangents[0] * ref.dot(tangents[0])).normalized()
    bm = bmesh.new(); rings = []
    k = 4 if square else segs
    if closed:
        # flat loops (wreaths): orient every section by the loop's plane normal (Newell) -> no twist, no seam
        pn = Vector((0, 0, 0))
        for i in range(len(pts)):
            a_, b_ = pts[i], pts[(i + 1) % len(pts)]
            pn += Vector(((a_.y - b_.y) * (a_.z + b_.z), (a_.z - b_.z) * (a_.x + b_.x), (a_.x - b_.x) * (a_.y + b_.y)))
        pn.normalize()
    for i, (p, t) in enumerate(zip(pts, tangents)):
        n = (pn - t * pn.dot(t)).normalized() if closed else (n - t * n.dot(t)).normalized()
        bnorm = t.cross(n)
        ring = []
        for j in range(k):
            a = 2 * math.pi * j / k + (math.pi / 4 if square else 0)
            ring.append(bm.verts.new(p + (n * math.cos(a) + bnorm * math.sin(a)) * radii[i]))
        rings.append(ring)
    pairs = list(zip(rings, rings[1:]))
    if closed:
        pairs.append((rings[-1], rings[0]))
    for a, b in pairs:
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
# lower stern: a straight raked sternpost from the keel heel to the post (the rudder hangs on it)
STERN_HEEL, STERN_POST_TOP = (23.6, -2.4), (25.35, 1.6)
def _sp(t):
    return (STERN_HEEL[0] + (STERN_POST_TOP[0] - STERN_HEEL[0]) * t, STERN_HEEL[1] + (STERN_POST_TOP[1] - STERN_HEEL[1]) * t)
STERN_PROFILE = [(14.0, Z_KEEL), (21.1, -2.45), STERN_HEEL, _sp(0.26), _sp(0.51), _sp(0.76), STERN_POST_TOP, (25.4, 3.3)]
STERN_RAKE = math.atan2(STERN_POST_TOP[0] - STERN_HEEL[0], STERN_POST_TOP[1] - STERN_HEEL[1])

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
def side_hw(y):
    """Outer face of the ship's side above the hull shell (rowing level + bulwark): follows the planform."""
    return half_beam(y, True)

SIDE_Y0, SIDE_Y1 = Y_GUNDECK_AFT - 0.1, FC_Y_BACK      # wall: tucked 0.1 into the cabin, flush with the forecastle back
BAND_Y0, BAND_Y1 = Y_GUNDECK_AFT, FC_Y_BACK            # mouldings end exactly at the castle faces
# horizontal bands (z0, z1, out from the side face, thickness inboard, role), shared by the side and the castles
BANDS = {
    'rub_rail': (Z_GUN_DECK - 0.32, Z_GUN_DECK - 0.1, 0.1, 0.14, 'trim'),
    'moulding': (GP_TOP + 0.08, GP_TOP + 0.14, 0.05, 0.08, 'gilt'),
    'cap_rail': (Z_BULWARK_TOP, Z_BULWARK_TOP + 0.1, 0.06, 0.34, 'trim'),
}
STRAKES = {
    'strake_low': (OARPORT_Z0 - 0.16, OARPORT_Z0 - 0.05, 0.06, 0.1, 'trim'),
    'strake_high': (OARPORT_Z1 + 0.05, OARPORT_Z1 + 0.16, 0.06, 0.1, 'trim'),
}
SIDE_T = 0.2                                             # planking thickness

def side_loft(name, y0, y1, z0, z1, out, thick, role, n=120, hw_fn=side_hw):
    """Continuous fore-and-aft strip on both sides following hw_fn(y): wall, strakes, rails.
    z0/z1 may be functions of y; `out` is the outer face offset from hw_fn, `thick` goes inboard."""
    objs = []
    for side in (-1, 1):
        bm = bmesh.new(); rings = []
        for i in range(n + 1):
            y = y0 + (y1 - y0) * i / n
            w = hw_fn(y)
            za = z0(y) if callable(z0) else z0
            zb = z1(y) if callable(z1) else z1
            xo, xi = side * (w + out), side * (w + out - thick)
            rings.append([bm.verts.new(c) for c in ((xi, y, za), (xo, y, za), (xo, y, zb), (xi, y, zb))])
        for a, b in zip(rings, rings[1:]):
            for k in range(4):
                bm.faces.new((a[k], a[(k + 1) % 4], b[(k + 1) % 4], b[k]))
        bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        objs.append(obj_from_bm(bm, f'{name}_{"stbd" if side > 0 else "port"}', role))
    return objs

def oar_y(i):
    return OAR_Y_AFT + (OAR_Y_FORE - OAR_Y_AFT) * (i + 0.5) / OARS_PER_SIDE

def gunport_y(i):
    span = (Y_GUNDECK_FORE - 3.0) - (Y_GUNDECK_AFT + 3.0)
    return Y_GUNDECK_AFT + 3.0 + span * (i + 0.5) / GUNPORTS_PER_SIDE

def box_inner_x(y):
    """Inner edge of the box's end walls: just inside the castle wall there (forecastle side / cabin side)."""
    return (fc_radius(Z_GUN_DECK) if y > 0 else sc_hw(y)) - 0.1

def cove_start_x(y):
    """Where the flare leaves the hull: the hull's widest point between the flare's start and the wall foot."""
    return max(hull_x_at(y, WING_Z0 + (WING_Z_FACE - WING_Z0) * k / 8) for k in range(9)) + 0.01

def cove_xz(y, t):
    """Hull flare (front section): a cubic curve leaving the hull side vertically at WING_Z0 and sweeping out,
    arriving almost horizontally at the outer wall's foot. t in [0, 1]."""
    hx, W, z0, zf = cove_start_x(y), WING_HW, WING_Z0, WING_Z_FACE
    P = [(hx, z0), (hx, z0 + 0.6 * (zf - z0)), (hx + 0.45 * (W - hx), zf - 0.06), (W, zf)]
    u = 1 - t
    b = (u ** 3, 3 * u * u * t, 3 * u * t * t, t ** 3)
    return sum(b[i] * P[i][0] for i in range(4)), sum(b[i] * P[i][1] for i in range(4))

def cove_t_at_x(y, x):
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if cove_xz(y, mid)[0] < x: lo = mid
        else: hi = mid
    return lo

def build_sides():
    """Wide upper hull: cove from the hull out to the outer wall at WING_HW, outer wall up to the bulwark cap with
    oar ports (low) and gunports (high), end walls against the forecastle/cabin, a full-width gun deck."""
    W, Y0, Y1 = WING_HW, WING_Y0, WING_Y1
    for side in (-1, 1):
        # cove (solid): leaves the hull upward and turns outward to the wall's foot
        bm = bmesh.new(); rings = []
        for i in range(91):                                        # ends tucked inside the end walls
            y = (Y0 + 0.05) + (Y1 - Y0 - 0.1) * i / 90
            hx = cove_start_x(y)
            pts = [(hx - 0.25, WING_Z0 - 0.05)] + [cove_xz(y, k / 20) for k in range(21)]
            pts += [(W - SIDE_T, WING_Z_FACE), (hx - 0.25, WING_Z_FACE)]
            rings.append([bm.verts.new((side * x, y, z)) for x, z in pts])
        k = len(rings[0])
        for a, b in zip(rings, rings[1:]):
            for j in range(k):
                bm.faces.new((a[j], a[(j + 1) % k], b[(j + 1) % k], b[j]))
        bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        obj_from_bm(bm, 'cove', 'hull', smooth=True)              # the hull itself flaring out (planking)
        # outer wall with oar ports and gunports
        x0, x1 = sorted((side * W, side * (W - SIDE_T)))
        wall = box(f'outer_wall', x0, x1, Y0 + 0.05, Y1 - 0.05, WING_Z_FACE - 0.01, Z_BULWARK_TOP, 'paint')
        cuts = []
        for i in range(OARS_PER_SIDE):
            y = oar_y(i); zc = (OARPORT_Z0 + OARPORT_Z1) / 2
            cuts.append(cutter_box(side * W, y, zc, 0.6, OARPORT_W, OARPORT_Z1 - OARPORT_Z0))
            lining('oarport_lining', (side * W, y, zc), (side, 0, 0), OARPORT_W, OARPORT_Z1 - OARPORT_Z0, SIDE_T, t=0.03)
            xb = side * (W - 0.5)
            box('oarport_back', *sorted((xb, xb - side * 0.05)), y - OARPORT_W, y + OARPORT_W,
                OARPORT_Z0 - 0.1, OARPORT_Z1 + 0.1, 'dark')
        for i in range(GUNPORTS_PER_SIDE):
            y = gunport_y(i); zc = (GP_SILL + GP_TOP) / 2
            cuts.append(cutter_box(side * W, y, zc, 0.8, GP_W, GP_TOP - GP_SILL))
            ring = [(side * (W + 0.06), y + WREATH_RY * math.cos(2 * math.pi * k / 48),
                     zc + WREATH_RZ * math.sin(2 * math.pi * k / 48)) for k in range(49)]
            sweep('gunport_wreath', ring, 0.05, 'gilt', segs=8, closed=True)
            lining('gunport_lining', (side * W, y, zc), (side, 0, 0), GP_W, GP_TOP - GP_SILL, SIDE_T, sill_out=0.05)
        subtract(wall, cuts)
        # end walls against the castles, lower edge on the cove
        for yend, d in ((Y1, -1), (Y0, 1)):
            xi = box_inner_x(yend)
            hx = cove_start_x(yend)
            t_in = cove_t_at_x(yend, xi) if xi > hx else 0.0
            prof = [cove_xz(yend, t_in + (1 - t_in) * k / 16) for k in range(17)]
            if xi < prof[0][0]:
                prof = [(xi, prof[0][1])] + prof
            # lower part (on the flare, up to the wall foot) is hull planking, the rest painted like the wall
            for poly, role in ((prof + [(xi, WING_Z_FACE)], 'hull'),
                               ([(xi, WING_Z_FACE), (W, WING_Z_FACE), (W, Z_BULWARK_TOP), (xi, Z_BULWARK_TOP)], 'paint')):
                bm = bmesh.new()
                front = [bm.verts.new((side * x, yend, z)) for x, z in poly]
                back = [bm.verts.new((side * x, yend + d * SIDE_T, z)) for x, z in poly]
                bm.faces.new(front); bm.faces.new(list(reversed(back)))
                for j in range(len(poly)):
                    jj = (j + 1) % len(poly)
                    bm.faces.new((front[j], back[j], back[jj], front[jj]))
                bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
                obj_from_bm(bm, 'end_wall', role)
            # gilded scroll on the end wall's outer upper corner (drawing's front section)
            c = (side * (W - 0.35), yend - d * 0.03, Z_BULWARK_TOP - 0.55)
            vol = [(c[0] + side * r * math.cos(a), c[1], c[2] + r * math.sin(a))
                   for r, a in [(0.05 + 0.22 * k / 24, math.pi * 2.2 * (1 - k / 24) - 0.4) for k in range(25)]]
            sweep('box_end_scroll', vol, [0.02 + 0.015 * k / 24 for k in range(25)], 'gilt', segs=8)
    # bands along the outer wall, wrapped round the end walls to the castles
    for name, (z0, z1, out, thick, role) in {**BANDS, **STRAKES}.items():
        segs = [(Y0 - out, Y1 + out)]
        if name == 'moulding':                                     # breaks round the gunport wreaths
            gap = WREATH_RY + 0.12
            edges = [Y0 - out] + [e for i in range(GUNPORTS_PER_SIDE) for e in (gunport_y(i) - gap, gunport_y(i) + gap)] + [Y1 + out]
            segs = list(zip(edges[::2], edges[1::2]))
        for side in (-1, 1):
            for a, b in segs:
                box(name, *sorted((side * (W + out), side * (W + out - thick))), a, b, z0, z1, role)
            for yend, d in ((Y1, 1), (Y0, -1)):                    # across the end walls (outer face at yend)
                xi = box_inner_x(yend) + 0.1
                box(name + '_end', *sorted((side * xi, side * (W + out - thick))),
                    *sorted((yend + d * out, yend + d * (out - min(thick, SIDE_T)))), z0, z1, role)
    # full-width gun deck; side decks beside the forecastle and the cabin
    WD = W - SIDE_T + 0.01
    box('gun_deck', -WD, WD, Y_GUNDECK_AFT, FC_Y_BACK, Z_GUN_DECK - 0.15, Z_GUN_DECK, 'deck')
    for side in (-1, 1):
        box('side_deck_fore', *sorted((side * (fc_radius(Z_GUN_DECK) - 0.02), side * WD)), FC_Y_BACK, Y1 - SIDE_T + 0.01,
            Z_GUN_DECK - 0.15, Z_GUN_DECK, 'deck')
        bm = bmesh.new(); rings = []
        for i in range(13):
            y = Y0 + SIDE_T - 0.01 + (Y_GUNDECK_AFT - Y0 - SIDE_T + 0.01) * i / 12
            xi, xo = side * (sc_hw(y) - 0.02), side * WD
            rings.append([bm.verts.new(c) for c in ((xi, y, Z_GUN_DECK - 0.15), (xo, y, Z_GUN_DECK - 0.15),
                                                     (xo, y, Z_GUN_DECK), (xi, y, Z_GUN_DECK))])
        for a, b in zip(rings, rings[1:]):
            for j in range(4):
                bm.faces.new((a[j], a[(j + 1) % 4], b[(j + 1) % 4], b[j]))
        bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        obj_from_bm(bm, 'side_deck_aft', 'deck')
        # stanchions on the inside of the bulwark
        for k in range(int((Y1 - Y0) / 1.6)):
            y = Y0 + 0.5 + k * 1.6
            if any(abs(y - gunport_y(i)) < 0.6 for i in range(GUNPORTS_PER_SIDE)) or y > Y1 - 0.4:
                continue
            w = W - SIDE_T
            box('stanchion', *sorted((side * w, side * (w - 0.12))), y - 0.07, y + 0.07, Z_GUN_DECK, Z_BULWARK_TOP, 'trim')

def build_deck_fittings():
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

def outer_x(y, z):
    """Half width of the ship's outer surface at (y, z): side wall / castle / forecastle skirt where they reach
    down to z (they stand on the hull top), otherwise the hull shell."""
    if z >= z_top(y) - 0.1:
        return half_beam(y, True) + (0.02 if y < SC_Y_FORE else 0.0)
    return hull_x_at(y, z)

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
    """Vertical-sided forecastle exactly as wide as the ship's side where they meet (flush corner)."""
    return side_hw(FC_Y_BACK)

def horseshoe_wall(name, z0, z1, wall, role, grow=0.0):
    bm = bmesh.new()
    o0, o1 = horseshoe(fc_radius(z0) + grow), horseshoe(fc_radius(z1) + grow)
    i0, i1 = horseshoe(fc_radius(z0) + grow - wall), horseshoe(fc_radius(z1) + grow - wall)
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
        sweep(f'{name}_handrail', [(x, y_bottom, z_bottom + 0.95), (x, y_top, z_top + 0.95)], 0.04, role, segs=12)
        for t in (0.0, 0.5, 1.0):
            y = y_bottom + (y_top - y_bottom) * t; z = z_bottom + (z_top - z_bottom) * t
            box(f'{name}_post', x - 0.04, x + 0.04, y - 0.04, y + 0.04, z, z + 0.95, role)

def build_forecastle():
    lower = horseshoe_wall('fc_lower', FC_Z_BASE, FC_Z_PLATFORM, 0.35, 'paint')
    cuts = []
    for deg in FC_LOWER_PORT_DEGS:
        x, y = fc_point(deg, fc_radius(2.95))
        a = math.radians(90 - deg)
        cuts.append(cutter_cyl(x, y, 2.95, 0.22, 1.2, (math.pi / 2, 0, a - math.pi / 2)))
        round_lining('fc_port_lining', (x, y, 2.95), (math.cos(a), math.sin(a), 0), 0.22, 0.35)
        R = fc_radius(2.95) + 0.07
        ring = []
        for t in [2 * math.pi * k / 48 for k in range(49)]:
            b = a + 0.32 * math.cos(t) / R               # walk along the curved wall
            ring.append((R * math.cos(b), FC_CY + R * math.sin(b), 2.95 + 0.32 * math.sin(t)))
        sweep('fc_port_wreath', ring, 0.05, 'gilt', segs=8, closed=True)
    subtract(lower, cuts)
    horseshoe_slab('fc_floor_low', fc_radius(FC_Z_BASE) - 0.35, FC_Z_BASE + 0.01, Z_GUN_DECK, 'deck')   # inside the wall, 1 cm up: no shared plane
    horseshoe_slab('fc_platform', fc_radius(FC_Z_PLATFORM) - 0.05, FC_Z_PLATFORM - 0.15, FC_Z_PLATFORM, 'deck')
    par = horseshoe_wall('fc_parapet', FC_Z_PLATFORM, FC_Z_PARAPET, 0.35, 'paint')
    cuts = []
    for deg in FC_GUN_DEGS:
        x, y = fc_point(deg, fc_radius(FC_EMB_SILL), back=0.6)
        a = math.radians(90 - deg) if abs(deg) < 90 else (0.0 if deg > 0 else math.pi)
        cuts.append(cutter_box(x, y, (FC_EMB_SILL + FC_EMB_TOP) / 2, 1.6, FC_EMB_W, FC_EMB_TOP - FC_EMB_SILL, a))
        lining('fc_embrasure_lining', (x, y, (FC_EMB_SILL + FC_EMB_TOP) / 2), (math.cos(a), math.sin(a), 0),
               FC_EMB_W, FC_EMB_TOP - FC_EMB_SILL, 0.35, sill_out=0.05,
               curve_r=None if abs(deg) >= 90 else fc_radius(FC_EMB_SILL))
        # gun position marker (cannon goes here later)
        r_in = fc_radius(FC_Z_PLATFORM) - 1.8
        gx, gy = fc_point(deg, r_in, back=0.6)
        box(f'fc_gun_{deg:+d}', gx - 0.1, gx + 0.1, gy - 0.1, gy + 0.1, FC_Z_PLATFORM, FC_Z_PLATFORM + 0.3, 'dark', 'markers')
    subtract(par, cuts)
    # mouldings: band at the platform level and cap of the parapet (no railing on top, user 2026-10-06)
    for name, (z0, z1, out, thick, role) in BANDS.items():   # same lines as along the side
        horseshoe_wall(f'fc_{name}', z0, z1, thick, role, grow=out)
    # skirt under the forecastle's overhang down to the rising hull top (no open slot into the hull)
    tapered_block('fc_skirt', FC_Y_BACK - 0.05, 24.0, lambda y: z_top(y) - 0.1, FC_Z_BASE + 0.005,
                  lambda y: half_beam(y, True), 'hull', n=24)
    horseshoe_wall('fc_cap', FC_Z_PARAPET, FC_Z_PARAPET + 0.1, 0.45, 'trim')
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

def side_strip(name, ya, yb, z0, z1, out, thick, role, n=48):
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
    """Captain's cabin (walk-in: floor = gun deck level, poop deck as ceiling) with doors fore and aft,
    windows, and a small stern balcony behind it."""
    body = tapered_block('sc_body', SC_Y_AFT, SC_Y_FORE, lambda y: z_top(y) - 0.1, SC_Z_FLOOR, sc_hw, 'paint', n=48)
    # (the hull end behind the cabin is closed by the stern balcony's plate)
    cuts = []
    # hollow the cabin: walls SC_WALL thick, open to the poop deck above (its underside is the ceiling)
    cuts.append(tapered_block('cut', SC_Y_AFT + SC_WALL, SC_Y_FORE - SC_WALL, FC_Z_BASE, SC_Z_FLOOR + 0.05,
                              lambda y: sc_hw(y) - SC_WALL, 'dark', n=16))
    PARTS.pop()                                           # the inner volume is a cutter, not a part
    c = cuts[-1]
    for col in c.users_collection: col.objects.unlink(c)
    coll('cutters').objects.link(c)
    # cabin door and two windows in the front bulkhead
    cuts.append(cutter_box(SC_DOOR_X, SC_Y_FORE, Z_GUN_DECK + 1.0, SC_DOOR_W, 0.6, 2.0))
    for x in (-SC_FWIN_X, SC_FWIN_X):
        cuts.append(cutter_box(x, SC_Y_FORE, SC_EWIN_Z, 0.5, 0.6, 0.5))
        lining('sc_window_lining', (x, SC_Y_FORE, SC_EWIN_Z), (0, 1, 0), 0.5, 0.5, SC_WALL, sill_out=0.04)
    # stern door onto the balcony, with a window on each side
    cuts.append(cutter_box(0, SC_Y_AFT, Z_GUN_DECK + 1.0, SC_DOOR_W, 0.6, 2.0))
    for x in (-SC_AWIN_X, SC_AWIN_X):
        cuts.append(cutter_box(x, SC_Y_AFT, SC_EWIN_Z, 0.5, 0.6, 0.5))
        lining('sc_window_lining', (x, SC_Y_AFT, SC_EWIN_Z), (0, -1, 0), 0.5, 0.5, SC_WALL, sill_out=0.04)
    # side windows (the drawing's band of small arched windows)
    nwin = 6
    for side in (-1, 1):
        for i in range(nwin):
            y = SC_Y_AFT + 1.0 + (SC_Y_FORE - SC_Y_AFT - 2.0) * (i + 0.5) / nwin
            nrm = wall_normal(sc_hw, y, side)
            cuts.append(cutter_box(side * sc_hw(y), y, (SCW_Z0 + SCW_Z1) / 2, 0.6, 0.5, SCW_Z1 - SCW_Z0,
                                   math.atan2(nrm.y, nrm.x)))
            lining('sc_window_lining', (side * sc_hw(y), y, (SCW_Z0 + SCW_Z1) / 2), nrm, 0.5,
                   SCW_Z1 - SCW_Z0, SC_WALL, sill_out=0.04)
            # arch over each window
            # wooden arched hood on top of the frame: a flat half-elliptical board in the wall plane whose inner
            # edge continues the jambs' inner faces, resting on the frame's top
            M = _basis(Vector((side * sc_hw(y), y, SCW_Z1)), nrm)
            ai, ao = 0.25 - 0.04, 0.25                      # same width as the jamb boards: the frame curving over
            bi, bo = SCW_ARCH, SCW_ARCH + 0.04
            bm = bmesh.new()
            K = 24
            rings = []
            for k in range(K + 1):
                t = math.pi * k / K
                ring = []
                for (a, b) in ((ai, bi), (ao, bo)):
                    for yy in (-0.01, 0.02):                # same 2 cm lip as the frame
                        ring.append(bm.verts.new(M @ Vector((a * math.cos(t), yy, b * math.sin(t)))))
                rings.append(ring)                           # [inner-back, inner-front, outer-back, outer-front]
            for r0, r1 in zip(rings, rings[1:]):
                for i0, i1 in ((0, 1), (1, 3), (3, 2), (2, 0)):
                    bm.faces.new((r0[i0], r0[i1], r1[i1], r1[i0]))
            for r, flip in ((rings[0], False), (rings[-1], True)):
                f = (r[0], r[2], r[3], r[1])
                bm.faces.new(tuple(reversed(f)) if flip else f)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            obj_from_bm(bm, 'sc_window_hood', 'trim')
    subtract(body, cuts)
    # cabin floor (planked, level with the gun deck) and door frames
    tapered_block('sc_floor', SC_Y_AFT + SC_WALL - 0.01, SC_Y_FORE - SC_WALL + 0.01, FC_Z_BASE, Z_GUN_DECK,
                  lambda y: sc_hw(y) - SC_WALL + 0.01, 'deck', n=16)
    # door linings (posts, lintel, low threshold) inside the openings, like the windows: no coplanar faces
    for dx, dy, out in ((SC_DOOR_X, SC_Y_FORE, 1), (0.0, SC_Y_AFT, -1)):
        lining('sc_door_lining', (dx, dy, Z_GUN_DECK + 1.0), (0, out, 0), SC_DOOR_W, 2.0, SC_WALL, t=0.07)
    # a little furniture: table with benches, a chest against the forward bulkhead
    ty = (SC_Y_AFT + SC_Y_FORE) / 2 - 1.0
    box('cabin_table_top', -0.55, 0.55, ty - 1.0, ty + 1.0, Z_GUN_DECK + 0.72, Z_GUN_DECK + 0.78, 'trim')
    for lx in (-0.42, 0.42):
        for ly in (ty - 0.85, ty + 0.85):
            box('cabin_table_leg', lx - 0.04, lx + 0.04, ly - 0.04, ly + 0.04, Z_GUN_DECK, Z_GUN_DECK + 0.72, 'trim')
    for bx in (-1.05, 1.05):
        box('cabin_bench', bx - 0.18, bx + 0.18, ty - 0.9, ty + 0.9, Z_GUN_DECK + 0.4, Z_GUN_DECK + 0.46, 'trim')
        for ly in (ty - 0.75, ty + 0.75):
            box('cabin_bench_leg', bx - 0.12, bx + 0.12, ly - 0.03, ly + 0.03, Z_GUN_DECK, Z_GUN_DECK + 0.4, 'trim')
    box('cabin_chest', -1.9, -0.9, SC_Y_FORE - SC_WALL - 0.65, SC_Y_FORE - SC_WALL - 0.05, Z_GUN_DECK, Z_GUN_DECK + 0.6, 'trim')
    box('cabin_chest_band', -1.92, -0.88, SC_Y_FORE - SC_WALL - 0.67, SC_Y_FORE - SC_WALL - 0.03, Z_GUN_DECK + 0.42, Z_GUN_DECK + 0.48, 'iron')
    build_stern_balcony()

def build_stern_lantern():
    """Venetian stern lantern on a turned post: bowl with drop knob, eight flat glass panes between gilded
    corner ribs and bands, moulded cornice, ogee dome, ball finial and cross."""
    x0, y0 = 0.0, LANTERN_Y
    lathe('lantern_post', [(0.11, 0), (0.13, 0.08), (0.1, 0.3), (0.1, 3.2), (0.13, 3.3), (0.1, 3.42), (0.1, 3.55)],
          'trim', at=(x0, y0, SC_Z_FLOOR + 0.12), segs=12)
    zl = SC_Z_FLOOR + 0.12 + 3.5                        # bottom of the lantern
    R, H = 0.42, 0.95                                     # pane circumradius, pane height
    zg0 = zl + 0.42; zg1 = zg0 + H
    rot = math.pi / 8                                     # octagon faces/ribs: ribs on the corners
    def octa(name, prof, role):
        o = lathe(name, prof, role, at=(x0, y0, 0), segs=8)
        o.rotation_euler = (0, 0, rot)                    # lathe is around the origin: rotate in place below
        o.location = (0, 0, 0)
        me = o.data
        me.transform(Matrix.Translation((-x0, -y0, 0)))
        me.transform(Matrix.Rotation(rot, 4, 'Z'))
        me.transform(Matrix.Translation((x0, y0, 0)))
        o.rotation_euler = (0, 0, 0)
        return o
    # bowl and drop knob (round), collar on the post
    lathe('lantern_bowl', [(0.0, zl - 0.18), (0.07, zl - 0.14), (0.05, zl - 0.06), (0.14, zl), (0.32, zl + 0.16),
                           (0.46, zl + 0.34), (0.48, zl + 0.42)], 'gilt', at=(x0, y0, 0), segs=48)
    # glass panes (flat, hard-edged) and the gilded frame
    octa('lantern_glass', [(R, zg0), (R, zg1)], 'glass')
    # corner ribs: flat boards squared to each octagon corner, running between the bands (ends hidden in them)
    for k in range(8):
        a = 2 * math.pi * k / 8 + rot
        n = Vector((math.cos(a), math.sin(a), 0))
        M = _basis(Vector((x0, y0, 0)) + n * R, n)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1)
        for v in bm.verts:
            v.co = M @ Vector((0.025 if v.co.x > 0 else -0.025, 0.025 if v.co.y > 0 else -0.02,
                               zg1 if v.co.z > 0 else zg0))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        obj_from_bm(bm, 'lantern_rib', 'gilt')
    RB = R + 0.05                                         # band circumradius: encloses the rib corners
    for zb in (zg0, zg0 + H * 0.62, zg1):                 # lower/upper rails and the transom bar
        octa('lantern_band', [(RB, zb - 0.025), (RB, zb + 0.025)], 'gilt')
    # cornice and ogee dome
    # cornice: its underside covers the top band's corners
    lathe('lantern_cornice', [(RB + 0.02, zg1 + 0.02), (R + 0.12, zg1 + 0.07), (R + 0.12, zg1 + 0.12),
                              (R + 0.03, zg1 + 0.15)], 'gilt', at=(x0, y0, 0), segs=48)
    zd = zg1 + 0.15
    lathe('lantern_dome', [(R + 0.03, zd), (R - 0.02, zd + 0.1), (0.3, zd + 0.24), (0.17, zd + 0.34), (0.09, zd + 0.44),
                           (0.06, zd + 0.52), (0.1, zd + 0.58), (0.11, zd + 0.64), (0.07, zd + 0.7), (0.035, zd + 0.74)],
          'gilt', at=(x0, y0, 0), segs=48)
    zc = zd + 0.72
    sweep('lantern_cross_v', [(x0, y0, zc), (x0, y0, zc + 0.6)], 0.03, 'gilt', square=True)
    sweep('lantern_cross_h', [(x0 - 0.16, y0, zc + 0.4), (x0 + 0.16, y0, zc + 0.4)], 0.03, 'gilt', square=True)

def build_stern_balcony():
    """Half-oval balcony behind the stern door, at cabin-floor level, with a turned balustrade ending on the
    stern post, carried by two carved knees."""
    rx, ry = sc_hw(SC_Y_AFT) + 0.1, BALC_RY              # flush with the rub rail's outer face at the stern wall
    def edge(t):                                          # t: 0 = port end at the stern wall, pi = starboard end
        return (-rx * math.cos(t), SC_Y_AFT - ry * math.sin(t))
    n = 24
    bm = bmesh.new()
    top = [bm.verts.new((*edge(math.pi * i / n), Z_GUN_DECK)) for i in range(n + 1)]
    bot = [bm.verts.new((*edge(math.pi * i / n), BALC_Z_BOT)) for i in range(n + 1)]
    bm.faces.new(top); bm.faces.new(list(reversed(bot)))
    for i in range(n):
        bm.faces.new((bot[i], bot[i + 1], top[i + 1], top[i]))
    bm.faces.new((bot[-1], bot[0], top[0], top[-1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    plate = obj_from_bm(bm, 'balcony_floor', 'deck')
    # notch for the stern post (it rakes aft: 0.1 m over 1.7 m), so its corners don't poke through the plate
    post = cutter_box(0, -25.40, 2.1, 0.3, 0.3, 1.2)
    post.rotation_euler = (math.atan2(0.1, 1.7), 0, 0)
    subtract(plate, [post])
    # balustrade along the curved edge; the stern post stands at the aft centre, the rail ends on it
    zb, zr = Z_GUN_DECK, Z_GUN_DECK + 1.0
    prof = [(r * 0.88, z) for r, z in BALUSTER]
    prof = smooth_profile([(r, z * (zr - zb - 0.08) / 0.9) for r, z in prof])
    # the balustrade stands BALC_INSET inside the floor edge, so nothing overhangs the plate (seen from below)
    def edge_in(t):
        return (-(rx - BALC_INSET) * math.cos(t), SC_Y_AFT - (ry - BALC_INSET) * math.sin(t))
    x_stop = 0.28                                         # last baluster/curve point before the stern post
    t_post = math.acos(x_stop / (rx - BALC_INSET))
    t_wall = 0.12                                         # just off the stern wall, room for the end post
    for ta, tb, sgn in ((t_wall, t_post, -1), (math.pi - t_post, math.pi - t_wall, 1)):
        ts = [ta + (tb - ta) * k / 12 for k in range(13)]
        pts = [edge_in(t) for t in ts]
        # the rail then turns in onto the post's front face (post front at rail height y -25.307)
        tip = (sgn * 0.1, -25.26)
        rail = pts + [tip] if sgn < 0 else [tip] + pts
        sweep('balcony_rail', [(x, y, zr - 0.04) for x, y in rail], 0.06, 'trim', square=True)
        for x, y in pts[1:]:
            lathe('balcony_baluster', prof, 'trim', at=(x, y, zb), segs=10)
    for side in (-1, 1):                                  # square end posts set against the stern wall
        x, y = edge_in(t_wall if side < 0 else math.pi - t_wall)
        box('balcony_end_post', x - 0.08, x + 0.08, SC_Y_AFT - 0.16, SC_Y_AFT, zb, zr + 0.06, 'trim')
        sweep('balcony_rail_end', [(x, SC_Y_AFT - 0.02, zr - 0.04), (x, y, zr - 0.04)], 0.06, 'trim', square=True)
    # mouldings: above the bulwark line, under the windows, under the poop deck
    sc_out = sc_hw(0) - side_hw(0)                       # cabin sides stand this far outside the ship's side line
    def wrap(name, z0, z1, out, thick, role, fore=None, aft=None):
        """Band along both cabin sides; with fore/aft gap lists it turns the corner and runs across that
        face between the given x intervals (doors, stairs), so no band ends in mid-air at a corner.
        Never deeper than the cabin wall (walk-in cabin)."""
        o = out - sc_out
        t = min(thick, o + SC_WALL - 0.03)
        ya = SC_Y_AFT - (o if aft else 0.0)
        yb = SC_Y_FORE + (o if fore else 0.0)
        side_strip(f'sc_{name}', ya, yb, z0, z1, o, t, role)
        for face_y, sgn, segs in ((SC_Y_FORE, 1, fore), (SC_Y_AFT, -1, aft)):
            if not segs:
                continue
            w = sc_hw(face_y) + o - t                     # stop at the side strip's inner face (no overlap)
            for xa, xb in segs:
                xa, xb = max(xa, -w), min(xb, w)
                box(f'sc_{name}_face', xa, xb, *sorted((face_y + sgn * o, face_y + sgn * (o - t))), z0, z1, role)
    door_f = [(-9, SC_DOOR_X - SC_DOOR_W / 2 - 0.12), (SC_DOOR_X + SC_DOOR_W / 2 + 0.12, 9)]
    door_a = [(-9, -SC_DOOR_W / 2 - 0.12), (SC_DOOR_W / 2 + 0.12, 9)]
    stairs_f = [(-9, -SC_STAIR_X - 0.55), (-SC_STAIR_X + 0.55, SC_STAIR_X - 0.55), (SC_STAIR_X + 0.55, 9)]
    for name, (z0, z1, out, thick, role) in BANDS.items():
        # rub rail: the balcony plate covers the stern face at its height
        wrap(name, z0, z1, out, thick, role, aft=None if name == 'rub_rail' else door_a)
    wrap('window_band', SCW_Z0 - 0.2, SCW_Z0 - 0.1, 0.06 + sc_out, 0.12, 'gilt', fore=door_f, aft=door_a)
    wrap('deck_line', SC_Z_FLOOR - 0.12, SC_Z_FLOOR, 0.06 + sc_out, 0.12, 'trim', fore=stairs_f, aft=[(-9, 9)])
    # poop deck and turned balustrade
    # even overhang: 2 cm past the deck-line band at the sides and front; longer aft, where the lantern stands
    tapered_block('poop_deck', SC_Y_AFT - 0.3, SC_Y_FORE + 0.08, SC_Z_FLOOR, SC_Z_FLOOR + 0.12, sc_hw, 'deck', grow=0.08, n=48)
    baluster = BALUSTER
    zb = SC_Z_FLOOR + 0.12
    hb = SC_Z_RAIL - zb - 0.1
    prof = smooth_profile([(r, z * hb / 0.9) for r, z in baluster])
    for side in (-1, 1):
        n = int((SC_Y_FORE - SC_Y_AFT) / 0.32)
        for i in range(n + 1):
            y = SC_Y_AFT + (SC_Y_FORE - SC_Y_AFT) * i / n
            x = side * (sc_hw(y) - POOP_INSET)
            if i % 6 == 0:                              # big posts with gilded finials
                box('sc_post', x - 0.09, x + 0.09, y - 0.09, y + 0.09, zb, SC_Z_RAIL + 0.1, 'trim')
                box('sc_post_cap', x - 0.105, x + 0.105, y - 0.105, y + 0.105, SC_Z_RAIL + 0.1, SC_Z_RAIL + 0.13, 'trim')
                lathe('sc_finial', FINIAL, 'gilt', at=(x, y, SC_Z_RAIL + 0.13), segs=16)
            else:
                lathe('sc_baluster', prof, 'trim', at=(x, y, zb), segs=10)
        rail = [(side * (sc_hw(SC_Y_AFT + (SC_Y_FORE - SC_Y_AFT) * k / 16) - POOP_INSET),
                 SC_Y_AFT + (SC_Y_FORE - SC_Y_AFT) * k / 16, SC_Z_RAIL - 0.05) for k in range(17)]
        sweep('sc_rail', rail, 0.07, 'trim', square=True)
    w = sc_hw(SC_Y_AFT) - POOP_INSET
    for i in range(int(2 * w / 0.32) + 1):
        x = -w + i * 0.32
        lathe('sc_baluster', prof, 'trim', at=(x, SC_Y_AFT, zb), segs=10)
    sweep('sc_rail_aft', [(-w, SC_Y_AFT, SC_Z_RAIL - 0.05), (w, SC_Y_AFT, SC_Z_RAIL - 0.05)], 0.07, 'trim', square=True)
    # forward rail of the poop with a gap for the stairs
    wf = sc_hw(SC_Y_FORE) - POOP_INSET
    yf = SC_Y_FORE - POOP_INSET
    for x0, x1 in ((-wf, -SC_STAIR_X - 0.5), (-SC_STAIR_X + 0.5, SC_STAIR_X - 0.5), (SC_STAIR_X + 0.5, wf)):
        sweep('sc_rail_fore', [(x0, yf, SC_Z_RAIL - 0.05), (x1, yf, SC_Z_RAIL - 0.05)], 0.07, 'trim', square=True)
        n = max(int((x1 - x0) / 0.32), 1)
        for k in range(1, n):
            lathe('sc_baluster', prof, 'trim', at=(x0 + (x1 - x0) * k / n, yf, zb), segs=10)
        for x in (x0, x1):
            box('sc_post', x - 0.09, x + 0.09, yf - 0.09, yf + 0.09, zb, SC_Z_RAIL + 0.1, 'trim')
    # awning frame (tendalino) over the after part of the poop
    ya, yb = SC_AWNING_Y
    aw = lambda y: sc_hw(y) - POOP_INSET               # on the balustrade line
    for y in (ya, (ya + yb) / 2, yb):
        for side in (-1, 1):
            x = side * aw(y)
            sweep('awning_post', [(x, y, SC_Z_RAIL - 0.1), (x, y, SC_Z_AWNING + 0.05)], 0.06, 'trim', segs=12)
            box('awning_post_cap', x - 0.08, x + 0.08, y - 0.08, y + 0.08, SC_Z_AWNING - 0.06, SC_Z_AWNING + 0.06, 'trim')
        arc = [(-aw(y) * math.cos(t), y, SC_Z_AWNING + 0.6 * math.sin(t)) for t in [math.pi * k / 24 for k in range(25)]]
        sweep('awning_hoop', arc, 0.05, 'trim', segs=12, cap=False)
    for side in (-1, 1):
        sweep('awning_rail', [(side * aw(y), y, SC_Z_AWNING) for y in (ya, (ya + yb) / 2, yb)], 0.05, 'trim', segs=12)
    sweep('awning_ridge', [(0, ya, SC_Z_AWNING + 0.6), (0, yb, SC_Z_AWNING + 0.6)], 0.05, 'trim', segs=12)
    build_stern_lantern()
    # stairs from the gun deck up to the poop, running aft along both sides of the cabin front
    run = (SC_Z_FLOOR - Z_GUN_DECK) / math.tan(math.radians(40))
    for side in (-1, 1):
        x = side * SC_STAIR_X
        stairs(f'sc_stairs_{side}', x - 0.5, x + 0.5, SC_Y_FORE + run, Z_GUN_DECK, SC_Y_FORE, SC_Z_FLOOR + 0.12)

# ================================================================= stem, spur, stern post, rudder
def build_ends():
    """Backbone: ONE continuous timber from the top of the curled stern post down the stern, along the keel and
    up the stem, following the hull outline (half embedded), smooth and densely sampled."""
    # hull bottom outline, offset outward by OFF along its 2D normal (cosine spacing: dense at the ends)
    OFF, N = 0.05, 160
    prof = []
    for i in range(N + 1):
        t = i / N
        y = -25.2 + 50.4 * (0.5 - 0.5 * math.cos(t * math.pi))
        prof.append(Vector((y, z_bottom(y))))
    pts = []
    for i, p in enumerate(prof):
        a, b = prof[max(i - 1, 0)], prof[min(i + 1, N)]
        tn = (b - a).normalized()
        nrm = Vector((-tn.y, tn.x))
        if nrm.dot(p - Vector((0, 1.0))) < 0:
            nrm = -nrm
        q = p + nrm * OFF
        pts.append((0.0, q.x, q.y))
    # stern post above the hull end (fixed: the balcony notch and rails fit these), stem up the hull's end cap
    stern_top = [(0, -26.6, 6.9), (0, -26.0, 6.2), (0, -25.6, 5.0), (0, -25.45, 3.3), (0, -25.35, 1.6)]
    stem_top = [(0, 25.3, 1.7), (0, 25.32, 2.3)]
    path = catmull(stern_top + pts[2:-2] + stem_top, 420)
    radii = [0.17 + 0.03 * smoothstep(23.0, 25.0, abs(p.y)) for p in path]
    sweep('backbone', path, radii, 'trim', square=True)
    # carved scroll: continues the stern post seamlessly (same square section, same direction at the joint),
    # curling forward over the top and tapering to its eye
    p0 = Vector((path[0].y, path[0].z))
    t0 = (p0 - Vector((path[1].y, path[1].z))).normalized()      # leaving the post upward/aft
    R0, turns = 0.4, 1.6
    best = None
    for nrm in (Vector((-t0.y, t0.x)), Vector((t0.y, -t0.x))):   # curl centre on either side; pick the forward one
        if best is None or nrm.x > best.x:
            best = nrm
    c = p0 + best * R0
    a0_ = math.atan2((p0 - c).y, (p0 - c).x)
    # direction of travel so the start tangent equals t0
    sgn = 1 if Vector((-math.sin(a0_), math.cos(a0_))).dot(t0) > 0 else -1
    vol = []
    for k in range(41):
        f = k / 40
        a = a0_ + sgn * 2 * math.pi * turns * f
        r = R0 - (R0 - 0.1) * f
        vol.append((0.0, c.x + r * math.cos(a), c.y + r * math.sin(a)))
    sweep('stern_volute', vol, [radii[0] - (radii[0] - 0.07) * k / 40 for k in range(41)], 'gilt', square=True)

# turned acorn finial (r, z): collar, neck with a bead, egg-shaped body, fine tip (foot stays inside the post)
FINIAL = None   # set after smooth_profile is defined

# classical turned baluster (r, z) over a 0.9 height: base block, swelling belly, neck, collar, top block
BALUSTER = [(0.058, 0.0), (0.07, 0.03), (0.07, 0.07), (0.05, 0.11), (0.055, 0.17), (0.072, 0.27), (0.083, 0.38),
            (0.082, 0.47), (0.068, 0.57), (0.05, 0.66), (0.042, 0.73), (0.05, 0.78), (0.066, 0.82), (0.066, 0.86),
            (0.052, 0.9)]

def smooth_profile(prof, n=22):
    """Turned profile (r, z) through a smooth curve: rounder silhouettes for lathe parts."""
    return [(v.x, v.y) for v in catmull([(r, z, 0) for r, z in prof], n)]

def _finial():
    return smooth_profile([(0.075, 0.0), (0.078, 0.02), (0.05, 0.045), (0.045, 0.06), (0.062, 0.075), (0.045, 0.095),
                           (0.05, 0.12), (0.078, 0.16), (0.092, 0.21), (0.088, 0.26), (0.068, 0.31), (0.038, 0.35),
                           (0.016, 0.38), (0.0, 0.395)], 26)

def catmull(pts, n=40):
    """Smooth curve through points (Catmull-Rom, ends clamped), returned as n+1 evenly parametrised points."""
    P = [Vector(p) for p in pts]
    P = [P[0]] + P + [P[-1]]
    out = []
    segs = len(pts) - 1
    for k in range(n + 1):
        u = k / n * segs; i = min(int(u), segs - 1); t = u - i
        p0, p1, p2, p3 = P[i], P[i + 1], P[i + 2], P[i + 3]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return out

def build_beak():
    """Carved beak (knee of the head) from the stem forward under the forecastle; the figurehead sits on its end.
    Knee and rail are smooth timbers; the painted cheek is recessed between them; a gilded trail board with a
    volute runs along the middle of the cheek, clear of both timbers."""
    fy, fz = FIG_POS[1], FIG_POS[2]
    # the knee grows out of the stem: it starts inside the hull at the backbone's thickness
    knee = catmull([(0, Y_STEM_WL - 0.6, -0.15), (0, Y_STEM_WL + 0.15, 0.15), (0, Y_STEM_WL + 0.75, 0.85),
                    (0, fy - 0.6, fz - 0.3), (0, fy + 0.1, fz - 0.02)], 40)
    knee_r = [0.2 + 0.12 * smoothstep(0, 8, k) - 0.06 * k / 40 for k in range(41)]
    sweep('beak_knee', knee, knee_r, 'trim', square=True)
    rail = catmull([(0, Y_STEM_WL + 0.35, FC_Z_BASE - 0.05), (0, Y_STEM_WL + 1.0, FC_Z_BASE - 0.1),
                    (0, fy - 0.15, fz + 0.28)], 30)
    sweep('beak_rail', rail, 0.17, 'trim', square=True)
    KNEE_HALF = 0.32 * 0.7071; RAIL_HALF = 0.17 * 0.7071; CHEEK_X = 0.1; TRAIL_R = 0.035
    # cheek: outline = rail (stem -> seat) + knee back (seat -> stem), only the part above the knee start
    kpart = [p for p in knee if p.y >= Y_STEM_WL + 0.2]
    outline = [(p.y, p.z) for p in rail] + [(p.y, p.z) for p in reversed(kpart)]
    bm = bmesh.new()
    for side in (-1, 1):
        vs = [bm.verts.new((side * CHEEK_X, y, z)) for y, z in outline]
        bm.faces.new(vs if side > 0 else list(reversed(vs)))
    obj_from_bm(bm, 'beak_cheek', 'paint')
    # trail board: parallel to the knee at a fixed offset above it, as far as it stays clear of the rail
    def nearest(p, curve):
        return min((p - q).length for q in curve)
    OFF = KNEE_HALF + TRAIL_R + 0.1
    cand = []
    for i in range(1, len(kpart) - 1):
        d = (kpart[i + 1] - kpart[i - 1]).normalized()
        up = Vector((0, -d.z, d.y))
        if up.z < 0: up = -up
        P = kpart[i] + up * OFF
        if P.y < Y_STEM_WL + 0.55:                        # only on the cheek, clear of the bow (and room for the volute)
            continue
        if nearest(P, rail) - RAIL_HALF - TRAIL_R > 0.06:
            cand.append(P)
        elif cand:
            break
    run = catmull(cand[::max(len(cand) // 6, 1)] + [cand[-1]], 24)
    print('beak trail: %d pts, min knee %.3f, min rail %.3f' % (len(run),
          min(nearest(p, knee) - KNEE_HALF for p in run), min(nearest(p, rail) - RAIL_HALF for p in run)))
    # volute at the lower (stem) end, wound on the side away from the knee, leaving tangentially into the board
    d = (run[1] - run[0]).normalized()
    rv = 0.13
    perp = Vector((0, -d.z, d.y))
    best = None
    for sgn in (1, -1):                                   # sgn=1: centre on +perp, CCW; sgn=-1: centre on -perp, CW
        c = run[0] + sgn * rv * perp
        a_end = math.atan2((run[0] - c).z, (run[0] - c).y)
        pts = []
        for k in range(21):
            r = 0.035 + (rv - 0.035) * k / 20
            a = a_end - sgn * 2.5 * math.pi * (1 - k / 20)
            pts.append(Vector((0, c.y + r * math.cos(a), c.z + r * math.sin(a))))
        clear = min(min(nearest(q, knee) - KNEE_HALF, nearest(q, rail) - RAIL_HALF, q.y - Y_STEM_WL - 0.2) for q in pts)
        if best is None or clear > best[0]:
            best = (clear, pts)
    vol = best[1]
    print('beak volute clearance %.3f centre y %.2f z %.2f, run0 y %.2f z %.2f, run_end y %.2f z %.2f' % (best[0], vol[0].y, vol[0].z, run[0].y, run[0].z, run[-1].y, run[-1].z))
    path = vol + run[1:]
    radii = [0.015 + 0.02 * min(k / 20, 1) for k in range(len(path))]
    for side in (-1, 1):
        x = side * (CHEEK_X + 0.02)
        sweep('beak_trail', [(x, p.y, p.z) for p in path], radii, 'gilt', segs=8)

def build_rudder():
    """Sternpost rudder hung on the straight raked sternpost. Modelled upright in its own frame (hinge = local Z,
    blade toward local -Y = aft); the object is tilted by the rake, so in the game it turns about its own Z.
    Blade widest low down, narrowing into a squared stock with an iron cap; tapering thickness; iron straps
    with pintles. Gudgeon straps go on the sternpost (part of the hull)."""
    # hinge line: the sternpost centre line pushed aft past the backbone (5 cm offset + 0.14 half width + 1 cm)
    hy, hz = STERN_HEEL; ty, tz = STERN_POST_TOP
    u = Vector((-(ty - hy), tz - hz)).normalized()                 # (y, z) up the post, ship frame (aft = -y)
    n_aft = Vector((-u.y, u.x)) if (-u.y) < 0 else Vector((u.y, -u.x))
    off = 0.05 + 0.14 + 0.01
    base = Vector((-hy, hz)) + n_aft * off + u * 0.12               # hinge bottom, just above the heel
    # along the hinge up to the post's knee (STERN_POST_TOP, just under the balcony): above it the post is steeper
    L = (STERN_POST_TOP[1] - base.y) / math.cos(STERN_RAKE) - 0.05
    # blade outline: (local z along hinge, aft extent)
    outline = [(0.0, 0.3), (0.15, 1.15), (0.6, 1.3), (1.5, 1.28), (2.3, 1.05), (2.9, 0.7), (3.3, 0.32),
               (3.6, 0.2), (L, 0.2)]
    zs = [z for z, _ in outline]
    def aft_at(z):
        for (z0, d0), (z1, d1) in zip(outline, outline[1:]):
            if z0 <= z <= z1:
                return d0 + (d1 - d0) * (z - z0) / max(z1 - z0, 1e-6)
        return outline[-1][1]
    bm = bmesh.new()
    rings = []
    stations = sorted(set([round(i * L / 40, 4) for i in range(41)] + zs))
    for z in stations:
        d = aft_at(z)
        th = 0.11                                                   # half thickness at the hinge
        tt = 0.04 if d > 0.3 else 0.1                               # ... and at the trailing edge (stock: square-ish)
        rings.append([bm.verts.new(c) for c in ((th, 0.04, z), (tt, -d, z), (-tt, -d, z), (-th, 0.04, z))])
    for a, b in zip(rings, rings[1:]):
        for k in range(4):
            bm.faces.new((a[k], a[(k + 1) % 4], b[(k + 1) % 4], b[k]))
    bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    parts = [(bm, 'trim')]
    def ibox(x0, x1, y0, y1, z0, z1):
        b = bmesh.new(); bmesh.ops.create_cube(b, size=1)
        for v in b.verts:
            v.co = Vector((x0 if v.co.x < 0 else x1, y0 if v.co.y < 0 else y1, z0 if v.co.z < 0 else z1))
        parts.append((b, 'iron'))
    STRAPS = (0.45, 1.25, 2.05, 2.85)
    for z in STRAPS:
        d = min(aft_at(z) * 0.55, 0.7)
        ibox(-0.125, 0.125, -d, 0.03, z - 0.05, z + 0.05)           # strap round the blade
        b = bmesh.new()                                             # pintle at the hinge
        bmesh.ops.create_cone(b, cap_ends=True, segments=12, radius1=0.05, radius2=0.05, depth=0.16)
        for v in b.verts: v.co += Vector((0, 0.06, z))
        parts.append((b, 'iron'))
    ibox(-0.13, 0.13, -0.24, 0.07, L - 0.08, L + 0.02)              # cap on the stock
    # join into one object with two materials, origin on the hinge bottom, tilted by the rake
    me = bpy.data.meshes.new('galleass_rudder')
    bm_all = bmesh.new()
    mats = ['trim', 'iron']
    for b, role in parts:
        tmp = bpy.data.meshes.new('tmp'); b.to_mesh(tmp); b.free()
        idx = mats.index(role)
        for poly in tmp.polygons: poly.material_index = idx
        bm_all.from_mesh(tmp); bpy.data.meshes.remove(tmp)
    for f in bm_all.faces: f.smooth = True
    bm_all.to_mesh(me); bm_all.free()
    for r in mats: me.materials.append(MATS[r])
    me.set_sharp_from_angle(angle=math.radians(40))
    o = bpy.data.objects.new('galleass_rudder', me); coll('final').objects.link(o)
    o.location = (0, base.x, base.y)
    o.rotation_euler = (STERN_RAKE, 0, 0)                          # local Z -> up the raked post
    # gudgeon straps on the sternpost (hull side) at the pintle heights
    bpy.context.view_layer.update()
    for z in STRAPS:                                               # squared to the raked post (rudder frame)
        b = bmesh.new(); bmesh.ops.create_cube(b, size=1)
        for v in b.verts:
            v.co = o.matrix_world @ Vector((0.17 if v.co.x > 0 else -0.17, 0.32 if v.co.y > 0 else 0.03,
                                            (z - 0.06) if v.co.z > 0 else (z - 0.13)))
        bmesh.ops.recalc_face_normals(b, faces=b.faces)
        obj_from_bm(b, 'gudgeon', 'iron')
    return o

# ================================================================= markers (not exported)
def build_markers():
    for name, y in MASTS.items():
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=0.35, radius2=0.18, depth=20)
        z0 = Z_GUN_DECK if name != 'fore' else FC_Z_PLATFORM
        for v in bm.verts: v.co.z += 10 + z0; v.co.y += y
        obj_from_bm(bm, f'mast_{name}', 'dark', 'markers', smooth=True)

# ================================================================= build
FINIAL = _finial()
build_hull()
wale('wale_low', lambda y: WING_Z0 + 0.05, -21.0, 21.0, height=0.18)   # covers the seam where the flare leaves the hull
wale('wale_top', lambda y: z_top(y) - 0.05, -19.5, 19.5, height=0.2)
build_sides(); build_deck_fittings()
build_forecastle(); build_sterncastle(); build_ends(); build_markers()
rudder = build_rudder()
build_beak()
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
    o = obj_from_bm(bm, f'galleass_{role}', role, 'final', smooth=True)
    # smooth along planks and turned parts (6-sided = 60 deg), hard at box corners; glass panes stay flat
    o.data.set_sharp_from_angle(angle=math.radians(30 if role == 'glass' else 65))
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

# preview only: vanilla figureheads on the beak with the planned transform (not exported)
PREVIEW = {}
for fid in ('figurehead_lion', 'dragon_l', 'wingsofvictoryfigurehead', 'sirenfigurehead', 'seaserpentfigurehead'):
    bpy.ops.wm.obj_import(filepath=os.path.join(HERE, f'ref/figureheads/{fid}.obj'), forward_axis='Y', up_axis='Z')
    objs = []
    for o in list(bpy.context.selected_objects):
        for c in o.users_collection: c.objects.unlink(o)
        if o.name.split('.')[-1] != '0':
            bpy.data.objects.remove(o); continue
        coll('preview').objects.link(o); objs.append(o)
        o.location = FIG_POS; o.rotation_euler = (FIG_ROT_X, 0, 0); o.scale = FIG_SCALE
        o.data.materials.clear(); o.data.materials.append(MATS['gilt'])
    PREVIEW[fid] = objs

def show_preview(fid):
    for k, objs in PREVIEW.items():
        for o in objs: o.hide_render = (k != fid)
show_preview('figurehead_lion')

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
for fid in list(PREVIEW) + [None]:
    show_preview(fid)
    look(f'chk_fig_{fid or "none"}.png', (9.0, 31.0, 3.2), (0, 26.0, 1.8), lens=30)
look('chk_fig_side.png', (12, 26.5, 2.0), (0, 26.0, 1.6), lens=30)
show_preview('figurehead_lion')
look('chk_poop_corner.png', (-6.5, -27.5, 8.5), (-3.0, -23.5, 6.0), lens=30)
look('chk_awning.png', (2.5, -16.5, 10.5), (0, -21.0, 8.4), lens=30)
look('chk_sc_stairs.png', (5.5, -9.5, 7.5), (3.2, -14.3, 5.8), lens=30)
look('chk_lantern.png', (1.6, -21.6, 10.4), (0.0, -24.15, 9.8), lens=45)
look('chk_balcony.png', (4.5, -29.5, 4.2), (0.0, -24.6, 2.8), lens=30)
look('chk_balcony_top.png', (0.0, -27.0, 6.5), (0.0, -24.3, 2.3), lens=26)
look('chk_cabin_in.png', (-1.5, -15.4, 3.9), (1.0, -23.0, 2.9), lens=20)
look('chk_cabin_aft_in.png', (0.6, -22.2, 3.6), (0.0, -25.0, 3.0), lens=24)
look('chk_sc_door.png', (0.5, -7.5, 4.2), (0.6, -14.5, 3.2), lens=30)
look('chk_fc_stairs.png', (5.0, 13.0, 5.5), (2.4, 18.4, 4.0), lens=30)
look('chk_scroll_fore.png', (10.5, 23.5, 3.2), (5.5, 20.6, 2.0), lens=30)
look('chk_scroll_aft.png', (10.5, -20.5, 3.2), (5.5, -17.6, 2.0), lens=30)
look('chk_stern_under.png', (-6, -28, 0.5), (-2.5, -22, 2.5), lens=28)
look('chk_side_row.png', (7.0, 22.0, 1.6), (4.3, 12.0, 1.7), lens=28)
look('chk_side_row_aft.png', (7.0, -20.0, 1.8), (4.3, -10.0, 1.8), lens=28)
look('chk_side_wall.png', (9.5, 3.0, 2.9), (4.4, 6.0, 1.6), lens=28)
look('chk_gunport.png', (6.2, gunport_y(1) - 1.2, 3.3), (4.4, gunport_y(1), 3.15), lens=35)
look('chk_gunport_fore.png', (6.2, gunport_y(4) + 1.6, 3.3), (4.2, gunport_y(4), 3.15), lens=35)
look('chk_fc_port.png', (2.5, 28.5, 3.0), (1.6, 25.2, 2.95), lens=35)
look('chk_sc_window.png', (6.5, -19.0, 5.0), (4.3, -20.5, 4.8), lens=35)
look('chk_side_wall_fore.png', (9.5, 13.0, 2.9), (4.2, 17.5, 1.8), lens=28)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print('model done')
