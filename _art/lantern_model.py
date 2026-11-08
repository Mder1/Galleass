"""The mast lanterns (user 2026-10-28: our own instead of the vanilla nord lantern), built parametrically, UV'd, exported
for the Modding Kit.

    blender -b --factory-startup --python lantern_model.py -- ref/galleass_lantern.blend ../AssetSources/export [renders/lantern]

A ship's lantern as carried at sea: a small square WOODEN box (the user's choice; tinned iron was as common) with HORN
panes (horn, boiled and pressed flat, lets a soft yellow light through and does not break when the ship rolls), a
tallow candle on an iron spike in a socket, a hinged door in one side for lighting and changing the candle, and on the
flat top board a sheet-iron pyramid cap punched with vent holes, a small hat over its vent and the carrying ring (user
2026-10-28: the wooden roof looked off). About 0.35 m from the bottom board to the hat.

Mesh galleass_horn_lantern (galleass_trim = wood, galleass_iron = cap / hat / ring / hinges / latch / socket,
galleass_horn = the panes, see-through (Kit: modulate + alpha test), galleass_sack = the tallow, galleass_dark = the
wick and the vent holes), ORIGIN AT THE HOOK POINT (the top of the inside of the ring: the lantern hangs from there), +Z
up, the door on the +X side (the prefab turns +X outboard). At night the candle's light on the inside shows through
the panes (user 2026-10-28: no glow shell, it hid the candle).
Points for the prefab (flame / light, candle, size, centre of mass) go to ref/galleass_lantern.json.
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:]
OUT_BLEND, OUT_FBX, RENDERS = argv[0], argv[1], (argv[2] if len(argv) > 2 else None)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from lod_util import make_lods
import grain_uv

ROLE = {'wood': 'galleass_trim', 'iron': 'galleass_iron', 'horn': 'galleass_horn', 'tallow': 'galleass_sack',
        'dark': 'galleass_dark'}
UV_S = {'galleass_trim': 0.135, 'galleass_iron': 0.5, 'galleass_sack': 0.3, 'galleass_dark': 0.5}
COL = {'wood': (0.36, 0.24, 0.14, 1), 'iron': (0.16, 0.16, 0.17, 1), 'horn': (0.85, 0.62, 0.28, 1),
       'tallow': (0.90, 0.86, 0.72, 1), 'dark': (0.05, 0.05, 0.05, 1)}
ROLES = list(ROLE)

# --- dimensions (metres, lantern frame: z down from the hook point)
HW, POST = 0.090, 0.018                 # half width over the corner posts, post section
BOARD_OUT = 0.006                       # top / bottom boards stand out of the posts
RING_R, RING_W = 0.024, 0.0045          # carrying ring (centre radius, wire radius); hangs in the y-z plane
Z_EYE = -0.062                          # the eye on the hat's tip (the ring passes through it)
Z_HAT_TIP, Z_HAT0, HAT_R = -0.060, -0.082, 0.034    # small conical hat over the vent
Z_VENT1, Z_VENT0, VENT_R = -0.090, -0.102, 0.020    # round vent collar at the cap's top (the smoke leaves under the hat)
Z_CAP1, CAP_HW = -0.100, 0.022                       # sheet-iron pyramid cap: top (half width there), foot on the board
Z_CAP0 = -0.150                         # cap foot = top board top
Z_TOP0 = -0.170                         # top board bottom = posts' top
Z_BOT1, Z_BOT0 = -0.390, -0.408         # bottom board top / bottom
Z_BAR = -0.280                          # middle glazing bar (horn came in small pieces)
HOLE_R, HOLE_T = 0.0045, 0.45           # punched vent holes: radius, height up the cap's slope (0 foot, 1 top)
PANE_X = HW - POST / 2                  # pane plane: in the middle of the posts
PANE_Y = HW - POST                      # panes span between the posts' inner faces
CANDLE_R, CANDLE_H = 0.011, 0.070
SOCKET_R, SOCKET_H = 0.018, 0.012
WICK_H = 0.009
Z_WICK = Z_BOT1 + SOCKET_H + CANDLE_H * 0.86 + 0.004
FLAME_Z = Z_WICK + WICK_H + 0.012       # the middle of a candle flame above the wick

for c in list(bpy.data.objects): bpy.data.objects.remove(c)
MATS = {}
for role, kit in ROLE.items():
    m = bpy.data.materials.get(kit) or bpy.data.materials.new(kit)
    m.diffuse_color = COL[role]; MATS[role] = m

def tag(faces, role):
    for f in faces: f.material_index = ROLES.index(role)

def hexa(bm, corners, role='wood'):
    """Six-sided block from 8 corners: bottom (x0y0, x1y0, x1y1, x0y1) then top in the same order."""
    vs = [bm.verts.new(c) for c in corners]
    fs = [bm.faces.new([vs[i] for i in idx]) for idx in
          ((3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))]
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    tag(fs, role)
    return fs

def box(bm, x0, x1, y0, y1, z0, z1, role='wood'):
    return hexa(bm, [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                     (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], role)

def frustum(bm, h0, z0, h1, z1, role='wood'):
    """Square frustum (h = half width) - the roof."""
    return hexa(bm, [(-h0, -h0, z0), (h0, -h0, z0), (h0, h0, z0), (-h0, h0, z0),
                     (-h1, -h1, z1), (h1, -h1, z1), (h1, h1, z1), (-h1, h1, z1)], role)

def lathe(bm, prof, at, segs=12, role='wood'):
    """Closed solid of revolution about +Z at 'at': prof = [(z, r)], r 0 closes an end."""
    rings = []
    for z, r in prof:
        if r <= 0:
            rings.append([bm.verts.new(Vector(at) + Vector((0, 0, z)))])
        else:
            rings.append([bm.verts.new(Vector(at) + Vector((r * math.cos(2 * math.pi * k / segs),
                                                             r * math.sin(2 * math.pi * k / segs), z)))
                          for k in range(segs)])
    faces = []
    for a, b in zip(rings, rings[1:]):
        for k in range(segs):
            kk = (k + 1) % segs
            if len(a) == 1: faces.append(bm.faces.new((a[0], b[k], b[kk])))
            elif len(b) == 1: faces.append(bm.faces.new((a[k], a[kk], b[0])))
            else: faces.append(bm.faces.new((a[k], a[kk], b[kk], b[k])))
    if len(rings[0]) > 1: faces.append(bm.faces.new(list(reversed(rings[0]))))
    if len(rings[-1]) > 1: faces.append(bm.faces.new(rings[-1]))
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    tag(faces, role)
    return faces

def torus_yz(bm, centre, R, r, segs=20, tube=6, role='iron'):
    """Ring in the y-z plane (the hook's wire runs along x through it)."""
    c = Vector(centre); rings = []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        d = Vector((0, math.cos(a), math.sin(a)))
        rings.append([bm.verts.new(c + d * (R + r * math.cos(2 * math.pi * k / tube)) +
                                   Vector((r * math.sin(2 * math.pi * k / tube), 0, 0))) for k in range(tube)])
    faces = []
    for i in range(segs):
        a, b = rings[i], rings[(i + 1) % segs]
        for k in range(tube):
            kk = (k + 1) % tube
            faces.append(bm.faces.new((a[k], a[kk], b[kk], b[k])))
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    tag(faces, role)
    return faces

def panes(bm, inset, thick, role, sides=True):
    """Horn panes on the four sides (one slab each, through the glazing bar); inset = from the pane plane inwards."""
    x = PANE_X - inset; out = []
    for ax in ('x', 'y'):
        for s in (-1, 1):
            x0, x1 = sorted((s * (x - thick / 2), s * (x + thick / 2)))
            if ax == 'x':
                out += box(bm, x0, x1, -PANE_Y, PANE_Y, Z_BOT1, Z_TOP0, role)
            else:
                out += box(bm, -PANE_Y, PANE_Y, x0, x1, Z_BOT1, Z_TOP0, role)
    return out

def build_lantern(bm):
    # boards, posts
    hb = HW + BOARD_OUT
    box(bm, -hb, hb, -hb, hb, Z_BOT0, Z_BOT1)
    box(bm, -hb, hb, -hb, hb, Z_TOP0, Z_CAP0)
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0, x1 = sorted((sx * HW, sx * (HW - POST))); y0, y1 = sorted((sy * HW, sy * (HW - POST)))
            box(bm, x0, x1, y0, y1, Z_BOT1, Z_TOP0)
    # the top: sheet-iron pyramid cap on the board, punched with vent holes; round vent collar, a small conical hat
    # over it on four posts (the smoke leaves through the gap), the carrying ring through an eye on the hat's tip
    h0 = hb - 0.004
    frustum(bm, h0, Z_CAP0, CAP_HW, Z_CAP1, 'iron')
    holes(bm, h0, CAP_HW)
    lathe(bm, [(0.0, VENT_R), (Z_VENT1 - Z_VENT0, VENT_R), (Z_VENT1 - Z_VENT0, 0.0)], (0, 0, Z_VENT0), segs=12, role='iron')
    lathe(bm, [(0.0, 0.0), (0.0005, VENT_R - 0.004), (0.0006, 0.0)], (0, 0, Z_VENT1), segs=12, role='dark')
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        px, py = (VENT_R - 0.003) * math.cos(a), (VENT_R - 0.003) * math.sin(a)
        box(bm, px - 0.0015, px + 0.0015, py - 0.0015, py + 0.0015, Z_VENT1, Z_HAT0, 'iron')
    lathe(bm, [(0.0, 0.0), (0.0, HAT_R), (0.003, HAT_R), (Z_HAT_TIP - Z_HAT0, 0.004), (Z_HAT_TIP - Z_HAT0 + 0.001, 0.0)],
          (0, 0, Z_HAT0), segs=12, role='iron')
    box(bm, -0.0025, 0.0025, -0.007, 0.007, Z_EYE, -2 * RING_R + 0.002, 'iron')
    torus_yz(bm, (0, 0, -RING_R), RING_R, RING_W)
    # horn panes + middle glazing bars (wood, across each side)
    panes(bm, 0.0, 0.002, 'horn')
    for s in (-1, 1):
        box(bm, s * PANE_X - 0.005, s * PANE_X + 0.005, -PANE_Y, PANE_Y, Z_BAR - 0.006, Z_BAR + 0.006)
        box(bm, -PANE_Y, PANE_Y, s * PANE_X - 0.005, s * PANE_X + 0.005, Z_BAR - 0.006, Z_BAR + 0.006)
    # the door (+x side): a frame round its pane standing proud of the posts, two strap hinges on the +y post with
    # their knuckles at the corner, a hasp over a staple on the -y post
    xo0, xo1 = PANE_X - 0.004, HW + 0.003
    fw = 0.010
    box(bm, xo0, xo1, -PANE_Y, -PANE_Y + fw, Z_BOT1, Z_TOP0)
    box(bm, xo0, xo1, PANE_Y - fw, PANE_Y, Z_BOT1, Z_TOP0)
    box(bm, xo0, xo1, -PANE_Y + fw, PANE_Y - fw, Z_TOP0 - fw, Z_TOP0)
    box(bm, xo0, xo1, -PANE_Y + fw, PANE_Y - fw, Z_BOT1, Z_BOT1 + fw)
    box(bm, xo0, xo1, -PANE_Y + fw, PANE_Y - fw, Z_BAR - 0.006, Z_BAR + 0.006)
    for zh in (Z_TOP0 - 0.035, Z_BOT1 + 0.035):
        box(bm, xo1, xo1 + 0.002, PANE_Y - 0.040, HW - 0.002, zh - 0.006, zh + 0.006, 'iron')
        lathe(bm, [(-0.009, 0.0035), (0.009, 0.0035)], (xo1 + 0.001, HW - 0.001, zh), segs=8, role='iron')
    box(bm, xo1, xo1 + 0.002, -PANE_Y + 0.004, -PANE_Y + 0.030, Z_BAR - 0.006, Z_BAR + 0.006, 'iron')
    box(bm, HW, xo1 + 0.006, -HW + 0.003, -HW + 0.011, Z_BAR - 0.004, Z_BAR + 0.004, 'iron')
    # candle: iron socket on the bottom board (the spike is inside the candle), tallow candle a little burnt down, wick
    lathe(bm, [(0.0, SOCKET_R + 0.004), (0.003, SOCKET_R + 0.004), (0.003, SOCKET_R), (SOCKET_H, SOCKET_R),
               (SOCKET_H, CANDLE_R + 0.001), (SOCKET_H - 0.004, 0.0)], (0, 0, Z_BOT1), segs=12, role='iron')
    zc = Z_BOT1 + SOCKET_H - 0.004
    lathe(bm, [(0.0, CANDLE_R), (CANDLE_H * 0.86, CANDLE_R), (CANDLE_H * 0.86 + 0.003, CANDLE_R * 0.75),
               (CANDLE_H * 0.86 + 0.004, 0.0)], (0, 0, zc), segs=10, role='tallow')
    lathe(bm, [(0.0, 0.0012), (WICK_H, 0.0012), (WICK_H + 0.001, 0.0)], (0, 0, Z_WICK), segs=6, role='dark')

def holes(bm, h0, h1, n=3, segs=8):
    """Punched vent holes on the pyramid cap: dark discs just proud of each face, in a row across it."""
    rise = Z_CAP1 - Z_CAP0
    for k in range(4):
        R = Matrix.Rotation(k * math.pi / 2, 3, 'Z')
        h = h0 + (h1 - h0) * HOLE_T
        up = Vector((h1 - h0, 0.0, rise)).normalized()                 # up the +x face
        nrm = Vector((rise, 0.0, h0 - h1)).normalized()                # out of it
        for i in range(n):
            u = (i - (n - 1) / 2) * h * 0.55
            c = Vector((h, u, Z_CAP0 + rise * HOLE_T)) + nrm * 0.0005
            vs = [bm.verts.new(R @ (c + HOLE_R * (math.cos(2 * math.pi * j / segs) * Vector((0, 1, 0)) +
                                                  math.sin(2 * math.pi * j / segs) * up))) for j in range(segs)]
            f = bm.faces.new(vs); f.normal_update()
            if f.normal.dot(R @ nrm) < 0: f.normal_flip()
            tag([f], 'dark')

def finish(bm, name, roles):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for r in ROLES: me.materials.append(MATS[r])
    for p in me.polygons: p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(40))
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    # only the materials used (the Kit warns about empty slots)
    used = sorted({p.material_index for p in me.polygons})
    idx = [used.index(p.material_index) for p in me.polygons]
    mats = [me.materials[i] for i in used]
    me.materials.clear()
    for m in mats: me.materials.append(m)
    for p, i in zip(me.polygons, idx): p.material_index = i
    assert {m.name for m in me.materials} <= {ROLE[r] for r in roles}, [m.name for m in me.materials]
    return o

