"""The captain's command table on the poop (user 2026-10-25), built parametrically, UV'd, exported for the Modding Kit.

    blender -b --factory-startup --python helm_model.py -- ref/galleass_helm.blend ../AssetSources/export [renders/helm]

The ship's control point (ShipControl_nested) is where the captain stands giving orders, not a helmsman: a 16th-century
Venetian galleass was steered by the rudder's tiller directly (a whipstaff would be anachronistic, a modelled tiller
would clip), and the game turns the stern rudder by itself (ShipControllerMachine: the rudder_rotation_entity, as
there is no 'controller' child). The vanilla captain idle rests the right hand forward, the left at the hip; the
prefab lets the game put only the right hand on the table (_isRightHandOnly).

Mesh galleass_command_desk (material galleass_trim = oak, galleass_iron = straps / bolts), ORIGIN ON THE DECK AT THE
MIDDLE OF THE DESK'S AFT EDGE, +Y FORWARD: four legs, a top sloping up forward with a lip on its low (aft) edge and a
level ledge along its high (fore) edge behind a small gallery rail (writing-slope style: the inkwell stands level), a
shelf low down, iron straps at the feet. With one box collision body bo_galleass_command_desk.
On it (user 2026-10-25), VANILLA props placed by the prefab: an open logbook on the slope, inkwell + quill and two
rolled charts on the ledge (DRESSING).
The hand point (the right wrist, just beyond the lip), the footprint, the slope frame and the props go to
ref/galleass_helm.json.
"""
import bpy, bmesh, json, math, os, subprocess, sys
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:]
OUT_BLEND, OUT_FBX, RENDERS = argv[0], argv[1], (argv[2] if len(argv) > 2 else None)
HERE = os.path.dirname(os.path.abspath(__file__))

ROLE = {'wood': 'galleass_trim', 'iron': 'galleass_iron'}
UV_S = {'galleass_trim': 0.135, 'galleass_iron': 0.5}
COL = {'wood': (0.36, 0.24, 0.14, 1), 'iron': (0.16, 0.16, 0.17, 1)}
ROLES = list(ROLE)

DESK = dict(y0=0.0, y1=0.56,   half=0.48,        # top: aft / fore edge, half width
            z0=0.98, rise=0.12 / 0.56, top=0.04,   # top surface at the aft edge, slope (z per y), thickness
            ledge_y=0.37, rail=0.02,            # level ledge from here to the fore edge; its gallery rail (h = t)
            leg=0.06, inset=0.05, apron=0.09, shelf_z=0.24, shelf_t=0.03, lip=0.025)
SLOPE = math.atan(DESK['rise'])
HAND = (0.25, 0.10)                             # right hand: to starboard of the middle, forward of the aft edge
WRIST_DZ = 0.04                                 # hand bone origin (wrist) above the top it rests on

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

