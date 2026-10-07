"""Build the galleass ship prefab from the meditheavy clone (make_packed_clone.py output).

python3 build_prefab.py <NavalDLC packed xml> <clone xml> <out xml>

Stage 1 (hull swap): our meshes + physics shapes replace the meditheavy ones, the meditheavy-only geometry is
removed, the rudder becomes a centreline stern rudder and the figureheads move to the beak. Everything else (oars,
sails, slots, spawn/boarding points, ...) still sits where the meditheavy has it; stage 2 relays it out.

Nested prefab entities inherit missing elements (transform, tags, components, physics, children, ...) from the
entity their <prefab guid> points to (NavalDLC base prefabs). Before removing something from such an entity it is
flattened: the inherited elements are copied in and the base link is cut, so nothing comes back through inheritance.
"""
import copy, math, os, re, sys, uuid
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model_geom
G = model_geom.load()      # the model's geometry; its z constants are UNLIFTED design values: + Z_LIFT above the cut
LIFT = G['Z_LIFT']

nav_path, clone_path, out_path = sys.argv[1:4]
ZERO = '{00000000-0000-0000-0000-000000000000}'

def load(p):
    s = re.sub(r'^<\?xml[^>]*\?>', '', open(p, encoding='utf-8').read())
    return ET.fromstring('<r>' + s + '</r>')

nav, doc = load(nav_path), load(clone_path)
by_guid = {}
for R in (doc, nav):
    for e in R.iter('entity'):
        g = e.find('prefab_link/instance')
        if g is not None:
            by_guid.setdefault(g.get('guid'), e)
folder = doc.find('prefab_folders/prefab_folder')
files = {pf.get('name'): pf.find('entity') for pf in folder.findall('prefab_file')}

def base(e):
    p = e.find('prefab_link/prefab')
    return by_guid.get(p.get('guid')) if p is not None and p.get('guid') != ZERO else None

# element order as the editor writes it
ORDER = ['prefab_link', 'transform', 'physics', 'tags', 'misc', 'flags', 'scripts', 'components', 'children']

def flatten(e):
    """Copy every inherited element into e and cut its base link."""
    b, depth = base(e), 0
    while b is not None and depth < 20:
        for tag in ORDER[1:]:
            if e.find(tag) is None and b.find(tag) is not None:
                e.append(copy.deepcopy(b.find(tag)))
        b, depth = base(b), depth + 1
    p = e.find('prefab_link/prefab')
    if p is not None:
        p.set('guid', ZERO)
    e[:] = sorted(e, key=lambda c: ORDER.index(c.tag) if c.tag in ORDER else len(ORDER))

def kids(e):
    c = e.find('children')
    return list(c) if c is not None else []

def meshes(e):
    c = e.find('components')
    return [m.get('name') for m in c.findall('meta_mesh_component')] if c is not None else []

def inherited_meshes(e):
    while e is not None:
        if e.find('components') is not None:
            return meshes(e)
        e = base(e)
    return []

def drop(e, tag):
    x = e.find(tag)
    if x is not None:
        e.remove(x)

def set_transform(e, pos=None, rot=None, scale=None):
    t = e.find('transform')
    if t is None:
        t = ET.Element('transform'); e.insert(1, t)
    for k, v in (('position', pos), ('rotation_euler', rot), ('scale', scale)):
        x = t.find(k)
        if v is None:
            continue
        if x is None:
            x = ET.SubElement(t, k, type_name='vec3')
        x.set('value', '%.3f, %.3f, %.3f' % v)
    t[:] = sorted(t, key=lambda c: ['position', 'rotation_euler', 'scale'].index(c.tag))

def el(tag, attrib=None, *children):
    x = ET.Element(tag, attrib or {})
    for c in children:
        x.append(c)
    return x

def new_entity(name, guid_seed):
    g = guid(guid_seed)
    return el('entity', {'name': name}, el('prefab_link', None, el('instance', {'guid': g}), el('prefab', {'guid': ZERO})))

def guid(seed):
    import uuid
    return '{%s}' % str(uuid.uuid5(uuid.UUID('6a1e7c52-9c1f-4f0e-9b5a-3d1a2f5e0c11'), 'galleass-stage1/' + seed)).upper()

