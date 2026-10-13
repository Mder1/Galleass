"""Build the galleass ship prefab from the meditheavy clone (make_packed_clone.py output).

python3 build_prefab.py <NavalDLC packed xml> <clone xml> <out xml>

Stage 1 (hull swap): our meshes + physics shapes replace the meditheavy ones, the meditheavy-only geometry is
removed, the rudder becomes a centreline stern rudder and the figureheads go (fixed spur). Everything else (oars,
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
# one mesh per material role, as the Kit imported galleass_hull.fbx (no glass since the open lantern, no interior
# since the cabin floor joined the deck mesh)
hull.append(mesh_component('hull', *['galleass_' + r for r in ('hull', 'paint', 'deck', 'trim', 'gilt', 'iron', 'dark')]))
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

# --- no figureheads (user 2026-10-08): the bow carries a fixed spur in the hull mesh instead; can_equip_figurehead is
# false in the hull XML, and the group is emptied like the fore weapon slot
fg = files['figurehead_group']
flatten(fg)                                   # cut the base link first, or the figureheads come back
n = len(kids(fg)); drop(fg, 'children')
report.append('figurehead_group: %d vanilla figureheads/platform removed' % n)
# no ram either (no bow slot since 2026-10-06; the fixed spur is in the hull mesh): the vanilla rams were left in the
# group and still showed in the Kit (user 2026-10-08)
rg = files['ram_group']
flatten(rg)
n = sum(1 for _ in rg.iter('meta_mesh_component')); drop(rg, 'children')
report.append('ram_group: vanilla rams removed (%d meshes)' % n)

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

# decks, stairs (also used by the navmesh below)
Z_POOP_TOP = G['SC_Z_FLOOR'] + 0.12 + LIFT           # poop deck surface (the stairs land on it)
FC_R_IN = FC_R - 0.35 - 0.15                           # inside the forecastle parapet, clear of it
DECK_X = W_IN - 0.25                                   # walkable half width between the bulwarks
DECK_Y0, DECK_Y1 = BOX_Y0 + SIDE_T + 0.1, BOX_Y1 - SIDE_T - 0.1
SC_STAIR_X, FC_STAIR_X = G['SC_STAIR_X'], G['FC_STAIR_X']
SC_STAIR_Y = (round(SC_Y1 + (G['SC_Z_FLOOR'] - G['Z_GUN_DECK']) / math.tan(math.radians(40)), 4), SC_Y1)   # foot, head
FC_STAIR_Y = (FC_YB - 3.0, FC_YB)
STAIRS = [(s * SC_STAIR_X - 0.5, s * SC_STAIR_X + 0.5, SC_STAIR_Y[0], SC_STAIR_Y[1], 'poop') for s in (-1, 1)] + \
         [(s * FC_STAIR_X - 0.5, s * FC_STAIR_X + 0.5, FC_STAIR_Y[0], FC_STAIR_Y[1], 'fc') for s in (-1, 1)]
LEVEL_Z = {'deck': Z_DECK, 'poop': Z_POOP_TOP, 'fc': Z_FC}

def lines(lo, hi, step, keep=()):
    """Grid lines from lo to hi about step apart, with the 'keep' lines exactly (others too close to them dropped)."""
    n = max(int(round((hi - lo) / step)), 1)
    base = [lo + (hi - lo) * k / n for k in range(n + 1)]
    keep = [k for k in keep if lo - 1e-6 <= k <= hi + 1e-6]
    return sorted(set(round(v, 4) for v in keep + [b for b in base if all(abs(b - k) > 0.4 for k in keep)]))

Y_DECK = lines(DECK_Y0, DECK_Y1, 1.5, keep=[SC_Y1, SC_STAIR_Y[0], FC_STAIR_Y[0], FC_YB])

# boarding (user 2026-10-13): ONE hook-thrower pair per side (a galleass was hard to board), on the gun deck's side strip
# beside the forecastle (between its wall and the bulwark, y 18.6..20.3; user: main floor, fore, on the side - not on
# the castle): we board from there, and it is the only place an enemy can hook on (a thrower always brings its own
# attach point - the game builds the bridge from that point's children). Rope cleats keep clear of the hooks, AI
# barriers of the crewmen
BOARDING_PER_SIDE = 1
BOARDING_X = (DECK_X + 4.75) / 2                       # crewman on the deck edge column, 0.85 m inside the bulwark
BOARDING_Y = [19.1]
def clear_of_boarding(y, gap=0.6):
    """y moved off the boarding hooks on the cap rail: to the nearest spot >= gap from all of them."""
    if all(abs(y - b) >= gap for b in BOARDING_Y):
        return y
    cand = [(a + b) / 2 for a, b in zip(BOARDING_Y, BOARDING_Y[1:])] + [BOARDING_Y[0] - gap, BOARDING_Y[-1] + gap]
    return min((c for c in cand if all(abs(c - b) >= gap - 1e-6 for b in BOARDING_Y)), key=lambda c: abs(c - y))

def rail_point(y, side):
    """Top surface where a rope from aloft is made fast on the ship's side (a cleat goes there): the box's cap
    rail, else the poop balustrade's rail or the forecastle parapet's cap."""
    y = min(max(y, SHIP_Y0), SHIP_Y1)
    if BOX_Y0 + 0.2 <= y <= BOX_Y1 - 0.2:
        return (side * X_CAP, clear_of_boarding(y), Z_CAP)
    if y < BOX_Y0:
        y = max(y, SC_Y0 + 0.4)
        return (side * (sc_hw(y) - 0.06), y, G['SC_Z_RAIL'] + LIFT)
    return (side * max(fc_half(y) - 0.2, 0.3), y, G['FC_Z_PARAPET'] + LIFT + 0.1)

MASTS_AT = []                                                 # (y, deck z) of the mast steps, filled with the rigs
HATCHES = [(-6.5, 0.75, 0.9), (12.0, 0.75, 0.9)]              # (y, half length, half width): the model's gratings

def deck_spot(x, y):
    """Open deck surface near (x, y) for a cleat: on the poop / forecastle platform / gun deck, clear of walls,
    stairs, mast steps and hatches."""
    y = min(max(y, SHIP_Y0), SHIP_Y1)
    if SC_Y0 <= y <= SC_Y1 and abs(x) < sc_hw(y):                                  # poop
        y = min(max(y, SC_Y0 + 0.5), SC_Y1 - 0.4)
        x = max(min(x, sc_hw(y) - 0.35), -(sc_hw(y) - 0.35))
        return (x, y, Z_POOP_TOP)
    if y >= FC_YB and abs(x) < fc_half(y):                                         # forecastle platform
        r = math.hypot(x, max(y - FC_CY, 0.0))
        if r > FC_R_IN - 0.2:
            k = (FC_R_IN - 0.2) / r
            x, y = x * k, (FC_CY + (y - FC_CY) * k) if y > FC_CY else y
        y = max(y, FC_YB + 0.4)
        z = Z_FC
    else:                                                                          # gun deck
        if y < SC_Y1 + 0.5 and abs(x) < sc_hw(SC_Y1) + 0.3:
            y = SC_Y1 + 0.6
        if y > FC_YB - 0.5 and abs(x) < FC_R + 0.3:
            y = FC_YB - 0.6
        for sx0, sx1, ya, yb, _ in STAIRS:
            if sx0 - 0.3 < x < sx1 + 0.3 and min(ya, yb) - 0.3 < y < max(ya, yb) + 0.3:
                x = sx1 + 0.45 if x > 0 else sx0 - 0.45
        for hy, hl, hw in HATCHES:
            if abs(y - hy) < hl + 0.25 and abs(x) < hw + 0.25:
                x = math.copysign(hw + 0.4, x if x else 1.0)
        x = max(min(x, DECK_X - 0.2), -(DECK_X - 0.2))
        z = Z_DECK
    for my, mz in MASTS_AT:
        if abs(z - mz) < 0.01 and math.hypot(x, y - my) < 0.9:
            x = math.copysign(0.9, x if x else 1.0)
    return (x, y, z)

KNOT_H = 0.13                                                 # cleat_a's knot_point above its base
FASTENERS = []                                                # [(x, y, z)] cleat bases

def fasten(surface):
    """A cleat at this surface point (or a close existing one); returns the rope's end (the knot point)."""
    x, y, z = surface
    for f in FASTENERS:
        if abs(f[2] - z) < 0.05 and math.hypot(f[0] - x, f[1] - y) < 0.25:
            return (f[0], f[1], f[2] + KNOT_H)
    while any(abs(f[2] - z) < 0.05 and math.hypot(f[0] - x, f[1] - y) < 0.45 for f in FASTENERS):
        y += 0.45                                             # neighbours along a rail: spread out
        if abs(z - Z_CAP) < 0.05:
            y = clear_of_boarding(y)
    FASTENERS.append((x, y, z))
    return (x, y, z + KNOT_H)

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

