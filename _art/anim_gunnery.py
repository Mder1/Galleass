"""Gunnery crew clips, scripted first pass (gunnery animations phase 2, 2026-10-20).

    blender -b --factory-startup --python anim_gunnery.py -- <clip> [<gun> ...] [--renders renders/anim]

Clips (so far): rammer - (user 2026-10-24) the near hand puts the ball in the mouth, the sponge-rammer turned round
rams it home (push, regrip, two thrusts) and is drawn out; the ball's place per frame is in the json ('ball').
sponge - the loader swabs the bore of the recoiled gun: sponge just in the muzzle, three strokes with
a small twist at the bottom, draw it out. ladle - the charged ladle goes in scoop up, is turned over at the bottom
(powder out, the game swaps in the empty ladle at 'empty_at'), tapped twice and drawn out scoop down.

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
CLIP, GUNS = argv[0], (argv[1:] or ['falcon'])        # (user 2026-10-20: falcons first, the other guns once
                                                        # the falcon clips work in the game)
REF = os.path.join(HERE, 'ref')
OUT_FBX = os.path.join(HERE, '..', 'AssetSources', 'anim')
OUT_TRACK = os.path.join(REF, 'anim')
FPS = tw_rig.FPS
GUN = json.load(open(os.path.join(REF, 'galleass_guns.json')))
STAFF = json.load(open(os.path.join(REF, 'galleass_stores.json')))['staff']
RECOIL = {'culverin': 1.0, 'falcon': 0.8, 'falconet': 0.6}            # = GalleassGunnery Config defaults
BORE = {'culverin': gp.CV['bore'], 'falcon': gp.FALCON['bore'], 'falconet': gp.FALCONET['bore']}
# load stance in the recoiled gun's frame (right side): off the bore axis, ahead of the muzzle (m)
# Every clip starts and ends in the game's STANDING IDLE (root at 0): the Kit stores the root track relative to the first
# frame, so a clip that began crouched would play that much too high in the game - and it blends from/to the idle
PRE, POST = 16, 16                                            # frames to crouch and take hold / let go and stand up
STAND_BEND = 6.0
AUTHOR_SCALE = 1.07                                           # median soldier scale (Agent.AgentScale; 118 men 2026-10-20:
                                                              # 0.994 .. 1.123, p10 1.021, p90 1.112)
IDLE = ('anim_stand_non_combat', 1.0)                         # the game's unarmed standing idle (stand_non_combat clip), frame
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
    P = PRE                                                  # standing -> crouched with the hands on the staff
    W = 120                                                  # the work itself
    n = P + W + POST
    return {
        'tool': 'galleass_sponge_' + g, 'frames': n,
        'tip_z': 3 * STAFF[g] / 4 + 0.012 + ls,              # the tool's +Z end in its item frame
        'grips': (g_near, g_far),
        # sponge at the mouth -> three full strokes (push in lunging towards the gun, draw back to the mouth; a small twist
        # at the bottom of each) -> pull it right out
        'd': [(0, 0.0), (P + 10, 0.0), (P + 26, dmax), (P + 42, 0.04), (P + 58, dmax), (P + 74, 0.04), (P + 90, dmax),
              (P + 108, -0.05), (n, -0.05)],
        'phi': [(0, 0.0), (P + 22, 0.0), (P + 28, 20.0), (P + 34, 0.0), (P + 54, 0.0), (P + 60, -20.0), (P + 66, 0.0),
                (P + 86, 0.0), (P + 92, 20.0), (P + 98, 0.0), (n, 0.0)],
        'lunge': [(0, 0.0), (P + 10, 0.0), (P + 26, 0.10), (P + 42, 0.03), (P + 58, 0.10), (P + 74, 0.03), (P + 90, 0.10),
                  (P + 108, 0.03), (P + W, 0.03), (n, 0.0)],
        'bend': [(0, STAND_BEND), (P, 40.0), (P + 10, 40.0), (P + 26, 46.0), (P + 42, 43.0), (P + 58, 46.0), (P + 74, 43.0),
                 (P + 90, 46.0), (P + 108, 45.0), (P + W, 45.0), (n, STAND_BEND)],
        'drop': [(0, 0.0), (P, 0.10), (P + 10, 0.10), (P + 26, 0.14), (P + 42, 0.12), (P + 58, 0.14), (P + 74, 0.12),
                 (P + 90, 0.14), (P + 108, 0.13), (P + W, 0.13), (n, 0.0)],
        'grip': [(0, 0.0), (P, 1.0), (P + W, 1.0), (n, 0.0)],             # hands on the staff (0 = hanging at rest)
    }
def ladle_clip(g):
    ls = 0.05 + 2.5 * BORE[g]                                # head block + copper scoop (stores_model build_ladle)
    g_near = 1.8 * BORE[g] + 0.30                            # grips as far from the tip as on the sponge: 0.11 m further
                                                             # out and he can't reach them with the scoop at the mouth
    g_far = g_near + 0.26
    dmax = g_near - 0.10
    P = PRE
    W = 100
    n = P + W + POST
    return {
        # the carried charged ladle goes in; once he has turned it over the game shows the empty one (empty_at)
        'tool': 'galleass_ladle_%s_charged' % g, 'tool_empty': 'galleass_ladle_' + g, 'empty_at': P + 52,
        'frames': n,
        'tip_z': 3 * STAFF[g] / 4 + ls,
        'grips': (g_near, g_far),
        # scoop open side up (roll 180: the item's open side is -Y, the bore frame's Y is up) at the mouth -> eased in
        # level to the bottom -> turned over (powder out) -> two taps on the bore's floor -> drawn out scoop down
        'd': [(0, 0.0), (P + 10, 0.0), (P + 36, dmax), (P + 58, dmax), (P + 61, dmax - 0.03), (P + 64, dmax),
              (P + 67, dmax - 0.03), (P + 70, dmax), (P + 94, -0.05), (n, -0.05)],
        'phi': [(0, 180.0), (P + 40, 180.0), (P + 56, 0.0), (n, 0.0)],
        # the hands' roll on the staff (deg; default half the tool's): neutral at the mouth, where he reaches furthest; at
        # the bottom they take hold for the turn (+45), turn with it (-45) and ease back while drawing it out
        'hroll': [(0, 0.0), (P + 34, 0.0), (P + 40, 45.0), (P + 56, -45.0), (P + 70, -45.0), (P + 94, 0.0), (n, 0.0)],
        'mirror_l': True,                                    # the l side man turns it the mirrored way
        'lunge': [(0, 0.0), (P + 10, 0.0), (P + 36, 0.10), (P + 70, 0.10), (P + 94, 0.03), (P + W, 0.03), (n, 0.0)],
        'bend': [(0, STAND_BEND), (P, 40.0), (P + 10, 40.0), (P + 36, 46.0), (P + 70, 46.0), (P + 94, 44.0), (P + W, 44.0),
                 (n, STAND_BEND)],
        'drop': [(0, 0.0), (P, 0.10), (P + 10, 0.10), (P + 36, 0.14), (P + 70, 0.14), (P + 94, 0.12), (P + W, 0.12), (n, 0.0)],
        'grip': [(0, 0.0), (P, 1.0), (P + W, 1.0), (n, 0.0)],
        'stills': (P + 20, P + 36, P + 50, P + 66, P + 90),
    }
BALL_R = {'culverin': 0.06, 'falcon': 0.038, 'falconet': 0.0265}      # = export_guns.py galleass_shot*
BALL_PALM, BALL_REACH = 0.025, 0.065                          # ball centre in front of the palm / along the fingers (m)

def rammer_clip(g):
    """(user 2026-10-24: the ball goes in by hand, then it is rammed.) The sponge-rammer turned round, rammer end at the
    bore. The far hand holds the staff just behind the head, the head well out of the mouth; the near hand brings the ball
    and pushes it just into the mouth, then takes the staff while the far hand slides back; first push, both hands
    regrip further back, two thrusts down to the sponge's depth, rammer drawn out."""
    rh = 0.06 * (BORE[g] / 2 * 0.9 / 0.056) + 0.02         # rammer head length (stores_model build_sponge)
    r = BALL_R[g]
    gs_near = 1.8 * BORE[g] + 0.30                           # the sponge's grips (reach)
    gs_far = gs_near + 0.26
    dmax = gs_near - 0.10
    d_off = -0.24                                            # rammer head out of the mouth while the ball goes in
    rest = r + 0.007                                         # ball centre just inside the mouth
    P = PRE
    W = 146
    n = P + W + POST
    return {
        'tool': 'galleass_sponge_' + g, 'reverse': True, 'frames': n,
        'tip_z': STAFF[g] / 4 + rh,                          # the rammer (-Z) end in the item frame
        # ball: in the near hand (centre at 'offset' in the hand bone's game frame s, f, u) until 'release', then in the
        # bore at max(rest, rammer depth + radius) (world m)
        'ball': {'mesh': 'galleass_shot_' + g, 'r': r, 'rest': rest, 'release': P + 24,
                 'offset': [BALL_REACH, r / AUTHOR_SCALE + BALL_PALM, 0.0]},
        'grips': ([(0, 0.22), (P + 70, 0.22), (P + 80, gs_near), (n, gs_near)],
                  [(0, 0.20), (P + 34, 0.20), (P + 44, 0.46), (P + 80, 0.46), (P + 90, gs_far), (n, gs_far)]),
        'hands': {'near': [(0, 'hang'), (P, ('ball', -0.10)), (P + 10, ('ball', -0.10)), (P + 20, ('ball', rest)),
                           (P + 24, ('ball', rest)), (P + 34, 'staff'), (P + W, 'staff'), (n, 'hang')],
                  'far': [(0, 'hang'), (P, 'staff'), (P + W, 'staff'), (n, 'hang')]},
        'd': [(0, d_off), (P + 44, d_off), (P + 62, 0.10), (P + 90, 0.10), (P + 100, dmax), (P + 106, dmax - 0.07),
              (P + 112, dmax), (P + 118, dmax), (P + 140, -0.05), (n, -0.05)],
        'phi': [(0, 0.0), (n, 0.0)],
        'lunge': [(0, 0.0), (P, 0.02), (P + 44, 0.02), (P + 62, 0.08), (P + 90, 0.03), (P + 100, 0.11), (P + 106, 0.06),
                  (P + 112, 0.11), (P + 118, 0.10), (P + 140, 0.03), (P + W, 0.03), (n, 0.0)],
        'bend': [(0, STAND_BEND), (P, 42.0), (P + 44, 42.0), (P + 62, 45.0), (P + 90, 43.0), (P + 100, 47.0),
                 (P + 106, 45.0), (P + 112, 47.0), (P + 140, 44.0), (P + W, 44.0), (n, STAND_BEND)],
        'drop': [(0, 0.0), (P, 0.11), (P + 44, 0.11), (P + 62, 0.13), (P + 90, 0.12), (P + 100, 0.15), (P + 112, 0.15),
                 (P + 140, 0.12), (P + W, 0.12), (n, 0.0)],
        'grip': [(0, 0.0), (P, 1.0), (P + W, 1.0), (n, 0.0)],             # body: idle -> working
        'stills': (P + 10, P + 22, P + 40, P + 62, P + 100, P + 130),
    }
