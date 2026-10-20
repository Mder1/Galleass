"""Reference scene for the gunnery crew animations (phase 1, 2026-10-20).

    blender -b --factory-startup --python anim_ref.py -- ref/gunnery_anim.blend [renders/anim_ref]

Per gun kind (culverin, falcon, falconet; the petriera later) side by side along X, 4 m apart:
- the gun from ref/galleass_guns.blend at its game frame, RECOILED (loading happens with the gun run in: moved -Y by
  the add-on's Recoil; GalleassGunnery Config RecoilCulverin/Falcon/Falconet), zero elevation;
- a LOADER figure on the game's loader spot (GunLoading.LoaderSpot case 1: x = half width + 0.40, y = muzzle - recoil
  - 0.30, facing -X across the gun) and a GUNNER figure beside the breech on the other side facing +X, the touch hole
  within arm's reach;
- the props from ref/galleass_stores.blend (charged ladle, sponge-rammer, linstock) laid by the figures;
- empties marking the targets the clips must reach: muzzle mouth, touch hole, spots.
Writes ref/gunnery_anim.json (targets in each gun's frame, recoiled; z above the deck) for anim_gunnery.py.

Figure: the game's human_skeleton (tw_rig.py) skinned with Blender's automatic weights to the vanilla body_male_a +
head_male_a (core_game.tpac, extracted with tpac_tools/mesh_extract.py into ref/anim_meshes/) and knee-high boots (the
body ends at the shin) - crude, only to judge reach and clearances. Bannerlord characters face +Y; the armature's rest
is the game's A-pose.
"""
import bpy, bmesh, json, math, os, subprocess, sys
from mathutils import Matrix, Vector
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tw_rig

argv = sys.argv[sys.argv.index('--') + 1:]
OUT_BLEND, RENDERS = argv[0], (argv[1] if len(argv) > 1 else None)
REF = os.path.join(HERE, 'ref')
NATIVE_CORE = os.path.join(HERE, '..', '..', 'Native', 'AssetPackages', 'core_game.tpac')
MESH_DIR = os.path.join(REF, 'anim_meshes')
GUNS = ('culverin', 'falcon', 'falconet')
RECOIL = {'culverin': 1.0, 'falcon': 0.8, 'falconet': 0.6}            # = GalleassGunnery Config defaults
SPACING = 4.0
MUZZLE_SIDE = {'culverin': 0.50, 'falcon': 0.42, 'falconet': 0.38}     # load stance off the bore axis (m)
STAFF = json.load(open(os.path.join(REF, 'galleass_stores.json')))['staff']
GUN = json.load(open(os.path.join(REF, 'galleass_guns.json')))

for o in list(bpy.data.objects): bpy.data.objects.remove(o)
sc = bpy.context.scene
sc.render.fps = tw_rig.FPS

# ---------------------------------------------------------------- vanilla body meshes
def extract(name):
    obj = os.path.join(MESH_DIR, name + '.obj')
    if not os.path.exists(obj):
        os.makedirs(MESH_DIR, exist_ok=True)
        subprocess.run(['python3', os.path.join(HERE, 'tpac_tools', 'mesh_extract.py'), NATIVE_CORE, MESH_DIR, name], check=True)
    return obj

def import_lod0(path, name):
    """The OBJ holds one object per LOD (name.0 .. name.N); keep the densest."""
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path, forward_axis='Y', up_axis='Z')
    new = [o for o in bpy.data.objects if o not in before]
    keep = max(new, key=lambda o: len(o.data.vertices))
    for o in new:
        if o is not keep: bpy.data.objects.remove(o)
    keep.name = keep.data.name = name
    return keep

def boot(foot_head, toe_head, calf_head, name):
    """Knee-high boot (the vanilla body mesh ends at the shin): hull of a sole from heel to past the toe and a ring
    round the calf; skinned with the body."""
    bm = bmesh.new()
    fwd = Vector((toe_head.x - foot_head.x, toe_head.y - foot_head.y, 0)).normalized()
    side = Vector((fwd.y, -fwd.x, 0))
    heel, tip = foot_head - fwd * 0.07, toe_head + fwd * 0.07
    for p, w, h in ((heel, 0.045, 0.10), (toe_head, 0.05, 0.07), (tip, 0.035, 0.05)):
        for sx in (-1, 1):
            for z in (0.0, h):
                bm.verts.new(Vector((p.x, p.y, 0)) + side * sx * w + Vector((0, 0, z)))
    c = Vector((calf_head.x, calf_head.y, 0))
    for zt, r in ((0.25, 0.055), (calf_head.z - 0.04, 0.06)):
        for k in range(10):
            a = 2 * math.pi * k / 10
            bm.verts.new(c + Vector((r * math.cos(a), r * math.sin(a), zt)))
    bmesh.ops.convex_hull(bm, input=bm.verts)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); sc.collection.objects.link(o)
    return o