# --- oars: ONE bank of unmanned oars at the model's ports (OARS_PER_SIDE), 11.5 m long (user 2026-10-08) ----------
# Each oar is a copy of vanilla's standalone oar definition (oar_left/right_lower_8m: no links inside), so its mesh can
# be swapped for ours (_art/make_oar.py) without the vanilla oar being rebuilt beside it (linked children that lose
# their link no longer override the base's - the old oars showed up next to ours). The game reads the oar length
# from the mesh's bounding box (ShipOarDeck.UpdateOarLength).
oh = files['oars_holder']
decks = {d.get('name'): d for d in kids(oh)}
oh.find('children').remove(decks['oar_deck_upper'])                 # the meditheavy's manned upper bank
dromon_oars = nav_file('dromon_ship_nested', 'oars_holder')
def root_def(e):
    while base(e) is not None:
        e = base(e)
    return e
tmpl = {}
for s, n in ((-1, 'oar_left_lower_8m'), (1, 'oar_right_lower_8m')):
    inst = next(e for e in dromon_oars.iter('entity') if re.fullmatch(n + r'_\d+', e.get('name') or ''))
    tmpl[s] = root_def(inst)
    assert all(p.get('guid') == ZERO for p in tmpl[s].iter('prefab')), 'oar definition with links'
OAR_X = W_OUT - SIDE_T / 2                                           # pivot in the middle of the wall
OAR_Z = G['lift_z'](0.0, (G['OARPORT_Z0'] + G['OARPORT_Z1']) / 2) - 0.7              # the oar pivots 0.7 above its entity
OAR_MESH = 'galleass_oar_11m'
# vanilla oar meshes -> ours (make_oar.py): the base oar and the 'oars' slot's upgrade oars (Light = narrow, Wide)
OAR_MESHES = {'base_oar_8m': OAR_MESH}
for _l in (1, 2, 3):
    OAR_MESHES['narrow_oar_l%d_8m' % _l] = 'galleass_oar_light_l%d' % _l
    OAR_MESHES['wide_oar_l%d_8m' % _l] = 'galleass_oar_wide_l%d' % _l
OAR_OUT, OAR_BLADE = 10.35, 2.0                                      # pivot -> blade tip, blade length (make_oar.py)
# retracted: the oar slides inboard straight through its port until only the blade tip stays outside (the vanilla
# dromon pulls its 8 m oars in 5.66 m; ours would have stood 4.7 m out - user 2026-10-08)
OAR_RETRACT = OAR_OUT - 0.4
# the brown: oar textures are greyscale; every vanilla ship tints all its oar meshes per sub-mesh with one factor
# colour (dromon 0.145/0.122/0.106 - ours come from it; user 2026-10-08: our oars were white). The sub-mesh names
# are read from the Kit's imported assets (they only exist once imported).
OAR_TINT = '0.145, 0.122, 0.106, 1.000'
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tpac_tools'))
import meshinfo
def oar_submeshes(name, _cache={}):
    if name not in _cache:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Assets', name + '_geo.tpac')
        _cache[name] = [m['name'] for tg, g, n, meta in (meshinfo.assets(path) if os.path.exists(path) else [])
                        if n == name and str(tg).startswith('a08f8b97') for m in meshinfo.meshes(meta)]
    return _cache[name]
def tint(component, name):
    drop(component, 'children')
    subs = oar_submeshes(name)
    if subs:
        component.append(el('children', None, *[el('mesh', {'name': m}, el('misc', None, el('factor_color',
                         {'type_name': 'vec4', 'value': OAR_TINT}))) for m in subs]))
    return len(subs)
