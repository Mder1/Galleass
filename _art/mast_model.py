"""Galleass masts (re-rig phase 1, user 2026-10-13): own meshes for the three lateen rigs' mast_mesh entities, in the
vanilla mast's local frame (z up from the heel at -0.484 to the masthead, same radii and heights as
ship_mast_lateen_a_<size>), so the vanilla yards, sails and ropes keep their places.

    blender -b --factory-startup --python mast_model.py -- ../AssetSources/export renders/masts ref/galleass_masts.blend

After the drawing (ref/galleass_drawing.jpg, 16th-c Venetian galleass): masts WOOLDED all along (rope bands, the
drawing's black marks), a CALCESE at each masthead (the squared block carrying the sheaves of the tie / amante),
and on the main mast a GABBIA (round fighting top / lookout basket) on trestles above the calcese, the mast going on
as a short pole for the flag.

Materials are vanilla ones, as on the vanilla masts and yards: wood bw_oar_wood_a (UVs as the vanilla mast:
u round, v along), woolding plank_stake_a (its rope strip, u 0.722..0.762, as the yard lashings mast_ropes_a),
sheave slots galleass_dark, hoops galleass_iron. LODs _lod1.._lod3 (woolding simplified, then dropped).
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:]
OUT = argv[0]; RENDERS = argv[1] if len(argv) > 1 else None
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rope_geom as rg

for _o in list(bpy.data.objects):                          # factory scene: cube, light, camera
    bpy.data.objects.remove(_o)

from mast_dims import Z_HEEL, MASTS, rad, calcese_span, calcese_half, SHEAVE_DZ
WOOL_U = (0.722, 0.762)                # plank_stake_a rope strip
WOOL_VPM = 0.55                        # V per metre along the rope (mast_ropes_a)
WOOL_ROPE = 0.021                      # woolding rope radius
WOOL_TURNS = 4
WOOL_SPACING = 1.55

MATS = {}
def mat(name, color):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = color; MATS[name] = m
    return m
M_WOOD = mat('bw_oar_wood_a', (0.45, 0.33, 0.22, 1))
M_ROPE = mat('plank_stake_a', (0.62, 0.55, 0.42, 1))
M_DARK = mat('galleass_dark', (0.03, 0.03, 0.03, 1))
M_IRON = mat('galleass_iron', (0.15, 0.15, 0.16, 1))
ORDER = ['bw_oar_wood_a', 'plank_stake_a', 'galleass_dark', 'galleass_iron']

class Builder:
    """Collects bmesh parts per material, then one object."""
    def __init__(self):
        self.bms = {k: bmesh.new() for k in ORDER}
    def uv(self, key):
        return rg.uv_layer(self.bms[key])
    def obj(self, name):
        me = bpy.data.meshes.new(name); bm = bmesh.new()
        for i, k in enumerate(ORDER):
            tmp = bpy.data.meshes.new('tmp'); self.bms[k].to_mesh(tmp); self.bms[k].free()
            n0 = len(bm.faces); bm.from_mesh(tmp); bpy.data.meshes.remove(tmp)
            bm.faces.ensure_lookup_table()
            for f in bm.faces[n0:]: f.material_index = i
        bm.to_mesh(me); bm.free()
        for k in ORDER: me.materials.append(MATS[k])
        for p in me.polygons: p.use_smooth = True
        me.set_sharp_from_angle(angle=math.radians(75))     # rope tubes (5-6 sides) shade round, block edges stay sharp
        col = me.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
        for d in col.data: d.color = (1, 1, 1, 1)
        o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
        return o

def wood_uv(p):
    a = math.atan2(p.y, p.x)
    return (-1.2 + 0.9 * (a / (2 * math.pi) + 0.5), 2.6 + 0.177 * p.z)

def lathe(B, key, prof, segs, uvf=wood_uv, cap_top=False, cap_bottom=False, ellipse=(1.0, 1.0)):
    """Solid of revolution about z: prof [(z, r)], optional elliptical section (x, y factors)."""
    bm = B.bms[key]; uvl = B.uv(key)
    rings = []
    for z, r in prof:
        rings.append([bm.verts.new((r * ellipse[0] * math.cos(2 * math.pi * k / segs),
                                    r * ellipse[1] * math.sin(2 * math.pi * k / segs), z)) for k in range(segs)])
    for ra, rb in zip(rings, rings[1:]):
        for k in range(segs):
            f = bm.faces.new((ra[k], ra[(k + 1) % segs], rb[(k + 1) % segs], rb[k]))
            for lp in f.loops: lp[uvl].uv = uvf(lp.vert.co)
            # seam: keep u continuous inside a face
            us = [lp[uvl].uv[0] for lp in f.loops]
            if max(us) - min(us) > 0.45:
                for lp in f.loops:
                    if lp[uvl].uv[0] < -0.75: lp[uvl].uv = (lp[uvl].uv[0] + 0.9, lp[uvl].uv[1])
    for ring, top in ((rings[-1], True), (rings[0], False)):
        if (top and cap_top) or (not top and cap_bottom):
            f = bm.faces.new(ring if top else ring[::-1])
            for lp in f.loops: lp[uvl].uv = (-1.2 + 0.2 * lp.vert.co.x, 2.6 + 0.2 * lp.vert.co.y)

def box(B, key, c, half, uvs=0.5, chamfer=0.0):
    """Axis-aligned box (optionally chamfered vertical edges) centred at c, half sizes half."""
    bm = B.bms[key]; uvl = B.uv(key)
    hx, hy, hz = half; ch = min(chamfer, hx * 0.4, hy * 0.4)
    if ch > 0:
        sect = [(hx, hy - ch), (hx - ch, hy), (-hx + ch, hy), (-hx, hy - ch), (-hx, -hy + ch), (-hx + ch, -hy),
                (hx - ch, -hy), (hx, -hy + ch)]
    else:
        sect = [(hx, hy), (-hx, hy), (-hx, -hy), (hx, -hy)]
    lo = [bm.verts.new((c[0] + x, c[1] + y, c[2] - hz)) for x, y in sect]
    hi = [bm.verts.new((c[0] + x, c[1] + y, c[2] + hz)) for x, y in sect]
    n = len(sect)
    faces = [bm.faces.new(hi), bm.faces.new(lo[::-1])]
    for i in range(n):
        faces.append(bm.faces.new((lo[i], lo[(i + 1) % n], hi[(i + 1) % n], hi[i])))
    for f in faces:
        f.normal_update(); nn = f.normal
        for lp in f.loops:
            p = lp.vert.co
            if abs(nn.z) > 0.7: lp[uvl].uv = (p.x * uvs, p.y * uvs)
            else:
                t = Vector((-nn.y, nn.x, 0))
                lp[uvl].uv = (p.dot(t) * uvs - 1.2, 2.6 + p.z * 0.177)

def woolding(B, sp, z, segs, tube, turns=WOOL_TURNS):
    """A band of rope turns round the mast at height z (centre)."""
    bm = B.bms['plank_stake_a']
    w = (turns - 1) * WOOL_ROPE * 2.05
    for i in range(turns):
        zz = z - w / 2 + i * WOOL_ROPE * 2.05
        R = rad(sp, zz) + WOOL_ROPE * 0.75
        rg.ring(bm, (0, 0, zz), (0, 0, 1), R, WOOL_ROPE, segs=segs, tube=tube, u_range=WOOL_U, vpm=WOOL_VPM)

def _box_bm(c, half, chamfer=0.0):
    """Closed (chamfered) box as a bmesh (for booleans)."""
    hx, hy, hz = half; ch = min(chamfer, hx * 0.4, hy * 0.4)
    sect = ([(hx, hy - ch), (hx - ch, hy), (-hx + ch, hy), (-hx, hy - ch), (-hx, -hy + ch), (-hx + ch, -hy),
             (hx - ch, -hy), (hx, -hy + ch)] if ch > 0 else [(hx, hy), (-hx, hy), (-hx, -hy), (hx, -hy)])
    bm = bmesh.new()
    lo = [bm.verts.new((c[0] + x, c[1] + y, c[2] - hz)) for x, y in sect]
    hi = [bm.verts.new((c[0] + x, c[1] + y, c[2] + hz)) for x, y in sect]
    n = len(sect)
    bm.faces.new(hi); bm.faces.new(lo[::-1])
    for i in range(n):
        bm.faces.new((lo[i], lo[(i + 1) % n], hi[(i + 1) % n], hi[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm

def _merge(B, key, me, uvs=0.5):
    """Append a mesh to B's material bmesh with box-projected wood UVs (v along z like the mast)."""
    bm = B.bms[key]; uvl = B.uv(key)
    tmp = bmesh.new(); tmp.from_mesh(me)
    vmap = {v: bm.verts.new(v.co) for v in tmp.verts}
    for f in tmp.faces:
        nf = bm.faces.new([vmap[v] for v in f.verts])
        f.normal_update(); nn = f.normal
        for lp in nf.loops:
            p = lp.vert.co
            if abs(nn.z) > 0.7: lp[uvl].uv = (p.x * uvs, p.y * uvs)
            elif abs(nn.x) > abs(nn.y): lp[uvl].uv = (p.y * uvs - 1.2, 2.6 + p.z * 0.177)
            else: lp[uvl].uv = (p.x * uvs - 1.2, 2.6 + p.z * 0.177)
    tmp.free()