def mesh_component(owner, *names):
    # every component carries its own <prefab_link> like an entity (NavalDLC: 78k components, none without);
    # a missing one fails the Kit's 'prefab_link_node != nullptr' assert (rglNested_prefab.cpp:3965) and crashes
    # the game's prefab loader at startup (TaleWorlds.Native.dll +0x22cc33, 2026-10-07)
    return el('components', None, *[el('meta_mesh_component', {'name': n},
                                       el('prefab_link', None, el('instance', {'guid': guid('%s/mmc/%s' % (owner, n))}),
                                          el('prefab', {'guid': ZERO})))
                                    for n in names])

def tags(*names):
    return el('tags', None, el('tags', {'type_name': 'string'}, *[el('tag', {'name': n}) for n in names]))

def mobility():
    return el('misc', None, el('mobility', {'type_name': 'int', 'value': '1'}))

report = []

# --- root: collision shape --------------------------------------------------------------------------------------
root = files['galleass_ship_nested']
root.find('physics/shape').set('value', 'bo_composite_conv_galleass')
# hull centre is ~0.6 m forward of the origin, castles fore and aft: centre of mass at the origin for now
root.find('physics/center_of_mass').set('value', '0.000, 0.000, -0.500')
report.append('root: shape bo_composite_conv_galleass, centre of mass (0, 0, -0.5)')

# --- mesh_holder: the hull itself ------------------------------------------------------------------------------
mh = files['mesh_holder']
ch = mh.find('children')
old = [c.get('name') for c in ch]
for c in list(ch):
    ch.remove(c)
hull = new_entity('galleass_hull', 'hull')
hull.append(el('physics', None,
               el('shape', {'type_name': 'string', 'value': 'bo_galleass'}),
               el('body_flags', None, el('body_flag', {'name': 'moveable'})),
               el('move_to_batched_kinematic', {'type_name': 'bool', 'value': '1'})))
hull.append(tags('body_mesh', 'rope_physics_body', 'hull_water_mesh'))
hull.append(mobility())
hull.append(mesh_component('hull', *['galleass_' + r for r in ('hull', 'paint', 'deck', 'trim', 'gilt', 'iron', 'dark', 'glass')],
                           'galleass_interior'))
paint = new_entity('galleass_faction_paint', 'faction_paint')
paint.append(tags('sail_mesh_entity')); paint.append(mobility()); paint.append(mesh_component('faction_paint', 'galleass_faction_paint'))
water = new_entity('deckwater', 'deckwater')
water.append(tags('render_to_depth'))
water.append(el('misc', None, el('is_visible', {'type_name': 'bool', 'value': '0'}),
                el('mobility', {'type_name': 'int', 'value': '1'})))
water.append(mesh_component('deckwater', 'galleass_deckwater'))
for x in (hull, paint, water):
    ch.append(x)
report.append('mesh_holder: %d meditheavy entities %s replaced by galleass_hull (9 meshes, bo_galleass), '
              'galleass_faction_paint, deckwater' % (len(old), sorted(set(old))))

# --- meditheavy-only geometry in the slot groups ----------------------------------------------------------------
def strip_meshes(group, pred, what):
    n = 0
    def walk(e):
        nonlocal n
        for c in kids(e):
            if any(pred(m) for m in inherited_meshes(c)):
                flatten(c)
                drop(c, 'components'); drop(c, 'physics')
                n += 1
            walk(c)
    top = files[group]
    if any(pred(m) for m in inherited_meshes(top)):
        flatten(top); drop(top, 'components'); drop(top, 'physics'); n += 1
    if top.find('children') is None and base(top) is not None:
        flatten(top)
    walk(top)
    report.append('%s: removed %s from %d entities' % (group, what, n))

strip_meshes('hull_group', lambda m: 'hull_plate_meditheavy' in m, 'hull_plate_meditheavy* (hull plating)')
strip_meshes('roof_group', lambda m: m == 'ship_meditheavy_roof_platform_a', 'ship_meditheavy_roof_platform_a')
strip_meshes('ship_ballista_holder', lambda m: m == 'ship_meditheavy_ballista_platform_a', 'the ballista platform')
strip_meshes('ram_group', lambda m: m == 'adaptor_meditheavy', 'the ram adaptor')
strip_meshes('figurehead_group', lambda m: m == 'figurehea_adapter_meditheavy', 'the figurehead adapter')

