"""Bannerlord human skeleton + animations in Blender (gunnery animations, 2026-10-19).

    blender -b --factory-startup --python tw_rig.py -- <out.blend> <out.fbx> [<source animation> <frame0> <frame1>]

Builds the armature 'human_skeleton_notused' from Native's human_skeleton (tpac_tools/anim_read.py, run by the system Python) and, with an
animation name, keys that source animation (animations.tpac) from frame0 to frame1 at 30 fps; then exports the FBX
for the Modding Kit and checks it by importing it again (bone world positions against the game data).

Axes: a game bone frame has rows s, f, u (images of the bone's local x, y, z; the bone points along x). Blender bones
point along their local Y, so a Blender bone gets Y = s, Z = u, X = -f; the FBX export maps them back (primary bone axis
X = Blender Y, secondary -Y = Blender X), so the FBX's bone frames are the game's. Z up, forward Y, metres, as the
Kit's mesh imports. Root motion (the animation's root position track) keys the armature object.
"""
import bpy, math, os, sys
from mathutils import Matrix, Quaternion, Vector
HERE = os.path.dirname(os.path.abspath(__file__))
import json, subprocess
NATIVE = os.path.join(HERE, '..', '..', 'Native', 'AssetPackages')
FPS = 30
ARM = 'human_skeleton_notused'
# game frame (columns s, f, u) -> Blender bone frame (columns X, Y, Z) = (-f, s, u)
G2B = Matrix(((0, 1, 0), (-1, 0, 0), (0, 0, 1)))       # columns: X_b = -f, Y_b = s, Z_b = u (applied on the right)

def game_data(anim_name=None):
    """Skeleton (+ a source animation) from the game, read by the system Python (Blender's has no lz4)."""
    cmd = ['python3', os.path.join(HERE, 'tpac_tools', 'anim_read.py'), 'json', NATIVE] + ([anim_name] if anim_name else [])
    d = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    if anim_name and d['anim'] is None:
        raise SystemExit('no source animation %s' % anim_name)
    return d['skeleton'], d['anim']

def rest_local(rows):
    s, f, u, o = rows
    m = Matrix(((s[0], f[0], u[0]), (s[1], f[1], u[1]), (s[2], f[2], u[2]))).to_4x4()
    m.translation = Vector(o)
    return m

def sample(track, t, default):
    """Linear (slerp for quaternions) value of a track at frame t."""
    if not track:
        return default
    if t <= track[0][0]:
        return track[0][1]
    for (t0, v0), (t1, v1) in zip(track, track[1:]):
        if t0 <= t <= t1:
            k = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            if len(v0) == 4:
                q0 = Quaternion((v0[3], v0[0], v0[1], v0[2])); q1 = Quaternion((v1[3], v1[0], v1[1], v1[2]))
                q = q0.slerp(q1, k)
                return (q.x, q.y, q.z, q.w)
            return tuple(a + (b - a) * k for a, b in zip(v0, v1))
    return track[-1][1]

def local_at(bone, rest, t):
    q = sample(bone['rot'], t, None)
    m = rest.copy() if q is None else Quaternion((q[3], q[0], q[1], q[2])).to_matrix().to_4x4()
    p = sample(bone['pos'], t, None)
    m.translation = Vector(p) if p is not None else rest.translation
    return m

def world_frames(skel, locals_):
    out = []
    for i, (name, parent, _) in enumerate(skel):
        out.append(locals_[i] if parent < 0 else out[parent] @ locals_[i])
    return out

def build_armature(skel):
    arm = bpy.data.armatures.new(ARM)
    obj = bpy.data.objects.new(ARM, arm)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    rest_w = world_frames(skel, [rest_local(r) for _, _, r in skel])
    eb = []
    for i, (name, parent, rows) in enumerate(skel):
        b = arm.edit_bones.new(name)
        kids = [j for j, (_, p, _) in enumerate(skel) if p == i]
        length = max((rest_w[j].translation - rest_w[i].translation).length for j in kids) if kids else 0.08
        b.length = max(length, 0.03)
        b.matrix = rest_w[i] @ G2B.to_4x4()
        if parent >= 0:
            b.parent = eb[parent]
        eb.append(b)
    bpy.ops.object.mode_set(mode='OBJECT')
    return obj, rest_w

