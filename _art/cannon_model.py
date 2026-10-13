"""Galleass guns, 16th-century Venetian (user 2026-10-13; references: Alberghetti pieces, Gasparoni 1779 plates,
'Colubrine di bronzo da 30'). Built parametrically; for now the culverin (colubrina da 14) on its wheelless sledge bed
(letto) for the forecastle's ground floor. The falcon / falconet on two-wheel carriages follow.

    blender -b --factory-startup --python cannon_model.py -- <out.blend> <render dir>

Local frame of every gun: barrel axis along +Y (muzzle forward), Z up, origin on the deck under the trunnions'
centre; the axis is AXIS_H above the deck (the round ports are centred 0.8 m above the ground floor).
Profiles are (y, r) with y from the rear face of the base ring forward (cascabel at negative y).
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT_BLEND = argv[0] if argv else None
RENDER_DIR = argv[1] if len(argv) > 1 else None

AXIS_H = 0.80

# ---------------------------------------------------------------- culverin (colubrina da 14 libbre)
# 14 Venetian pounds (libbra grossa 0.477 kg) of iron = 6.7 kg ball, 12.0 cm; bore 12.4 cm. Bore ~32 calibres
# (Museo Storico Navale), so 4.05 m from the base ring to the muzzle; the ground floor takes it with 1 m recoil
# (fc_gun_layout.py, layout_H). Trunnions at 0.44 of the length, on a raised ring (Alberghetti drawings).
CV = dict(
    bore=0.124,
    length=4.05,                      # base ring rear face -> muzzle face
    trunnion_y=0.44 * 4.05,
    trunnion_r=0.062, trunnion_len=0.12, trunnion_dz=-0.01,
    flutes=16, flute_depth=0.006,
    # spiral on the first reinforce: dominant in the plates - 12 broad ribs, ~30 deg twist (0.75 turns), deep grooves
    spiral_ribs=12, spiral_depth=0.016, spiral_turns=0.75,
    # slender like the plates: ~3 calibres over the breech, ~2 at the muzzle (length / breech diameter ~11)
    r_breech=0.190, r_reinforce_end=0.172, r_ring=0.186, r_chase_start=0.164, r_chase_end=0.124,
)

def culverin_profile():
    L, ty = CV['length'], CV['trunnion_y']
    rb, rt, rc, rm = CV['r_breech'], CV['r_reinforce_end'], CV['r_chase_start'], CV['r_chase_end']
    rr = CV['r_ring']
    return [
        # cascabel: pear-shaped button on a neck, then the rounded breech (Gasparoni plates)
        (-0.28, 0.0), (-0.28, 0.016), (-0.273, 0.030), (-0.258, 0.041), (-0.235, 0.047), (-0.21, 0.048),
        (-0.188, 0.043), (-0.17, 0.034), (-0.156, 0.030), (-0.143, 0.032), (-0.134, 0.041), (-0.125, 0.041),
        (-0.116, 0.055), (-0.093, 0.103), (-0.065, 0.145), (-0.035, 0.175), (-0.014, 0.190), (0.0, rb + 0.004),
        # base ring: broad fillet, step, small astragal
        (0.0, rb + 0.016), (0.042, rb + 0.016), (0.047, rb + 0.009), (0.07, rb + 0.009), (0.078, rb + 0.004),
        (0.094, rb + 0.004), (0.099, rb),
        # first reinforce (fluted) up to the trunnion ring
        (ty - 0.10, rt),
        (ty - 0.095, rr - 0.008), (ty - 0.07, rr - 0.008), (ty - 0.065, rr), (ty + 0.065, rr), (ty + 0.07, rr - 0.008),
        (ty + 0.095, rr - 0.008), (ty + 0.10, rc),
        # chase (fluted, plain band for the arms / inscription) to the muzzle astragal
        (L - 0.25, rm),
        (L - 0.245, rm + 0.010), (L - 0.218, rm + 0.010), (L - 0.213, rm + 0.003), (L - 0.195, rm + 0.001),
        # muzzle: gentle swell (acanthus leaves) and lip
        (L - 0.14, rm + 0.006), (L - 0.08, rm + 0.014), (L - 0.045, rm + 0.022), (L - 0.03, rm + 0.026),
        (L - 0.026, rm + 0.030), (L, rm + 0.030), (L, CV['bore'] / 2 + 0.012), (L - 0.008, CV['bore'] / 2),
    ]

def smooth01(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)

def flute_cut(y, a, y0, y1, n, depth, turns=0.0, fade=0.035):
    """Concave flutes between y0 and y1 (rounded ends), optionally spiralling 'turns' times over the zone."""
    if y <= y0 or y >= y1:
        return 0.0
    u = (a / (2 * math.pi) + turns * (y - y0) / (y1 - y0)) * n
    u -= math.floor(u)
    land = 0.22                                            # fillet between the flutes, fraction of a pitch
    if u > 1 - land:
        return 0.0
    s = math.sin(math.pi * u / (1 - land))
    return depth * s ** 0.8 * smooth01((y - y0) / fade) * smooth01((y1 - y) / fade)

def spiral_ribs(y, a, y0, y1, n, depth, turns, fade=0.05):
    """Twisted convex ribs (rope-like spiral fluting of the colubrina da 30): broad rounded ribs, narrow deep
    grooves between them; returns the cut below the profile radius (0 on the rib crests)."""
    if y <= y0 or y >= y1:
        return 0.0
    u = (a / (2 * math.pi) + turns * (y - y0) / (y1 - y0)) * n
    u -= math.floor(u)
    rib = math.sin(math.pi * u) ** 0.6                  # 1 on the crest, 0 in the groove
    return depth * (1 - rib) * smooth01((y - y0) / fade) * smooth01((y1 - y) / fade)

def acanthus(y, a, y0, y1, n=8, height=0.009):
    """Raised leaves rising up the muzzle flare: wide at the neck, pointed tips."""
    if y <= y0 or y >= y1:
        return 0.0
    t = (y - y0) / (y1 - y0)
    u = a / (2 * math.pi) * n
    u = u - math.floor(u) - 0.5                            # -0.5..0.5 around a leaf's centre line
    hw = 0.42 * (1 - t) ** 0.8 + 0.03
    if abs(u) >= hw:
        return 0.0
    lobe = math.cos(math.pi / 2 * u / hw)
    return height * lobe * math.sin(math.pi * min(t * 1.15, 1.0)) ** 0.6

def culverin_mod(y, a, r):
    L, ty = CV['length'], CV['trunnion_y']
    if 0.16 < y < ty - 0.12:                               # first reinforce: spiral ribs (colubrina da 30, lower)
        r -= spiral_ribs(y, a, 0.16, ty - 0.12, CV['spiral_ribs'], CV['spiral_depth'], CV['spiral_turns'])
    elif ty + 0.12 < y < L - 0.29:                         # chase: straight flutes, plain band for the arms
        band0, band1 = ty + 0.62, ty + 1.02
        r -= flute_cut(y, a, ty + 0.12, band0, CV['flutes'], CV['flute_depth'] * 0.85)
        r -= flute_cut(y, a, band1, L - 0.29, CV['flutes'], CV['flute_depth'] * 0.85)
    elif L - 0.19 < y < L - 0.035:
        r += acanthus(y, a, L - 0.19, L - 0.035, height=0.007)
    return r

# ---------------------------------------------------------------- Blender helpers
ROLE_COL = {'fuse': (0.30, 0.22, 0.12, 1), 'bronze': (0.62, 0.45, 0.18, 1), 'wood': (0.36, 0.24, 0.14, 1), 'iron': (0.16, 0.16, 0.17, 1),
            'dark': (0.02, 0.02, 0.02, 1)}
MATS = {}
for _r, _c in ROLE_COL.items():
    _m = bpy.data.materials.get('galleass_gun_' + _r) or bpy.data.materials.new('galleass_gun_' + _r)
    _m.diffuse_color = _c; MATS[_r] = _m

def coll(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name); bpy.context.scene.collection.children.link(c)
    return c

def obj_from_bm(bm, name, role, collection='gun_parts', sharp=40):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    me.materials.append(MATS[role])
    for p in me.polygons: p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(sharp))
    o = bpy.data.objects.new(name, me); coll(collection).objects.link(o)
    return o

def resample(prof, step):
    """Insert points so no profile segment is longer than step (fluted / spiral zones need the rings)."""
    out = [prof[0]]
    for (y0, r0), (y1, r1) in zip(prof, prof[1:]):
        n = max(int(math.ceil(math.hypot(y1 - y0, r1 - r0) / step)), 1)
        for k in range(1, n + 1):
            out.append((y0 + (y1 - y0) * k / n, r0 + (r1 - r0) * k / n))
    return out

def lathe_y(name, prof, role, at=(0, 0, 0), segs=32, mod=None, cap_end=False, twist=None):
    """Solid of revolution about the Y axis (prof: (y, r)); mod(y, angle, r) -> r adds flutes and reliefs;
    twist(y) -> angle turns each ring so the mesh's edges follow a spiral relief (clean shading)."""
    bm = bmesh.new(); rings = []
    for y, r in prof:
        if r < 1e-6:
            rings.append([bm.verts.new((at[0], at[1] + y, at[2]))])
            continue
        ring = []
        for i in range(segs):
            a = 2 * math.pi * i / segs + (twist(y) if twist else 0.0)
            rr = mod(y, a, r) if mod else r
            ring.append(bm.verts.new((at[0] + rr * math.sin(a), at[1] + y, at[2] + rr * math.cos(a))))
        rings.append(ring)
    for ra, rb in zip(rings, rings[1:]):
        if len(ra) == 1 and len(rb) == 1:
            continue
        if len(ra) == 1:
            for i in range(segs): bm.faces.new((ra[0], rb[(i + 1) % segs], rb[i]))
        elif len(rb) == 1:
            for i in range(segs): bm.faces.new((ra[i], ra[(i + 1) % segs], rb[0]))
        else:
            for i in range(segs):
                bm.faces.new((ra[i], ra[(i + 1) % segs], rb[(i + 1) % segs], rb[i]))
    if cap_end and len(rings[-1]) > 1:
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, name, role)

