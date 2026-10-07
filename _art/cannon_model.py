"""Galleass cannon: 16th-century bronze gun on a wooden truck carriage (two cheeks, two axletrees, four trucks,
elevation quoin), built parametrically. Local frame: barrel axis along +Y (muzzle forward), Z up, origin on the deck
under the middle of the carriage's front axletree... see GUN_ORIGIN notes below.

    blender -b ref/galleass_model.blend --python cannon_model.py -- <out.blend> <render dir>

Opens the galleass model for context, builds the long (broadside) and short (forecastle) variants, places preview
copies at a broadside gunport and at the five forecastle embrasures, renders review shots and saves <out.blend>.
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:]
OUT_BLEND, RENDER_DIR = argv[0], argv[1]
os.makedirs(RENDER_DIR, exist_ok=True)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model_geom
G = model_geom.load()
LIFT = G['Z_LIFT']

AXIS_H = 0.80          # barrel axis above the deck (broadside ports centred 0.85 up, forecastle embrasures 0.75)

# barrel profile (y from the base ring forward, radius) for a culverin-style gun of length L; scaled for the short one
def barrel_profile(L):
    k = L / 2.5
    P = [(-0.20 * k, 0.0), (-0.20 * k, 0.03), (-0.19 * k, 0.065), (-0.165 * k, 0.07),       # cascabel button
         (-0.12 * k, 0.045), (-0.06 * k, 0.045),                                         # neck
         (-0.03 * k, 0.15), (0.0, 0.19), (0.05 * k, 0.19), (0.06 * k, 0.172),              # base ring
         (1.00 * k, 0.158), (1.00 * k, 0.176), (1.05 * k, 0.176), (1.05 * k, 0.152),        # reinforce + ring
         (1.50 * k, 0.142), (1.50 * k, 0.158), (1.54 * k, 0.158), (1.54 * k, 0.136),        # 2nd reinforce + ring
         (2.30 * k, 0.108), (2.40 * k, 0.12), (2.44 * k, 0.132), (2.48 * k, 0.132),         # chase + muzzle swell
         (2.50 * k, 0.122), (2.50 * k, 0.055), (2.20 * k, 0.055), (2.20 * k, 0.0)]          # muzzle face + bore
    return P

ROLE_COL = {'bronze': (0.62, 0.45, 0.18, 1), 'wood': (0.36, 0.24, 0.14, 1), 'iron': (0.16, 0.16, 0.17, 1),
            'dark': (0.02, 0.02, 0.02, 1)}
MATS = {}
for r, c in ROLE_COL.items():
    m = bpy.data.materials.new('galleass_cannon_' + r); m.diffuse_color = c; MATS[r] = m

def coll(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name); bpy.context.scene.collection.children.link(c)
    return c

def obj_from_bm(bm, name, role, collection='cannon_parts'):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    me.materials.append(MATS[role])
    for p in me.polygons: p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(40))
    o = bpy.data.objects.new(name, me); coll(collection).objects.link(o)
    return o

def lathe_y(name, prof, role, at=(0, 0, 0), segs=32):
    """Solid of revolution about the Y axis (prof: (y, r))."""
    bm = bmesh.new(); rings = []
    for y, r in prof:
        ring = []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            ring.append(bm.verts.new((at[0] + r * math.cos(a), at[1] + y, at[2] + r * math.sin(a))))
        rings.append(ring)
    for ra, rb in zip(rings, rings[1:]):
        for i in range(segs):
            bm.faces.new((ra[i], ra[(i + 1) % segs], rb[(i + 1) % segs], rb[i]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
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
        v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0), (y0 + y1) / 2 + v.co.y * (y1 - y0), (z0 + z1) / 2 + v.co.z * (z1 - z0)))
    return obj_from_bm(bm, name, role)

def plank_yz(name, x0, x1, outline, role):
    """Prism: a (y, z) outline extruded between x0 and x1 (the carriage cheeks)."""
    bm = bmesh.new()
    a = [bm.verts.new((x0, y, z)) for y, z in outline]
    b = [bm.verts.new((x1, y, z)) for y, z in outline]
    bm.faces.new(a[::-1]); bm.faces.new(b)
    n = len(outline)
    for i in range(n):
        bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, name, role)

def handle(name, y, z, r, role, half_w=0.07):
    """Dolphin (lifting handle) on top of the barrel: a small arch across the axis."""
    bm = bmesh.new()
    pts = [Vector((-half_w + 2 * half_w * t / 10, y, z + 0.06 * math.sin(math.pi * t / 10))) for t in range(11)]
    rings = []
    for i, p in enumerate(pts):
        ring = []
        for k in range(8):
            a = 2 * math.pi * k / 8
            ring.append(bm.verts.new(p + Vector((0, r * math.cos(a), r * math.sin(a)))))
        rings.append(ring)
    for ra, rb in zip(rings, rings[1:]):
        for k in range(8):
            bm.faces.new((ra[k], ra[(k + 1) % 8], rb[(k + 1) % 8], rb[k]))
    bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
    return obj_from_bm(bm, name, role)

def build_gun(tag, L):
    """One gun; returns the parts. Barrel base ring at local y = 0; origin moved so the carriage stands on z 0."""
    k = L / 2.5
    parts = []
    tr_y = 1.0 * k                                          # trunnions at ~2/5 of the length
    prof = barrel_profile(L)
    parts.append(lathe_y(f'{tag}_barrel', [(y, r) for y, r in prof[:-4]] + [prof[-4]], 'bronze', at=(0, 0, AXIS_H)))
    parts.append(lathe_y(f'{tag}_bore', [(prof[-2][0] - 0.001, 0.0), (prof[-2][0] - 0.001, 0.056), (L - 0.002, 0.056), (L - 0.002, 0.0)],
                         'dark', at=(0, 0, AXIS_H), segs=24))
    parts.append(cyl_x(f'{tag}_trunnions', -0.28 * k, 0.28 * k, tr_y, AXIS_H - 0.02, 0.05 * k, 'bronze'))
    parts.append(handle(f'{tag}_dolphin', tr_y + 0.12 * k, AXIS_H + 0.15 * k, 0.018, 'bronze'))
    # carriage: two cheeks (stepped tops), front + rear axletrees, four trucks, transom, quoin, iron cap squares
    half = 0.2 * k + 0.04                                   # cheek centre lines either side of the breech
    t = 0.08
    yr, yf = -0.65 * k, tr_y + 0.25 * k                     # carriage rear / front ends
    zt = AXIS_H - 0.07 * k                                  # trunnion bed on the cheek
    outline = [(yr, 0.14), (yf, 0.14), (yf, zt), (tr_y + 0.06 * k, zt), (tr_y - 0.08 * k, zt + 0.02),
               (tr_y - 0.2 * k, zt - 0.12), (0.2 * k, zt - 0.12), (0.1 * k, zt - 0.22), (yr, zt - 0.3)]
    for s in (-1, 1):
        parts.append(plank_yz(f'{tag}_cheek', s * half - t / 2, s * half + t / 2, outline, 'wood'))
    wheel_r = 0.17
    for ya in (tr_y, yr + 0.2):
        parts.append(box(f'{tag}_axletree', -half - 0.1, half + 0.1, ya - 0.08, ya + 0.08, wheel_r - 0.06, wheel_r + 0.07, 'wood'))
        for s in (-1, 1):
            parts.append(cyl_x(f'{tag}_truck', s * (half + 0.1), s * (half + 0.22), ya, wheel_r, wheel_r, 'wood'))
            parts.append(cyl_x(f'{tag}_linchpin', s * (half + 0.22), s * (half + 0.25), ya, wheel_r, 0.035, 'iron', segs=12))
    parts.append(box(f'{tag}_transom', -half, half, 0.25 * k, 0.4 * k, 0.2, zt - 0.14, 'wood'))
    parts.append(box(f'{tag}_bed', -half + t / 2, half - t / 2, yr + 0.1, 0.35 * k, 0.22, 0.3, 'wood'))
    q = bmesh.new()                                          # elevation quoin under the breech
    vs = [q.verts.new(c) for c in ((-0.12, -0.25 * k, 0.3), (0.12, -0.25 * k, 0.3), (0.12, 0.25 * k, 0.3), (-0.12, 0.25 * k, 0.3),
                                   (-0.12, -0.25 * k, AXIS_H - 0.17 * k), (0.12, -0.25 * k, AXIS_H - 0.17 * k),
                                   (0.12, 0.25 * k, 0.4), (-0.12, 0.25 * k, 0.4))]
    for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        q.faces.new([vs[i] for i in f])
    bmesh.ops.recalc_face_normals(q, faces=q.faces)
    parts.append(obj_from_bm(q, f'{tag}_quoin', 'wood'))
    for s in (-1, 1):
        parts.append(box(f'{tag}_capsquare', s * half - t / 2 - 0.005, s * half + t / 2 + 0.005, tr_y - 0.07 * k, tr_y + 0.07 * k,
                         zt + 0.04, zt + 0.07, 'iron'))
    # join into one object per gun (multi-material), origin: deck level, under the trunnions
    bm = bmesh.new(); mats = []
    for p in parts:
        idx = list(MATS.values()).index(p.data.materials[0])
        me = p.data.copy()
        for poly in me.polygons: poly.material_index = idx
        bm.from_mesh(me); bpy.data.meshes.remove(me)
        bpy.data.objects.remove(p)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, -tr_y, 0))
    me = bpy.data.meshes.new(tag); bm.to_mesh(me); bm.free()
    for m in MATS.values(): me.materials.append(m)
    for p in me.polygons: p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(40))
    o = bpy.data.objects.new(tag, me); coll('cannon').objects.link(o)
    o['muzzle_y'] = L - tr_y; o['breech_y'] = -0.2 * k - tr_y; o['rear_y'] = yr - tr_y; o['front_y'] = yf - tr_y
    o['half_w'] = half + 0.25
    return o

LONG = build_gun('galleass_cannon_long', 2.5)
SHORT = build_gun('galleass_cannon_short', 1.8)
for o in (LONG, SHORT):
    print('%s: muzzle %.2f, cascabel %.2f, carriage %.2f..%.2f, half width %.2f (from the trunnions)'
          % (o.name, o['muzzle_y'], o['breech_y'], o['rear_y'], o['front_y'], o['half_w']))

# --- preview placement (the prefab will do the real placement) ----------------------------------------------------
Z_DECK = G['Z_GUN_DECK'] + LIFT
Z_FC = G['FC_Z_PLATFORM'] + LIFT
W_IN = G['WING_HW'] - G['SIDE_T']
prev = coll('cannon_preview')
def place(src, name, x, y, z, heading):
    o = bpy.data.objects.new(name, src.data); prev.objects.link(o)
    o.location = (x, y, z); o.rotation_euler = (0, 0, heading)
    return o
placed = []
for i in range(G['GUNPORTS_PER_SIDE']):
    gy = G['gunport_y'](i)
    for s in (-1, 1):
        # muzzle just inside the port (wall inner face W_IN): the gun points out along +-x
        d = W_IN + 0.06 - LONG['muzzle_y']
        placed.append(place(LONG, f'gun_bs_{i}_{s}', s * d, gy, Z_DECK, -s * math.pi / 2))
R_IN = G['fc_radius'](G['FC_Z_PLATFORM']) - 0.35
def fc_gun(deg):
    """(x, y, heading) of a forecastle gun: muzzle just inside its embrasure (the side ones sit 0.6 m aft, as in the model)."""
    ex, ey = G['fc_point'](deg, R_IN + 0.06, back=0.6)
    a = math.atan2(ey - G['FC_CY'] + (0.6 if abs(deg) >= 90 else 0.0), ex) if abs(deg) < 90 else (0.0 if deg > 0 else math.pi)
    d = SHORT['muzzle_y']
    return ex - d * math.cos(a), ey - d * math.sin(a), a - math.pi / 2, a
fore_y = G['MASTS']['fore']
for deg in G['FC_GUN_DEGS']:
    x, y, h, a = fc_gun(deg)
    placed.append(place(SHORT, f'gun_fc_{deg}', x, y, Z_FC, h))
    rx, ry = x + SHORT['rear_y'] * math.cos(a), y + SHORT['rear_y'] * math.sin(a)
    print('forecastle gun %+4d: trunnions (%.2f, %.2f), carriage rear (%.2f, %.2f), %.2f m from the fore mast (step r 0.62)'
          % (deg, x, y, rx, ry, math.hypot(rx, ry - fore_y)))

# --- renders -----------------------------------------------------------------------------------------------------
sc = bpy.context.scene
for o in bpy.data.objects:
    if o.type == 'MESH':
        cols = [c.name for c in o.users_collection]
        o.hide_render = not (('final' in cols and '.lod' not in o.name) or 'cannon_preview' in cols or 'cannon' in cols)
        if o.name in ('galleass_faction_paint', 'galleass_hull_plate'): o.hide_render = True
for o in (LONG, SHORT): o.location = (0, 60, 0)                 # the masters out of the way (solo shots move them)
cam = bpy.data.objects.new('cannon_cam', bpy.data.cameras.new('cannon_cam')); sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'MATERIAL'; sc.display.shading.show_shadows = True
sc.render.resolution_x, sc.render.resolution_y = 1200, 760
def shot(fname, loc, tgt, lens=35):
    cam.location = loc; cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler(); cam.data.lens = lens
    sc.render.filepath = os.path.join(RENDER_DIR, fname); bpy.ops.render.render(write_still=True)
LONG.location = (0, 60, 0); SHORT.location = (2.0, 60, 0)
shot('gun_solo.png', (3.2, 63.0, 1.8), (1.0, 60.2, 0.6), lens=40)
gy = G['gunport_y'](2)
shot('gun_broadside_in.png', (1.5, gy - 3.0, Z_DECK + 1.7), (4.6, gy, Z_DECK + 0.6), lens=30)
shot('gun_broadside_out.png', (10.5, gy - 3.5, Z_DECK + 1.0), (6.2, gy, Z_DECK + 0.8), lens=35)
shot('gun_forecastle_top.png', (0.0, 21.6, Z_FC + 9.0), (0.0, 21.61, Z_FC), lens=24)
shot('gun_forecastle_persp.png', (-4.5, 16.0, Z_FC + 3.5), (0.5, 22.5, Z_FC + 0.5), lens=28)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print('cannon done')