# --- figureheads: move the whole group onto the beak ------------------------------------------------------------
# vanilla figureheads sit at (0, 21.24, 3.05) inside the group; ours go to (0, 26.7, 1.75), ~1.13x larger
FIG_S = 1.13
fg = files['figurehead_group']
set_transform(fg, pos=(0.0, 26.7 - FIG_S * 21.24, 1.75 + LIFT - FIG_S * 3.05), scale=(FIG_S, FIG_S, FIG_S))
report.append('figurehead_group: scale %.2f, figureheads at (0, 26.7, %.2f)' % (FIG_S, 1.75 + LIFT))

# --- rudder: centreline stern rudder on the raked post ----------------------------------------------------------
RUDDER_POS, RUDDER_ROT = (0.0, -23.831, -2.370), (0.4124, 0.0, 0.0)
STOCK = (0.0, -24.25, -1.4)    # on the hinge line at z -1.4; ModuleData rudder_stock_position must match
ro = files['rudder_objects']
flatten(ro)
set_transform(ro, pos=(0.0, 0.0, 0.0))
rud = [c for c in kids(ro) if 'rudder_rotation_entity' in [t.get('name') for t in c.iter('tag')]
       or c.get('name') == 'rudder_meditheavy']
assert len(rud) == 1, rud
r = rud[0]
flatten(r)
r.set('name', 'galleass_rudder')
drop(r, 'transform'); set_transform(r, pos=RUDDER_POS, rot=RUDDER_ROT)
drop(r, 'components'); r.append(mesh_component('rudder_objects/rudder', 'galleass_rudder_a'))
r[:] = sorted(r, key=lambda c: ORDER.index(c.tag) if c.tag in ORDER else len(ORDER))
rh = files['rudders_holder']
for c in kids(rh):
    if c.get('name') == 'rudder_stock':
        flatten(c); set_transform(c, pos=STOCK)
    elif c.get('name') == 'rudder_objects':
        # the holder carries its own copy of rudder_objects: same treatment
        flatten(c); set_transform(c, pos=(0.0, 0.0, 0.0))
        for k in kids(c):
            if k.get('name') == 'rudder_meditheavy':
                flatten(k); k.set('name', 'galleass_rudder')
                drop(k, 'transform'); set_transform(k, pos=RUDDER_POS, rot=RUDDER_ROT)
                drop(k, 'components'); k.append(mesh_component('rudders_holder/rudder', 'galleass_rudder_a'))
                k[:] = sorted(k, key=lambda c: ORDER.index(c.tag) if c.tag in ORDER else len(ORDER))
report.append('rudder: galleass_rudder_a at %s rot %s, stock %s' % (RUDDER_POS, RUDDER_ROT, STOCK))

# --- no shield upgrades: high bulwarks instead (ModuleData galleass_side slot offers only the brazier) --------------
# and no battlements (shield rows) fore and aft: galleass_fore offers only the ballistas, the hull has no aft slot
for name in ('shields_holder', 'battlements_holder_fore', 'battlements_holder_aft'):
    sh = files[name]
    assert sh.find('prefab_link/prefab').get('guid') == ZERO     # unlinked root: nothing to inherit back
    n = len(kids(sh))
    drop(sh, 'children')
    report.append('%s: %d shield groups removed (holder kept, empty)' % (name, n))

# ==================================================================================================================
# Stage 2: relayout onto the galleass (oars, masts + rigging, fittings). Deck heights and widths come from the model.
# ==================================================================================================================
Z_DECK, Z_POOP, Z_FC = G['Z_GUN_DECK'] + LIFT, G['SC_Z_FLOOR'] + LIFT, G['FC_Z_PLATFORM'] + LIFT
W_OUT, SIDE_T = G['WING_HW'], G['SIDE_T']
W_IN = W_OUT - SIDE_T                                    # inner face of the bulwark
X_CAP, Z_CAP = W_OUT - 0.11, G['Z_BULWARK_TOP'] + LIFT + 0.1  # middle / top of the cap rail
BOX_Y0, BOX_Y1 = G['WING_Y0'], G['WING_Y1']
SC_Y0, SC_Y1 = G['SC_Y_AFT'], G['SC_Y_FORE']
FC_YB, FC_CY, FC_R = G['FC_Y_BACK'], G['FC_CY'], G['fc_radius'](G['FC_Z_PLATFORM'])
sc_hw = G['sc_hw']