def cyl_x(name, x0, x1, y, z, r, role, segs=24):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r, depth=abs(x1 - x0))
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'Y'))
    bmesh.ops.translate(bm, verts=bm.verts, vec=((x0 + x1) / 2, y, z))
    return obj_from_bm(bm, name, role)

def box(name, x0, x1, y0, y1, z0, z1, role):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0), (y0 + y1) / 2 + v.co.y * (y1 - y0),
                       (z0 + z1) / 2 + v.co.z * (z1 - z0)))
    return obj_from_bm(bm, name, role, sharp=30)

def plank_yz(name, x0, x1, outline, role):
    """Prism: a (y, z) outline (convex or not, no holes) extruded between x0 and x1."""
    bm = bmesh.new()
    a = [bm.verts.new((x0, y, z)) for y, z in outline]
    b = [bm.verts.new((x1, y, z)) for y, z in outline]
    bm.faces.new(a[::-1]); bm.faces.new(b)
    n = len(outline)
    for i in range(n):
        bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, name, role, sharp=30)

def torus_x(name, x, y, z, R, r, role, segs=16, tube=8):
    """Ring in the y-z plane (tackle rings on the cheek sides)."""
    bm = bmesh.new(); rings = []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        c = Vector((x, y + R * math.cos(a), z + R * math.sin(a)))
        n = Vector((0, math.cos(a), math.sin(a)))
        rings.append([bm.verts.new(c + n * r * math.cos(2 * math.pi * k / tube) + Vector((r * math.sin(2 * math.pi * k / tube), 0, 0)))
                      for k in range(tube)])
    for i in range(segs):
        ra, rb = rings[i], rings[(i + 1) % segs]
        for k in range(tube):
            bm.faces.new((ra[k], ra[(k + 1) % tube], rb[(k + 1) % tube], rb[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, name, role)

def strap_yz(name, x0, x1, path, w, t, role):
    """Iron strap of width w (along x: x0..x1) and thickness t following a (y, z) polyline (cap squares, bands);
    the strap lies on the outside of the path (left of the walking direction)."""
    bm = bmesh.new(); inner, outer = [], []
    for i, (y, z) in enumerate(path):
        p0 = path[max(i - 1, 0)]; p1 = path[min(i + 1, len(path) - 1)]
        dy, dz = p1[0] - p0[0], p1[1] - p0[1]; L = math.hypot(dy, dz) or 1
        ny, nz = -dz / L, dy / L
        inner.append((y, z)); outer.append((y + ny * t, z + nz * t))
    vs = [[bm.verts.new((x, y, z)) for (y, z) in ring] for ring in (inner, outer) for x in (x0, x1)]
    ia, ib, oa, ob = vs
    for i in range(len(path) - 1):
        for q in ((ia[i], ia[i + 1], ib[i + 1], ib[i]), (oa[i], ob[i], ob[i + 1], oa[i + 1]),
                  (ia[i], oa[i], oa[i + 1], ia[i + 1]), (ib[i], ib[i + 1], ob[i + 1], ob[i])):
            bm.faces.new(q)
    for j in (0, len(path) - 1):
        bm.faces.new((ia[j], ib[j], ob[j], oa[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, name, role, sharp=50)

def tube(name, path, r, role, segs=8):
    """Round cord along a 3D polyline (the fuse)."""
    bm = bmesh.new(); rings = []
    pts = [Vector(p) for p in path]
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        u = t.cross(Vector((1, 0, 0)) if abs(t.x) < 0.9 else Vector((0, 1, 0))).normalized(); v = t.cross(u)
        rr = r * (0.75 if i == len(pts) - 1 else 1.0)     # frayed, thinner tip
        rings.append([bm.verts.new(p + (u * math.cos(2 * math.pi * k / segs) + v * math.sin(2 * math.pi * k / segs)) * rr)
                      for k in range(segs)])
    for ra, rb in zip(rings, rings[1:]):
        for k in range(segs):
            bm.faces.new((ra[k], ra[(k + 1) % segs], rb[(k + 1) % segs], rb[k]))
    bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, name, role, sharp=80)

def vent_and_fuse(tag, parts, y, r_top, ah, scale, shift_y):
    """Touch hole on top of the barrel near the breech: a raised round vent boss with the dark vent bored into it
    (added to parts), and a short priming fuse (quill + match cord) standing in the vent, bending back over the
    breech - a SEPARATE object <tag>_fuse (same origin as the gun) so the game can hide it once the gun has fired."""
    zt = ah + r_top
    br, bh, vr = 0.024 * scale, 0.008 * scale, 0.0065 * scale
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=br, radius2=br * 0.85, depth=bh + 0.02)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, y, zt + bh / 2 - 0.01))
    parts.append(obj_from_bm(bm, f'{tag}_vent_boss', 'bronze', sharp=40))
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=vr, radius2=vr, depth=0.06 * scale)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, y, zt + bh - 0.03 * scale + 0.002))
    parts.append(obj_from_bm(bm, f'{tag}_vent', 'dark', sharp=40))
    k = scale
    z0 = zt + bh
    path = [(0, y, z0 - 0.02 * k), (0, y, z0 + 0.012 * k), (0.002 * k, y - 0.006 * k, z0 + 0.03 * k),
            (0.006 * k, y - 0.022 * k, z0 + 0.042 * k), (0.012 * k, y - 0.045 * k, z0 + 0.044 * k),
            (0.018 * k, y - 0.07 * k, z0 + 0.036 * k), (0.022 * k, y - 0.088 * k, z0 + 0.026 * k)]
    f = tube(f'{tag}_fuse', path, 0.0042 * k, 'fuse')
    f.data.transform(Matrix.Translation((0, shift_y, 0)))
    for m in list(f.users_collection): m.objects.unlink(f)
    coll('guns').objects.link(f)
    return f

