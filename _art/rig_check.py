"""Rig checker: replays where the game puts the galleass's running ropes, over each yard's whole swing.

The braces (sail_rotate_pulleys), sheet pulleys and sheets (stability_ropes_parent) keep no deck end of their own: every
tick NavalDLC's SailVisual.TickRopesAndPulleys (BLSource v1.5.5) gives each the nearest knot_point(s) of the ship's
knob_points_parent - braces / stability pulleys FindClosestTwoKnobPoint (knots on one side of the yard: index 0 the
side the yard's forward axis points to, index 1 the other; horizontal distance < 'Rope Connection Max Distance', ranked
in 3D), sheets FindClosestKnobPoint (3D distance; keeps the decompiled quirk of storing the XY distance), and when
none qualifies FindClosestPointFallback (nearest knot in XY, no side, no limit). This script does the same for every
yaw in the sail's limits (galleass_mission_ships.xml), with the lateen roll (+-'Lateen Roll Degrees' about the roll
entity's y, yard_shift x = +-'Lateen Yard Shift', switched by yaw with the 'Lateen Roll Change Degree Limit'
hysteresis - both roll states are checked inside the hysteresis band).

Free bones are taken at their prefab rest frames (the game adds a small wind push); the fold / unfold / roll animations
(when the ropes are not re-picked) are not covered.

usage: python3 rig_check.py <packed xml>[,<base packed xml>] [--strict] [--verbose]
       (from Modules/Galleass: python3 _art/rig_check.py AssetPackages/nested_prefabs_packed.xml,../NavalDLC/AssetPackages/nested_prefabs_packed.xml)
--strict: exit 1 on any error (build_prefab / install use it).
--dump=<json>: the picked ropes per rig and yaw (first roll state), for rig_preview.py's RUNTIME mode.
"""
import math, os, sys
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prefab_layout as PL

HERE = os.path.dirname(os.path.abspath(__file__))
SHIP = 'galleass_ship_nested'
MISSION_SHIPS = os.path.join(HERE, '..', 'ModuleData', 'galleass_mission_ships.xml')
# deck surfaces (ship frame) for the 'rope through the ship' test - galleass_model / build_prefab values
Z_DECK, Z_POOP_TOP, Z_FC, Z_CAP = 3.8, 6.92, 6.3, 5.30
X_IN = 6.0                                     # bulwark inner face
Y_POOP_FRONT, Y_FC_BACK = -14.5, 18.6
FC_CY, FC_R = 21.6, 3.85                       # forecastle: round front, straight sides
YAW_STEP = 5

# --- 4x4 frames: (m, p), m 3x3 row-major as prefab_layout ---------------------------------------------------------
def mmul(a, b): return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
def mvec(a, v): return [sum(a[i][k] * v[k] for k in range(3)) for i in range(3)]
def inv3(m):
    a, b, c = m[0]; d, e, f = m[1]; g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]
def fmul(A, B): return (mmul(A[0], B[0]), [A[1][i] + mvec(A[0], B[1])[i] for i in range(3)])
def finv(A):
    mi = inv3(A[0]); return (mi, [-v for v in mvec(mi, A[1])])
def frame(row): return (row['mat'], row['pos'])
def rot_z(a):
    c, s = math.cos(a), math.sin(a); return [[c, -s, 0], [s, c, 0], [0, 0, 1]]
def rot_y(a):
    c, s = math.cos(a), math.sin(a); return [[c, 0, s], [0, 1, 0], [-s, 0, c]]
def sub(a, b): return [a[i] - b[i] for i in range(3)]
def dot(a, b): return sum(a[i] * b[i] for i in range(3))
def d2(a, b): return sum((a[i] - b[i]) ** 2 for i in range(3))
def d2xy(a, b): return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2

# --- engine selection, as decompiled ------------------------------------------------------------------------------
def sgn(v):
    return (v > 0) - (v < 0)

def closest_two(pos, knots, side, maxd, square=False):
    # square sails also want the knot on the bone's side of the centre line (Sign(x) equal; lateens don't)
    lim, best, bd = maxd * maxd, [-1, -1], [1e12, 1e12]
    for i, k in enumerate(knots):
        if k['right'] != side or (square and sgn(k['pos'][0]) != sgn(pos[0])):
            continue
        l = d2(pos, k['pos'])
        if d2xy(pos, k['pos']) < lim:
            if l < bd[0]:
                bd[1], best[1], bd[0], best[0] = bd[0], best[0], l, i
            elif l < bd[1]:
                bd[1], best[1] = l, i
    return best