def box(bm, x0, x1, y0, y1, z0, z1, role='wood'):
    hexa(bm, [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
              (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], role)

def lathe(bm, prof, at, segs=12, role='wood', axis='z'):
    """Closed solid of revolution about +Z at 'at' (or about +X: axis 'x'): prof = [(along, r)], r 0 closes an end."""
    M = Matrix.Rotation(math.pi / 2, 3, 'Y') if axis == 'x' else Matrix.Identity(3)
    def P(v): return Vector(at) + M @ Vector(v)
    rings = []
    for z, r in prof:
        if r <= 0:
            rings.append([bm.verts.new(P((0, 0, z)))])
        else:
            rings.append([bm.verts.new(P((r * math.cos(2 * math.pi * k / segs), r * math.sin(2 * math.pi * k / segs), z)))
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

def bolt(bm, x, y, z, axis='z', out=1, r=0.010, l=0.008):
    """Bolt head on a face: a short cylinder from (x, y, z) along +-axis ('z' or 'x', out = +1 / -1)."""
    lathe(bm, [(0.0, r), (l, r)] if out > 0 else [(-l, r), (0.0, r)], (x, y, z), segs=8, role='iron', axis=axis)

def top_z(y):
    """The desk top's surface at y: the slope from the aft edge up to the ledge, then level."""
    d = DESK
    return d['z0'] + d['rise'] * (min(y, d['ledge_y']) - d['y0'])

LEDGE_Z = top_z(DESK['ledge_y'])
# the props on the table: vanilla meshes (Native), (name, mesh, frame, (x, y, z), yaw). Frame 'slope' = the sloping top
# (origin on its surface at the aft edge, y up the slope), 'desk' = the desk's own frame (props on the ledge)
_SL = (DESK['ledge_y'] - DESK['y0']) / math.cos(SLOPE)                   # slope length up to the ledge
DRESSING = [
    ('logbook', 'lib_book_open_b', 'slope', (-0.17, 0.21, 0.0), 0.0),      # 0.51 x 0.33, clear of the hand (x +0.25)
    ('inkwell', 'lib_inkwell', 'desk', (-0.32, 0.455, LEDGE_Z), 0.0),       # 0.16 dia
    ('quill', 'lib_quill_pen', 'desk', (-0.32, 0.455, LEDGE_Z), 0.0),       # (authored on the inkwell's origin)
    ('chart_1', 'lib_scroll_c', 'desk', (0.13, 0.43, LEDGE_Z + 0.006), 1.52),     # rolls (0.37 long on y), athwartships
    ('chart_2', 'lib_scroll_c', 'desk', (0.20, 0.495, LEDGE_Z + 0.006), 1.64),
]
PROP_PKG = {'lib_book_open_b': 'meshes_shared_4', 'lib_inkwell': 'building_details', 'lib_quill_pen': 'meshes_shared_0',
            'lib_scroll_c': 'building_details'}                          # (Native AssetPackages, for the preview)
assert 0.165 + 0.03 <= DRESSING[0][3][1] <= _SL - 0.165, 'logbook off the slope'
assert DRESSING[1][3][1] - 0.08 >= DESK['ledge_y'] and DRESSING[1][3][1] + 0.08 <= DESK['y1'] - DESK['rail'], 'inkwell'


def build_desk(bm):
    d = DESK
    hx, y0, y1, t, L, ins = d['half'], d['y0'], d['y1'], d['top'], d['leg'], d['inset']
    # the top: sloped slab, level ledge, lip along the low (aft) edge, gallery rail along the ledge's fore edge
    yl = d['ledge_y']
    hexa(bm, [(-hx, y0, top_z(y0) - t), (hx, y0, top_z(y0) - t), (hx, yl, top_z(yl) - t), (-hx, yl, top_z(yl) - t),
              (-hx, y0, top_z(y0)), (hx, y0, top_z(y0)), (hx, yl, top_z(yl)), (-hx, yl, top_z(yl))])
    box(bm, -hx, hx, yl, y1, LEDGE_Z - t, LEDGE_Z)
    box(bm, -hx, hx, y0, y0 + 0.025, top_z(y0) - 0.005, top_z(y0) + d['lip'])
    box(bm, -hx, hx, y1 - d['rail'], y1, LEDGE_Z - 0.005, LEDGE_Z + d['rail'])
    # legs at the corners, inset under the top; apron frame round their heads, its top under the slab
    lx0, lx1 = -hx + ins, hx - ins
    ly0, ly1 = y0 + ins, y1 - ins
    def under(y): return top_z(y) - t
    for x in (lx0, lx1):
        for y in (ly0, ly1):
            hexa(bm, [(x - L / 2, y - L / 2, 0.0), (x + L / 2, y - L / 2, 0.0), (x + L / 2, y + L / 2, 0.0), (x - L / 2, y + L / 2, 0.0),
                      (x - L / 2, y - L / 2, under(y - L / 2)), (x + L / 2, y - L / 2, under(y - L / 2)),
                      (x + L / 2, y + L / 2, under(y + L / 2)), (x - L / 2, y + L / 2, under(y + L / 2))])
    a, at = d['apron'], 0.022
    for y in (ly0, ly1):                                        # aft / fore aprons (level)
        yy0, yy1 = (y - L / 2, y - L / 2 + at) if y == ly0 else (y + L / 2 - at, y + L / 2)
        box(bm, lx0 + L / 2, lx1 - L / 2, yy0, yy1, under(yy1 if y == ly0 else yy0) - a, under(yy1 if y == ly0 else yy0))
    for x in (lx0, lx1):                                        # side aprons (follow the slope, then level)
        xx0, xx1 = (x - L / 2, x - L / 2 + at) if x == lx0 else (x + L / 2 - at, x + L / 2)
        for ya, yb in ((ly0 + L / 2, yl), (yl, ly1 - L / 2)):
            hexa(bm, [(xx0, ya, under(ya) - a), (xx1, ya, under(ya) - a), (xx1, yb, under(yb) - a), (xx0, yb, under(yb) - a),
                      (xx0, ya, under(ya)), (xx1, ya, under(ya)), (xx1, yb, under(yb)), (xx0, yb, under(yb))])
    # shelf low down between the legs (notched round them: four boards fill between)
    sz, st = d['shelf_z'], d['shelf_t']
    box(bm, lx0 + L / 2, lx1 - L / 2, ly0 - L / 2, ly1 + L / 2, sz - st, sz)
    # iron straps at the feet, outboard faces, a bolt each into the deck and the leg
    for x in (lx0, lx1):
        s = 1 if x > 0 else -1
        for y in (ly0, ly1):
            xo = x + s * L / 2
            box(bm, min(xo, xo + s * 0.006), max(xo, xo + s * 0.006), y - 0.02, y + 0.02, 0.0, 0.12, 'iron')
            box(bm, min(xo, xo + s * 0.07), max(xo, xo + s * 0.07), y - 0.02, y + 0.02, 0.0, 0.006, 'iron')
            bolt(bm, xo + s * 0.045, y, 0.006)                          # into the deck
            bolt(bm, xo + s * 0.006, y, 0.08, 'x', s)                    # into the leg

def finish(bm, name):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for m in MATS.values(): me.materials.append(m)
    for p in me.polygons: p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(40))
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    return o

def add_uvs(o):
    me = o.data
    uv = me.uv_layers[0] if me.uv_layers else me.uv_layers.new(name='UVMap')
    for poly in me.polygons:
        n = poly.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        i, j = [k for k in range(3) if k != ax]
        s = UV_S[ROLE[ROLES[poly.material_index]]]
        for li in poly.loop_indices:
            p = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (p[i] * s, p[j] * s)
    col = me.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
    for d in col.data: d.color = (1, 1, 1, 1)

def export(o):
    bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT_FBX, o.name + '.fbx'), use_selection=True, object_types={'MESH'},
                             use_mesh_modifiers=True, mesh_smooth_type='FACE', use_tspace=False, axis_forward='Y',
                             axis_up='Z', apply_unit_scale=True, global_scale=1.0, bake_anim=False, path_mode='STRIP',
                             add_leaf_bones=False)
    print('EXPORT %-30s tris %6d  materials %s' % (o.name + '.fbx', sum(len(p.vertices) - 2 for p in o.data.polygons),
                                                    [m.name for m in o.data.materials]))