def join(tag, parts, shift_y, collection):
    """One object per gun (multi-material); parts moved by shift_y so the trunnions sit at y 0."""
    bm = bmesh.new(); mats = list(MATS.values())
    for p in parts:
        me = p.data.copy()
        idx = mats.index(p.data.materials[0])
        for poly in me.polygons: poly.material_index = idx
        bm.from_mesh(me); bpy.data.meshes.remove(me); bpy.data.objects.remove(p)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, shift_y, 0))
    me = bpy.data.meshes.new(tag); bm.to_mesh(me); bm.free()
    for m in mats: me.materials.append(m)
    o = bpy.data.objects.new(tag, me); coll(collection).objects.link(o)
    return o

# ---------------------------------------------------------------- culverin barrel + sledge bed
def build_culverin(tag='galleass_culverin'):
    L, ty, D = CV['length'], CV['trunnion_y'], CV['bore']
    prof = culverin_profile()
    barrel_prof = resample(prof[:-2], 0.032) + prof[-2:]
    y0s, y1s = 0.16, ty - 0.12                               # spiral zone (culverin_mod)
    def twist(y):                                            # rings follow the ribs; a whole number of segments after
        return -2 * math.pi * CV['spiral_turns'] * min(max((y - y0s) / (y1s - y0s), 0.0), 1.0)
    parts = [lathe_y(f'{tag}_barrel', barrel_prof, 'bronze', at=(0, 0, AXIS_H), segs=96, mod=culverin_mod,
                     twist=twist)]
    parts.append(lathe_y(f'{tag}_bore', [(L - 0.008, D / 2), (L - 0.6, D / 2), (L - 0.6, 0.0)], 'dark',
                         at=(0, 0, AXIS_H), segs=32))
    r_ring = CV['r_ring']
    tz = AXIS_H + CV['trunnion_dz']

    # sledge bed (letto): two cheeks on two runners, front/rear transoms, breech bed + quoin, iron work.
    # Galley bow guns slid back on greased rails (Eliav 2013); our recoil slide moves this whole gun.
    gap = r_ring + CV['trunnion_len'] - 0.115           # inner face of a cheek (trunnion goes 0.115 into it)
    ct = 0.15                                           # cheek thickness
    xi, xo = gap, gap + ct
    for s in (-1, 1):                                   # trunnions run through the cheek, ends flush with its face
        x_in, x_out = s * (r_ring - 0.02), s * (xo + 0.004)
        parts.append(cyl_x(f'{tag}_trunnion', min(x_in, x_out), max(x_in, x_out), ty, tz, CV['trunnion_r'], 'bronze', segs=24))
    y_front, y_rear = ty + 0.48, -0.34
    run_h = 0.11                                        # runner (skid) height
    seat_r = CV['trunnion_r'] + 0.004
    # cheek side outline (y, z): trunnion seat on top, stepped down towards the breech, chamfered ends
    outline = [(y_rear, run_h), (y_front, run_h), (y_front, AXIS_H - 0.30), (y_front - 0.10, tz - 0.02),
               (ty + seat_r, tz - 0.02)]
    for k in range(1, 8):                               # half-round trunnion seat
        a = math.pi * k / 8
        outline.append((ty + seat_r * math.cos(a), tz - seat_r * math.sin(a)))
    # behind the seat the top steps down in two curved brackets towards the breech (low bed, like a galley's)
    outline += [(ty - seat_r, tz - 0.02), (ty - 0.16, tz - 0.02)]
    outline += [(ty - 0.16 - 0.12 * math.sin(math.pi / 2 * k / 6), tz - 0.02 - 0.16 * (1 - math.cos(math.pi / 2 * k / 6)))
                for k in range(1, 7)]
    outline += [(0.75, AXIS_H - 0.18)]
    outline += [(0.75 - 0.10 * math.sin(math.pi / 2 * k / 5), AXIS_H - 0.18 - 0.14 * (1 - math.cos(math.pi / 2 * k / 5)))
                for k in range(1, 6)]
    outline += [(y_rear + 0.10, AXIS_H - 0.32), (y_rear, AXIS_H - 0.42)]
    for s in (-1, 1):
        parts.append(plank_yz(f'{tag}_cheek', min(s * xi, s * xo), max(s * xi, s * xo), outline, 'wood'))
        # runner under each cheek, ends rounded up like a sledge
        rw = 0.16; rx = s * (xi + xo) / 2
        run = [(y_rear - 0.06, 0.05), (y_rear - 0.03, 0.015), (y_rear + 0.04, 0.0), (y_front - 0.04, 0.0),
               (y_front + 0.05, 0.02), (y_front + 0.09, 0.06), (y_front + 0.09, run_h), (y_rear - 0.06, run_h)]
        parts.append(plank_yz(f'{tag}_runner', rx - rw / 2, rx + rw / 2, run, 'wood'))
        # iron cap square over the trunnion, bolted down in front of and behind the seat
        cap = [(ty + seat_r + 0.07, tz - 0.02)] + \
              [(ty + (seat_r + 0.004) * math.cos(math.pi * k / 10), tz + (seat_r + 0.004) * math.sin(math.pi * k / 10))
               for k in range(11)] + [(ty - seat_r - 0.07, tz - 0.02)]
        parts.append(strap_yz(f'{tag}_capsquare', min(s * xi, s * xo) - 0.005, max(s * xi, s * xo) + 0.005,
                              cap, 0.0, 0.012, 'iron'))
        # iron bands round the cheek + runner
        for yb in (0.12, ty + 0.30):
            z_top = AXIS_H - 0.32 if yb < 0.48 else AXIS_H - 0.30
            band = [(yb - 0.02, -0.0), (yb - 0.02, z_top), (yb + 0.02, z_top), (yb + 0.02, 0.0)]
            for x0b, x1b in ((xo, xo + 0.008), (xi - 0.008, xi)):
                parts.append(box(f'{tag}_band', min(s * x0b, s * x1b), max(s * x0b, s * x1b), yb - 0.025, yb + 0.025,
                                 0.0, z_top + 0.006, 'iron'))
            parts.append(box(f'{tag}_band', min(s * xi, s * xo), max(s * xi, s * xo), yb - 0.025, yb + 0.025,
                             z_top, z_top + 0.008, 'iron'))
        # tackle rings (breeching / run-out tackle) on the outer face, front and rear
        for yr, zr in ((y_front - 0.22, AXIS_H - 0.42), (y_rear + 0.20, 0.30)):
            parts.append(cyl_x(f'{tag}_eyebolt', min(s * xo, s * (xo + 0.035)), max(s * xo, s * (xo + 0.035)),
                               yr, zr, 0.018, 'iron', segs=10))
            parts.append(torus_x(f'{tag}_ring', s * (xo + 0.045), yr, zr - 0.05, 0.05, 0.011, 'iron'))
    # transoms between the cheeks
    parts.append(box(f'{tag}_transom_front', -xi, xi, y_front - 0.30, y_front - 0.08, run_h, AXIS_H - 0.38, 'wood'))
    parts.append(box(f'{tag}_transom_rear', -xi, xi, y_rear + 0.02, y_rear + 0.22, run_h, AXIS_H - 0.46, 'wood'))
    # bed plank on the transoms and the elevation quoin (cuneo) under the breech
    bed_top = AXIS_H - 0.46
    parts.append(box(f'{tag}_bed', -xi, xi, y_rear + 0.02, ty - 0.30, bed_top - 0.06, bed_top, 'wood'))
    under_base = AXIS_H - CV['r_breech'] - 0.016 - 0.004                 # bottom of the base ring
    q = bmesh.new(); qw = 0.15
    qv = [q.verts.new(c) for c in (
        (-qw, -0.12, bed_top), (qw, -0.12, bed_top), (qw, 0.62, bed_top), (-qw, 0.62, bed_top),
        (-qw, -0.12, under_base + 0.012), (qw, -0.12, under_base + 0.012), (qw, 0.62, under_base - 0.05),
        (-qw, 0.62, under_base - 0.05))]
    for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        q.faces.new([qv[i] for i in f])
    bmesh.ops.recalc_face_normals(q, faces=q.faces)
    parts.append(obj_from_bm(q, f'{tag}_quoin', 'wood', sharp=30))
    parts.append(box(f'{tag}_quoin_handle', -0.03, 0.03, -0.24, -0.12, under_base - 0.05, under_base - 0.01, 'wood'))

    vent_and_fuse(tag, parts, 0.13, CV['r_breech'] - 0.0012, AXIS_H, 1.0, -ty)
    o = join(tag, parts, -ty, 'guns')
    o['muzzle_y'] = L - ty; o['cascabel_y'] = -0.28 - ty
    o['front_y'] = y_front + 0.09 - ty; o['rear_y'] = y_rear - 0.06 - ty; o['half_w'] = xo + 0.1
    return o

