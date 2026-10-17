"""Galleass guns, 16th-century Venetian (user 2026-10-13; references: Alberghetti pieces, Gasparoni 1779 plates,
'Colubrine di bronzo da 30'). Built parametrically; for now the culverin (colubrina da 14) on its wheelless sledge bed
(letto) for the forecastle's ground floor. The falcon / falconet on two-wheel carriages follow.

    blender -b --factory-startup --python cannon_model.py -- <out.blend> <render dir>

Local frame of every gun: barrel axis along +Y (muzzle forward), Z up, origin on the deck under the trunnions'
centre; the axis is AXIS_H above the deck (the round ports are centred 0.8 m above the ground floor).
Profiles are (y, r) with y from the rear face of the base ring forward (cascabel at negative y).
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT_BLEND = argv[0] if argv else None
RENDER_DIR = argv[1] if len(argv) > 1 else None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gun_profiles import *                           # AXIS_H, CV, FALCON(ET), profiles, reliefs
import rope_geom as rg
import gun_elevation as gel

# ---------------------------------------------------------------- Blender helpers
ROLE_COL = {'fuse': (0.30, 0.22, 0.12, 1), 'bronze': (0.62, 0.45, 0.18, 1), 'bronze_trim': (0.62, 0.45, 0.18, 1), 'wood': (0.36, 0.24, 0.14, 1), 'iron': (0.16, 0.16, 0.17, 1), 'rope': (0.55, 0.45, 0.30, 1),
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

def lathe_y(name, prof, role, at=(0, 0, 0), segs=32, mod=None, cap_end=False, twist=None, inside=False):
    """Solid of revolution about the Y axis (prof: (y, r)); mod(y, angle, r) -> r adds flutes and reliefs;
    twist(y) -> angle turns each ring so the mesh's edges follow a spiral relief (clean shading).
    inside: a bore seen from the muzzle - walls face the axis, the bottom faces +y (user 2026-10-13: open, outward
    facing bores were culled, the sky showed through the barrel)."""
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
    if inside:
        for f in bm.faces:
            c = f.calc_center_median(); f.normal_update()
            radial = Vector((c.x - at[0], 0.0, c.z - at[2]))
            want = -radial if radial.length > 1e-4 and abs(f.normal.y) < 0.7 else Vector((0, 1, 0))
            if f.normal.dot(want) < 0:
                f.normal_flip()
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
    parts.append(obj_from_bm(bm, f'{tag}_vent_boss', 'bronze_trim', sharp=40))
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

# Moving parts (gunnery add-on, 2026-10-15): export_guns.py splits every gun by the face attribute 'part' into the
# carriage (0), the barrel on its trunnions (1: barrel, bore, trunnions, vent, breeching collar), the sliding quoin (2)
# and the lashing (3: cascabel lashing, cast off in action).
PART_GROUPS = {'barrel': 1, 'bore': 1, 'trunnion': 1, 'vent_boss': 1, 'vent': 1, 'breeching_collar': 1,
               'quoin': 2, 'quoin_handle': 2, 'lashing': 3}

def part_group(tag, name):
    return PART_GROUPS.get(name.split('.')[0][len(tag) + 1:], 0)

def join(tag, parts, shift_y, collection):
    """One object per gun (multi-material); parts moved by shift_y so the trunnions sit at y 0. Faces carry the
    integer attribute 'part' (PART_GROUPS)."""
    bm = bmesh.new(); mats = list(MATS.values())
    lay = bm.faces.layers.int.new('part')
    for p in parts:
        me = p.data.copy()
        idx = mats.index(p.data.materials[0])
        for poly in me.polygons: poly.material_index = idx
        n0 = len(bm.faces)
        bm.from_mesh(me); bm.faces.ensure_lookup_table()
        grp = part_group(tag, p.name)
        for f in bm.faces[n0:]: f[lay] = grp
        bpy.data.meshes.remove(me); bpy.data.objects.remove(p)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, shift_y, 0))
    me = bpy.data.meshes.new(tag); bm.to_mesh(me); bm.free()
    for m in mats: me.materials.append(m)
    o = bpy.data.objects.new(tag, me); coll(collection).objects.link(o)
    return o

def prof_r(prof, y):
    """Largest profile radius at y (profiles have vertical steps)."""
    best = 0.0
    for (y0, r0), (y1, r1) in zip(prof, prof[1:]):
        if abs(y1 - y0) < 1e-9:
            if abs(y - y0) < 1e-9: best = max(best, r0, r1)
        elif min(y0, y1) <= y <= max(y0, y1):
            best = max(best, r0 + (r1 - r0) * (y - y0) / (y1 - y0))
    return best

def rope_part(name, build):
    """One rope object from a bmesh builder (rope_geom calls); rope UVs are kept by export_guns.py."""
    bm = bmesh.new(); build(bm)
    return obj_from_bm(bm, name, 'rope', sharp=80)

def rig_point(p, ty):
    """Profile coordinates -> the exported gun frame (trunnions at y 0)."""
    return [float(p[0]), float(p[1] - ty), float(p[2])]

def quoin_parts(tag, qn, half_w, handle_k=1.0):
    """Wedge (thick end at qn.yt, to the rear) + a short handle sticking out of the thick end."""
    zb = qn.zb
    w = [(qn.yt, zb), (qn.yt + qn.L, zb), (qn.yt + qn.L, zb + qn.hthin), (qn.yt, zb + qn.ht)]
    hz = zb + qn.ht * 0.55
    return [plank_yz(f'{tag}_quoin', -half_w, half_w, w, 'wood'),
            box(f'{tag}_quoin_handle', -0.025 * handle_k, 0.025 * handle_k, qn.yt - 0.10 * handle_k, qn.yt + 0.01,
                hz - 0.02 * handle_k, hz + 0.02 * handle_k, 'wood')]

def elev_info(qn):
    """For the add-on (galleass_guns.json 'elev'): trunnion pivot height in the gun frame (y 0), elevation limits and
    the quoin's slide (m, + = pulled back, i.e. towards -y of the gun) per elevation."""
    return {'pivot_z': qn.tz, 'min_deg': qn.emin, 'max_deg': qn.emax, 'quoin': qn.table()}

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
    parts.append(lathe_y(f'{tag}_bore', [(L - 0.008, D / 2), (L - 0.6, D / 2), (L - 0.6, 0.0)], 'dark', inside=True,
                         at=(0, 0, AXIS_H), segs=96))   # = barrel rings (no slivers at the muzzle)
    r_ring = CV['r_ring']
    tz = AXIS_H + CV['trunnion_dz']

    # sledge bed (letto): two cheeks on two runners, front/rear transoms, breech bed + quoin, iron work.
    # Galley bow guns slid back on greased rails (Eliav 2013); our recoil slide moves this whole gun.
    gap = r_ring + CV['trunnion_len'] - 0.115           # inner face of a cheek (trunnion goes 0.115 into it)
    ct = 0.15                                           # cheek thickness
    xi, xo = gap, gap + ct
    for s in (-1, 1):                                   # trunnions run through the cheek, ends flush with its face
        x_in, x_out = s * (r_ring - 0.02), s * (xo + 0.004)
        parts.append(cyl_x(f'{tag}_trunnion', min(x_in, x_out), max(x_in, x_out), ty, tz, CV['trunnion_r'], 'bronze_trim', segs=24))
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
        # cap squares are a little narrower than the cheek; the path runs front -> rear, so a negative thickness
        # builds the strap outward (over the trunnion, on top of the cheek) instead of sunk into them
        parts.append(strap_yz(f'{tag}_capsquare', min(s * xi, s * xo) + 0.008, max(s * xi, s * xo) - 0.008,
                              cap, 0.0, -0.012, 'iron'))
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
    # the quoin: a wedge on the bed, thick end to the rear, touching the barrel at zero elevation (gun_elevation.py
    # solves its slide for every elevation; the add-on slides it)
    qn = gel.Quoin(tag, prof, AXIS_H, ty, tz, gel.QUOIN[tag]['zb'])
    parts.append(box(f'{tag}_stool', -0.17, 0.17, y_rear + 0.04, qn.yt + qn.L + 0.25, bed_top, qn.zb, 'wood'))
    parts += quoin_parts(tag, qn, 0.15)

    # cascabel lashing (user 2026-10-13: rigging that holds the gun in its bed): a seized collar round the cascabel
    # neck, two turns down each side to ringbolts on the bed behind the quoin
    yn, rl = -0.150, 0.011
    rc = prof_r(prof, yn) + rl * 0.9
    ring_R, y_rb = 0.032, -0.235
    def lashing(bm):
        rg.ring(bm, (0, yn, AXIS_H), (0, 1, 0), rc, rl, segs=14, tube=6)
        for s in (-1, 1):
            xb = s * 0.13
            top = Vector((xb, y_rb, bed_top + 0.022 + 2 * ring_R))
            for dy in (-0.011, 0.011):
                p0 = Vector((s * rc * 0.75, yn + dy, AXIS_H - rc * 0.66))
                rg.rope(bm, rg.catmull([p0, (p0 + top) / 2 + Vector((s * 0.015, 0, 0)), top + Vector((0, dy, 0))], 0.05),
                        rl, segs=6)
    parts.append(rope_part(f'{tag}_lashing', lashing))
    for s in (-1, 1):
        parts.append(lathe_y(f'{tag}_bed_eyebolt', [(-0.012, 0.0), (-0.012, 0.012), (0.03, 0.012), (0.03, 0.0)],
                             'iron', at=(0, 0, 0), segs=8))
        eb = parts[-1]; eb.rotation_euler = (math.pi / 2, 0, 0); eb.location = (s * 0.13, y_rb, bed_top)
        bpy.context.view_layer.update(); eb.data.transform(eb.matrix_world); eb.matrix_world = Matrix()
        parts.append(torus_x(f'{tag}_bed_ring', s * 0.13, y_rb, bed_top + 0.022 + ring_R, ring_R, 0.009, 'iron'))
    # breeching: the sledge recoils as a whole, so the breeching takes the front side rings (gun_rigging.py)
    rig = {'rope_r': 0.019, 'breech': {'p': rig_point((xo + 0.045, y_front - 0.22, AXIS_H - 0.47), ty), 'ring_r': 0.05},
           'tackle': None}

    vent_and_fuse(tag, parts, 0.13, CV['r_breech'] - 0.0012, AXIS_H, 1.0, -ty)
    o = join(tag, parts, -ty, 'guns')
    o['rig'] = json.dumps(rig)
    o['elev'] = json.dumps(elev_info(qn))
    o['muzzle_y'] = L - ty; o['cascabel_y'] = -0.28 - ty
    o['front_y'] = y_front + 0.09 - ty; o['rear_y'] = y_rear - 0.06 - ty; o['half_w'] = xo + 0.1
    return o