def fc_half(y):
    """Half width of the forecastle platform at y (straight sides, round front)."""
    d = max(y - FC_CY, 0.0)
    return math.sqrt(max(FC_R * FC_R - d * d, 0.0))

def deck_z(x, y):
    if SC_Y0 <= y <= SC_Y1 and abs(x) < sc_hw(y):
        return Z_POOP
    if y >= FC_YB and abs(x) < fc_half(y):
        return Z_FC
    return Z_DECK

SHIP_Y0, SHIP_Y1 = SC_Y0 + 0.3, FC_CY + FC_R - 0.3          # rope anchors stay between cabin end and bow

def rail_point(y, side):
    """Where a rope from aloft is made fast on the ship's side: the box's cap rail, else the poop balustrade
    or the forecastle parapet."""
    y = min(max(y, SHIP_Y0), SHIP_Y1)
    if BOX_Y0 + 0.2 <= y <= BOX_Y1 - 0.2:
        return (side * X_CAP, y, Z_CAP)
    if y < BOX_Y0:
        return (side * (sc_hw(y) - 0.06), y, G['SC_Z_RAIL'] + LIFT)
    return (side * max(fc_half(y) - 0.15, 0.3), y, G['FC_Z_PARAPET'] + LIFT)

# transforms (TaleWorlds Mat3.ApplyEulerAngles: z, then x, then y; as prefab_layout.py)
I3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
def mmul(a, b): return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
def mvec(a, v): return [sum(a[i][k] * v[k] for k in range(3)) for i in range(3)]
def minv(m):
    (a, b, c), (d, e, f), (g, h, i) = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]
def rot_m(eu):
    x, y, z = eu
    cz, sz, cx, sx, cy, sy = math.cos(z), math.sin(z), math.cos(x), math.sin(x), math.cos(y), math.sin(y)
    return mmul(mmul([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]),
                [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])

def inh(e, path):
    d = 0
    while e is not None and d < 20:
        x = e.find(path)
        if x is not None:
            return x
        e, d = base(e), d + 1
    return None

def vec(x, default):
    return [float(v) for v in x.get('value').split(',')] if x is not None else list(default)

def tf(e):
    return (vec(inh(e, 'transform/position'), (0, 0, 0)), vec(inh(e, 'transform/rotation_euler'), (0, 0, 0)),
            vec(inh(e, 'transform/scale'), (1, 1, 1)))

def local_m(e):
    p, r, s = tf(e)
    m = rot_m(r)
    return [[m[i][j] * s[j] for j in range(3)] for i in range(3)], p

def walk(e, pm=I3, pp=(0, 0, 0), own_only=True):
    """[(entity, world matrix, world pos, parent matrix, parent pos)] for e and its descendants."""
    m, p = local_m(e)
    wm = mmul(pm, m); wp = [pp[i] + mvec(pm, p)[i] for i in range(3)]
    out = [(e, wm, wp, pm, pp)]
    ks = kids(e)
    if not ks and not own_only:
        b = base(e)
        while b is not None and not kids(b):
            b = base(b)
        ks = kids(b) if b is not None else []
    for c in ks:
        out += walk(c, wm, wp, own_only)
    return out

def write_tf(e, pos=None, rot=None):
    """Own transform with position, rotation and scale written out (nothing left to inherit)."""
    p, r, s = tf(e)
    p = list(pos) if pos is not None else p
    r = list(rot) if rot is not None else r
    drop(e, 'transform')
    t = ET.Element('transform')
    ET.SubElement(t, 'position', type_name='vec3', value='%.3f, %.3f, %.3f' % tuple(p))
    ET.SubElement(t, 'rotation_euler', type_name='vec3', value='%.3f, %.3f, %.3f' % tuple(r))
    if any(abs(v - 1) > 1e-6 for v in s):
        ET.SubElement(t, 'scale', type_name='vec3', value='%.3f, %.3f, %.3f' % tuple(s))
    e.insert(1, t)

def set_world_pos(e, pm, pp, target):
    write_tf(e, pos=mvec(minv(pm), [target[i] - pp[i] for i in range(3)]))