def calcese(B, sp, z0, z1):
    """Squared masthead block, wider fore-and-aft (y). Two sheave slots run right through it athwartships (x; user
    2026-10-13: painted-on slots read as patches), each with a wooden sheave on an iron pin (axis fore-and-aft):
    the tie comes up from the yard on one side, over the sheave and down the other. Iron hoops, a cap."""
    r = rad(sp, z1)
    hx, hy = calcese_half(sp)
    block = _box_bm((0, 0, (z0 + z1) / 2), (hx, hy, (z1 - z0) / 2), chamfer=r * 0.35)
    me = bpy.data.meshes.new('calcese_tmp'); block.to_mesh(me); block.free()
    ob = bpy.data.objects.new('calcese_tmp', me); bpy.context.scene.collection.objects.link(ob)
    slots = []
    for dz in SHEAVE_DZ:
        zc = z0 + dz * (z1 - z0); h = (z1 - z0) * 0.17
        slots.append((zc, h))
        cb = _box_bm((0, 0, zc), (hx + 0.2, 0.05, h))
        cme = bpy.data.meshes.new('slot_tmp'); cb.to_mesh(cme); cb.free()
        co = bpy.data.objects.new('slot_tmp', cme); bpy.context.scene.collection.objects.link(co)
        mod = ob.modifiers.new('slot', 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.solver = 'EXACT'; mod.object = co
        co.hide_set(True)
    dg = bpy.context.evaluated_depsgraph_get()
    res = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    for m in list(ob.modifiers):
        o2 = m.object; ob.modifiers.remove(m); bpy.data.meshes.remove(o2.data)
    bpy.data.objects.remove(ob); bpy.data.meshes.remove(me)
    _merge(B, 'bw_oar_wood_a', res); bpy.data.meshes.remove(res)
    for zc, h in slots:
        rs = min(h * 0.92, hx * 0.86)
        # sheave: disc in the x-z plane (axis y), thickness 0.07, a rope groove round its rim
        prof = [(-0.035, 0.0), (-0.035, rs * 0.92), (-0.03, rs), (-0.012, rs * 0.94), (0.012, rs * 0.94),
                (0.03, rs), (0.035, rs * 0.92), (0.035, 0.0)]
        bm = B.bms['bw_oar_wood_a']; uvl = B.uv('bw_oar_wood_a'); segs = 16
        rings = []
        for yy, rr in prof:
            rings.append([bm.verts.new((rr * math.cos(2 * math.pi * k / segs), yy, zc + rr * math.sin(2 * math.pi * k / segs)))
                          for k in range(segs)] if rr > 1e-6 else [bm.verts.new((0, yy, zc))])
        for ra, rb in zip(rings, rings[1:]):
            for k in range(segs):
                if len(ra) == 1: vs = (ra[0], rb[(k + 1) % segs], rb[k])
                elif len(rb) == 1: vs = (ra[k], ra[(k + 1) % segs], rb[0])
                else: vs = (ra[k], ra[(k + 1) % segs], rb[(k + 1) % segs], rb[k])
                f = bm.faces.new(vs)
                for lp in f.loops: lp[uvl].uv = (0.3 + lp.vert.co.x * 0.5, 2.6 + lp.vert.co.z * 0.177)
        # iron pin through the block, fore and aft, ends just proud of the faces
        pin = bmesh.ops.create_cone(B.bms['galleass_iron'], cap_ends=True, segments=10, radius1=0.022, radius2=0.022,
                                    depth=2 * hy + 0.02)
        for v in pin['verts']:
            v.co = Vector((v.co.x, v.co.z, v.co.y + zc))
    # iron hoop at the foot and below the cap
    for zz in (z0 + 0.06, z1 - 0.08):
        box(B, 'galleass_iron', (0, 0, zz), (hx + 0.008, hy + 0.008, 0.025), chamfer=r * 0.35 + 0.008)
    # tapered foot: from the round mast into the block
    lathe(B, 'bw_oar_wood_a', [(z0 - 0.35, rad(sp, z0 - 0.35)), (z0 + 0.02, hx * 1.02)], 12)
    # cap
    box(B, 'bw_oar_wood_a', (0, 0, z1 + 0.05), (hx * 1.15, hy * 1.12, 0.05), chamfer=r * 0.4)

# lubber's hole: the flag halyard (vanilla flag_capture_rope, the capture flag runs along it - it can't be rerouted)
# crosses the floor 0.39 m from the axis at bearing -84 deg (mast-local, from the rig layout; it went through the
# planking, user 2026-10-13/18)
LUBBER_DEG, LUBBER_HALF = -84.0, 9.0

def floor_ring(B, key, z, r0, r1, th, gap_c, gap_h, segs=20):
    """Annular floor slab, open in the sector gap_c +- gap_h (radians)."""
    bm = B.bms[key]; uvl = B.uv(key)
    a0, a1 = gap_c + gap_h, gap_c - gap_h + 2 * math.pi
    ring = []
    for k in range(segs + 1):
        a = a0 + (a1 - a0) * k / segs
        ring.append([bm.verts.new((rr * math.cos(a), rr * math.sin(a), zz)) for rr, zz in ((r0, z), (r1, z), (r1, z + th), (r0, z + th))])
    made = []
    def face(vs):
        f = bm.faces.new(vs); made.append(f)
        for lp in f.loops: lp[uvl].uv = (-1.2 + 0.5 * lp.vert.co.x, 2.6 + 0.5 * lp.vert.co.y + 0.177 * lp.vert.co.z)
    for p, q in zip(ring, ring[1:]):
        for i in range(4):
            j = (i + 1) % 4
            face((p[i], q[i], q[j], p[j]))
    face(ring[0]); face(ring[-1][::-1])
    bmesh.ops.recalc_face_normals(bm, faces=made)

def gabbia(B, sp, zf):
    """Round fighting top: two trestle cheeks under a planked floor, a ring of staves 1.0 m high with two iron
    hoops, a top rail."""
    R = 0.78; H = 1.0
    r = rad(sp, zf)
    for s in (-1, 1):                                       # trestle trees fore-and-aft each side of the mast
        box(B, 'bw_oar_wood_a', (s * (r + 0.07), 0, zf - 0.14), (0.06, R * 0.85, 0.09))
    for s in (-1, 1):                                       # cross trees
        box(B, 'bw_oar_wood_a', (0, s * (r + 0.12), zf - 0.03), (R * 0.85, 0.05, 0.05))
    floor_ring(B, 'bw_oar_wood_a', zf, r + 0.01, R, 0.06, math.radians(LUBBER_DEG), math.radians(LUBBER_HALF))
    n = 22
    for k in range(n):                                      # staves
        a = 2 * math.pi * (k + 0.5) / n
        c = Vector((math.cos(a) * (R - 0.02), math.sin(a) * (R - 0.02), zf + 0.06 + H / 2))
        bm = B.bms['bw_oar_wood_a']; uvl = B.uv('bw_oar_wood_a')
        t = Vector((-math.sin(a), math.cos(a), 0)); nrm = Vector((math.cos(a), math.sin(a), 0))
        w, d = math.pi * 2 * R / n * 0.48, 0.025
        pts = [c + t * sx * w + nrm * sy * d for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
        lo = [bm.verts.new(p - Vector((0, 0, H / 2))) for p in pts]
        hi = [bm.verts.new(p + Vector((0, 0, H / 2))) for p in pts]
        fs = [bm.faces.new(hi), bm.faces.new(lo[::-1])] + [bm.faces.new((lo[i], lo[(i + 1) % 4], hi[(i + 1) % 4], hi[i])) for i in range(4)]
        for f in fs:
            for lp in f.loops:
                p = lp.vert.co
                lp[uvl].uv = (-1.2 + 0.9 * (k / n) + p.dot(t) * 0.5, 2.6 + 0.177 * p.z)
    for zz in (zf + 0.30, zf + 0.85):                      # iron hoops
        lathe(B, 'galleass_iron', [(zz - 0.02, R + 0.008), (zz + 0.02, R + 0.008), (zz + 0.02, R + 0.035),
                                   (zz - 0.02, R + 0.035), (zz - 0.02, R + 0.008)], 24)
    lathe(B, 'bw_oar_wood_a', [(zf + H + 0.06, R - 0.05), (zf + H + 0.06, R + 0.04), (zf + H + 0.11, R + 0.04),
                               (zf + H + 0.11, R - 0.05), (zf + H + 0.06, R - 0.05)], 24)          # top rail

def build(size, level):
    sp = MASTS[size]
    B = Builder()
    segs = (16, 12, 8, 6)[level]
    top = sp['top']
    c0, c1 = calcese_span(sp)                               # calcese above the yard's tie
    zf = c1 + 0.55                                          # gabbia floor (main)
    shaft_top = c0 - 0.35
    # shaft: heel to the calcese foot
    zs = [Z_HEEL] + [Z_HEEL + (shaft_top - Z_HEEL) * k / 6 for k in range(1, 7)]
    lathe(B, 'bw_oar_wood_a', [(z, rad(sp, z)) for z in zs], segs, cap_bottom=True)
    if level < 3:
        calcese(B, sp, c0, c1)
    if sp['gabbia']:
        if level < 3:
            gabbia(B, sp, zf)
        # pole above the calcese through the gabbia to the masthead
        rp = rad(sp, top) * 0.75
        lathe(B, 'bw_oar_wood_a', [(c1 + 0.1, rp * 1.1), (top - 0.15, rp), (top, rp * 0.6)], max(segs - 4, 6), cap_top=True)
        if level < 2:
            lathe(B, 'bw_oar_wood_a', [(top, 0.001), (top, rp * 1.25), (top + 0.18, rp * 1.25), (top + 0.18, 0.001)], 10)   # truck
    else:
        if level < 2:
            rp = rad(sp, top) * 0.5                          # short truck pole + truck above the cap
            lathe(B, 'bw_oar_wood_a', [(c1 + 0.1, rp), (top + 0.1, rp), (top + 0.1, 0.001)], 8)
    # woolding: bands from 1.6 m above the deck up to just under the yard's parrel, and between parrel and calcese
    if level < 2:
        z = sp['deck'] + 1.6
        tube, rs = (4, 18) if level == 0 else (4, 12)
        while z < c0 - 0.6:
            if abs(z - sp['yard']) > 0.6:                    # leave the parrel / yard hoist clear
                woolding(B, sp, z, rs, tube)
            z += WOOL_SPACING
    name = 'galleass_mast_%s' % size + ('' if level == 0 else '_lod%d' % level)
    o = B.obj(name)
    return o

objs = {}
for size in MASTS:
    objs[size] = [build(size, lvl) for lvl in range(4)]
    print('MAST %s tris %s' % (size, [sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs[size]]))

os.makedirs(OUT, exist_ok=True)
for size, lst in objs.items():
    bpy.ops.object.select_all(action='DESELECT')
    for o in lst: o.select_set(True)
    bpy.context.view_layer.objects.active = lst[0]
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, 'galleass_mast_%s.fbx' % size), use_selection=True,
                             object_types={'MESH'}, use_mesh_modifiers=True, mesh_smooth_type='FACE',
                             use_tspace=False, axis_forward='Y', axis_up='Z', apply_unit_scale=True, global_scale=1.0,
                             bake_anim=False, path_mode='STRIP', add_leaf_bones=False)
    print('MAST exported galleass_mast_%s.fbx' % size)