def material(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = rgba
    return m

SKEL, _ = tw_rig.game_data()

def figure(tag, rgba):
    """Armature + skinned body; returns the armature object (move/rotate it to place the figure)."""
    arm, rest_w = tw_rig.build_armature(SKEL)
    arm.name = 'crew_' + tag
    arm.data.display_type = 'STICK'
    names = [n for n, _, _ in SKEL]
    parts = [import_lod0(extract('body_male_a'), 'body_' + tag), import_lod0(extract('head_male_a'), 'head_' + tag)]
    for side in ('l', 'r'):
        parts.append(boot(rest_w[names.index(side + '_foot')].translation, rest_w[names.index(side + '_toe0')].translation,
                          rest_w[names.index(side + '_calf')].translation, 'boot_%s_%s' % (side, tag)))
    mat = material('crew_' + tag, rgba)
    for p in parts:
        p.data.materials.clear(); p.data.materials.append(mat)
        for poly in p.data.polygons: poly.use_smooth = True
    bpy.ops.object.select_all(action='DESELECT')
    for p in parts: p.select_set(True)
    arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    return arm

# ---------------------------------------------------------------- guns and props
def append(blend, names):
    with bpy.data.libraries.load(blend, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in names]
    out = {}
    for o in dst.objects:
        if o is None: continue
        sc.collection.objects.link(o); out[o.name] = o
    return out

guns = append(os.path.join(REF, 'galleass_guns.blend'), ['galleass_%s%s' % (g, s) for g in GUNS for s in ('', '_fuse')])
props = append(os.path.join(REF, 'galleass_stores.blend'),
               ['galleass_ladle_%s_charged' % g for g in GUNS] + ['galleass_sponge_%s' % g for g in GUNS] + ['galleass_linstock'])

def empty(name, loc, size=0.05, kind='SPHERE'):
    e = bpy.data.objects.new(name, None); e.empty_display_type = kind; e.empty_display_size = size
    e.location = loc; sc.collection.objects.link(e)
    return e

def world_bbox(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)])