# ---------------------------------------------------------------- falcon / falconet carriage (profiles in gun_profiles.py)
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
                                         (L - 0.4 * sp['k_len'], 0.0)], 'dark', at=(0, 0, ah), segs=36, inside=True))   # = barrel rings
    tr, tl = 0.042 * kr, 0.075 * kr                         # trunnion radius / length out of the ring
    tz = ah - 0.008 * kr
    # carriage: two cheeks from just ahead of the axle back to a trail on the deck, axletree + two solid wheels,
    # transoms, breech bed + quoin, cap squares, trail ring for the tackle
    ct = 0.09 * ks + 0.01
    xi = info['rr'] + tl - 0.06 * kr; xo = xi + ct
    for s in (-1, 1):                                        # trunnions through the cheek, ends flush with its face
        parts.append(cyl_x(f'{tag}_trunnion', min(s * (info['rr'] - 0.015), s * (xo + 0.004)),
                           max(s * (info['rr'] - 0.015), s * (xo + 0.004)), ty, tz, tr, 'bronze_trim', segs=16))
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
    qn = gel.Quoin(tag, prof, ah, ty, tz, under_base - gel.QUOIN[tag]['zb_below'])
    y_drop = qn.yt                                          # level under the quoin's thick end, then the steps
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
        parts.append(strap_yz(f'{tag}_capsquare', x0 + 0.006, x1 - 0.006, cap, 0.0, -0.009, 'iron'))   # see culverin
        parts += wheel_x(f'{tag}_wheel', s * (xo + 0.015 + 0.045 * ks), y_axle, wr, wr, 0.09 * ks)
        parts.append(cyl_x(f'{tag}_linchpin', min(s * (xo + 0.11 * ks), s * (xo + 0.14 * ks)),
                           max(s * (xo + 0.11 * ks), s * (xo + 0.14 * ks)), y_axle, wr, 0.016, 'iron', segs=8))
        # side ring for the run-out tackle: high on the cheek just behind the trunnion seat, above the wheel, so the
        # tackle (gun_rigging.py) runs forward over the tyre (user 2026-10-13: the old low ring clipped the wheel)
        z_eye = z_seat - 0.035 * ks
        z_ring = z_eye - 0.04 * ks
        y_eye = ty - seat_r - 0.06 * ks
        while True:                                           # ring bottom 2 cm above the tyre at that y
            dy = abs(y_eye - y_axle)
            top = wr + math.sqrt(wr * wr - dy * dy) if dy < wr else 0.0
            if z_ring - 0.04 * ks - 0.009 >= top + 0.02 or y_eye < ty - 0.12 * ks:
                break
            y_eye -= 0.01
        parts.append(cyl_x(f'{tag}_eyebolt', min(s * xo, s * (xo + 0.03)), max(s * xo, s * (xo + 0.03)),
                           y_eye, z_eye, 0.014, 'iron', segs=8))
        parts.append(torus_x(f'{tag}_ring', s * (xo + 0.038), y_eye, z_ring, 0.04 * ks, 0.009, 'iron'))
    # axletree under the cheeks, transoms
    parts.append(box(f'{tag}_axletree', -(xo + 0.02), xo + 0.02, y_axle - 0.065 * ks, y_axle + 0.065 * ks,
                     wr - 0.06 * ks, wr + 0.06 * ks, 'wood'))
    parts.append(cyl_x(f'{tag}_axle_arm', -(xo + 0.13 * ks), xo + 0.13 * ks, y_axle, wr, 0.035 * ks, 'wood', segs=12))
    # front transom: its top stays under the chase at the lowest elevation (falcons -10, falconets -15 deg since
    # 2026-10-16; it used to stop the barrel at -3.5 / -8), 1.5 cm clear
    ty0, ty1 = y_front - 0.16 * ks, y_front - 0.02 * ks
    chase = min(z for y, z in gel.underside(prof, ah, ty, tz, math.radians(gel.QUOIN[tag]['emin'])) if ty0 <= y <= ty1)
    t_top = min(z_seat - 0.10 * ks, chase - 0.015)
    assert t_top > wr + 0.06 * ks + 0.04, '%s: no room for the front transom under the depressed chase' % tag
    print('CARRIAGE %s front transom top %.3f (was %.3f), chase at %.1f deg %.3f' % (tag, t_top, z_seat - 0.10 * ks,
          gel.QUOIN[tag]['emin'], chase))
    parts.append(box(f'{tag}_transom_front', -xi, xi, ty0, ty1, wr + 0.06 * ks, t_top, 'wood'))
    parts.append(box(f'{tag}_transom_trail', -xi, xi, y_trail + 0.02, y_trail + 0.20 * ks, 0.02, depth * 0.7, 'wood'))
    # stool bed between the cheeks under the breech, the quoin (wedge) on it
    # the wedge and its bed leave a 4.5 cm lane beside each cheek for the cascabel lashing (2026-10-16: the taller,
    # longer quoins for -10 / -15 deg met the old lashing)
    q_hw = min(0.075 * ks, xi - 0.045)
    yb0, yb1 = y_drop + 0.01, 0.55 * ks
    parts.append(box(f'{tag}_stool_bed', -(q_hw + 0.01), q_hw + 0.01, yb0, yb1, qn.zb - 0.08 * ks, qn.zb, 'wood'))
    parts += quoin_parts(tag, qn, q_hw, handle_k=0.8 * ks)
    # trail ring
    parts.append(torus_x(f'{tag}_trail_ring', 0.0, y_trail - 0.035, depth * 0.45, 0.04 * ks, 0.009, 'iron'))
    yv = 0.115 * sp['k_len']
    rv = info['rb'] - (info['rb'] - 0.100 * kr) * (yv - 0.08 * sp['k_len']) / (ty - 0.155 * sp['k_len'])
    # breeching collar round the cascabel neck; both legs hug the breech and leave beside the base ring toward the
    # ringbolts at the port (gun_rigging.py); a lashing (two turns a side) ties the cascabel down to ringbolts on the
    # cheeks' inner faces behind the stool bed (user 2026-10-13: rigging that holds the gun in its carriage)
    kl = sp['k_len']
    yn, rb_r, rl = -0.097 * kl, 0.016 * kr, 0.010 * kr
    rc = prof_r(prof, yn) + rb_r * 0.9
    y_out = 0.05 * kl
    x_out = info['rb'] + 0.015 * kr + rb_r + 0.006
    lash_R = 0.028 * ks
    y_lr = yn                                               # rings on the cheeks right beside the cascabel neck,
    z_le = z_step - 0.04 * ks                               # in the lane between the cheek and the quoin
    def collar(bm):
        rg.ring(bm, (0, yn, ah), (0, 1, 0), rc, rb_r, segs=14, tube=6)
        for s in (-1, 1):
            pts = [Vector((s * rc, yn, ah))]
            for k in range(1, 7):
                y = yn + (y_out - yn) * k / 6
                pts.append(Vector((s * max(prof_r(prof, y) + rb_r + 0.004, rc), y, ah)))
            pts[-1] = Vector((s * x_out, y_out, ah))
            rg.rope(bm, rg.catmull(pts, 0.03), rb_r, segs=6)
    x_lane = (q_hw + xi) / 2                                 # middle of the lane
    def lashing(bm):
        # from the side of the neck at bore height straight out over the quoin (its top stays under the barrel), then
        # down the lane to the ring: clear of the wedge wherever it slides
        for s in (-1, 1):
            for dy in (-0.010 * ks, 0.010 * ks):
                p0 = Vector((s * rc, yn + dy, ah))
                p1 = Vector((s * x_lane, yn + dy, ah - 0.01))
                p2 = Vector((s * x_lane, y_lr + dy, z_le - 2 * lash_R))
                rg.rope(bm, rg.catmull([p0, p1, (p1 + p2) / 2, p2], 0.03), rl, segs=6)
    parts.append(rope_part(f'{tag}_breeching_collar', collar))
    parts.append(rope_part(f'{tag}_lashing', lashing))
    for s in (-1, 1):
        parts.append(cyl_x(f'{tag}_lash_eyebolt', min(s * xi, s * x_lane), max(s * xi, s * x_lane),
                           y_lr, z_le, 0.011, 'iron', segs=8))
        parts.append(torus_x(f'{tag}_lash_ring', s * x_lane, y_lr, z_le - lash_R, lash_R, 0.007, 'iron'))
    rig = {'rope_r': rb_r, 'breech': {'p': rig_point((x_out, y_out, ah), ty), 'ring_r': 0.0},
           'tackle': {'p': rig_point((xo + 0.038, y_eye, z_ring), ty), 'ring_r': 0.04 * ks}}

    vent_and_fuse(tag, parts, yv, rv - 0.001, ah, 0.55 + 0.45 * kr, -ty)
    o = join(tag, parts, -ty, 'guns')
    o['rig'] = json.dumps(rig)
    o['elev'] = json.dumps(elev_info(qn))
    o['muzzle_y'] = L - ty; o['cascabel_y'] = info['cascabel'] - ty; o['axis_h'] = ah
    o['front_y'] = y_front - ty; o['rear_y'] = y_trail - 0.08 - ty; o['half_w'] = xo + 0.15 * ks
    return o