def body(o):
    """The desk's footprint box (build_prefab cuts it from the navmesh). Not exported any more: the table has no
    physics (user 2026-10-27: a body keeps walkers a capsule radius, 0.37 m, off the table)."""
    xs, ys, zs = zip(*[v.co for v in o.data.vertices])
    bm = bmesh.new()
    box(bm, min(xs), max(xs), min(ys), max(ys), 0.0, max(zs))
    name = 'bo_' + o.name
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    me.materials.append(bpy.data.materials.get('wood') or bpy.data.materials.new('wood'))
    bo = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(bo)
    return bo, (min(xs), max(xs), min(ys), max(ys), max(zs))

bm = bmesh.new()
build_desk(bm)
helm = finish(bm, 'galleass_command_desk')
add_uvs(helm); helm.data.name = helm.name
os.makedirs(OUT_FBX, exist_ok=True)
export(helm)
bo, foot = body(helm)
hand = (HAND[0], HAND[1], round(top_z(HAND[1]) + WRIST_DZ, 4))
json.dump({'hand': hand, 'desk': DESK, 'foot': [round(v, 4) for v in foot],    # foot = x0, x1, y0, y1, height (desk frame)
           'slope': {'origin': [0.0, DESK['y0'], DESK['z0']], 'pitch': round(SLOPE, 5)},
           'props': [{'name': n, 'mesh': m, 'frame': f, 'pos': [round(v, 4) for v in p], 'yaw': y}
                     for n, m, f, p, y in DRESSING]},
          open(os.path.join(HERE, 'ref', 'galleass_helm.json'), 'w'), indent=1)