NS = uuid.UUID('6a1e7c52-9c1f-4f0e-9b5a-3d1a2f5e0c11')
def copy_regen(e, seed):
    """Deep copy of a NavalDLC instance tree with fresh instance GUIDs (entities, scripts, components)."""
    e = copy.deepcopy(e)
    for x in e.iter('instance'):
        x.set('guid', '{%s}' % str(uuid.uuid5(NS, seed + x.get('guid'))).upper())
    return e

def nav_folder(name):
    return next(f for f in nav.find('prefab_folders') if f.get('name') == name)

def nav_file(folder_name, file_name):
    return next(pf for pf in nav_folder(folder_name).findall('prefab_file') if pf.get('name') == file_name).find('entity')

def deck_profile(spawn_holder):
    """Vanilla deck height along the ship: lowest spawn point within 1 m of y."""
    pts = [wp for e, _, wp, _, _ in walk(spawn_holder, own_only=False)[1:]]
    def z_at(y):
        near = [p[2] for p in pts if abs(p[1] - y) < 1.0] or [min(pts, key=lambda p: abs(p[1] - y))[2]]
        return min(near)
    return z_at

DECK_MEDITHEAVY = deck_profile(files['spawn_point_holder'])          # still the meditheavy's (stage 2 later)
DECK_MEDITLIGHT = deck_profile(nav_file('meditlight_ship_nested', 'spawn_point_holder'))

# --- oars: ONE bank of unmanned oars (the dromon's lower 8 m oars) at the model's 20 ports per side ------------
oh = files['oars_holder']
decks = {d.get('name'): d for d in kids(oh)}
oh.find('children').remove(decks['oar_deck_upper'])                 # the meditheavy's manned upper bank
dromon_oars = nav_file('dromon_ship_nested', 'oars_holder')
tmpl = {}
for s, n in ((-1, 'oar_left_lower_8m'), (1, 'oar_right_lower_8m')):
    tmpl[s] = next(e for e in dromon_oars.iter('entity') if re.fullmatch(n + r'_\d+', e.get('name') or ''))
OAR_X = W_OUT - SIDE_T / 2                                           # pivot in the middle of the wall
OAR_Z = (G['OARPORT_Z0'] + G['OARPORT_Z1']) / 2 + LIFT - 0.7               # the oar pivots 0.7 above its entity
n_oars = 0
for grp_name, s in (('left_oar_machines', -1), ('right_oar_machines', 1)):
    grp = next(c for c in kids(decks['oar_deck_lower']) if c.get('name') == grp_name)
    assert base(grp) is None and grp.find('children') is not None
    ch = grp.find('children'); ch[:] = []
    for i in range(G['OARS_PER_SIDE']):
        o = copy_regen(tmpl[s], 'galleass-oar/%d/%d/' % (s, i))
        o.set('name', '%s_%d' % (tmpl[s].get('name').rsplit('_', 1)[0], i))
        write_tf(o, pos=(s * OAR_X, G['oar_y'](i), OAR_Z), rot=(0, 0, 0))
        ch.append(o); n_oars += 1
report.append('oars: upper (manned) bank removed; %d unmanned 8 m oars at x +-%.2f, pivot z %.2f, y %.1f..%.1f'
              % (n_oars, OAR_X, OAR_Z + 0.7, G['oar_y'](0), G['oar_y'](G['OARS_PER_SIDE'] - 1)))

# --- masts: small (mizzen), large (main), medium (fore) lateen rigs through the model's mast partners ----------
# sail_center_i <-> i-th <sail> in galleass_mission_ships.xml. Rake: gentler than vanilla so the fore yard
# clears the main mast; the main yard's lower end still crosses the fore mast when it lies fore and aft.
sh = files['sail_holder']
rigs = {c.get('name'): c for c in kids(sh)}
small = copy_regen(next(e for e in nav_file('meditlight_ship_nested', 'sail_holder').iter('entity')
                        if e.get('name') == 'lateen_sail_small_nested'), 'galleass-rig/mizzen/')
for t in small.iter('tag'):
    if t.get('name', '').startswith('sail_center_'):
        t.set('name', 'sail_center_2')