# ---------------------------------------------------------------- petriera da mascolo (swivel gun on the rails)
def cyl_z(name, x, y, z0, z1, r, role, segs=16):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r, depth=z1 - z0)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(x, y, (z0 + z1) / 2))
    return obj_from_bm(bm, name, role)

def prism_y(name, outline, y0, y1, role):
    """An (x, z) outline (no holes) extruded between y0 and y1."""
    bm = bmesh.new()
    a = [bm.verts.new((x, y0, z)) for x, z in outline]
    b = [bm.verts.new((x, y1, z)) for x, z in outline]
    bm.faces.new(a); bm.faces.new(b[::-1])
    n = len(outline)
    for i in range(n):
        bm.faces.new((a[i], b[i], b[(i + 1) % n], a[(i + 1) % n]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, name, role, sharp=35)

def stave_seams(n, depth, width=0.10):
    """Shallow grooves between n staves (wrought-iron barrels were forged from staves under the hoops)."""
    def mod(y, a, r):
        u = a / (2 * math.pi) * n; u -= math.floor(u)
        d = abs(u - 0.5) * 2                                # 1 on a seam, 0 mid-stave
        return r - depth * smooth01((d - (1 - width)) / width)
    return mod

# Moving parts beyond PART_GROUPS: 4 yoke (turns about the pin = traverse), 5 chamber (the removable mascolo),
# 6 wedge (knocked out to free the chamber). The barrel group (1) carries the cradle, end plate and tail.
PART_GROUPS.update({'cradle': 1, 'end_plate': 1, 'tail': 1, 'knob': 1, 'band': 1,
                    'yoke': 4, 'yoke_eye': 4, 'pin': 4, 'washer': 4,
                    'chamber': 5, 'chamber_hoop': 5, 'chamber_handle': 5, 'chamber_vent': 5, 'chamber_vent_boss': 5,
                    'wedge': 6})

def build_petriera(sp=PETRIERA, tag='galleass_petriera'):
    ah, L, yt = sp['axis_h'], sp['barrel_len'], sp['trunnion_y']
    rt, rm, rb, hp = sp['r_tube'], sp['r_muzzle'], sp['r_band'], sp['hoop']
    def tube_r(y): return rt + (rm - rt) * y / L
    # barrel (profile y from its rear face = the front of the chamber seat): rear band carrying the trunnions, the
    # hooped tube, a broad muzzle band
    prof = [(0.0, 0.0), (0.0, rb - 0.004), (0.004, rb), (0.100, rb), (0.104, rb - 0.004), (0.106, tube_r(0.106) + hp), (0.122, tube_r(0.122) + hp), (0.125, tube_r(0.125))]
    for yh in sp['hoops']:
        r = tube_r(yh)
        prof += [(yh - 0.016, r), (yh - 0.013, r + hp), (yh + 0.013, r + hp), (yh + 0.016, r)]
    prof += [(L - 0.065, tube_r(L - 0.065)), (L - 0.058, rm + 0.010), (L - 0.004, rm + 0.010), (L, rm + 0.006),
             (L, sp['bore'] / 2 + 0.006), (L - 0.004, sp['bore'] / 2)]
    seams = stave_seams(10, 0.0018)
    hoop_ys = [(0.0, 0.125)] + [(yh - 0.016, yh + 0.016) for yh in sp['hoops']] + [(L - 0.065, L)]
    def mod(y, a, r):                                         # seams on the bare tube only, not under the hoops
        return r if any(y0 - 1e-6 <= y <= y1 + 1e-6 for y0, y1 in hoop_ys) else seams(y, a, r)
    parts = [lathe_y(f'{tag}_barrel', resample(prof[:-2], 0.04) + prof[-2:], 'iron', at=(0, 0, ah), segs=30, mod=mod)]
    parts.append(lathe_y(f'{tag}_bore', [(L - 0.004, sp['bore'] / 2), (L - 0.35, sp['bore'] / 2), (L - 0.35, 0.0)],
                         'dark', at=(0, 0, ah), segs=30, inside=True))
    tr = 0.017
    for s in (-1, 1):
        parts.append(cyl_x(f'{tag}_trunnion', min(s * (rb - 0.01), s * 0.108), max(s * (rb - 0.01), s * 0.108),
                           yt, ah, tr, 'iron', segs=12))
    # chamber seat (cradle): open trough behind the barrel, flat sides up to just above the axis; the wedge goes
    # across through slots at its rear, against the iron end plate; the tail (coda) leaves the plate cranked down
    cl, co, ci = sp['cradle_len'], sp['cradle_r'], sp['cradle_in']
    top = 0.016
    outer = [(-co, top)] + [(-co * math.cos(math.pi * k / 12), -co * math.sin(math.pi * k / 12)) for k in range(13)] + [(co, top)]
    inner = [(ci, top)] + [(ci * math.cos(math.pi * k / 12), -ci * math.sin(math.pi * k / 12)) for k in range(13)] + [(-ci, top)]
    outline = [(x, ah + z) for x, z in outer + inner]
    parts.append(prism_y(f'{tag}_cradle', outline, -cl, 0.0, 'iron'))
    y_w0, y_w1 = -cl + 0.004, -cl + 0.030                      # wedge slot (wedge = part 6)
    y_e = -cl - 0.032
    plate = [(x, ah + z) for x, z in [(-co, top)] + [(-co * math.cos(math.pi * k / 12), -co * math.sin(math.pi * k / 12))
                                                       for k in range(13)] + [(co, top)]]
    parts.append(prism_y(f'{tag}_end_plate', plate, y_e, -cl, 'iron'))
    for s in (-1, 1):                                          # raised lips round the slots (the plate's ears)
        parts.append(box(f'{tag}_band', *sorted((s * co, s * (co + 0.006))), y_w0 - 0.012, y_w1 + 0.012,
                         ah - 0.030, ah + top, 'iron'))
    tail = [(0, y_e + 0.01, ah), (0, y_e - 0.10, ah - 0.004), (0, y_e - 0.25, ah - 0.020),
            (0, y_e - 0.38, ah - 0.045), (0, y_e - sp['tail_len'], ah - sp['tail_drop'])]
    parts.append(tube(f'{tag}_tail', [Vector(p) for p in rg.catmull([Vector(p) for p in tail], 0.03)], 0.016, 'iron', segs=10))
    ye_t, ze_t = tail[-1][1], tail[-1][2]
    parts.append(lathe_y(f'{tag}_knob', [(-0.030, 0.0), (-0.028, 0.012), (-0.020, 0.022), (-0.008, 0.026),
                                          (0.004, 0.024), (0.012, 0.018), (0.016, 0.0)], 'iron', at=(0, ye_t, ze_t), segs=14))
    # the chamber (mascolo): stout iron mug with a spigot into the barrel, two hoops, a handle on top, the vent at the
    # rear; separate part, so the add-on swaps it (and spare chambers use the same mesh)
    cr, cln = sp['chamber_r'], sp['chamber_len']
    yc0, yc1 = y_w1 + 0.002, y_w1 + 0.002 + cln               # rear face against the wedge, spigot into the barrel
    cprof = [(yc0, 0.0), (yc0, cr - 0.010), (yc0 + 0.008, cr - 0.002), (yc0 + 0.012, cr), (yc1 - 0.035, cr),
             (yc1 - 0.030, cr - 0.010), (yc1 - 0.012, 0.034), (yc1, 0.032), (yc1 + 0.03, 0.030), (yc1 + 0.03, 0.0)]
    parts.append(lathe_y(f'{tag}_chamber', cprof, 'iron', at=(0, 0, ah), segs=24))
    for yh in (yc0 + 0.030, yc1 - 0.050):
        parts.append(lathe_y(f'{tag}_chamber_hoop', [(yh - 0.012, cr - 0.001), (yh - 0.010, cr + 0.004),
                                                     (yh + 0.010, cr + 0.004), (yh + 0.012, cr - 0.001)], 'iron', at=(0, 0, ah), segs=24))
    hy0, hy1 = yc0 + 0.075, yc1 - 0.080
    handle = [Vector((0, hy0, ah + cr - 0.004)), Vector((0, hy0 + 0.008, ah + cr + 0.040)),
              Vector((0, (hy0 + hy1) / 2, ah + cr + 0.058)), Vector((0, hy1 - 0.008, ah + cr + 0.040)),
              Vector((0, hy1, ah + cr - 0.004))]
    parts.append(tube(f'{tag}_chamber_handle', rg.catmull(handle, 0.012), 0.008, 'iron', segs=8))
    yv = yc0 + 0.035
    f = vent_and_fuse(tag, parts, yv, cr + 0.003, ah, 0.55, -yt)
    for p in parts:                                            # the vent belongs to the chamber
        if p.name.startswith(f'{tag}_vent'):
            p.name = p.name.replace(f'{tag}_vent', f'{tag}_chamber_vent')
            if p.data.materials[0] == MATS['bronze_trim']: p.data.materials[0] = MATS['iron']
    # the wedge: tapered iron key across the slot, thin end to port, head on the thick end
    def wedge(bm):
        x0, x1, zc = -0.098, 0.112, ah - 0.006
        h0, h1 = 0.024, 0.040
        t0, t1 = y_w0 + 0.002, y_w1 - 0.002
        vs = [bm.verts.new(c) for c in ((x0, t0, zc - h0 / 2), (x0, t1, zc - h0 / 2), (x0, t1, zc + h0 / 2), (x0, t0, zc + h0 / 2),
                                         (x1, t0, zc - h1 / 2), (x1, t1, zc - h1 / 2), (x1, t1, zc + h1 / 2), (x1, t0, zc + h1 / 2))]
        for q in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 4, 7, 3)):
            bm.faces.new([vs[i] for i in q])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm = bmesh.new(); wedge(bm)
    parts.append(obj_from_bm(bm, f'{tag}_wedge', 'iron', sharp=30))
    # swivel yoke (forcella): eyes round the trunnions, a fork under the barrel, the pin down into the socket
    xa = 0.108 + 0.004
    z_top = ah
    fork = [Vector((-xa, yt, z_top - 0.024))]
    for k in range(13):
        t = math.pi * k / 12
        fork.append(Vector((-xa * math.cos(t), yt, ah - 0.060 - 0.034 * math.sin(t))))
    fork.append(Vector((xa, yt, z_top - 0.024)))
    parts.append(tube(f'{tag}_yoke', rg.catmull(fork, 0.012), 0.012, 'iron', segs=8))
    for s in (-1, 1):
        parts.append(torus_x(f'{tag}_yoke_eye', s * xa, yt, ah, 0.026, 0.009, 'iron', segs=14, tube=6))
    z_fork = ah - 0.094 - 0.012                                 # underside of the fork
    parts.append(cyl_z(f'{tag}_pin', 0.0, yt, 0.02, z_fork + 0.01, 0.017, 'iron', segs=12))
    parts.append(cyl_z(f'{tag}_washer', 0.0, yt, 0.100, 0.110, 0.030, 'iron', segs=16))
    assert z_fork > 0.110, 'petriera: fork below the washer'
    # mount (fixed): oak block on the rail top, iron socket plate + collar, four bolt heads
    parts.append(box(f'{tag}_block', -0.09, 0.09, yt - 0.09, yt + 0.09, 0.0, 0.082, 'wood'))
    parts.append(box(f'{tag}_socket_plate', -0.065, 0.065, yt - 0.065, yt + 0.065, 0.082, 0.090, 'iron'))
    parts.append(cyl_z(f'{tag}_socket', 0.0, yt, 0.088, 0.100, 0.032, 'iron', segs=16))
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(cyl_z(f'{tag}_bolt', sx * 0.048, yt + sy * 0.048, 0.088, 0.096, 0.009, 'iron', segs=8))
    # chamber frame for the add-on (spare chambers + swap): centre of the chamber body on the axis
    chamber_c = (yc0 + yc1) / 2 - yt
    wedge_c = (y_w0 + y_w1) / 2 - yt
    o = join(tag, parts, -yt, 'guns')
    elev = {'pivot_z': ah, 'min_deg': -30.0, 'max_deg': 20.0, 'quoin': []}
    o['rig'] = json.dumps({}); o['elev'] = json.dumps(elev)
    o['muzzle_y'] = L - yt; o['cascabel_y'] = ye_t - 0.03 - yt; o['axis_h'] = ah
    o['front_y'] = 0.09; o['rear_y'] = ye_t - 0.03 - yt; o['half_w'] = 0.14
    o['chamber_y'] = chamber_c; o['wedge_y'] = wedge_c
    return o