if RENDERS:
    os.makedirs(RENDERS, exist_ok=True)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'MATERIAL'
    sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = 1400, 900
    bo.hide_render = True
    deck = bpy.data.meshes.new('deck'); b2 = bmesh.new(); box(b2, -1.5, 1.5, -1.5, 1.5, -0.05, 0.0); b2.to_mesh(deck); b2.free()
    sc.collection.objects.link(bpy.data.objects.new('deck', deck))
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    def shot(fname, loc, tgt, lens=35):
        cam.location = loc; cam.data.lens = lens
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(RENDERS, fname); bpy.ops.render.render(write_still=True)
    # the vanilla props as the prefab places them (meshes extracted by the system Python: Blender's has no lz4)
    PROPS = os.path.join(HERE, 'ref', 'props')
    native = os.path.join(HERE, '..', '..', 'Native', 'AssetPackages')
    for mesh, pkg in PROP_PKG.items():
        if not os.path.exists(os.path.join(PROPS, mesh + '.obj')):
            subprocess.run(['python3', os.path.join(HERE, 'tpac_tools', 'mesh_extract.py'),
                            os.path.join(native, pkg + '.tpac'), PROPS, mesh], check=True, capture_output=True)
    slope = Matrix.Translation((0.0, DESK['y0'], DESK['z0'])) @ Matrix.Rotation(SLOPE, 4, 'X')
    for name, mesh, frame, pos, yaw in DRESSING:
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.wm.obj_import(filepath=os.path.join(PROPS, mesh + '.obj'), forward_axis='Y', up_axis='Z')
        local = Matrix.Translation(pos) @ Matrix.Rotation(yaw, 4, 'Z')
        for o in bpy.context.selected_objects:
            o.matrix_world = (slope @ local) if frame == 'slope' else local
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.03, location=hand)      # the hand point
    mk = bpy.context.active_object; mk.color = (1, 0, 0, 1); sc.display.shading.color_type = 'OBJECT'
    for o in sc.objects:
        if o is not mk and o.type == 'MESH':
            o.color = (0.36, 0.24, 0.14, 1) if o.name.startswith(('galleass', 'deck')) else (0.85, 0.82, 0.72, 1)
    shot('desk_quarter.png', (1.9, -1.8, 1.8), (0.0, 0.2, 0.7), 35)        # from aft, starboard quarter
    shot('desk_captain.png', (0.0, -0.75, 1.65), (0.0, 0.4, 1.0), 30)      # the captain's view
    shot('desk_front.png', (-1.4, 2.0, 1.5), (0.0, 0.2, 0.6), 35)          # from forward, port bow
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print('helm done')