n_oars, n_mesh, n_tint = 0, 0, 0
for grp_name, s in (('left_oar_machines', -1), ('right_oar_machines', 1)):
    grp = next(c for c in kids(decks['oar_deck_lower']) if c.get('name') == grp_name)
    assert base(grp) is None and grp.find('children') is not None
    ch = grp.find('children'); ch[:] = []
    for i in range(G['OARS_PER_SIDE']):
        o = copy_regen(tmpl[s], 'galleass-oar/%d/%d/' % (s, i))
        o.set('name', '%s_%d' % (tmpl[s].get('name'), i))
        write_tf(o, pos=(s * OAR_X, G['oar_y'](i), OAR_Z), rot=(0, 0, 0))
        for m in o.iter('meta_mesh_component'):
            if m.get('name') in OAR_MESHES:
                m.set('name', OAR_MESHES[m.get('name')]); n_mesh += 1
                n_tint += tint(m, m.get('name'))
        rf = next(c for c in o.iter('entity') if c.get('name') == 'retracted_frame')
        write_tf(rf, pos=(-s * OAR_RETRACT, 0.0, 0.7), rot=(0.0, 0.0, tf(rf)[1][2]))   # level, through the port
        ch.append(o); n_oars += 1
# stroke (MissionOar: blade tip at OarLength along the oar, its dip angle = base + cos(phase) * amplitude): at the
# deepest point the shaft meets the water where the blade begins, at the highest the tip clears it by ~0.3 m - only
# the blade goes under (user 2026-10-08). Waterline z 0 (the floaters are tuned to it).
OAR_H = OAR_Z + 0.7
dip_max = math.degrees(math.asin(OAR_H / (OAR_OUT - OAR_BLADE)))
dip_min = math.degrees(math.asin((OAR_H - 0.3) / OAR_OUT))
od = next(sc for sc in decks['oar_deck_lower'].iter('script') if sc.get('name') == 'ShipOarDeck')
for k, v in (('_verticalBaseAngle', (dip_max + dip_min) / 2), ('_verticalRotationAngle', (dip_max - dip_min) / 2)):
    var = next(x for x in od.iter('variable') if x.get('name') == k)
    var.set('value', '%.3f' % v)
report.append('oar tint %s on %d sub-meshes' % (OAR_TINT, n_tint))
report.append('oars: upper (manned) bank removed; %d unmanned oars (%s, %d meshes) at x +-%.2f, pivot z %.2f, y %.1f..%.1f; '
              'retract %.2f m inboard; dip %.1f..%.1f deg (blade tip %.2f above .. %.2f below the water)'
              % (n_oars, OAR_MESH, n_mesh, OAR_X, OAR_H, G['oar_y'](0), G['oar_y'](G['OARS_PER_SIDE'] - 1), OAR_RETRACT,
                 dip_min, dip_max, OAR_H - OAR_OUT * math.sin(math.radians(dip_min)),
                 OAR_OUT * math.sin(math.radians(dip_max)) - OAR_H))

# --- cleats (knot points) onto the cap rail; the meditheavy's hull-side cosmetic ropes go --------------------
kh = files['knobs_holder']
n = 0
for e, wm, wp, pm, pp in walk(kh)[1:]:
    if e.get('name') != 'cleat_a':
        continue
    side = 1 if wp[0] > 0 else -1
    y = clear_of_boarding(min(max(wp[1], BOX_Y0 + 0.4), BOX_Y1 - 0.4))
    set_world_pos(e, pm, pp, (side * X_CAP, y, Z_CAP))
    write_tf(e, rot=(0.0, 0.0, tf(e)[1][2]))
    FASTENERS.append((side * X_CAP, y, Z_CAP))
    n += 1
CLEAT_TMPL = next(c for c in kids(kh) if c.get('name') == 'cleat_a')
N_RAIL_CLEATS = len(FASTENERS)
report.append('knobs_holder: %d cleats on the cap rail (x +-%.2f, z %.2f)' % (n, X_CAP, Z_CAP))

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
    (rigs['lateen_sail_large_nested'], 'main', Z_DECK, -G['MAST_RAKE']['main'], DECK_MEDITHEAVY),
    (rigs['lateen_sail_medium_nested'], 'fore', Z_FC, -G['MAST_RAKE']['fore'], DECK_MEDITHEAVY),
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
    MASTS_AT.append((MASTS[mast], zd))
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
            goal = fasten(deck_spot(t1[0], t1[1]))
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
            target = fasten(rail_point(wp[1], 1 if wp0[0] > 0 else -1))
        else:
            target = fasten(deck_spot(wp[0], wp[1]))
        set_world_pos(e, pm, pp, target)
        moved.append(e.get('name'))
    report.append('%s mast: %s through (0, %.1f, %.2f), rake %.3f, rig origin (0, %.2f, %.2f); %d rope ends re-anchored %s'
                  % (mast, rig.get('name'), MASTS[mast], zd, rake, P[1], P[2], len(moved),
                     dict(sorted({m: moved.count(m) for m in moved}.items()))))

# new cleats where the rigs' rope ends are made fast (rails and decks)
for i, (x, y, z) in enumerate(FASTENERS[N_RAIL_CLEATS:]):
    c = copy_regen(CLEAT_TMPL, 'galleass-cleat/%d/' % i)
    write_tf(c, pos=(x, y, z), rot=(0.0, 0.0, 0.0))
    kh.find('children').append(c)
report.append('rope fasteners: %d new cleats (%d rail cleats reused)' % (len(FASTENERS) - N_RAIL_CLEATS, N_RAIL_CLEATS))
rc = files['rope_cosmetics_holder']
assert base(rc) is None
n = len(kids(rc)); drop(rc, 'children')
report.append('rope_cosmetics_holder: %d meditheavy hull-side ropes/cleats removed (CosmeticRopeManager kept)' % n)

# --- arrow braziers: clamped to the bulwark (box) / poop balustrade, standing on the deck --------------------
# ship_brazier_b reaches 0.65 m outboard of its origin, foot 0.69 m below it (mesh bounds)
BRAZIER_Y = [-16.3, -13.0, -11.0, -6.1, -0.65, 4.75, 10.2, 20.0]          # clear of the gunports and boarding
BRAZIER_POOP_Y = [-23.0, -20.0, -16.0]          # between the awning posts (y -17.2, -19.7, -21.9)
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