def build_petriera_step(tag='galleass_petriera_step', h=0.30, wall=0.05, depth=1.20, tread=0.30, half_len=0.75):
    """Gunner's step under a waist swivel (user 2026-10-17: the rail top is 1.5 m above the gun deck): two treads
    against the bulwark's inner face. Frame = the swivel's, dropped to the deck: origin on the deck under the pin, +y
    outboard; the bulwark's inner face is 'wall' inboard of the pin."""
    parts = []
    y_wall, y_up, y_low = -wall, -wall - depth, -wall - depth - tread
    nose = 0.025
    parts.append(box(f'{tag}_frame', -half_len + 0.03, half_len - 0.03, y_up + 0.03, y_wall, 0.0, h - 0.035, 'wood'))
    parts.append(box(f'{tag}_frame_low', -half_len + 0.03, half_len - 0.03, y_low + 0.03, y_up + 0.03, 0.0, h / 2 - 0.035, 'wood'))
    n = 5                                                    # top boards, small gaps, nosing over the riser
    for top, y0, y1 in ((h, y_up - nose, y_wall), (h / 2, y_low - nose, y_up)):
        w = (y1 - y0) / n
        for k in range(n):
            parts.append(box(f'{tag}_board', -half_len, half_len, y0 + k * w + 0.004, y0 + (k + 1) * w - 0.004, top - 0.035, top, 'wood'))
    for x in (-half_len + 0.015, half_len - 0.015):          # end cleats
        parts.append(box(f'{tag}_cleat', x - 0.015, x + 0.015, y_low, y_wall, 0.0, 0.06, 'wood'))
    o = join(tag, parts, 0.0, 'guns')
    o['muzzle_y'] = 0.0; o['cascabel_y'] = y_low; o['axis_h'] = h; o['front_y'] = 0.0; o['rear_y'] = y_low
    o['half_w'] = half_len; o['rig'] = '{}'; o['elev'] = '{}'
    return o

