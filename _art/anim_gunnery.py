"""Gunnery crew clips, scripted first pass (gunnery animations phase 2, 2026-10-20).

    blender -b --factory-startup --python anim_gunnery.py -- <clip> [<gun> ...] [--renders renders/anim]

Clips (so far): sponge - the loader swabs the bore of the recoiled gun: sponge just in the muzzle, push in, roll the
staff back and forth, draw it out.

Per gun kind (culverin, falcon, falconet) and side (r: the loader on the gun's +X side, l: mirrored) one clip
galleass_<clip>_<gun>_<side>:
- AGENT FRAME: the clip is made with the man at the origin facing +Y (as every game clip); the gun is placed round him
  from his LOAD STANCE (STANCE below, in the recoiled gun's frame: beside the staff just ahead of the muzzle, turned
  towards the bore - there is no room in front of a recoiled muzzle on the galleass, see gunnery-animations notes).
- TOOL: the tool slides along the bore (depth d of its working end inside the muzzle, roll phi about the staff),
  keyed; the hands hold the staff at two grips. In the game the add-on moves the tool along the gun's bore from the
  same track (ref/anim/<clip name>.json: frames, fps, tool, [frame, d, phi]) - the man only has to stand on his stance.
- POSE: arms by IK (shoulder -> wrist; the twist bones locked), hands copy a grip frame built from the game's hand bone
  axes (palm = bone f, fingers = s, thumb = u right / -u left), legs by IK with the feet planted, body lowered by the
  root track, spine/pelvis keyed. Baked to plain keys, exported with tw_rig.export_fbx to
  AssetSources/anim/<clip name>.fbx (Kit: animation only, skeletal animations on, owner skeleton human_skeleton).
"""
import bpy, json, math, os, sys
from mathutils import Matrix, Quaternion, Vector
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tw_rig, crew_figure
import gun_profiles as gp

argv = sys.argv[sys.argv.index('--') + 1:]
RENDERS = None
if '--renders' in argv:
    i = argv.index('--renders'); RENDERS = argv[i + 1]; argv = argv[:i] + argv[i + 2:]
CLIP, GUNS = argv[0], (argv[1:] or ['culverin', 'falcon', 'falconet'])
REF = os.path.join(HERE, 'ref')
OUT_FBX = os.path.join(HERE, '..', 'AssetSources', 'anim')
OUT_TRACK = os.path.join(REF, 'anim')
FPS = tw_rig.FPS
GUN = json.load(open(os.path.join(REF, 'galleass_guns.json')))
STAFF = json.load(open(os.path.join(REF, 'galleass_stores.json')))['staff']
RECOIL = {'culverin': 1.0, 'falcon': 0.8, 'falconet': 0.6}            # = GalleassGunnery Config defaults
BORE = {'culverin': gp.CV['bore'], 'falcon': gp.FALCON['bore'], 'falconet': gp.FALCONET['bore']}
# load stance in the recoiled gun's frame (right side): off the bore axis, ahead of the muzzle (m)
GRIP_CURL = 55.0                                              # finger0 curl for a closed grip (deg)
STANCE = {'culverin': (0.36, 0.16), 'falcon': (0.34, 0.14), 'falconet': (0.32, 0.10)}

def smooth(keys, t):
    """Value at frame t from [(frame, value)], smoothstep between keys (values may be tuples)."""
    if t <= keys[0][0]: return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            u = (t - t0) / (t1 - t0); u = u * u * (3 - 2 * u)
            if isinstance(v0, tuple): return tuple(a + (b - a) * u for a, b in zip(v0, v1))
            return v0 + (v1 - v0) * u
    return keys[-1][1]

# ---------------------------------------------------------------- clip definitions
def sponge_clip(g):
    ls = 1.8 * BORE[g]                                       # sponge length (stores_model build_sponge)
    g_near = ls + 0.30                                       # grips, from the sponge's tip along the staff
    g_far = g_near + 0.26
    dmax = g_near - 0.10                                     # the near hand stops 10 cm short of the muzzle
    n = 120
    return {
        'tool': 'galleass_sponge_' + g, 'frames': n,
        'tip_z': 3 * STAFF[g] / 4 + 0.012 + ls,              # the tool's +Z end in its item frame
        'grips': (g_near, g_far),
        'd': [(0, 0.20), (14, 0.20), (40, dmax), (86, dmax), (110, 0.14), (n, 0.14)],
        'phi': [(0, 0.0), (40, 0.0), (52, 70.0), (64, -60.0), (76, 60.0), (86, 0.0), (n, 0.0)],
        'bend': [(0, 40.0), (14, 40.0), (40, 46.0), (86, 46.0), (110, 43.0), (n, 43.0)],      # spine forward, deg
        'drop': [(0, 0.10), (14, 0.10), (40, 0.14), (86, 0.14), (110, 0.12), (n, 0.12)],      # pelvis lowered, m
    }