def key_anim(obj, skel, anim, f0, f1):
    rest_l = [rest_local(r) for _, _, r in skel]
    obj.animation_data_create()
    act = bpy.data.actions.new(anim['name'])
    obj.animation_data.action = act
    sc = bpy.context.scene
    sc.render.fps = FPS
    n = int(round(f1 - f0))
    sc.frame_start, sc.frame_end = 0, n
    for k in range(n + 1):
        t = f0 + k
        sc.frame_set(k)
        w = world_frames(skel, [local_at(anim['bones'][i], rest_l[i], t) if i < len(anim['bones']) else rest_l[i]
                                for i in range(len(skel))])
        for i, (name, _, _) in enumerate(skel):
            pb = obj.pose.bones[name]
            pb.matrix = w[i] @ G2B.to_4x4()
            bpy.context.view_layer.update()
        for i, (name, _, _) in enumerate(skel):
            pb = obj.pose.bones[name]
            pb.keyframe_insert('rotation_quaternion', frame=k); pb.keyframe_insert('location', frame=k)
        rp = sample(anim['root_pos'], t, (0, 0, 0))
        obj.location = Vector(rp); obj.keyframe_insert('location', frame=k)
    return n

def export_fbx(obj, path):
    bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'ARMATURE'}, add_leaf_bones=False,
                             primary_bone_axis='X', secondary_bone_axis='-Y', armature_nodetype='NULL',
                             axis_forward='Y', axis_up='Z', apply_unit_scale=True, global_scale=1.0,
                             bake_anim=obj.animation_data is not None, bake_anim_use_all_actions=False,
                             bake_anim_use_nla_strips=False, bake_anim_simplify_factor=0.0,
                             bake_anim_force_startend_keying=True, path_mode='STRIP')

def check_fbx(path, skel, expect, frames):
    """Import the FBX into a fresh scene and compare bone heads (world) with the game's at some frames."""
    sc = bpy.data.scenes.new('check'); bpy.context.window.scene = sc
    bpy.ops.import_scene.fbx(filepath=path, automatic_bone_orientation=False, primary_bone_axis='X',
                             secondary_bone_axis='-Y', axis_forward='Y', axis_up='Z')
    imp = next(o for o in sc.objects if o.type == 'ARMATURE')
    act = imp.animation_data.action if imp.animation_data else None
    k0 = int(round(act.frame_range[0])) if act else 0          # (the importer starts the action at frame 1)
    worst = 0.0
    for k in frames:
        sc.frame_set(k + k0)
        for i, (name, _, _) in enumerate(skel):
            got = (imp.matrix_world @ imp.pose.bones[name].matrix).translation
            worst = max(worst, (got - expect[k][i]).length)
    print('RIG check: worst bone position error %.4f m over frames %s' % (worst, frames))
    return worst

if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:]
    out_blend, out_fbx = argv[0], argv[1]
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    skel, anim = game_data(argv[2] if len(argv) >= 5 else None)
    obj, rest_w = build_armature(skel)
    print('RIG armature %s: %d bones' % (ARM, len(skel)))
    expect, frames = {0: rest_w}, [0]
    if len(argv) >= 5:
        f0, f1 = float(argv[3]), float(argv[4])
        n = key_anim(obj, skel, anim, f0, f1)
        rest_l = [rest_local(r) for _, _, r in skel]
        frames = sorted({0, n // 2, n})
        for k in frames:
            t = f0 + k
            w = world_frames(skel, [local_at(anim['bones'][i], rest_l[i], t) for i in range(len(skel))])
            rp = Vector(sample(anim['root_pos'], t, (0, 0, 0)))
            expect[k] = [Matrix.Translation(rp) @ m for m in w]
        print('RIG keyed %s frames %g..%g (%d frames at %d fps)' % (anim['name'], f0, f1, n + 1, FPS))
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    export_fbx(obj, out_fbx)
    print('RIG exported', out_fbx)
    check_fbx(out_fbx, skel, {k: [m.translation for m in v] for k, v in expect.items()}, frames)