# --- bowsprit (re-rig phase 4, user 2026-10-19: the drawing's spar over the spur carrying the spritsail's yard), in
# the SHIP frame (its prefab entity sits at the ship's origin, like the standing rigging): stepped on a chock on the
# forecastle platform and out through the parapet (collar on its face), gammoned down to the chock, iron bands at the sling and the end, the yard's sling block
# under it, a lift block at the end, and a belaying pin through it near the end (its two ends are knot points:
# mast_dims.sprit_pins). Collision bo_galleass_bowsprit: the spar as one convex prism.
from mast_dims import (SPRIT_HEEL, SPRIT_RISE, SPRIT_LEN, SPRIT_R0, SPRIT_R1, SPRIT_SLING_Y, SPRIT_CHOCK,
                       SPRIT_PIN_HALF, SPRIT_WALL, SPRIT_HOLE, sprit_point, sprit_tip, sprit_pins)
SPRIT_M = Matrix.Translation(Vector(SPRIT_HEEL)) @ Matrix.Rotation(SPRIT_RISE - math.pi / 2, 4, 'X')   # spar z -> ship
SPRIT_BUTT = -0.20                                          # the heel's butt behind the step
def sprit_r(t):
    return SPRIT_R0 + (SPRIT_R1 - SPRIT_R0) * max(t, 0.0) / SPRIT_LEN