def closest_one(pos, knots, side, maxd, square=False):
    lim, res, num2 = maxd * maxd, -1, 1e12
    for i, k in enumerate(knots):
        if k['right'] == side and not (square and sgn(k['pos'][0]) != sgn(pos[0])):
            l = d2(pos, k['pos'])
            if l < num2 and l < lim:
                res, num2 = i, d2xy(pos, k['pos'])       # (sic: compares 3D, keeps XY)
    return res

def fallback(pos, knots):
    return min(range(len(knots)), key=lambda i: d2xy(pos, knots[i]['pos'])) if knots else -1

# --- prefab -------------------------------------------------------------------------------------------------------
def under(rows, row):
    p = row['path'] + '/'
    return [r for r in rows if r['path'].startswith(p)]

def first(rows, tag):
    return next((r for r in rows if tag in r['tags']), None)

def sail_limits():
    """[(left, right)] per sail index of the galleass in galleass_mission_ships.xml (degrees)."""
    t = ET.parse(MISSION_SHIPS).getroot()
    out = []
    for ship in t.iter():
        if ship.get('id', '').startswith('galleass') or 'galleass' in (ship.get('prefab', '') + ship.get('id', '')):
            for s in ship.iter('sail'):
                out.append((float(s.get('left_rotation_limit', 170)), float(s.get('right_rotation_limit', 5))))
            if out:
                break
    return out

def rig_role(y):
    return 'sprit' if y > 26 else 'fore' if y > 12 else 'main' if y > -5 else 'mizzen'