sh.find('children').append(small)
MASTS = G['MASTS']
RIGS = [  # (rig entity, mast, deck crossing z, rake, vanilla deck profile of the ship it came from)
    (rigs['lateen_sail_large_nested'], 'main', Z_DECK, -0.10, DECK_MEDITHEAVY),
    (rigs['lateen_sail_medium_nested'], 'fore', Z_FC, -0.157, DECK_MEDITHEAVY),
    (small, 'mizzen', Z_DECK, -0.157, DECK_MEDITLIGHT),
]
for rig, mast, zd, rake, vdeck in RIGS:
    P0, R0, _ = tf(rig)
    a0 = (0.0, -math.sin(R0[0]), math.cos(R0[0]))
    t = 0.0
    for _ in range(30):                     # where the vanilla mast passes through its deck
        t = (vdeck(P0[1] + t * a0[1]) - P0[2]) / a0[2]
    old = walk(rig)
    a = (0.0, -math.sin(rake), math.cos(rake))
    P = (0.0, MASTS[mast] - t * a[1], zd - t * a[2])
    write_tf(rig, pos=P, rot=(rake, 0.0, 0.0))
    new = {id(e): (wm, wp, pm, pp) for e, wm, wp, pm, pp in walk(rig)}
    moved = []
    done = set()
    # sail furling (fold) pulley blocks: block + belay target (+ the rope ends meeting there) come down onto our
    # deck together, 0.6 m above it
    old_pos = {id(e): wp0 for e, _, wp0, _, _ in old}
    for fold in (e for e in rig.iter('entity') if e.get('name') == 'sail_fold_pulleys'):
        for system in kids(fold):
            parts = {k.get('name'): k for k in kids(system)}
            tgt = parts.get('end_target_point')
            if tgt is None:
                continue
            t0, t1 = old_pos[id(tgt)], new[id(tgt)][1]
            y = min(max(t1[1], SHIP_Y0), SHIP_Y1)
            goal = (t1[0], y, deck_z(t1[0], y) + 0.6)
            if abs(t1[2] - goal[2]) < 0.3 and abs(y - t1[1]) < 0.01:
                continue
            d = [goal[i] - t1[i] for i in range(3)]
            group = [parts[n] for n in ('end_target_point', 'end_point_rope', 'pulley') if n in parts]
            group += [e for e, _, wp0, _, _ in old if e.get('name') in ('rope_start', 'rope_end')
                      and math.dist(wp0, t0) < 0.05]
            for e in group:
                _, wp, pm, pp = new[id(e)]
                set_world_pos(e, pm, pp, [wp[i] + d[i] for i in range(3)])
                done.add(id(e)); moved.append(e.get('name'))
    # rope ends made fast low on the vanilla ship (not at the mast, not on the yard) go to our rails / decks
    for e, _, wp0, _, _ in old[1:]:
        if id(e) in done or kids(e) or not re.fullmatch(r'rope_start|rope_end|free_rope\d+|fixed_rope\d+', e.get('name') or '') \
                or 'attached_to_yard' in [x.get('name') for x in e.iter('tag')]:
            continue
        h = wp0[2] - vdeck(wp0[1])
        y_axis = P0[1] + (wp0[2] - P0[2]) * a0[1] / a0[2]
        wm, wp, pm, pp = new[id(e)]
        side = abs(wp0[0]) > 1.2
        outside = not (SHIP_Y0 - 0.5 <= wp[1] <= SHIP_Y1 + 0.5) and wp[2] < 12.0     # beyond our bow / stern
        # stays to the vanilla ship's stern post / other mast: low and far from this mast
        far = e.get('name') in ('rope_start', 'rope_end') and wp[2] < 12.0 and math.hypot(wp0[0], wp0[1] - y_axis) > 6.0
        # side ropes end on the vanilla rail (up to ~3.5 m above its main deck where it has castles)
        if not (outside or far) and (h > (3.5 if side else 2.5) or math.hypot(wp0[0], wp0[1] - y_axis) < 1.0):
            continue
        if side:
            target = rail_point(wp[1], 1 if wp0[0] > 0 else -1)
        else:
            y = min(max(wp[1], SHIP_Y0), SHIP_Y1)
            target = (wp[0], y, deck_z(wp[0], y) + min(max(h, 0.1), 0.6))
        set_world_pos(e, pm, pp, target)
        moved.append(e.get('name'))
    report.append('%s mast: %s through (0, %.1f, %.2f), rake %.3f, rig origin (0, %.2f, %.2f); %d rope ends re-anchored %s'
                  % (mast, rig.get('name'), MASTS[mast], zd, rake, P[1], P[2], len(moved),
                     dict(sorted({m: moved.count(m) for m in moved}.items()))))