def sprit_t(y):
    """Spar-local z of the ship y on its axis."""
    return (y - SPRIT_HEEL[1]) / math.cos(SPRIT_RISE)

def build_bowsprit(level):
    B = Builder()
    segs = (16, 12, 8, 6)[level]
    # spar-local parts (z along the spar from the heel), then into the ship frame
    ts = [SPRIT_BUTT] + [SPRIT_LEN * k / 8 for k in range(9)]
    lathe(B, 'bw_oar_wood_a', [(t, sprit_r(t)) for t in ts], segs, cap_top=True, cap_bottom=True)
    if level < 3:
        t_face = sprit_t(SPRIT_WALL[1] + 0.175) + 0.04          # the collar on the parapet's outer face covers the hole
        for t, w in ((sprit_t(SPRIT_SLING_Y) - 0.32, 0.07), (sprit_t(SPRIT_SLING_Y) + 0.32, 0.07), (SPRIT_LEN - 0.12, 0.09),
                     (t_face, 0.08)):
            r = sprit_r(t) + (SPRIT_HOLE + 0.03 if abs(t - t_face) < 1e-6 else 0.012)
            lathe(B, 'galleass_iron', [(t - w / 2, r - 0.01), (t - w / 2, r), (t + w / 2, r), (t + w / 2, r - 0.01)],
                  segs)
    if level < 2:                                           # rope bands round the spar by the step
        tube, rs = (4, 18) if level == 0 else (4, 12)
        for t0 in (0.35, sprit_t(SPRIT_WALL[1] + 0.175) + 0.25):     # inside behind the wall, outside by the collar
            for i in range(WOOL_TURNS):
                t = t0 + i * WOOL_ROPE * 2.05
                rg.ring(B.bms['plank_stake_a'], (0, 0, t), (0, 0, 1), sprit_r(t) + WOOL_ROPE * 0.75, WOOL_ROPE,
                        segs=rs, tube=tube, u_range=WOOL_U, vpm=WOOL_VPM)
    for bm in B.bms.values():
        bmesh.ops.transform(bm, matrix=SPRIT_M, verts=bm.verts)
    # ship-frame parts
    cx, cy, ch = SPRIT_CHOCK
    z_cap = SPRIT_HEEL[2] - SPRIT_R0 - ch
    box(B, 'bw_oar_wood_a', (0.0, SPRIT_HEEL[1] + 0.12, z_cap + ch / 2), (cx, cy, ch / 2), chamfer=0.04)
    if level < 2:
        # gammoning: each turn goes over the spar (clear of it: in a y plane the inclined spar is r / cos(rise) high)
        # and straight down both sides of the chock to an iron ring on the platform each side (user 2026-10-19: the
        # first turns, flat ellipses, ran into the spar's top and through the chock)
        z_ring = z_cap + 0.10                                # ring centre (radius 0.08) above the platform
        for i in range(3):
            y = SPRIT_HEEL[1] + 0.02 + i * 0.07
            zc = sprit_point(y)[2]
            hx = cx + WOOL_ROPE * 1.6
            hz = sprit_r(sprit_t(y)) / math.cos(SPRIT_RISE) + WOOL_ROPE * 1.3
            top = [(hx * math.cos(a), y, zc + hz * math.sin(a)) for a in [math.pi * k / 14 for k in range(15)]]
            pts = [(hx, y, z_ring)] + top + [(-hx, y, z_ring)]
            rg.rope(B.bms['plank_stake_a'], pts, WOOL_ROPE, segs=5, caps=True, u_range=WOOL_U, vpm=WOOL_VPM)
        ym = SPRIT_HEEL[1] + 0.09
        for sx in (-1, 1):                                   # the rings the turns are made fast to
            rg.ring(B.bms['galleass_iron'], (sx * (cx + WOOL_ROPE * 1.6), ym, z_ring), (1, 0, 0), 0.08, 0.012,
                    segs=12, tube=5, role_uv='iron')
    if level < 3:
        # the yard's sling block hangs under the spar between the iron bands; the lift block under the end
        for y, drop, size in ((SPRIT_SLING_Y, 0.30, (0.30, 0.20, 0.13)), (sprit_tip()[1] - 0.35, 0.26, (0.24, 0.16, 0.11))):
            p = Vector(sprit_point(y)); r = sprit_r(sprit_t(y))
            c = p - Vector((0, 0, r + drop))
            rg.block(B.bms['bw_oar_wood_a'], c, (0, 0, 1), (1, 0, 0), *size)
            rg.rope(B.bms['plank_stake_a'], [c + Vector((0, 0, size[0] / 2 - 0.02)), p - Vector((0, 0, r - 0.02))],
                    0.018, segs=5, u_range=WOOL_U, vpm=WOOL_VPM)
        # belaying pin through the spar
        _, y0, z0 = sprit_pins()[0]
        rg.rope(B.bms['bw_oar_wood_a'], [(-SPRIT_PIN_HALF, y0, z0), (SPRIT_PIN_HALF, y0, z0)], 0.025, segs=8)
    o = B.obj('galleass_bowsprit' + ('' if level == 0 else '_lod%d' % level))
    return o