def through_ship(a, b):
    """Does the straight rope a-b run through a deck or the bulwark (not counting 0.3 m at each end)?"""
    L = math.dist(a, b)
    n = max(2, int(L / 0.2))
    for i in range(n + 1):
        t = i / n
        if t * L < 0.3 or (1 - t) * L < 0.3:
            continue
        p = [a[j] + (b[j] - a[j]) * t for j in range(3)]
        x, y, z = abs(p[0]), p[1], p[2]
        fc_in = y > Y_FC_BACK and x < math.sqrt(max(FC_R ** 2 - max(y - FC_CY, 0.0) ** 2, 0.0))
        floor = Z_POOP_TOP if y < Y_POOP_FRONT else Z_FC if fc_in else Z_DECK   # (beside the round forecastle: deck)
        if x < X_IN and z < floor - 0.05:
            return 'below the deck at (%.1f, %.1f, %.1f)' % tuple(p)
        if X_IN <= x < X_IN + 0.3 and z < Z_CAP - 0.05 and -17.6 < y < 20.6:
            return 'through the bulwark at (%.1f, %.1f, %.1f)' % tuple(p)
    return None

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    strict, verbose = '--strict' in sys.argv, '--verbose' in sys.argv
    dump_path = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--dump=')), None)
    dump = {}
    PL.load(args[0])
    rows = PL.layout(SHIP)
    root = next(r for r in rows if r['path'].count('/') == 1)
    kp = first(rows, 'knob_points_parent')
    knots = []
    if kp is not None:
        for r in under(rows, kp):
            if 'knot_point' in r['tags']:
                knots.append({'pos': r['pos'], 'name': '%s(%.2f, %.2f, %.2f)' % (r['path'].split('/')[-2], *r['pos'])})
    limits = sail_limits()
    errors, warns, used = [], [], set()
    print('%d knot points' % len(knots))
    rigs = [r for r in rows if 'sail_visual' in r['scripts']]
    rigs.sort(key=lambda r: [x for x in r['tags'] if x.startswith('sail_center_')] or [''])
    for idx, rig in enumerate(rigs):
        sub_rows = under(rows, rig)
        v = PL.script_vars(rig['el'], 'sail_visual')
        maxd = float(v.get('Rope Connection Max Distance', 7))
        roll_deg = float(v.get('Lateen Roll Degrees', 45))
        shift = float(v.get('Lateen Yard Shift', 0))
        lim = float(v.get('Lateen Roll Change Degree Limit', 20))
        yaw_e = next(r for r in rows if r['path'].startswith(rig['path'] + '/') and 'yaw_rotation_entity' in r['tags']
                     and r['path'].count('/') == rig['path'].count('/') + 1)
        roll_e = first(under(rows, yaw_e), 'roll_rotation_entity')
        square = roll_e is None                                   # a square rig (the spritsail): yard and sail on the yaw
        if square:                                                # entity itself, no lateen roll / yard shift
            roll_e = shift_e = yaw_e
            roll_deg = shift = 0.0
        else:
            shift_e = next(r for r in under(rows, roll_e) if 'yard_shift' in r['tags'] and r['path'].count('/') == roll_e['path'].count('/') + 1)
        skel = first(under(rows, shift_e), 'sail_mesh_entity')
        yard = first(under(rows, shift_e), 'sail_yard')
        bones = {r['name']: r for r in under(rows, skel) if 'free_bone' in r['tags']}
        # pulleys / ropes per bone (child order kept)
        pp = next(r for r in sub_rows if 'pulley_systems_parent' in (r['name'], *r['tags']))   # (square rigs name them
        def kids(parent_name):                                                                   # differently: by tag)
            par = next((r for r in under(rows, pp) if parent_name in (r['name'], *r['tags'])), None)
            if par is None:
                return []
            return [r for r in under(rows, par) if r['path'].count('/') == par['path'].count('/') + 1]
        def bone_of(r, skip):
            return next((t for t in r['tags'] if t not in skip and t in bones), None)
        rot = {}
        for r in kids('sail_rotate_pulleys'):
            b = bone_of(r, ('pulley_system',))
            if b: rot.setdefault(b, []).append(r)
        stab_p, stab_r = {}, {}
        for r in kids('stability_ropes_parent'):
            if 'simple_rope' in r['tags']:
                b = bone_of(r, ('simple_rope',))
                if b: stab_r.setdefault(b, []).append(r)
            else:
                b = bone_of(r, ('pulley_system',))
                if b: stab_p.setdefault(b, []).append(r)
        if square:                                                # its bone entities keep stale rest frames: the
            for b_, r_ in list(bones.items()):                    # corner is where vanilla's own ropes end on it
                for r in under(rows, pp):
                    if b_ in r['tags']:
                        mine = {id(x) for x in r['el'].iter('entity')}            # (sibling paths are not unique)
                        end = next((x for x in under(rows, r) if id(x['el']) in mine and x['name'] in ('end_target_point', 'rope_end')
                                    and ('attached_to_yard' in x['tags'] or x['name'] == 'end_target_point')), None)
                        if end is not None:
                            bones[b_] = end
                            break
        role = rig_role(rig['pos'][1])
        left, right = limits[idx] if idx < len(limits) else (170, 5)
        print('\n== %s rig (%s, y %.1f): max distance %.1f, roll %.0f, shift %.2f, yaw %g..%g; bones %s; braces %s, '
              'sheet pulleys %s, sheets %s' % (role, rig['name'], rig['pos'][1], maxd, roll_deg, shift, -right, left,
              sorted(bones), {b: len(x) for b, x in rot.items()}, {b: len(x) for b, x in stab_p.items()},
              {b: len(x) for b, x in stab_r.items()}))
        Wyaw = frame(yaw_e)
        L_roll = fmul(finv(Wyaw), frame(roll_e))
        L_shift = fmul(finv(frame(roll_e)), frame(shift_e))
        R_yard = fmul(finv(frame(shift_e)), frame(yard))
        R_bone = {b: fmul(finv(frame(shift_e)), frame(r)) for b, r in bones.items()}
        Wroot = frame(root)
        picks = {}                                                # (rope, leg) -> {knot index: [yaws]}
        def record(key, i, yaw, how):
            picks.setdefault(key, {}).setdefault((i, how), []).append(yaw)
        yaws = list(range(int(-right), int(left) + 1, YAW_STEP))
        for yaw in yaws:
            y180 = yaw
            while y180 > 180: y180 -= 180
            while y180 < -180: y180 += 180
            if square: states = [1]
            elif y180 < -lim - 90 or y180 > lim + 90: states = [-1]
            elif lim - 90 < y180 < 90 - lim: states = [1]
            else: states = [1, -1]
            for st in states:
                frame_dump = None
                if st == states[0]:
                    frame_dump = dump.setdefault(str(yaw), {}).setdefault(role, {'bones': {}, 'ropes': []})
                Y = (mmul(Wyaw[0], rot_z(math.radians(yaw))), Wyaw[1])
                Lr = (rot_y(math.radians(roll_deg * st)), L_roll[1])
                Ls = (L_shift[0], [shift * st, L_shift[1][1], L_shift[1][2]])
                S = fmul(fmul(Y, Lr), Ls)
                yd = fmul(S, R_yard)
                yf = [yd[0][0][1], yd[0][1][1], yd[0][2][1]]
                for k in knots:
                    k['right'] = dot(sub(k['pos'], yd[1]), yf) > 0
                for b in bones:
                    bp = fmul(S, R_bone[b])[1]
                    if frame_dump is not None:
                        frame_dump['bones'][b] = bp
                    for kind, lst in (('brace', rot.get(b, [])), ('sheet pulley', stab_p.get(b, []))):
                        if len(knots) > 1:
                            for n, r in enumerate(lst[:2]):
                                two = closest_two(bp, knots, n == 0, maxd, square)
                                for leg, i in zip(('fixed', 'free'), two):
                                    how = 'ok'
                                    if i == -1:
                                        i, how = fallback(bp, knots), 'FALLBACK'
                                    record((kind, b, n, leg), i, yaw, how)
                                    if frame_dump is not None:
                                        frame_dump['ropes'].append([kind, knots[i]['pos'], bp])
                                    rope_err = through_ship(knots[i]['pos'], bp)
                                    if rope_err:
                                        record((kind, b, n, leg + ' THROUGH SHIP ' + rope_err.split(' at')[0]), i, yaw, 'ERR')
                    for n, r in enumerate(stab_r.get(b, [])[:2]):
                        if knots:
                            i = closest_one(bp, knots, n == 0, maxd, square)
                            how = 'ok'
                            if i == -1:
                                i, how = fallback(bp, knots), 'FALLBACK'
                            record(('sheet', b, n, 'start'), i, yaw, how)
                            if frame_dump is not None:
                                frame_dump['ropes'].append(['sheet', knots[i]['pos'], bp])
        for key in sorted(picks, key=str):
            res = picks[key]
            parts = []
            for (i, how), ys in sorted(res.items(), key=lambda kv: -len(kv[1])):
                parts.append('%s %s x%d' % (knots[i]['name'], '' if how == 'ok' else how, len(ys)))
                if how == 'FALLBACK':
                    errors.append('%s %s %s #%d %s: FALLBACK to %s at %d yaw steps' % (role, key[0], key[1], key[2], key[3], knots[i]['name'], len(ys)))
                if how == 'ERR':
                    errors.append('%s %s %s #%d %s to %s at %d yaw steps' % (role, key[0], key[1], key[2], key[3], knots[i]['name'], len(ys)))
            print('  %-58s %s' % ('%s %s #%d %s' % key, '; '.join(parts)))
        for res in picks.values():
            used.update(i for i, _ in res)
    # static rope ends and anything in the water / outboard
    for r in rows:
        if r['name'] in ('rope_start', 'rope_end') and 'simple_rope' not in r['tags'] and abs(r['mat'][0][0]) + abs(r['mat'][1][1]) > 0.01:   # (hidden: shrunk)
            x, y, z = r['pos']
            if z < 8.0 and (z < 3.5 or abs(x) > 6.3 or y < -25 or y > 25.6):     # (aloft: yard lifts beyond the bow)
                warns.append('rope end %s at (%.2f, %.2f, %.2f): outboard / low' % (r['path'][-70:], x, y, z))
    idle = [knots[i]['name'] for i in range(len(knots)) if i not in used]
    if idle:
        warns.append('%d pins no brace or sheet ever uses: %s' % (len(idle), ', '.join(idle)))
    print('\n%d errors, %d warnings' % (len(errors), len(warns)))
    for e in errors: print('ERROR', e)
    for w in warns: print('WARN ', w)
    if dump_path:
        import json
        json.dump({'knots': [k['pos'] for k in knots], 'yaws': dump}, open(dump_path, 'w'))
    if strict and errors:
        sys.exit(1)

if __name__ == '__main__':
    main()