# --- cleats (knot points) onto the cap rail; the meditheavy's hull-side cosmetic ropes go --------------------
kh = files['knobs_holder']
n = 0
for e, wm, wp, pm, pp in walk(kh)[1:]:
    if e.get('name') != 'cleat_a':
        continue
    side = 1 if wp[0] > 0 else -1
    y = min(max(wp[1], BOX_Y0 + 0.4), BOX_Y1 - 0.4)
    set_world_pos(e, pm, pp, (side * X_CAP, y, Z_CAP))
    write_tf(e, rot=(0.0, 0.0, tf(e)[1][2]))
    n += 1
report.append('knobs_holder: %d cleats on the cap rail (x +-%.2f, z %.2f)' % (n, X_CAP, Z_CAP))
rc = files['rope_cosmetics_holder']
assert base(rc) is None
n = len(kids(rc)); drop(rc, 'children')
report.append('rope_cosmetics_holder: %d meditheavy hull-side ropes/cleats removed (CosmeticRopeManager kept)' % n)

# --- arrow braziers: clamped to the bulwark (box) / poop balustrade, standing on the deck --------------------
# ship_brazier_b reaches 0.65 m outboard of its origin, foot 0.69 m below it (mesh bounds)
BRAZIER_Y = [-16.3, -13.0, -11.0, -6.1, -0.65, 4.75, 10.2, 15.0, 17.3, 19.6]          # clear of the gunports
BRAZIER_POOP_Y = [-20.0]
bh = files['brazier_holder']
by_side = {-1: [], 1: []}
for c in kids(bh):
    by_side[1 if tf(c)[0][0] > 0 else -1].append(c)
for s, lst in by_side.items():
    spots = [(s * (W_IN - 0.65), y, Z_DECK + 0.69) for y in BRAZIER_Y] + \
            [(s * (sc_hw(y) - 0.06 - 0.65), y, Z_POOP + 0.69) for y in BRAZIER_POOP_Y]
    assert len(lst) == len(spots), (s, len(lst), len(spots))
    for c, p in zip(lst, spots):
        write_tf(c, pos=p, rot=(0.0, 0.0, s * math.pi / 2))
        for k in kids(c):
            write_tf(k, pos=(0, 0, 0), rot=(0, 0, 0))
report.append('brazier_holder: %d braziers on the bulwark (deck z %.2f) and the poop (z %.2f)'
              % (sum(map(len, by_side.values())), Z_DECK, Z_POOP))

# --- deck upgrades (ammo / arrow crates, boarding weapons): base mesh 0.095 below the entity -----------------
du = files['deck_upgrade_holder']
for c in kids(du):
    (x, y, z), _, _ = tf(c)
    if y < SC_Y1:
        p = (x, y, Z_POOP + 0.095)                # on the poop
    elif y > 10.0:
        p = (x, 9.0, Z_DECK + 0.095)              # was over the fore hatch (y 11.25..12.75)
    else:
        p = (x, y, Z_DECK + 0.095)
    write_tf(c, pos=p)
    report.append('deck upgrade %.1f -> (%.2f, %.2f, %.3f)' % (y, *p))

# --- floaters: columns filling OUR watertight body (vanilla physics: each floater is a box, origin = centre of its
# bottom face, scale = size; buoyancy = submerged height x footprint x 1020 x g x hull floating_force_multiplier;
# the ship settles where that equals mass x g). The meditheavy's columns were the wrong shape (roll/pitch/damage).
FLOAT_DX, FLOAT_DY = 2 * W_OUT / 7, 2.1                 # 7 columns across the full width; ~vanilla floater count (max 140)
WL_TARGET = 0.0                                         # design waterline (model z 0); decks lifted in the model instead
WING_Z0, WING_ZF = G['WING_Z0'], G['WING_Z_FACE']

def cove_x_at_z(y, z):
    lo, hi = 0.0, 1.0
    for _ in range(30):
        mid = (lo + hi) / 2
        if G['cove_xz'](y, mid)[1] < z: lo = mid
        else: hi = mid
    return G['cove_xz'](y, lo)[0]