sprit = [build_bowsprit(lvl) for lvl in range(4)]
print('BOWSPRIT tris %s' % [sum(len(p.vertices) - 2 for p in o.data.polygons) for o in sprit])
bm = bmesh.new()                                            # collision: an 8-sided prism along the spar
ring0 = [bm.verts.new(SPRIT_M @ Vector((SPRIT_R0 * math.cos(a), SPRIT_R0 * math.sin(a), SPRIT_BUTT)))
         for a in [2 * math.pi * k / 8 for k in range(8)]]
ring1 = [bm.verts.new(SPRIT_M @ Vector((SPRIT_R1 * math.cos(a), SPRIT_R1 * math.sin(a), SPRIT_LEN)))
         for a in [2 * math.pi * k / 8 for k in range(8)]]
bm.faces.new(ring0[::-1]); bm.faces.new(ring1)
for k in range(8):
    bm.faces.new((ring0[k], ring0[(k + 1) % 8], ring1[(k + 1) % 8], ring1[k]))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
me = bpy.data.meshes.new('bo_galleass_bowsprit'); bm.to_mesh(me); bm.free()
me.materials.append(bpy.data.materials.get('wood') or bpy.data.materials.new('wood'))   # the PHYSICS material (as the
                                                                                        # bitts' bo_): the Kit looks it up