# ---------------------------------------------------------------- falcon / falconet (two-wheel carriage)
# Plain service pieces after the Alberghetti drawings (user's reference 1, piece 1: ~2.85 m overall, trunnions at
# ~47 % from the cascabel, one raised ring, plain chase, short muzzle band, conical cascabel button). Arms, founder's
# initials (Z.A) and date go into the texture. Falcon da 6 (libbra sottile, ~1.8 kg ball): bore 8 cm, for the
# broadside / stern / cabin ports (centred 0.85 m above the deck); the falconet is the same design scaled to fit the
# forecastle platform and the cabin (layout_G: <= 2.2 m muzzle -> trail); axis 0.80 suits both the platform
# embrasures (0.4..1.1 above the floor) and the cabin's gunports (0.55..1.15).
FALCON = dict(bore=0.080, length=2.65, axis_h=0.85, k_len=1.0, k_r=1.0, wheel_r=0.36)
FALCONET = dict(bore=0.056, length=1.62, axis_h=0.80, k_len=1.62 / 2.65, k_r=0.70, wheel_r=0.30)

def falcon_profile(sp):
    L, kl, kr = sp['length'], sp['k_len'], sp['k_r']
    ty = 0.43 * L
    rb, rt, rr, rc, rm = 0.112 * kr, 0.100 * kr, 0.110 * kr, 0.094 * kr, 0.072 * kr
    def Y(v): return v * kl                                       # fixed details (fillets, button) scale with length
    def R(v): return v * kr
    prof = [
        # conical cascabel button with a fillet, short neck, rounded breech
        (Y(-0.20), 0.0), (Y(-0.20), R(0.026)), (Y(-0.194), R(0.032)), (Y(-0.118), R(0.050)), (Y(-0.112), R(0.054)),
        (Y(-0.104), R(0.054)), (Y(-0.100), R(0.046)), (Y(-0.090), R(0.046)),
        (Y(-0.080), R(0.064)), (Y(-0.058), R(0.086)), (Y(-0.034), R(0.101)), (Y(-0.013), R(0.110)), (0.0, rb + R(0.004)),
        # base ring: flared fillet + step + astragal
        (0.0, rb + R(0.015)), (Y(0.032), rb + R(0.015)), (Y(0.037), rb + R(0.009)), (Y(0.060), rb + R(0.009)),
        (Y(0.065), rb + R(0.004)), (Y(0.076), rb + R(0.004)), (Y(0.080), rb),
        # reinforce to the trunnion ring
        (ty - Y(0.075), rt), (ty - Y(0.070), rr - R(0.006)), (ty - Y(0.050), rr - R(0.006)), (ty - Y(0.046), rr),
        (ty + Y(0.046), rr), (ty + Y(0.050), rr - R(0.006)), (ty + Y(0.070), rr - R(0.006)), (ty + Y(0.075), rc),
        # plain chase, muzzle astragal, slight swell, muzzle band
        (L - Y(0.17), rm), (L - Y(0.165), rm + R(0.008)), (L - Y(0.145), rm + R(0.008)), (L - Y(0.140), rm + R(0.003)),
        (L - Y(0.10), rm + R(0.004)), (L - Y(0.07), rm + R(0.008)), (L - Y(0.066), rm + R(0.017)),
        (L - Y(0.012), rm + R(0.017)), (L - Y(0.006), rm + R(0.012)), (L, rm + R(0.012)),
        (L, sp['bore'] / 2 + R(0.008)), (L - 0.006, sp['bore'] / 2),
    ]
    return prof, ty, dict(rb=rb, rr=rr, cascabel=Y(-0.20))