def body_half_width(y, z):
    """Half width of the watertight body at (y, z) (lifted, real heights): hull shell, the flare and the box up to
    the gun deck, castles. The model's shapes are evaluated at the unlifted height."""
    z = G['unlift_z'](y, z)
    w, zt = 0.0, G['z_top'](y)
    if min(G['z_bottom'](y), zt - 0.15) <= z <= zt:
        w = G['hull_x_at'](y, z)
    if BOX_Y0 <= y <= BOX_Y1 and z >= WING_Z0:
        w = max(w, W_OUT if z >= WING_ZF else cove_x_at_z(y, z))
    if y >= FC_YB and G['FC_Z_BASE'] - 0.2 <= z <= G['FC_Z_PLATFORM']:
        w = max(w, fc_half(y))
    if SC_Y0 <= y <= SC_Y1 and zt - 0.1 <= z <= G['SC_Z_FLOOR']:
        w = max(w, sc_hw(y))
    return w

def column(x, y):
    cap = Z_POOP if (SC_Y0 <= y <= SC_Y1 and abs(x) < sc_hw(y)) else \
          Z_FC if (y >= FC_YB and abs(x) < fc_half(y)) else Z_DECK
    zs = [-3.0 + 0.04 * k for k in range(int((cap + 3.0) / 0.04) + 1)]
    inside = [z for z in zs if body_half_width(y, z) >= abs(x)]
    return (min(inside), max(inside)) if inside and max(inside) - min(inside) > 0.2 else None

def balance_z(cols, mass, mult):
    z = min(b for _, _, b, _ in cols)
    while True:
        f = sum(min(z - b, t - b) * FLOAT_DX * FLOAT_DY * 1020.0 * mult for _, _, b, t in cols if z > b)
        if f >= mass:
            return z
        z += 0.01

fh = files['floater_volume_holder']
tmpl_f = kids(fh)[0]
cols = []
for j in range(int(52 / FLOAT_DY) + 1):
    y = -26.0 + FLOAT_DY * (j + 0.5)
    for i in range(7):
        x = -W_OUT + FLOAT_DX * (i + 0.5)
        c = column(x, y)
        if c:
            cols.append((x, y, c[0], c[1]))
fh.find('children')[:] = []
for n, (x, y, b, t) in enumerate(cols):
    f = copy_regen(tmpl_f, 'galleass-floater/%d/' % n)
    f.set('name', 'floater_volume_%03d_galleass' % n)
    drop(f, 'transform')
    tr = ET.Element('transform')
    ET.SubElement(tr, 'position', type_name='vec3', value='%.3f, %.3f, %.3f' % (x, y, b))
    ET.SubElement(tr, 'scale', type_name='vec3', value='%.3f, %.3f, %.3f' % (FLOAT_DX, FLOAT_DY, t - b))
    f.insert(1, tr)
    fh.find('children').append(f)
mass = float(re.search(r'\bmass="([\d.]+)"', open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                             '..', 'ModuleData', 'galleass_mission_ships.xml')).read()).group(1))
vol_wl = sum(max(min(WL_TARGET - b, t - b), 0) for _, _, b, t in cols) * FLOAT_DX * FLOAT_DY
mult = mass / (1020.0 * vol_wl)
report.append('floaters: %d columns (%.2f x %.2f m), volume %.0f m3, %.0f m3 below z %.2f -> galleass_ship_hulls.xml '
              'floating_force_multiplier = %.3f for the waterline at z %.2f (mass %.0f); +10/+20 %% weight (upgrades) '
              '-> z %.2f / %.2f' % (len(cols), FLOAT_DX, FLOAT_DY, sum(t - b for *_, b, t in cols) * FLOAT_DX * FLOAT_DY,
                                     vol_wl, WL_TARGET, mult, balance_z(cols, mass, round(mult, 3)), mass,
                                     balance_z(cols, mass * 1.1, round(mult, 3)), balance_z(cols, mass * 1.2, round(mult, 3))))

# --- write --------------------------------------------------------------------------------------------------------
ET.indent(folder, '\t', level=1)
body = ET.tostring(folder, encoding='unicode').replace(' />', '/>')   # the editor's style
with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
    f.write('<?xml version="1.0"?>\n<prefab_files>\n</prefab_files>\n<prefab_folders>\n\t' + body + '\n</prefab_folders>\n')
for line in report:
    print('PREFAB', line)