bo = bpy.data.objects.new('bo_galleass_bowsprit', me); bpy.context.scene.collection.objects.link(bo)
for name, lst in (('galleass_bowsprit', sprit), ('bo_galleass_bowsprit', [bo])):
    bpy.ops.object.select_all(action='DESELECT')
    for o in lst: o.select_set(True)
    bpy.context.view_layer.objects.active = lst[0]
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, name + '.fbx'), use_selection=True,
                             object_types={'MESH'}, use_mesh_modifiers=True, mesh_smooth_type='FACE',
                             use_tspace=False, axis_forward='Y', axis_up='Z', apply_unit_scale=True, global_scale=1.0,
                             bake_anim=False, path_mode='STRIP', add_leaf_bones=False)
    print('MAST exported %s.fbx' % name)

if RENDERS:
    os.makedirs(RENDERS, exist_ok=True)
    for o in sprit[1:] + [bo]: o.hide_render = True
    sprit[0].hide_render = True                            # (own shots below)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'MATERIAL'
    sc.display.shading.show_cavity = True
    for size, lst in objs.items():
        for o in lst[1:]: o.hide_render = True
    xs = {'large': 0.0, 'medium': 3.0, 'small': 6.0}
    for size, lst in objs.items(): lst[0].location = (xs[size], 0, 0)
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    def shot(fname, loc, tgt, lens=50, ortho=None, res=(1200, 1600)):
        sc.render.resolution_x, sc.render.resolution_y = res
        cam.location = loc; cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        if ortho: cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
        else: cam.data.type = 'PERSP'; cam.data.lens = lens
        sc.render.filepath = os.path.join(RENDERS, fname); bpy.ops.render.render(write_still=True)
    shot('masts_side.png', (3, -60, 16), (3, 0, 16), ortho=36)
    shot('mast_large_top.png', (2.5, -3.5, 31.5), (0, 0, 29.0), lens=40, res=(1400, 1400))
    shot('mast_medium_top.png', (5.2, -2.6, 24.6), (3, 0, 23.2), lens=40, res=(1400, 1400))
    shot('mast_wool.png', (1.2, -1.6, 11.0), (0, 0, 10.0), lens=50, res=(1400, 1000))
    for lst in objs.values(): lst[0].hide_render = True
    sprit[0].hide_render = False
    shot('bowsprit_side.png', (-14, 29.8, 9.2), (0, 29.8, 9.0), lens=35, res=(1600, 1000))
    shot('bowsprit_heel.png', (-1.6, 23.3, 7.4), (0, 24.6, 6.6), lens=35, res=(1400, 1000))
    shot('bowsprit_end.png', (-1.8, 32.6, 12.0), (0, 34.5, 11.3), lens=35, res=(1400, 1000))
    print('MAST renders in', RENDERS)
if len(argv) > 2:                                          # blend for rig_preview.py (MASTS_BLEND)
    for lst in objs.values():
        lst[0].location = (0, 0, 0)
    bpy.ops.wm.save_as_mainfile(filepath=argv[2])