def wheel_x(name, xc, y, z, r, w, role_wood='wood'):
    """Solid plank wheel (three planks, flats only in the texture) with an iron tyre and a hub boss."""
    parts = [cyl_x(name, xc - w / 2, xc + w / 2, y, z, r - 0.012, role_wood, segs=28)]
    tyre = lathe_y(name + '_tyre', [(-w / 2 - 0.002, r - 0.014), (-w / 2 - 0.002, r), (w / 2 + 0.002, r),
                                     (w / 2 + 0.002, r - 0.014)], 'iron', segs=28)
    tyre.rotation_euler = (0, 0, math.pi / 2)
    tyre.location = (xc, y, z)
    bpy.context.view_layer.update()
    tyre.data.transform(tyre.matrix_world); tyre.matrix_world = Matrix()
    parts.append(tyre)
    s = 1 if xc > 0 else -1
    parts.append(cyl_x(name + '_hub', min(xc, xc + s * (w / 2 + 0.05)), max(xc, xc + s * (w / 2 + 0.05)), y, z,
                       0.075 * r / 0.30, 'wood', segs=16))
    return parts

def build_falcon(sp, tag):
    prof, ty, info = falcon_profile(sp)
    L, ah, kr = sp['length'], sp['axis_h'], sp['k_r']
    ks = sp['axis_h'] / 0.85                                 # carriage timber scale
    parts = [lathe_y(f'{tag}_barrel', prof, 'bronze', at=(0, 0, ah), segs=36)]
    parts.append(lathe_y(f'{tag}_bore', [(L - 0.006, sp['bore'] / 2), (L - 0.4 * sp['k_len'], sp['bore'] / 2),
                                         (L - 0.4 * sp['k_len'], 0.0)], 'dark', at=(0, 0, ah), segs=20))
    tr, tl = 0.042 * kr, 0.075 * kr                         # trunnion radius / length out of the ring
    tz = ah - 0.008 * kr
    # carriage: two cheeks from just ahead of the axle back to a trail on the deck, axletree + two solid wheels,
    # transoms, breech bed + quoin, cap squares, trail ring for the tackle
    ct = 0.09 * ks + 0.01
    xi = info['rr'] + tl - 0.06 * kr; xo = xi + ct
    for s in (-1, 1):                                        # trunnions through the cheek, ends flush with its face
        parts.append(cyl_x(f'{tag}_trunnion', min(s * (info['rr'] - 0.015), s * (xo + 0.004)),
                           max(s * (info['rr'] - 0.015), s * (xo + 0.004)), ty, tz, tr, 'bronze', segs=16))
    wr = sp['wheel_r']; y_axle = ty + 0.04
    y_front = ty + 0.30 * ks
    y_trail = info['cascabel'] - 0.42 * ks                  # trail end on the deck behind the breech
    depth = 0.22 * ks                                        # cheek depth
    seat_r = tr + 0.002
    z_seat = tz                                              # seat centred on the trunnion axis
    outline = [(y_front, wr + 0.02), (y_front, z_seat - 0.06 * ks), (y_front - 0.06 * ks, z_seat),
               (ty + seat_r, z_seat)]
    for k in range(1, 8):
        a = math.pi * k / 8
        outline.append((ty + seat_r * math.cos(a), z_seat - seat_r * math.sin(a)))
    under_base = ah - info['rb'] - 0.015 * kr - 0.003      # bottom of the base ring
    z_step = under_base - 0.05 * ks                          # cheek top under the breech (room for the quoin)
    outline += [(ty - seat_r, z_seat), (ty - 0.12 * ks, z_seat)]
    outline += [(ty - 0.12 * ks - 0.08 * ks * math.sin(math.pi / 2 * k / 5),
                 z_seat - (z_seat - z_step) * (1 - math.cos(math.pi / 2 * k / 5))) for k in range(1, 6)]
    # level under the breech, then the trail drops in a curve to the deck
    # level under the breech, then two curved steps down and a straight run to the trail end (stepped brackets)
    y_drop = -0.02                                           # just behind the base ring (quoin ahead of it)
    outline += [(y_drop, z_step)]
    z_tr = depth * 0.9
    dz = (z_step - z_tr) / 3
    run = max((y_drop - (y_trail + 0.10 * ks) - 2 * dz - 0.06) / 2, 0.03) / ks
    y = y_drop; z = z_step
    for _ in range(2):
        for k in range(1, 5):                                # quarter-round step, radius ~dz
            a = math.pi / 2 * k / 4
            outline.append((y - dz * math.sin(a), z - dz * (1 - math.cos(a))))
        y -= dz; z -= dz
        y -= run * ks
        outline.append((y, z))
    outline += [(y_trail + 0.10 * ks, z_tr)]
    outline += [(y_trail, depth * 0.75), (y_trail, 0.0), (y_trail + 0.25 * ks, 0.0),
                (y_axle - wr * 0.9, wr - 0.06 * ks)]
    for s in (-1, 1):
        x0, x1 = sorted((s * xi, s * xo))
        parts.append(plank_yz(f'{tag}_cheek', x0, x1, outline, 'wood'))
        cap = [(ty + seat_r + 0.05 * ks, z_seat)] + \
              [(ty + (seat_r + 0.002) * math.cos(math.pi * k / 10), z_seat + (seat_r + 0.002) * math.sin(math.pi * k / 10))
               for k in range(11)] + [(ty - seat_r - 0.05 * ks, z_seat)]
        parts.append(strap_yz(f'{tag}_capsquare', x0 - 0.004, x1 + 0.004, cap, 0.0, 0.009, 'iron'))
        parts += wheel_x(f'{tag}_wheel', s * (xo + 0.015 + 0.045 * ks), y_axle, wr, wr, 0.09 * ks)
        parts.append(cyl_x(f'{tag}_linchpin', min(s * (xo + 0.11 * ks), s * (xo + 0.14 * ks)),
                           max(s * (xo + 0.11 * ks), s * (xo + 0.14 * ks)), y_axle, wr, 0.016, 'iron', segs=8))
        # side ring for the run-out tackle, near the axle
        parts.append(cyl_x(f'{tag}_eyebolt', min(s * xo, s * (xo + 0.03)), max(s * xo, s * (xo + 0.03)),
                           ty - 0.30 * ks, z_step - 0.08 * ks, 0.014, 'iron', segs=8))
        parts.append(torus_x(f'{tag}_ring', s * (xo + 0.038), ty - 0.30 * ks, z_step - 0.12 * ks, 0.04 * ks, 0.009, 'iron'))
    # axletree under the cheeks, transoms
    parts.append(box(f'{tag}_axletree', -(xo + 0.02), xo + 0.02, y_axle - 0.065 * ks, y_axle + 0.065 * ks,
                     wr - 0.06 * ks, wr + 0.06 * ks, 'wood'))
    parts.append(cyl_x(f'{tag}_axle_arm', -(xo + 0.13 * ks), xo + 0.13 * ks, y_axle, wr, 0.035 * ks, 'wood', segs=12))
    parts.append(box(f'{tag}_transom_front', -xi, xi, y_front - 0.16 * ks, y_front - 0.02 * ks, wr + 0.06 * ks,
                     z_seat - 0.10 * ks, 'wood'))
    parts.append(box(f'{tag}_transom_trail', -xi, xi, y_trail + 0.02, y_trail + 0.20 * ks, 0.02, depth * 0.7, 'wood'))
    # stool bed between the cheeks under the breech, the quoin (wedge) on it
    yb0, yb1 = y_drop + 0.01, 0.55 * ks
    parts.append(box(f'{tag}_stool_bed', -xi, xi, yb0, yb1, z_step - 0.09 * ks, z_step - 0.01, 'wood'))
    yq0, yq1 = y_drop + 0.03, 0.42 * ks
    q = [(yq0, z_step - 0.01), (yq1, z_step - 0.01), (yq1, z_step + 0.005), (yq0, under_base + 0.002)]
    parts.append(plank_yz(f'{tag}_quoin', -0.075 * ks, 0.075 * ks, q, 'wood'))
    parts.append(box(f'{tag}_quoin_handle', -0.02, 0.02, yq0 - 0.08 * ks, yq0, z_step + 0.005, z_step + 0.03, 'wood'))
    # trail ring
    parts.append(torus_x(f'{tag}_trail_ring', 0.0, y_trail - 0.035, depth * 0.45, 0.04 * ks, 0.009, 'iron'))
    yv = 0.115 * sp['k_len']
    rv = info['rb'] - (info['rb'] - 0.100 * kr) * (yv - 0.08 * sp['k_len']) / (ty - 0.155 * sp['k_len'])
    vent_and_fuse(tag, parts, yv, rv - 0.001, ah, 0.55 + 0.45 * kr, -ty)
    o = join(tag, parts, -ty, 'guns')
    o['muzzle_y'] = L - ty; o['cascabel_y'] = info['cascabel'] - ty; o['axis_h'] = ah
    o['front_y'] = y_front - ty; o['rear_y'] = y_trail - 0.08 - ty; o['half_w'] = xo + 0.15 * ks
    return o

