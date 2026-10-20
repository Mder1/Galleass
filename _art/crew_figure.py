"""Crew figure for the gunnery animation scenes (anim_ref.py, anim_gunnery.py): the game's human_skeleton (tw_rig.py)
skinned with Blender's automatic weights to the vanilla body_male_a + head_male_a + hands_male_a (core_game.tpac, extracted with
tpac_tools/mesh_extract.py into ref/anim_meshes/) and knee-high boots (the body ends at the shin) - crude, only to
judge reach and clearances. Bannerlord characters face +Y; the armature's rest is the game's A-pose.
"""
import bpy, bmesh, math, os, subprocess
from mathutils import Vector
import tw_rig
HERE = os.path.dirname(os.path.abspath(__file__))
NATIVE_CORE = os.path.join(HERE, '..', '..', 'Native', 'AssetPackages', 'core_game.tpac')
MESH_DIR = os.path.join(HERE, 'ref', 'anim_meshes')

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
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    return o

def material(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = rgba
    return m

SKEL = None

def figure(tag, rgba, arm=None):
    """Armature + skinned body; returns the armature object (move/rotate it to place the figure)."""
    global SKEL
    if SKEL is None:
        SKEL = tw_rig.game_data()[0]
    if arm is None:                                          # (or skin an existing armature, e.g. an animated one)
        arm, rest_w = tw_rig.build_armature(SKEL)
        arm.name = 'crew_' + tag
    else:
        rest_w = [arm.matrix_world @ b.matrix_local @ tw_rig.G2B.to_4x4().inverted() for b in arm.data.bones]
    arm.data.display_type = 'STICK'
    names = [n for n, _, _ in SKEL]
    parts = [import_lod0(extract(m), m.split('_')[0] + '_' + tag) for m in ('body_male_a', 'head_male_a', 'hands_male_a')]
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