def add_uvs(o):
    me = o.data
    uv = me.uv_layers[0] if me.uv_layers else me.uv_layers.new(name='UVMap')
    mat = lambda pi: me.materials[me.polygons[pi].material_index].name
    flat = [p.index for p in me.polygons if mat(p.index) == 'galleass_horn']
    rest = [p.index for p in me.polygons if p.index not in set(flat)]
    if rest:                                       # grain along each piece (grain_uv)
        grain_uv.piece_uvs(me, uv.data, rest, lambda pi: UV_S[mat(pi)], lambda pi: mat(pi) == 'galleass_trim', o.name)
    # horn: each pane shows the whole texture (its streaks and darker rim), u across the side, v up
    for pi in flat:
        p = me.polygons[pi]
        n = p.normal
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            h = co.y if abs(n.x) >= abs(n.y) else co.x
            uv.data[li].uv = ((h + PANE_Y) / (2 * PANE_Y), (co.z - Z_BOT1) / (Z_TOP0 - Z_BOT1))
    col = me.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
    for d in col.data: d.color = (1, 1, 1, 1)

def export(o, lods=()):
    bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o
    for lo in lods: lo.select_set(True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT_FBX, o.name + '.fbx'), use_selection=True, object_types={'MESH'},
                             use_mesh_modifiers=True, mesh_smooth_type='FACE', use_tspace=False, axis_forward='Y',
                             axis_up='Z', apply_unit_scale=True, global_scale=1.0, bake_anim=False, path_mode='STRIP',
                             add_leaf_bones=False)
    print('EXPORT %-34s tris %6d  materials %s  lods %s' % (
        o.name + '.fbx', sum(len(p.vertices) - 2 for p in o.data.polygons), [m.name for m in o.data.materials],
        [sum(len(p.vertices) - 2 for p in lo.data.polygons) for lo in lods]))