# ==================================================================================================================
# Stage 2b: navmesh + the gameplay points the agents use (they still stood on the meditheavy's deck, 1.5 m below
# ours after the lift: agents fell through the hull, user 2026-10-07)
# ==================================================================================================================
import navmesh
NAVMESH = 'galleass_ship_navmesh'
NAV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'NavMeshPrefabs')

xs_half = [0.0, 0.4, 0.95, 1.75] + sorted({abs(a) for a, b, *_ in STAIRS} | {abs(b) for a, b, *_ in STAIRS}) + [4.1, 4.75, DECK_X]
X_LINES = sorted({-x for x in xs_half} | set(xs_half))
Y_POOP = lines(SC_Y0 + 0.3, SC_Y1, 1.5)
Y_FC = lines(FC_YB, FC_CY + FC_R_IN, 1.0, keep=[FC_CY])

def in_stairs(x0, x1, y0, y1):
    return next((s for s in STAIRS if s[0] - 1e-3 <= x0 and x1 <= s[1] + 1e-3 and
                 min(s[2], s[3]) - 1e-3 <= y0 and y1 <= max(s[2], s[3]) + 1e-3), None)

def walkable(level, x0, x1, y0, y1):
    xc, yc = (x0 + x1) / 2, (y0 + y1) / 2
    corners = [(x, y) for x in (x0, x1) for y in (y0, y1)]
    if level == 'deck':
        if in_stairs(x0, x1, y0, y1):
            return False
        if yc < SC_Y1 and min(abs(x0), abs(x1)) < max(sc_hw(y0), sc_hw(y1)) + 0.02 and x0 * x1 >= 0:
            return False                                          # the cabin
        if yc < SC_Y1 and x0 * x1 < 0:
            return False
        if yc > FC_YB and min(abs(x0), abs(x1)) < FC_R + 0.15 or (yc > FC_YB and x0 * x1 < 0):
            return False                                          # the forecastle
        return True
    if level == 'poop':
        return all(abs(x) <= sc_hw(y) - 0.1 + 1e-6 for x, y in corners)
    return all((abs(x) if y <= FC_CY else math.hypot(x, y - FC_CY)) <= FC_R_IN + 1e-6 for x, y in corners)

verts, vindex, faces = [], {}, []
def vid(key, xyz):
    if key not in vindex:
        vindex[key] = len(verts); verts.append(tuple(xyz))
    return vindex[key]

def add_cell(level, x0, x1, y0, y1, fid=0):
    z = LEVEL_Z[level]
    ks = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]                    # CCW from above
    faces.append(([vid((level, round(x, 4), round(y, 4)), (x, y, z)) for x, y in ks], fid))
    return len(faces) - 1

cells = {}
for level, ys in (('deck', Y_DECK), ('poop', Y_POOP), ('fc', Y_FC)):
    for y0, y1 in zip(ys, ys[1:]):
        for x0, x1 in zip(X_LINES, X_LINES[1:]):
            if walkable(level, x0, x1, y0, y1):
                cells[(level, x0, x1, y0, y1)] = add_cell(level, x0, x1, y0, y1)
# forecastle ground floor (walk-in, at gun-deck level; it shares the deck's vertices along its open back)
for y0, y1 in zip(Y_FC, Y_FC[1:]):
    for x0, x1 in zip(X_LINES, X_LINES[1:]):
        if walkable('fc', x0, x1, y0, y1):
            cells[('fcg', x0, x1, y0, y1)] = add_cell('deck', x0, x1, y0, y1)
# stairs: ramps whose foot vertices are the gun deck's and whose head vertices are the upper deck's
for sx0, sx1, ya, yb, upper in STAIRS:
    ys = sorted({ya, yb} | {y for y in Y_DECK if min(ya, yb) < y < max(ya, yb)})
    if ya > yb: ys = ys[::-1]
    cols = [(a, b) for a, b in zip(X_LINES, X_LINES[1:]) if sx0 - 1e-6 <= a and b <= sx1 + 1e-6]
    def sv(x, y):
        t = (y - ya) / (yb - ya)
        if t <= 1e-6: return vid(('deck', round(x, 4), round(y, 4)), (x, y, Z_DECK))
        if t >= 1 - 1e-6: return vid((upper, round(x, 4), round(y, 4)), (x, y, LEVEL_Z[upper]))
        return vid(('stair', upper, round(x, 4), round(y, 4)), (x, y, Z_DECK + t * (LEVEL_Z[upper] - Z_DECK)))
    for (x0, x1) in cols:
        for y0, y1 in zip(ys, ys[1:]):
            q = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            if y1 < y0:                                                   # keep CCW from above
                q = [(x0, y1), (x1, y1), (x1, y0), (x0, y0)]
            faces.append(([sv(x, y) for x, y in q], 0))

# --- the cabin (a gun room, walk-in at gun-deck level) and the open stern platform behind it (user 2026-10-08: the
# boarding nets go there): own vertex keys, so nothing bridges through a wall; the fore door's cell shares the deck's
# vertices along the cabin front, the aft door's cell the platform's
SC_WALL_T, BALC_RX, BALC_RY = G['SC_WALL'], sc_hw(SC_Y0) + 0.1, G['BALC_RY']
DOOR_F, DOOR_A = (0.95, 1.75), (-0.4, 0.4)                        # clear widths inside the door linings
def cab_vid(x, y):
    key = ('deck' if abs(y - SC_Y1) < 1e-6 else 'cab', round(x, 4), round(y, 4))
    return vid(key, (x, y, Z_DECK))
def cab_cell(x0, x1, y0, y1):
    faces.append(([cab_vid(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))], 0))
Y_CAB = lines(SC_Y0 + SC_WALL_T, SC_Y1 - SC_WALL_T, 1.0)
n_cab = 0
for y0, y1 in zip(Y_CAB, Y_CAB[1:]):
    for x0, x1 in zip(X_LINES, X_LINES[1:]):
        if all(abs(x) <= sc_hw(y) - SC_WALL_T - 0.15 + 1e-6 for x in (x0, x1) for y in (y0, y1)):
            cab_cell(x0, x1, y0, y1); n_cab += 1