CLIPS = {'sponge': sponge_clip}

# ---------------------------------------------------------------- geometry helpers
def game_frame_to_bone(s, f, u, origin):
    M = Matrix((s, f, u)).transposed().to_4x4()             # columns s, f, u
    M.translation = origin
    return M @ tw_rig.G2B.to_4x4()

def grip_frame(P, w, toward, right_hand, roll):
    """Blender bone matrix of a hand holding the staff at P (staff direction w, towards the tool's working end):
    palm (f) onto the staff from the side 'toward' (unit, perpendicular to w; rolled about w by 'roll' rad), thumb
    towards the working end (u = w right, -w left), fingers s = f x u; the wrist set back from the grip."""
    a = Quaternion(w, roll) @ toward
    f = -a
    u = w if right_hand else -w
    s = f.cross(u).normalized()
    wrist = P + a * 0.045 - s * 0.07
    return game_frame_to_bone(s, f, u, wrist)

def build(g, side, clip):
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    for a in list(bpy.data.actions): bpy.data.actions.remove(a)
    sc = bpy.context.scene; sc.render.fps = FPS
    name = 'galleass_%s_%s_%s' % (CLIP, g, side)
    sc.name = name
    mx = 1 if side == 'r' else -1
    d = GUN['galleass_' + g]; rc = RECOIL[g]
    sx, sy = STANCE[g]
    stance = Vector((mx * sx, d['muzzle_y'] - rc + sy, 0.0))
    muzzle_g = Vector((0.0, d['muzzle_y'] - rc, d['axis_h']))
    aim = Vector((0.0, muzzle_g.y + 0.75, 0.0))              # he faces a point on the axis ahead of the muzzle
    yaw = math.atan2(-(aim.x - stance.x), aim.y - stance.y)
    G2A = Matrix.Rotation(-yaw, 4, 'Z') @ Matrix.Translation(-stance)   # gun frame -> agent frame
    m_a = G2A @ muzzle_g
    w = (G2A.to_3x3() @ Vector((0, -1, 0))).normalized()     # into the bore

    skel, _ = tw_rig.game_data()
    arm, rest_w = tw_rig.build_armature(skel)
    names = [b for b, _, _ in skel]
    arm.name = name
    pbs = arm.pose.bones
    for b in pbs: b.rotation_mode = 'QUATERNION'

    def empty(nm, size=0.05):
        e = bpy.data.objects.new(nm, None); e.empty_display_size = size; sc.collection.objects.link(e); return e
    # hands: the one nearer the muzzle (sideways) takes the near grip
    near_left = m_a.x < 0
    hand_of = {'l': 'near' if near_left else 'far', 'r': 'far' if near_left else 'near'}
    tgt = {}
    for hs in ('l', 'r'):
        t = empty('ik_%s_hand' % hs); tgt[hs] = t
        ik = pbs[hs + '_foretwist1'].constraints.new('IK'); ik.target = t; ik.chain_count = 4; ik.use_stretch = False
        pole = empty('pole_%s_elbow' % hs)
        sh = rest_w[names.index(hs + '_upperarm_twist')].translation
        pole.location = sh + Vector((0.45 if hs == 'r' else -0.45, -0.35, -0.45))    # elbows out, back and down
        ik.pole_target = pole; ik.pole_angle = math.radians(-90)
        cr = pbs[hs + '_hand'].constraints.new('COPY_ROTATION'); cr.target = t
        for b in (hs + '_upperarm_twist1', hs + '_foretwist1'):
            pbs[b].lock_ik_x = pbs[b].lock_ik_y = pbs[b].lock_ik_z = True
        for b in (hs + '_upperarm_twist', hs + '_foretwist'):
            pbs[b].ik_stretch = 0.0
    for hs in ('l', 'r'):                                    # legs: feet planted where they stand at rest
        ft = rest_w[names.index(hs + '_foot')]
        t = empty('ik_%s_foot' % hs); t.matrix_world = ft @ tw_rig.G2B.to_4x4()
        ik = pbs[hs + '_calf'].constraints.new('IK'); ik.target = t; ik.chain_count = 2; ik.use_tail = True
        pole = empty('pole_%s_knee' % hs); pole.location = rest_w[names.index(hs + '_calf')].translation + Vector((0, 0.6, 0))
        ik.pole_target = pole; ik.pole_angle = math.radians(-90)
        cr = pbs[hs + '_foot'].constraints.new('COPY_ROTATION'); cr.target = t

    clip['n'] = n = clip['frames']
    sc.frame_start, sc.frame_end = 0, n
    arm.animation_data_create()
    act = bpy.data.actions.new(name); arm.animation_data.action = act
    local_axis = {b.name: b.matrix_local.to_3x3().inverted() for b in arm.data.bones}
    def spin(bone, axis, deg):
        return Quaternion(local_axis[bone] @ Vector(axis), math.radians(deg))
    track = []
    for k in range(n + 1):
        dd = smooth(clip['d'], k); phi = math.radians(smooth(clip['phi'], k))
        bend = smooth(clip['bend'], k); drop = smooth(clip['drop'], k)
        tip = m_a + w * dd
        grips = {'near': tip - w * clip['grips'][0], 'far': tip - w * clip['grips'][1]}
        mid = (grips['near'] + grips['far']) / 2
        twist = math.degrees(math.atan2(-mid.x, mid.y))     # chest turned towards the hands
        arm.location = (0, 0, -drop); arm.keyframe_insert('location', frame=k)
        for bone, b_deg, t_part in (('pelvis', 0.15, 0.25), ('spine', 0.30, 0.25), ('spine1', 0.30, 0.25), ('spine2', 0.25, 0.25)):
            pbs[bone].rotation_quaternion = spin(bone, (0, 0, 1), twist * t_part) @ spin(bone, (1, 0, 0), -bend * b_deg)
            pbs[bone].keyframe_insert('rotation_quaternion', frame=k)
        for bone, deg in (('neck', 0.4), ('head', 0.6)):     # look down at the muzzle
            pbs[bone].rotation_quaternion = spin(bone, (1, 0, 0), bend * deg * 0.6)
            pbs[bone].keyframe_insert('rotation_quaternion', frame=k)
        for hs in ('l', 'r'):                                # fingers closed round the staff (vanilla curls finger0
            fb = hs + '_finger0'                             # about its f axis; the tool is no held item, so the
            pbs[fb].rotation_quaternion = Quaternion((-1, 0, 0), math.radians(GRIP_CURL))   # engine won't close the hand)
            pbs[fb].keyframe_insert('rotation_quaternion', frame=k)
        for hs in ('l', 'r'):
            P = grips[hand_of[hs]]
            sh = Vector(rest_w[names.index(hs + '_upperarm_twist')].translation) + Vector((0, 0.25, -0.12 - drop))
            toward = (sh - P); toward -= w * toward.dot(w); toward.normalize()
            tgt[hs].matrix_world = grip_frame(P, w, toward, hs == 'r', phi * 0.5)
            tgt[hs].keyframe_insert('location', frame=k); tgt[hs].keyframe_insert('rotation_euler', frame=k)
        track.append([k, round(dd, 4), round(math.degrees(phi), 2)])

    # bake to plain keys
    bpy.context.view_layer.objects.active = arm
    for o in bpy.context.selected_objects: o.select_set(False)
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='POSE')
    for b in arm.pose.bones:                                 # (Blender 5: selection lives on the pose bone)
        if hasattr(b, "select"): b.select = True
        else: b.bone.select = True
    bpy.ops.nla.bake(frame_start=0, frame_end=n, only_selected=True, visual_keying=True, clear_constraints=True,
                     use_current_action=True, bake_types={'POSE'})
    bpy.ops.object.mode_set(mode='OBJECT')
    # how well the hands reach their grips (IK may fall short)
    worst, worst_at = 0.0, None
    for k in range(0, n + 1, 5):
        sc.frame_set(k)
        for hs in ('l', 'r'):
            want = tgt[hs].matrix_world.translation
            got = arm.matrix_world @ arm.pose.bones[hs + '_hand'].head
            if (want - got).length > worst: worst, worst_at = (want - got).length, (k, hs)
    print('ANIM %s: %d frames, worst hand miss %.3f m (frame %s, %s hand)' % (name, n + 1, worst, *worst_at))
    for o in [o for o in bpy.data.objects if o.type == 'EMPTY']: bpy.data.objects.remove(o)
    return arm, act, track, G2A, m_a, w, worst