def clear_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)

# ---------------------------------------------------------------- renders
def render_views(objs, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.light = 'STUDIO'
    sc.display.shading.color_type = 'MATERIAL'
    sc.display.shading.show_shadows = False
    sc.display.shading.show_cavity = True
    sc.display.shading.cavity_type = 'BOTH'
    sc.display.shading.show_object_outline = True
    sc.render.film_transparent = False
    sc.world = sc.world or bpy.data.worlds.new('w')
    cam = bpy.data.objects.new('gun_cam', bpy.data.cameras.new('gun_cam')); sc.collection.objects.link(cam)
    sc.camera = cam

    def shot(fname, loc, tgt, lens=50, ortho=None, res=(1600, 900)):
        sc.render.resolution_x, sc.render.resolution_y = res
        cam.location = loc
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        if ortho:
            cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
        else:
            cam.data.type = 'PERSP'; cam.data.lens = lens
        sc.render.filepath = os.path.join(out_dir, fname)
        bpy.ops.render.render(write_still=True)

    for o, pre in objs:
        for other in coll('guns').objects:              # this gun and its fuse only
            other.hide_render = other.name not in (o.name, o.name + '_fuse')
        ah = o.get('axis_h', AXIS_H)
        span = o['muzzle_y'] - min(o['cascabel_y'], o['rear_y'])
        mid = (o['muzzle_y'] + min(o['cascabel_y'], o['rear_y'])) / 2
        sz = span / 4.9
        shot(f'{pre}_side.png', (12.0, mid, ah * 0.6), (0.0, mid, ah * 0.6), ortho=span + 0.3, res=(1800, 640))
        shot(f'{pre}_top.png', (0.0, mid, 12.0), (0.0, mid + 0.0001, 0.0), ortho=span + 0.3, res=(1800, 640))
        shot(f'{pre}_persp.png', (2.6 * sz, 3.4 * sz, 2.0 * sz), (0.0, 0.5 * sz, 0.55 * sz), lens=40)
        shot(f'{pre}_rear.png', (-2.2 * sz, -3.0 * sz, 1.7 * sz), (0.0, 0.2 * sz, 0.55 * sz), lens=45)
        shot(f'{pre}_muzzle.png', (0.9 * sz, o['muzzle_y'] + 0.9 * sz, ah + 0.35 * sz), (0.0, o['muzzle_y'] - 0.1, ah), lens=60)
        shot(f'{pre}_breech.png', (1.4 * sz, -2.4 * sz, ah + 0.9 * sz), (0.0, -0.4 * sz, ah - 0.15), lens=50)
    # group: all guns side by side, culverin in front
    for o in coll('guns').objects: o.hide_render = False
    xs = 0.0
    for o, _ in objs:
        o.location = (xs, 0, 0)
        f = bpy.data.objects.get(o.name + '_fuse')
        if f: f.location = o.location
        xs -= 1.3
    shot('guns_group.png', (3.6, 4.6, 2.6), (-1.3, 0.0, 0.5), lens=32)
    for o in coll('guns').objects: o.location = (0, 0, 0)

if __name__ == '__main__':
    clear_scene()
    cv = build_culverin()
    print('culverin: muzzle %.2f, cascabel %.2f, bed %.2f..%.2f, half width %.2f (from the trunnions); %d verts'
          % (cv['muzzle_y'], cv['cascabel_y'], cv['rear_y'], cv['front_y'], cv['half_w'], len(cv.data.vertices)))
    fa = build_falcon(FALCON, 'galleass_falcon')
    ft = build_falcon(FALCONET, 'galleass_falconet')
    for o in (fa, ft):
        print('%s: muzzle %.2f, cascabel %.2f, carriage %.2f..%.2f, half width %.2f; %d verts'
              % (o.name, o['muzzle_y'], o['cascabel_y'], o['rear_y'], o['front_y'], o['half_w'], len(o.data.vertices)))
    if RENDER_DIR:
        render_views([(cv, 'cv'), (fa, 'fa'), (ft, 'ft')], RENDER_DIR)
    if OUT_BLEND:
        import json                                   # gun dimensions for gun_layout.py (preview + prefab)
        json.dump({o.name: {k: float(o[k]) for k in ('muzzle_y', 'cascabel_y', 'front_y', 'rear_y', 'half_w')}
                   | {'axis_h': float(o.get('axis_h', AXIS_H))} for o in (cv, fa, ft)},
                  open(os.path.splitext(OUT_BLEND)[0] + '.json', 'w'), indent=1)
        bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    print('guns done')