for (xa, xb), (ya, yb) in ((DOOR_F, (SC_Y1 - SC_WALL_T, SC_Y1)), (DOOR_A, (SC_Y0, SC_Y0 + SC_WALL_T))):
    for x0, x1 in zip(X_LINES, X_LINES[1:]):
        if xa - 1e-6 <= x0 and x1 <= xb + 1e-6:
            cab_cell(x0, x1, ya, yb); n_cab += 1
def on_platform(x, y):
    return ((x / (BALC_RX - 0.15)) ** 2 + ((SC_Y0 - y) / (BALC_RY - 0.15)) ** 2 <= 1 + 1e-6 and y <= SC_Y0 + 1e-6
            and not (abs(x) < 0.35 and y < SC_Y0 - BALC_RY + 0.45))   # clear of the stern post
# own finer grid (the curved plate is small); it keeps the aft door's x lines, so the door cell joins it
X_PLAT = [-1.65, -1.35, -1.05, -0.75, -0.4, 0.0, 0.4, 0.75, 1.05, 1.35, 1.65]
Y_PLAT = [SC_Y0 - 1.1, SC_Y0 - 0.9, SC_Y0 - 0.6, SC_Y0 - 0.3, SC_Y0]
n_plat = 0
for y0, y1 in zip(Y_PLAT, Y_PLAT[1:]):
    for x0, x1 in zip(X_PLAT, X_PLAT[1:]):
        if all(on_platform(x, y) for x in (x0, x1) for y in (y0, y1)):
            cab_cell(x0, x1, y0, y1); n_plat += 1
report.append('navmesh: cabin %d cells (incl. both door openings), stern platform %d cells' % (n_cab, n_plat))

# --- boarding (user 2026-10-13): BOARDING_PER_SIDE pairs (attachment_machine_nested = thrower + its own attach point)
# beside the forecastle (see BOARDING_Y); everything else goes. All kept pairs take the hanging look of the vanilla pair
# whose grapnel hangs from the rail ring (the others lie in a coil meant for the floor; user 2026-10-13). The crewman
# stays on deck; hook, rope pile, rail fitting and hook point go up BOARDING_DZ onto the cap rail (vanilla roundship
# raises the same children for its taller sides). Each pair gets its own navmesh id face under the crewman
BOARDING_DZ = (G['Z_BULWARK_TOP'] + 0.1 - G['Z_GUN_DECK']) - 0.69       # vanilla rail fitting ('visual') sits 0.69 up
BOARDING_RAISE = {'hook', 'pile_holder', 'focus_object', 'visual', 'hook_attach_point', 'capsule_physics_a'}
V_med, _, F_med = navmesh.read(os.path.join(os.path.dirname(nav_path), '..', 'NavMeshPrefabs', 'meditheavy_ship_navmesh.bin'))
med_ids = {fid: [sum(V_med[v][k] for v in vs) / len(vs) for k in range(3)] for vs, _, fid in F_med if fid}
ah = files['attachment_machine_holder']
att = []
for e in kids(ah):
    ids = [int(v.get('value')) for v in e.iter('variable') if v.get('name') == 'RelatedShipNavmeshOffset']
    p, r, _ = tf(e)
    fid = ids[0] if ids else min(med_ids, key=lambda i: math.dist(med_ids[i][:2], p[:2]))
    att.append((e, fid, p, r))
def ancestors(root, target):
    """Entities from root's children down to target's parent."""
    def go(e, path):
        for c in kids(e):
            if c is target:
                return path
            r = go(c, path + [c])
            if r is not None:
                return r
        return None
    return go(root, []) or []
def sub_kids(e):
    return {(sub.get('name'), c.get('name')): c for sub in kids(e) for c in kids(sub)}
pairs = [a for a in att if a[0].get('name').startswith('attachment_machine')]
tmpl = max(pairs, key=lambda a: tf(sub_kids(a[0])[('attachment_machine', 'hook')])[0][2])[0]
TMPL = {k: tf(c)[:2] for k, c in sub_kids(tmpl).items()}
kept = []
for side in (-1, 1):
    mine = [a for a in pairs if (a[2][0] > 0) == (side > 0)]
    for (e, fid, p, r), y in zip(mine, BOARDING_Y):
        x = side * BOARDING_X
        key = next(k for k in cells if k[0] == 'deck' and min(k[1], k[2]) <= x - side * 0.1 <= max(k[1], k[2])
                   and k[3] <= y <= k[4])
        vs, _ = faces[cells[key]]; faces[cells[key]] = (vs, fid)
        write_tf(e, pos=(x, y, Z_DECK), rot=(0.0, 0.0, -side * math.pi / 2))
        for k, c in sub_kids(e).items():
            cp, cr = TMPL.get(k, tf(c)[:2])
            if k[1] in BOARDING_RAISE:
                cp = (cp[0], cp[1], cp[2] + BOARDING_DZ)
            write_tf(c, pos=cp, rot=cr)
        # the raised children carry vanilla floor dressing (crates, sacks, rope coils, the grapnel's floor coil): back down
        for c, wm, wp, pm, pp in walk(e)[1:]:
            if c.get('name') not in BOARDING_RAISE and wp[2] - Z_DECK - BOARDING_DZ < 0.45 \
                    and any(a.get('name') in BOARDING_RAISE for a in ancestors(e, c)):
                set_world_pos(c, pm, pp, (wp[0], wp[1], wp[2] - BOARDING_DZ))
        kept.append((e, fid, y))
keep = {id(k[0]) for k in kept}
ch = ah.find('children')
dropped = 0
for e in list(ch):
    if id(e) not in keep:
        ch.remove(e); dropped += 1
report.append('boarding: %d thrower pairs beside the forecastle (x +-%.2f, y %s, ids %s, look of %s), %d others removed, '
              'hooks raised %.2f' % (len(kept), BOARDING_X, BOARDING_Y, sorted(k[1] for k in kept),
                                     [round(v, 2) for v in tf(tmpl)[0]], dropped, BOARDING_DZ))

os.makedirs(NAV_DIR, exist_ok=True)
nv, ne, nf = navmesh.write(os.path.join(NAV_DIR, NAVMESH + '.bin'), verts, faces)
for v in folder.iter('variable'):
    if v.get('name') == 'NavMeshPrefabName' and v.get('value') == 'meditheavy_ship_navmesh':
        v.set('value', NAVMESH)