def build_petriera_stand(tag='galleass_petriera_stand', h=None):
    """Timber stand for a poop swivel (user 2026-10-17: the balustrade is too frail): a square oak post from a broad
    foot on the deck up to the swivel's mount block (its cap), two iron bands, the foot spiked to the deck. Frame = the
    swivel's: origin on the post top under the pin, +y outboard; the deck is h below."""
    import gun_layout
    h = h or gun_layout.STAND_H
    parts = []
    # set into the balustrade line (user 2026-10-17): the foot stays on the deck - 7 cm outboard of the rail line (the
    # deck's edge is 14 cm out), the rest inboard
    pw, fw, fh = 0.075, 0.17, 0.10                           # post half width, foot half width (along the rail), height
    fo, fi = 0.07, 0.14                                      # foot outboard / inboard of the post's centre
    z0 = -h
    parts.append(box(f'{tag}_post', -pw, pw, -pw, pw, z0 + fh - 0.01, 0.0, 'wood'))
    foot = [(-fi, z0), (fo, z0), (fo, z0 + fh - 0.02), (fo - 0.02, z0 + fh), (-fi + 0.04, z0 + fh), (-fi, z0 + fh - 0.04)]
    parts.append(plank_yz(f'{tag}_foot', -fw, fw, foot, 'wood'))
    for zb in (z0 + fh + 0.10, -0.16):                        # iron bands round the post
        parts.append(box(f'{tag}_band', -pw - 0.006, pw + 0.006, -pw - 0.006, pw + 0.006, zb - 0.02, zb + 0.02, 'iron'))
    for sx in (-1, 1):                                       # spikes / bolt heads on the foot
        for sy in (-1, 1):
            parts.append(cyl_z(f'{tag}_bolt', sx * (fw - 0.04), -0.10 if sy < 0 else 0.0, z0 + fh - 0.035, z0 + fh + 0.006,
                               0.012, 'iron', segs=8))
    o = join(tag, parts, 0.0, 'guns')
    o['muzzle_y'] = fo; o['cascabel_y'] = -fi; o['axis_h'] = 0.0; o['front_y'] = fo; o['rear_y'] = -fi
    o['half_w'] = fw; o['rig'] = '{}'; o['elev'] = '{}'
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
    pe = build_petriera()
    st = build_petriera_step()
    sd = build_petriera_stand()
    for o in (fa, ft, pe):
        print('%s: muzzle %.2f, cascabel %.2f, carriage %.2f..%.2f, half width %.2f; %d verts'
              % (o.name, o['muzzle_y'], o['cascabel_y'], o['rear_y'], o['front_y'], o['half_w'], len(o.data.vertices)))
    if RENDER_DIR:
        render_views([(cv, 'cv'), (fa, 'fa'), (ft, 'ft'), (pe, 'pe')], RENDER_DIR)
    if OUT_BLEND:
        # gun dimensions for gun_layout.py (preview + prefab) and the rigging anchors for gun_rigging.py
        json.dump({o.name: {k: float(o[k]) for k in ('muzzle_y', 'cascabel_y', 'front_y', 'rear_y', 'half_w')}
                   | {'axis_h': float(o.get('axis_h', AXIS_H)), 'rig': json.loads(o['rig']), 'elev': json.loads(o['elev'])}
                   | {k: float(o[k]) for k in ('chamber_y', 'wedge_y') if k in o}
                   for o in (cv, fa, ft, pe)},
                  open(os.path.splitext(OUT_BLEND)[0] + '.json', 'w'), indent=1)
        bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
    print('guns done')