targets = {}
loader_col, gunner_col = (0.55, 0.62, 0.75, 1), (0.75, 0.58, 0.50, 1)
for i, g in enumerate(GUNS):
    d = GUN['galleass_' + g]
    X, rc = i * SPACING, RECOIL[g]
    gun, fuse = guns['galleass_' + g], guns['galleass_%s_fuse' % g]
    for o in (gun, fuse): o.location = (X, -rc, 0)
    bpy.context.view_layer.update()
    lo, hi = world_bbox(fuse)                                  # the priming quill stands in the vent: its foot is the hole
    vent = Vector(((lo.x + hi.x) / 2 - X, (lo.y + hi.y) / 2, lo.z))
    muzzle = Vector((0, d['muzzle_y'] - rc, d['axis_h']))
    loader = Vector((d['half_w'] + 0.40, d['muzzle_y'] - rc - 0.30, 0))     # the game's waiting/loading spot (formula)
    # LOAD STANCE (2026-10-20): ladle and rammer go in along the bore, their staffs running out through the port, and
    # there is only 0.2-0.6 m between a recoiled muzzle and the bulwark - so the loader works BESIDE the muzzle, his
    # shoulders level with it, turned 45 deg towards the bore axis, hands on the staff just ahead of the muzzle
    stance = Vector((MUZZLE_SIDE[g], d['muzzle_y'] - rc - 0.05, 0))
    stance_yaw = math.atan2(stance.x, (muzzle.y + 0.40) - stance.y)       # faces a point 0.4 m ahead on the axis
    gunner = Vector((-(d['half_w'] + 0.45), vent.y + 0.15, 0))
    targets[g] = {'recoil': rc, 'axis_h': d['axis_h'], 'bore': None, 'muzzle': list(muzzle), 'vent': list(vent),
                  'loader': list(loader) + [math.pi / 2], 'load_stance': list(stance) + [stance_yaw], 'gunner': list(gunner) + [-math.pi / 2],
                  'staff': STAFF[g]}
    off = Vector((X, 0, 0))
    empty('muzzle_' + g, muzzle + off, 0.04)
    empty('vent_' + g, vent + off, 0.02)
    empty('loader_spot_' + g, loader + off, 0.25, 'CIRCLE').rotation_euler = (math.pi / 2, 0, 0)
    empty('gunner_spot_' + g, gunner + off, 0.25, 'CIRCLE').rotation_euler = (math.pi / 2, 0, 0)
    empty('load_stance_' + g, stance + off, 0.25, 'CIRCLE').rotation_euler = (math.pi / 2, 0, 0)
    ld = figure('loader_' + g, loader_col); ld.location = stance + off; ld.rotation_euler = (0, 0, stance_yaw)
    gn = figure('gunner_' + g, gunner_col); gn.location = gunner + off; gn.rotation_euler = (0, 0, -math.pi / 2)  # faces +X
    # props on the deck beside the figures: ladle and sponge along the gun outboard of the loader, linstock stuck
    # upright in the deck in front of the gunner
    for k, name in enumerate(('galleass_ladle_%s_charged' % g, 'galleass_sponge_%s' % g)):
        p = props[name]
        p.location = (X + d['half_w'] + 0.85 + 0.12 * k, loader.y - STAFF[g] / 4 - 0.3, 0.04)
        p.rotation_euler = (-math.pi / 2, 0, 0)                 # staff along +Y, head forward (towards the muzzle end)
    if g == 'culverin':
        ls = props['galleass_linstock']
    else:
        ls = bpy.data.objects.new('galleass_linstock_' + g, props['galleass_linstock'].data); sc.collection.objects.link(ls)
    ls.location = (X + gunner.x + 0.35, gunner.y + 0.25, 1.1 / 4 + 0.05)   # spike 5 cm into the deck

# deck planes under each gun for a ground reference
bpy.ops.mesh.primitive_plane_add(size=1, location=(SPACING, 0, 0))
deck = bpy.context.active_object; deck.name = 'deck'; deck.scale = (SPACING * 3 + 2, 9, 1)
deck.data.materials.append(material('deck', (0.42, 0.36, 0.28, 1)))

json.dump({'note': 'gun frame, recoiled; x right, y forward (muzzle), z up from the deck; spots = x, y, yaw '
                   '(rad, Bannerlord RotateAboutUp: pi/2 faces -X)', 'guns': targets},
          open(os.path.join(REF, 'gunnery_anim.json'), 'w'), indent=1)
print('ANIMREF targets', json.dumps({g: {k: [round(v, 3) for v in t[k]] for k in ('muzzle', 'vent', 'loader', 'load_stance', 'gunner')} for g, t in targets.items()}))

# ---------------------------------------------------------------- reach check in the rest pose (A-pose): how far the
# hands are from the targets with the figure standing on its spot - phase 2 poses close these gaps
for g, t in targets.items():
    X = GUNS.index(g) * SPACING
    for who, tgt in (('loader', 'muzzle'), ('gunner', 'vent')):
        arm = bpy.data.objects['crew_%s_%s' % (who, g)]
        bpy.context.view_layer.update()
        sh = arm.matrix_world @ arm.pose.bones['r_upperarm_twist'].head
        hand = arm.matrix_world @ arm.pose.bones['r_hand'].head
        tv = Vector(t[tgt]) + Vector((X, 0, 0))
        print('ANIMREF %-8s %-6s -> %-6s shoulder %.2f m, hand %.2f m (shoulder height %.2f, target %.2f)'
              % (g, who, tgt, (tv - sh).length, (tv - hand).length, sh.z, tv.z))

# ---------------------------------------------------------------- renders
if RENDERS:
    os.makedirs(RENDERS, exist_ok=True)
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'MATERIAL'
    sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    def shot(fname, loc, tgt, lens=35):
        cam.location = loc; cam.data.lens = lens
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(RENDERS, fname); bpy.ops.render.render(write_still=True)
    shot('anim_ref_all.png', (SPACING, -9.5, 4.5), (SPACING, 0, 0.6), 30)
    for i, g in enumerate(GUNS):
        X = i * SPACING
        shot('anim_ref_%s.png' % g, (X + 3.2, -3.4, 2.2), (X, -0.3, 0.8), 30)
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print('ANIMREF done')