CLIPS = {'sponge': sponge_clip, 'ladle': ladle_clip, 'rammer': rammer_clip}

def val(x, k):
    """A constant or keyed value at frame k."""
    return smooth(x, k) if isinstance(x, list) else x

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

def ball_frame(C, w, toward, right_hand, r):
    """Blender bone matrix of a hand pushing a ball (centre C) into the bore (direction w) from behind and from the man's
    side ('toward': unit, perpendicular to w, towards him): palm onto the ball, thumb up (u = up right / -up left)."""
    f = (w - toward * 0.7).normalized()
    up = Vector((0, 0, 1)); up -= f * up.dot(f); up.normalize()
    u = up if right_hand else -up
    s = f.cross(u).normalized()
    wrist = C - f * r - s * BALL_REACH - f * BALL_PALM
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
    # gun frame -> agent frame, shrunk by the soldiers' typical scale: the game scales a clip with the man, so a clip made
    # round a gun 1/S the size fits a man of scale S exactly
    G2A = Matrix.Scale(1.0 / AUTHOR_SCALE, 4) @ Matrix.Rotation(-yaw, 4, 'Z') @ Matrix.Translation(-stance)
    m_a = G2A @ muzzle_g
    w = (G2A.to_3x3() @ Vector((0, -1, 0))).normalized()     # into the bore

    skel, idle = tw_rig.game_data(IDLE[0])
    arm, rest_w = tw_rig.build_armature(skel)
    names = [b for b, _, _ in skel]
    arm.name = name
    pbs = arm.pose.bones
    for b in pbs: b.rotation_mode = 'QUATERNION'
    # the game's standing idle (first and last frames of every clip): its world frames and pose rotations
    rest_l = [tw_rig.rest_local(r) for _, _, r in skel]
    idle_w = tw_rig.world_frames(skel, [tw_rig.local_at(idle['bones'][i], rest_l[i], IDLE[1]) for i in range(len(skel))])
    bpy.context.view_layer.update()
    for i, b in enumerate(names):
        pbs[b].matrix = idle_w[i] @ tw_rig.G2B.to_4x4()
        bpy.context.view_layer.update()
    q_idle = {b: pbs[b].rotation_quaternion.copy() for b in names}
    for b in names: pbs[b].matrix_basis = Matrix()
    bpy.context.view_layer.update()

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
    for hs in ('l', 'r'):                                    # legs: feet planted where the idle has them
        ft = idle_w[names.index(hs + '_foot')]
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
        sgn = -1 if side == 'l' and clip.get('mirror_l') else 1
        dd = smooth(clip['d'], k); phi = sgn * math.radians(smooth(clip['phi'], k))
        hroll = sgn * math.radians(smooth(clip['hroll'], k)) if 'hroll' in clip else phi * 0.5
        bend = smooth(clip['bend'], k); drop = smooth(clip['drop'], k); hold = smooth(clip['grip'], k)
        tip = m_a + w * dd / AUTHOR_SCALE                    # (lengths along the staff shrunk with the gun)
        grips = {'near': tip - w * val(clip['grips'][0], k) / AUTHOR_SCALE, 'far': tip - w * val(clip['grips'][1], k) / AUTHOR_SCALE}
        mid = (grips['near'] + grips['far']) / 2
        twist = math.degrees(math.atan2(-mid.x, mid.y)) * hold   # chest turned towards the hands
        lunge = smooth(clip['lunge'], k) if 'lunge' in clip else 0.0   # body shifted along the staff towards the gun
        wh = Vector((w.x, w.y, 0)).normalized()
        arm.location = wh * lunge + Vector((0, 0, -drop)); arm.keyframe_insert('location', frame=k)
        for bone, b_deg, t_part in (('pelvis', 0.15, 0.25), ('spine', 0.30, 0.25), ('spine1', 0.30, 0.25), ('spine2', 0.25, 0.25)):
            work = spin(bone, (0, 0, 1), twist * t_part) @ spin(bone, (1, 0, 0), -bend * b_deg)
            pbs[bone].rotation_quaternion = q_idle[bone].slerp(work, hold)
            pbs[bone].keyframe_insert('rotation_quaternion', frame=k)
        for bone, deg in (('neck', 0.4), ('head', 0.6)):     # look down at the muzzle
            pbs[bone].rotation_quaternion = q_idle[bone].slerp(spin(bone, (1, 0, 0), bend * deg * 0.6), hold)
            pbs[bone].keyframe_insert('rotation_quaternion', frame=k)
        for bone in ('l_clavicle', 'r_clavicle', 'l_upperarm_twist1', 'r_upperarm_twist1', 'l_foretwist1', 'r_foretwist1',
                     'l_toe0', 'r_toe0'):                    # not posed by the clip: from the idle to rest while working
            pbs[bone].rotation_quaternion = q_idle[bone].slerp(Quaternion(), hold if 'toe' not in bone else 0.0)
            pbs[bone].keyframe_insert('rotation_quaternion', frame=k)
        curl = {}
        for hs in ('l', 'r'):
            P = grips[hand_of[hs]]
            sh = Vector(rest_w[names.index(hs + '_upperarm_twist')].translation) + Vector((0, 0.25, -0.12 - drop))
            toward = (sh - P); toward -= w * toward.dot(w); toward.normalize()
            hanging = idle_w[names.index(hs + '_hand')] @ tw_rig.G2B.to_4x4()
            hanging = Matrix.Translation((0, 0, -drop)) @ hanging
            def target(mode):
                if mode == 'hang': return hanging
                if mode == 'staff': return grip_frame(P, w, toward, hs == 'r', hroll)
                return ball_frame(m_a + w * mode[1] / AUTHOR_SCALE, w, toward, hs == 'r', clip['ball']['r'] / AUTHOR_SCALE)
            if 'hands' in clip:                              # keyed targets per hand (hang / staff / ('ball', depth))
                keys = clip['hands'][hand_of[hs]]
                i = max([j for j, (t, _) in enumerate(keys) if t <= k] or [0]); i = min(i, len(keys) - 2)
                (t0, m0), (t1, m1) = keys[i], keys[i + 1]
                u = min(max((k - t0) / (t1 - t0), 0.0), 1.0); u = u * u * (3 - 2 * u)
                tgt[hs].matrix_world = target(m0).lerp(target(m1), u)
                curl[hs] = (m0 != 'hang') * (1 - u) + (m1 != 'hang') * u
            else:
                tgt[hs].matrix_world = hanging.lerp(target('staff'), hold)
                curl[hs] = hold
            tgt[hs].keyframe_insert('location', frame=k); tgt[hs].keyframe_insert('rotation_euler', frame=k)
        for hs in ('l', 'r'):                                # fingers closed round the staff / ball (vanilla curls finger0
            fb = hs + '_finger0'                             # about its f axis; the tool is no held item, so the
            pbs[fb].rotation_quaternion = q_idle[fb].slerp(Quaternion((-1, 0, 0), math.radians(GRIP_CURL)), curl[hs])   # engine won't close the hand)
            pbs[fb].keyframe_insert('rotation_quaternion', frame=k)
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
            if os.environ.get('ANIM_MISS'): print('MISS %3d %s %.3f' % (k, hs, (want - got).length))
    print('ANIM %s: %d frames, worst hand miss %.3f m (frame %s, %s hand)' % (name, n + 1, worst, *worst_at))
    for o in [o for o in bpy.data.objects if o.type == 'EMPTY']: bpy.data.objects.remove(o)
    clip['yaw'] = yaw
    clip['ball_hand'] = 'l' if near_left else 'r'
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
    tools = [clip['tool']] + ([clip['tool_empty']] if 'tool_empty' in clip else [])
    with bpy.data.libraries.load(os.path.join(REF, 'galleass_stores.blend'), link=False) as (src, dst2):
        dst2.objects = tools
    gun = dst.objects[0]
    sc.collection.objects.link(gun)
    for t in dst2.objects: sc.collection.objects.link(t)
    gun.matrix_world = G2A @ Matrix.Translation((0, -RECOIL[g], 0))
    bpy.ops.mesh.primitive_plane_add(size=6, location=(0, 0, 0)); bpy.context.active_object.name = 'deck'
    bpy.context.active_object.data.materials.append(crew_figure.material('deck', (0.42, 0.36, 0.28, 1)))
    x0 = Vector((0, 0, 1)).cross(w).normalized()
    ball = None
    if 'ball' in clip:
        bpy.ops.mesh.primitive_uv_sphere_add(radius=clip['ball']['r'] / AUTHOR_SCALE, segments=16, ring_count=10)
        ball = bpy.context.active_object; ball.name = 'ball'
        ball.data.materials.append(crew_figure.material('iron', (0.12, 0.12, 0.13, 1)))
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'MATERIAL'; sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = 1000, 800
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    os.makedirs(RENDERS, exist_ok=True)
    for k in clip.get('stills', (0, 40, 64, n_last(track))):
        _, dd, phi = track[k]
        sc.frame_set(k)
        tool = dst2.objects[1 if len(dst2.objects) > 1 and k >= clip['empty_at'] else 0]
        for t in dst2.objects: t.hide_render = t is not tool
        R = Matrix((x0, w.cross(x0), w)).transposed()       # tool frame columns X, Y, Z(= w)
        if clip.get('reverse'):                              # working end at -Z: turned over about X
            R = Matrix((x0, -w.cross(x0), -w)).transposed()
        if ball:
            b = clip['ball']
            if k < b['release']:                             # in the hand: offset in the hand bone's game frame
                hm = arm.matrix_world @ arm.pose.bones[clip['ball_hand'] + '_hand'].matrix
                ball.location = hm @ (tw_rig.G2B.inverted() @ Vector(b['offset']))
            else:
                ball.location = m_a + w * max(b['rest'], dd + b['r']) / AUTHOR_SCALE
        M = (Matrix.Rotation(math.radians(phi), 4, w) @ R.to_4x4())
        M.translation = m_a + (w * dd - w * clip['tip_z']) / AUTHOR_SCALE
        tool.matrix_world = M @ Matrix.Scale(1.0 / AUTHOR_SCALE, 4)
        hands = sum(((arm.matrix_world @ arm.pose.bones[h + '_hand'].head) for h in ('l', 'r')), Vector()) / 2
        views = [('profile', (2.8, 0.25, 1.0), (0.0, 0.25, 0.9), 35), ('front', (-0.9, 2.6, 1.6), (0.0, 0.3, 0.9), 35),
                 ('hands', tuple(hands + Vector((0.35, 0.75, 0.45))), tuple(hands), 50)]
        if ball:                                             # the muzzle from outboard and below the staff
            views.append(('ball', tuple(m_a - w * 0.25 + Vector((-0.5, 0.45, 0.10))), tuple(m_a - w * 0.05), 50))
        for view, loc_c, tgt_c, lens in views:
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
                   **({'tool_empty': clip['tool_empty'], 'empty_at': clip['empty_at']} if 'tool_empty' in clip else {}),
                   **({'reverse': True} if clip.get('reverse') else {}),
                   **({'ball': dict(clip['ball'], hand=clip['ball_hand'])} if 'ball' in clip else {}),
                   'stance': [sx if side == 'r' else -sx, sy], 'yaw': round(clip['yaw'], 5), 'worst_hand_miss': round(worst, 3),
                   'note': 'stance: x off the bore axis, y ahead of the muzzle (gun root frame); yaw: his facing, rad, '
                           '(-sin, cos) in the gun frame; track: frame, '
                           'depth of the tool tip inside the muzzle (m), roll about the staff (deg)',
                   'track': track}, open(os.path.join(OUT_TRACK, name + '.json'), 'w'), indent=0)
        if RENDERS and side == 'r':
            preview(g, side, clip, arm, G2A, m_a, w, track)
print('ANIM done')