report.append('navmesh %s: %d verts, %d edges, %d faces (deck %.2f, poop %.2f, forecastle %.2f, 4 stairs)'
              % (NAVMESH, nv, ne, nf, Z_DECK, Z_POOP_TOP, Z_FC))

# --- meditheavy deck -> our deck: spawn points, helm, AI barriers --------------------------------------------------
def med_level(x, y, z):
    """(face z, raised?) of the meditheavy navmesh face under (x, y) nearest to z."""
    best = None
    for vs, _, _ in F_med:
        fz = navmesh.face_z(V_med, vs, x, y)
        if fz is not None and (best is None or abs(z - fz) < abs(z - best)):
            best = fz
    if best is None:
        best = DECK_MEDITHEAVY(y)
    return best, best > 4.4                                    # its raised stern deck vs the main deck

med_deck = [v for v in V_med if v[2] <= 4.4]; med_poop = [v for v in V_med if v[2] > 4.4]
MED_DECK_Y = (min(v[1] for v in med_deck), max(v[1] for v in med_deck))
MED_POOP_Y = (min(v[1] for v in med_poop), max(v[1] for v in med_poop))
def med_half(y, pool):
    near = [abs(v[0]) for v in pool if abs(v[1] - y) < 2.5] or [max(abs(v[0]) for v in pool)]
    return max(max(near), 1.5)

def remap(p):
    x, y, z = p
    fz, raised = med_level(x, y, z)
    h = max(z - fz, 0.0)
    if raised:
        t = min(max((y - MED_POOP_Y[0]) / (MED_POOP_Y[1] - MED_POOP_Y[0]), 0.0), 1.0)
        y2 = SC_Y0 + 0.6 + t * (SC_Y1 - 0.4 - SC_Y0 - 0.6)
        x2 = max(min(x / med_half(y, med_poop), 1.0), -1.0) * (sc_hw(y2) - 0.45)
        return (x2, y2, Z_POOP_TOP + h)
    t = min(max((y - MED_DECK_Y[0]) / (MED_DECK_Y[1] - MED_DECK_Y[0]), 0.0), 1.0)
    y2 = DECK_Y0 + 1.0 + t * (FC_YB - 0.4 - DECK_Y0 - 1.0)
    x2 = max(min(x / med_half(y, med_deck), 1.0), -1.0) * (DECK_X - 0.35)
    if y2 < SC_Y1 and abs(x2) < sc_hw(y2) + 0.4:               # beside the cabin: out on the side deck
        x2 = math.copysign(sc_hw(y2) + 0.6, x2 if x2 else 1)
    for sx0, sx1, ya, yb, _ in STAIRS:                          # not on/under a stair
        if sx0 - 0.3 < x2 < sx1 + 0.3 and min(ya, yb) - 0.3 < y2 < max(ya, yb) + 0.3:
            x2 = sx1 + 0.5 if x2 > 0 else sx0 - 0.5                 # outboard of the stair
    return (x2, y2, Z_DECK + h)

moved = {}
for e in kids(files['control_point_holder']):                    # the helm: front of the poop, as on the meditheavy
    p, r, _ = tf(e)
    write_tf(e, pos=(p[0], SC_Y1 - 0.9, Z_POOP_TOP), rot=r)
    moved['control_point_holder'] = 1
for holder in ('spawn_point_holder', 'barrier_holder'):
    for e in kids(files[holder]):
        p, r, _ = tf(e)
        write_tf(e, pos=remap(p), rot=r)
        moved[holder] = moved.get(holder, 0) + 1
# the meditheavy's AI limiter walls (invisible, AI only) that land on the fore boarding spots would fence the crewmen
# off; our 1.4 m bulwark keeps everyone aboard there anyway
bch = files['barrier_holder'].find('children')
cut = [e for e in list(bch) if any(math.hypot(abs(tf(e)[0][0]) - BOARDING_X, tf(e)[0][1] - by) < 2.5 for by in BOARDING_Y)]
for e in cut:
    bch.remove(e)
report.append('barrier_holder: %d AI barriers at the boarding spots removed' % len(cut))
report.append('meditheavy deck -> galleass deck: %s' % moved)

# --- rope climbers (boarding nets, from boats up the hull) hang from the open stern platform's edge, one at each
# rear quarter (user 2026-10-08). Climber frame: origin = top landing, local +x outboard, climb_point 0.7 m inboard
# where the climber steps onto the deck. The net (ship_climbing_rope_large: flat, 1.7 m wide, top bar 2.1 above its
# origin, plane 0..0.25 outboard of it, turned 90 deg) is placed on its own: its straight top bar is a chord of the
# curved edge, tucked into the plate's rim below the deck surface (middle 0.1 inside the edge, ends ~0.1 outside;
# user 2026-10-08: the nets did not meet the platform). Hanging plumb: the vanilla tilts were for a sloping hull side.
NET_IN, NET_BAR_Z = 0.1, -0.15            # net plane middle inside the edge / bar top below the deck surface
spots = []
for e in kids(files['climbers_holder']):
    p, r, _ = tf(e)
    t = math.pi / 4 if p[0] < 0 else 3 * math.pi / 4
    ex, ey = -BALC_RX * math.cos(t), SC_Y0 - BALC_RY * math.sin(t)
    nx, ny = -math.cos(t) / BALC_RX, -math.sin(t) / BALC_RY
    nl = math.hypot(nx, ny); nx, ny = nx / nl, ny / nl
    pos = (ex, ey, Z_DECK)                                            # landing on the deck at the edge
    write_tf(e, pos=pos, rot=(0.0, 0.0, math.atan2(ny, nx)))
    for c in kids(e):
        if c.get('name') == 'ship_climbing_rope_large':               # plane middle = x + 0.125
            write_tf(c, pos=(-NET_IN - 0.125, 0.004, NET_BAR_Z - 2.1), rot=(0.0, 0.0, 1.571))
        elif c.get('name') == 'end_position':                         # finish the climb on the deck itself
            write_tf(c, pos=(0.0, 0.0, 0.0))
    step = (pos[0] - 0.7 * nx, pos[1] - 0.7 * ny)
    assert any(x0 <= step[0] <= x1 and y0 <= step[1] <= y1 and all(on_platform(x, y) for x in (x0, x1) for y in (y0, y1))
               for y0, y1 in zip(Y_PLAT, Y_PLAT[1:]) for x0, x1 in zip(X_PLAT, X_PLAT[1:])), step   # on a navmesh cell
    spots.append(tuple(round(v, 2) for v in pos))