def preview(g, side, clip, arm, G2A, m_a, w, track):
    """Skinned figure, the recoiled gun and the sponge, a few stills."""
    sc = bpy.context.scene
    act = arm.animation_data.action
    arm.animation_data.action = None                        # skin in the rest pose
    for b in arm.pose.bones: b.matrix_basis = Matrix()
    loc = arm.location.copy(); arm.location = (0, 0, 0)
    bpy.context.view_layer.update()
    crew_figure.figure(g + side, (0.55, 0.62, 0.75, 1), arm=arm)
    arm.animation_data.action = act; arm.location = loc
    with bpy.data.libraries.load(os.path.join(REF, 'galleass_guns.blend'), link=False) as (src, dst):
        dst.objects = ['galleass_' + g]
    with bpy.data.libraries.load(os.path.join(REF, 'galleass_stores.blend'), link=False) as (src, dst2):
        dst2.objects = [clip['tool']]
    gun = dst.objects[0]; tool = dst2.objects[0]
    sc.collection.objects.link(gun); sc.collection.objects.link(tool)
    gun.matrix_world = G2A @ Matrix.Translation((0, -RECOIL[g], 0))
    bpy.ops.mesh.primitive_plane_add(size=6, location=(0, 0, 0)); bpy.context.active_object.name = 'deck'
    bpy.context.active_object.data.materials.append(crew_figure.material('deck', (0.42, 0.36, 0.28, 1)))
    x0 = Vector((0, 0, 1)).cross(w).normalized()
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'MATERIAL'; sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = 1000, 800
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    os.makedirs(RENDERS, exist_ok=True)
    for k in (0, 40, 64, n_last(track)):
        _, dd, phi = track[k]
        sc.frame_set(k)
        R = Matrix((x0, w.cross(x0), w)).transposed()       # tool frame columns X, Y, Z(= w)
        M = (Matrix.Rotation(math.radians(phi), 4, w) @ R.to_4x4())
        M.translation = m_a + w * dd - w * clip['tip_z']
        tool.matrix_world = M
        hands = sum(((arm.matrix_world @ arm.pose.bones[h + '_hand'].head) for h in ('l', 'r')), Vector()) / 2
        for view, loc_c, tgt_c, lens in (('profile', (2.8, 0.25, 1.0), (0.0, 0.25, 0.9), 35),
                                         ('front', (-0.9, 2.6, 1.6), (0.0, 0.3, 0.9), 35),
                                         ('hands', tuple(hands + Vector((0.35, 0.75, 0.45))), tuple(hands), 50)):
            cam.location = loc_c; cam.data.lens = lens
            cam.rotation_euler = (Vector(tgt_c) - Vector(loc_c)).to_track_quat('-Z', 'Y').to_euler()
            sc.render.filepath = os.path.join(RENDERS, '%s_%03d_%s.png' % (sc.name, k, view))
            bpy.ops.render.render(write_still=True)

def n_last(track):
    return track[-1][0]

os.makedirs(OUT_FBX, exist_ok=True); os.makedirs(OUT_TRACK, exist_ok=True)
for g in GUNS:
    for side in ('r', 'l'):
        clip = CLIPS[CLIP](g)
        arm, act, track, G2A, m_a, w, worst = build(g, side, clip)
        name = arm.name
        tw_rig.export_fbx(arm, os.path.join(OUT_FBX, name + '.fbx'))
        sx, sy = STANCE[g]
        json.dump({'clip': name, 'fps': FPS, 'frames': clip['n'], 'tool': clip['tool'], 'tip_z': clip['tip_z'],
                   'stance': [sx if side == 'r' else -sx, sy], 'worst_hand_miss': round(worst, 3),
                   'note': 'stance: x off the bore axis, y ahead of the recoiled muzzle (gun frame); track: frame, '
                           'depth of the tool tip inside the muzzle (m), roll about the staff (deg)',
                   'track': track}, open(os.path.join(OUT_TRACK, name + '.json'), 'w'), indent=0)
        if RENDERS and side == 'r':
            preview(g, side, clip, arm, G2A, m_a, w, track)
print('ANIM done')