os.makedirs(OUT_FBX, exist_ok=True)
bm = bmesh.new(); build_lantern(bm)
lantern = finish(bm, 'galleass_horn_lantern', ('wood', 'iron', 'horn', 'tallow', 'dark'))
add_uvs(lantern)
# LODs: the wick and the tallow (behind the horn) go first, then the iron details
lods = make_lods(lantern, drop={'galleass_dark': 1, 'galleass_sack': 2})
export(lantern, lods)

zs = [v.co.z for v in lantern.data.vertices]
info = {'hook': [0.0, 0.0, 0.0], 'flame': [0.0, 0.0, round(FLAME_Z, 4)],
        'half': round(HW + BOARD_OUT, 4), 'bottom': round(min(zs), 4), 'top': round(max(zs), 4),
        'com': [0.0, 0.0, round((Z_BOT0 + Z_CAP0) / 2, 4)], 'door': '+x'}
json.dump(info, open(os.path.join(HERE, 'ref', 'galleass_lantern.json'), 'w'), indent=1)
print('LANTERN', info)

if RENDERS:
    os.makedirs(RENDERS, exist_ok=True)
    for lo in lods: lo.hide_render = True
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'MATERIAL'
    sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = 900, 1100
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    def shot(fname, loc, tgt, lens=50):
        cam.location = loc; cam.data.lens = lens
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(RENDERS, fname); bpy.ops.render.render(write_still=True)
    shot('lantern_door.png', (0.75, 0.42, -0.05), (0, 0, -0.20))            # door side, from above
    shot('lantern_back.png', (-0.7, -0.5, -0.30), (0, 0, -0.21))             # from the other corner, low
    shot('lantern_top.png', (0.32, 0.20, 0.10), (0, 0, -0.10), 50)           # the cap, vent, hat and ring
    lantern.hide_render = False
    MATS['horn'].diffuse_color = (0.85, 0.62, 0.28, 0.25)                    # see through to the candle
    sc.display.shading.show_xray = True; sc.display.shading.xray_alpha = 0.6
    shot('lantern_inside.png', (0.55, 0.30, -0.20), (0, 0, -0.30), 50)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print('lantern done')