report.append('climbers: on the stern platform edge %s' % spots)

# --- roof upgrades (awnings over the poop): vanilla roofs (rounded end aft, origin at that end, +y -> -y by the
# 180 deg turn) sit on the model's awning frame, scaled to it (user 2026-10-07: 'on our frame'); level poop -> no tilt
RSX, RSY, RSZ = G['roof_scale_x'](), G['ROOF_SY'], 0.8          # the model's awning frame follows this footprint
R_ORIGIN = (0.0, G['ROOF_ORIGIN_Y'], G['SC_Z_AWNING'] + 0.05 + LIFT)  # base plane on the frame's beam tops
n = 0
for vis in (e for e in kids(files['roof_group']) if e.get('name') == 'visuals'):              # the 'roof' upgrade slot
    for c in kids(vis):
        if not re.fullmatch(r'roof_\d+', c.get('name') or ''):
            continue
        drop(c, 'transform')
        t = ET.Element('transform')
        ET.SubElement(t, 'position', type_name='vec3', value='%.3f, %.3f, %.3f' % R_ORIGIN)
        ET.SubElement(t, 'rotation_euler', type_name='vec3', value='0.000, 0.000, %.3f' % math.pi)
        ET.SubElement(t, 'scale', type_name='vec3', value='%.3f, %.3f, %.3f' % (RSX, RSY, RSZ))
        c.insert(1, t)
        n += 1
report.append('roof upgrades: %d roofs on the awning frame at %s, scale %.2f/%.2f/%.2f' % (n, tuple(round(v, 2) for v in R_ORIGIN), RSX, RSY, RSZ))

# --- hull plating upgrades: our galleass_hull_plate (layer 0 oxidised overlay, layer 1 metal) with NavalDLC's
# hull_plate_* materials per upgrade, as vanilla's hull_group does (both layers set explicitly)
PLATE = {'hull_lead_lvl1': ('hull_plate_lead_oxidize', 'hull_plate_lead'),
         'hull_bronze_lvl2': ('hull_plate_bronze_oxidize', 'hull_plate_bronze'),
         'hull_bronze_lvl3': ('hull_plate_bronze_oxidize', 'hull_plate_bronze_reinforced'),
         'hull_copper_lvl2': ('hull_plate_copper_oxidize', 'hull_plate_copper'),
         'hull_copper_lvl3': ('hull_plate_copper_oxidize', 'hull_plate_copper_polished')}
n = 0
for e in kids(files['hull_group']):
    if e.get('name') not in PLATE:
        continue
    drop(e, 'components')
    write_tf(e, pos=(0, 0, 0), rot=(0, 0, 0))                # the mesh is in ship coordinates (vanilla's was turned)
    comp = mesh_component('plate/' + e.get('name'), 'galleass_hull_plate')
    ch = ET.SubElement(comp.find('meta_mesh_component'), 'children')
    for lod in [''] + ['.lod%d' % k for k in (1, 2, 3)]:
        for i, mat in enumerate(PLATE[e.get('name')]):
            m = ET.SubElement(ch, 'mesh', name='galleass_hull_plate%s.%d' % (lod, i))
            ET.SubElement(ET.SubElement(m, 'misc'), 'material', type_name='string', value=mat)
    e.append(comp)
    e[:] = sorted(e, key=lambda c: ORDER.index(c.tag) if c.tag in ORDER else len(ORDER))
    n += 1
report.append('hull plating: %d upgrades -> galleass_hull_plate with %s' % (n, {k: v[1] for k, v in PLATE.items()}))

# --- lanterns hang on the masts on vanilla's iron arms (nord_lantern_nested: hook 0.75 m from the mast's centre,
# arm pointing out along the entity's +y): pairs either side of the main and mizzen masts, one on the fore mast
# looking aft over the forecastle platform; LANTERN_H above each mast's deck (vanilla: 2.7 .. 3.5 m)
LANTERN_H, LANTERN_ARM = 3.2, 0.75       # 2.8 hung too low (user 2026-10-13)
RAKES = {m: rk for _, m, _, rk, _ in RIGS}
def mast_y(mast, z):
    deck = Z_FC if mast == 'fore' else Z_DECK
    return MASTS[mast] + (z - deck) * math.tan(-RAKES[mast])
lan = kids(files['torch_holder'])
side = [e for e in lan if abs(tf(e)[1][2]) > 1.0 and abs(abs(tf(e)[1][2]) - math.pi) > 0.5]
single = [e for e in lan if e not in side]
assert len(side) == 4 and len(single) == 1, (len(side), len(single))
spots = []
for mast, pair in (('main', side[:2]), ('mizzen', side[2:])):
    z = Z_DECK + LANTERN_H
    for e in pair:
        sgn = 1 if tf(e)[0][0] > 0 else -1
        write_tf(e, pos=(sgn * LANTERN_ARM, mast_y(mast, z), z), rot=(0.0, 0.0, sgn * -math.pi / 2))
        spots.append((mast, round(sgn * LANTERN_ARM, 2), round(mast_y(mast, z), 2), round(z, 2)))
z = Z_FC + LANTERN_H
write_tf(single[0], pos=(0.0, mast_y('fore', z) - LANTERN_ARM, z), rot=(0.0, 0.0, math.pi))     # arm points aft
spots.append(('fore', 0.0, round(mast_y('fore', z) - LANTERN_ARM, 2), round(z, 2)))
report.append('lanterns on the masts: %s' % spots)

# --- no fore weapon slot on the galleass (user 2026-10-07: cannons only, they come from their own project): the
# vanilla ballistas/siphon go; the hull XML has no fore slot any more
bh = files['ship_ballista_holder']
flatten(bh)                                   # linked root: cut the base link first, or the weapons come back
n = len(kids(bh)); drop(bh, 'children')
report.append('ship_ballista_holder: %d vanilla fore weapons removed' % n)

# --- the stern lantern lights up: vanilla's lantern light (LightCycle: on at night; light, flame, ember) copied into
# the model's lantern, a little stronger than the mast lanterns'. The lantern is an open cage (user 2026-10-08: the
# glass kept the light in); vanilla lights cast shadows (light_flags 96), so the light sits in the middle of the cage,
# not at the flame: from there the gilt bowl only shades a cone under the lantern (rays escape down to ~45 deg)
th = files['torch_holder']
LANTERN_Z0 = G['SC_Z_FLOOR'] + 0.12 + 3.5 + LIFT + 0.42          # bottom of the lantern's glass (model)
LIGHT_Z0, LIGHT_R, LIGHT_I = LANTERN_Z0 + 0.95 / 2, 14.0, 220.0  # middle of the cage (pane height 0.95); deck ~4 below
# a fire to match the 0.84 m lantern (user 2026-10-08: bigger wood, light to match): burned_wood_a is 1.25 x 1.0 x 0.48
# at scale 1 (origin at its bottom; vanilla lantern 0.189) -> 0.44 = a 0.55 m pile on the bowl floor; the flame is
# vanilla's ship torch fire (psys_torch_fire_moving; its torches light r 20 / i 100) instead of the small lantern fire
EMBER_S, TORCH_FIRE = 0.44, ('psys_torch_fire_moving', '{516757BC-A1C9-44C7-84DF-9EA28E4E1055}')
src = next(e for e in th.iter('entity') if e.get('name') == 'light')
# not a link: its base is an entity INSIDE nord_lantern_nested, which may not resolve outside that prefab (night
# test 2026-10-08: still dark) -> copy the full vanilla definition (all base links there are already zero)
src = base(src)
assert src is not None and all(p.get('guid') == ZERO for p in src.iter('prefab')), 'vanilla lantern light'
light = copy_regen(src, 'galleass-stern-lantern/')
write_tf(light, pos=(0.0, G['LANTERN_Y'], LANTERN_Z0 + 0.12), rot=(0, 0, 0))
lamp = next(e for e in kids(light) if e.get('name') == 'torch_light')
write_tf(lamp, pos=(0.0, 0.0, LIGHT_Z0 - (LANTERN_Z0 + 0.12)), rot=(0, 0, 0))
ember = next(e for e in kids(light) if e.get('name') == 'burning_campfire')
set_transform(ember, pos=(0.0, 0.0, LANTERN_Z0 + 0.005 - (LANTERN_Z0 + 0.12)), scale=(EMBER_S,) * 3)
flame = next(e for e in kids(light) if e.get('name') == 'prt_torch_light')
set_transform(flame, pos=(0.0, 0.0, LANTERN_Z0 + 0.48 * EMBER_S * 0.6 - (LANTERN_Z0 + 0.12)))
ps = flame.find('components/particle_system_instanced_component')
ps.set('name', TORCH_FIRE[0]); ps.find('misc/guid').set('value', TORCH_FIRE[1])
for lc in light.iter('light_component'):
    misc = lc.find('misc')
    if misc is None:
        misc = ET.SubElement(lc, 'misc')
    # vanilla always keeps the light frame's scale equal to the radius
    for k, t, v in (('light_intensity', 'float', '%.3f' % LIGHT_I), ('light_radius', 'float', '%.3f' % LIGHT_R),
                    ('light_local_frame_rot', 'mat3', ', '.join('%.6f' % (LIGHT_R if i % 4 == 0 else 0) for i in range(9))),
                    ('light_shadow_radius', 'float', '%.3f' % (LIGHT_R - 2))):
        x = misc.find(k)
        if x is None:
            x = ET.SubElement(misc, k, type_name=t)
        x.set('value', v)
th.find('children').append(light)
report.append('stern lantern: wood x%.2f on the bowl floor %.2f, %s, light at (0, %.2f, %.2f) r %.0f i %.0f'
              % (EMBER_S, LANTERN_Z0, TORCH_FIRE[0], G['LANTERN_Y'], LIGHT_Z0, LIGHT_R, LIGHT_I))

# --- banners (user 2026-10-08): vanilla cloth banners (Native generic_flag_vertical_a: force_enable_cloth -> it
# flutters; material with use_tableau_blending). Tagged banner_with_faction_color only: MissionShip collects every child
# with that tag and NavalMissionPrepareView paints the owner's banner on at spawn (not bd_banner_b: SailVisual takes the
# first child with that tag as its cloth top banner). On capture only the sails switch. Layout and iron holders: the
# model's banner_mounts() (one source for both).
BANNER_MESH = 'generic_flag_vertical_a'
def banner(name, pos, normal, s):
    """Cloth banner pinned along its top edge at pos, its face towards the horizontal 'normal' (local x -> normal)."""
    e = new_entity(name, 'banner/' + name)
    write_tf(e, pos=pos, rot=(0.0, 0.0, math.atan2(normal[1], normal[0])))
    t = e.find('transform'); ET.SubElement(t, 'scale', type_name='vec3', value='%.3f, %.3f, %.3f' % (s, s, s))
    e.append(tags('banner_with_faction_color')); e.append(mobility()); e.append(mesh_component('banner/' + name, BANNER_MESH))
    return e
bl = [banner(b['name'], (b['pin'][0], b['pin'][1], b['pin'][2] + LIFT), b['normal'], b['scale']) for b in G['banner_mounts']()]
grp = new_entity('galleass_banners', 'banners')
grp.append(mobility()); grp.append(el('children', None, *bl))
files['torch_holder'].find('children').append(grp)          # ship frame (like the stern lantern)
report.append('banners: %d (%s)' % (len(bl), ', '.join(b.get('name') for b in bl)))
import json
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'renders'), exist_ok=True)
json.dump([(b.get('name'), tf(b)[0], tf(b)[1], float(b.find('transform/scale').get('value').split(',')[0])) for b in bl],
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'renders', 'banners.json'), 'w'))

# --- write --------------------------------------------------------------------------------------------------------
ET.indent(folder, '\t', level=1)
body = ET.tostring(folder, encoding='unicode').replace(' />', '/>')   # the editor's style
with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
    f.write('<?xml version="1.0"?>\n<prefab_files>\n</prefab_files>\n<prefab_folders>\n\t' + body + '\n</prefab_folders>\n')
for line in report:
    print('PREFAB', line)
