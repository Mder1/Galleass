"""Build the galleass ship prefab from the meditheavy clone (make_packed_clone.py output).

python3 build_prefab.py <NavalDLC packed xml> <clone xml> <out xml>

Stage 1 (hull swap): our meshes + physics shapes replace the meditheavy ones, the meditheavy-only geometry is
removed, the rudder becomes a centreline stern rudder and the figureheads go (fixed spur). Everything else (oars,
sails, slots, spawn/boarding points, ...) still sits where the meditheavy has it; stage 2 relays it out.

Nested prefab entities inherit missing elements (transform, tags, components, physics, children, ...) from the
entity their <prefab guid> points to (NavalDLC base prefabs). Before removing something from such an entity it is
flattened: the inherited elements are copied in and the base link is cut, so nothing comes back through inheritance.
"""
import copy, json, math, os, re, sys, uuid
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

# --- deleting inherited children -----------------------------------------------------------------------------------
# The game builds an entity's children as its own (overrides, each linked to the base child it replaces) PLUS every
# base child none of them overrides (NavalDLC's packs leave unchanged children out - 804 entities). So a child deleted
# from a still-linked entity comes back (2026-10-18: the mizzen's vanilla backstay and sheets were in the game again,
# past the stern / at the waterline). Cutting the links instead (up to sail_holder: the three sail rigs unlinked) hung
# the battle loading in MissionShipFactory.CreateMissionShip. So unwanted inherited children are HIDDEN: an override
# kept linked to its base child, moved to the parent's origin and shrunk to a point (scale 0.001: the rope between its
# ends has no length, the rope pile no size), its tags replaced (SailVisual skips it: no simple_rope / bone tag).
def eff_kids(e, depth=0):
    own = kids(e); b = base(e)
    if b is None or depth > 20:
        return own
    taken = {c.find('prefab_link/prefab').get('guid') for c in own if c.find('prefab_link/prefab') is not None}
    return own + [c for c in eff_kids(b, depth + 1) if c.find('prefab_link/instance').get('guid') not in taken]

def name_of(e):
    d = 0
    while e is not None and d < 20:
        if e.get('name'):
            return e.get('name')
        e, d = base(e), d + 1
    return ''

def hide(parent, c):
    """Hide child c of parent (an own override, or a base child the game would merge in)."""
    if not any(x is c for x in kids(parent)):            # a base child: add an override for it
        g = c.find('prefab_link/instance').get('guid')
        o = el('entity', {'name': name_of(c)}, el('prefab_link', None, el('instance', {'guid': guid('hide/%s' % g)}),
                                                   el('prefab', {'guid': g})))
        ch = parent.find('children')
        if ch is None:
            ch = ET.SubElement(parent, 'children')
        ch.append(o)
        c = o
    p, r = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)                  # at the parent's origin (inside the hull)
    drop(c, 'transform'); drop(c, 'tags'); drop(c, 'children'); drop(c, 'components'); drop(c, 'scripts')
    c.append(el('transform', None, el('position', {'type_name': 'vec3', 'value': '%.3f, %.3f, %.3f' % tuple(p)}),
                el('rotation_euler', {'type_name': 'vec3', 'value': '%.3f, %.3f, %.3f' % tuple(r)}),
                el('scale', {'type_name': 'vec3', 'value': '0.001, 0.001, 0.001'})))
    c.append(tags('galleass_hidden'))
    c[:] = sorted(c, key=lambda x: ORDER.index(x.tag) if x.tag in ORDER else len(ORDER))

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
# sail_mesh_entity: in missions only entities with this tag get their 'faction_color' meshes tinted
# (NavalMissionPrepareView.OnShipSpawned) - the painted planking galleass_paint
hull.append(tags('body_mesh', 'rope_physics_body', 'hull_water_mesh', 'sail_mesh_entity'))
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
# no faction-colour overlay any more: the painted planking mesh (galleass_paint, own material) carries the
# 'faction_color' tag itself (user 2026-10-16). GALLEASS_FACTION_PAINT=1 brings the old overlay entity back.
with_paint = os.environ.get('GALLEASS_FACTION_PAINT', '0') == '1'
for x in (hull, paint, water) if with_paint else (hull, water):
    ch.append(x)
report.append('mesh_holder: %d meditheavy entities %s replaced by galleass_hull (9 meshes, bo_galleass), '
              '%sdeckwater' % (len(old), sorted(set(old)), 'galleass_faction_paint, ' if with_paint else '(NO faction paint) '))

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

# a flattened child no longer overrides anything, so the game merges the base child it replaced back in next to it
# (hull_group: 5 plating upgrades twice, roof_group: two platforms). Where that base child is a bare marker (tags,
# transform) the flattened one is linked to it again: it overrides it and, carrying everything itself, inherits nothing
def relink_flattened(parent):
    b, n = base(parent), 0
    if b is None:
        return 0
    taken = {c.find('prefab_link/prefab').get('guid') for c in kids(parent)}
    free = {}
    for c in eff_kids(b):
        g = c.find('prefab_link/instance').get('guid')
        if g not in taken and base(c) is None and all(x.tag in ('prefab_link', 'transform', 'tags') for x in c):
            free.setdefault(name_of(c), []).append(g)
    for c in kids(parent):
        if c.find('prefab_link/prefab').get('guid') == ZERO and free.get(c.get('name')):
            c.find('prefab_link/prefab').set('guid', free[c.get('name')].pop(0)); n += 1
    return n + sum(relink_flattened(c) for c in kids(parent))
for group in ('hull_group', 'roof_group', 'ship_ballista_holder', 'ram_group', 'figurehead_group'):
    n = relink_flattened(files[group])
    if n:
        report.append('%s: %d flattened children linked to their (marker-only) base child again' % (group, n))

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
# 1.5 m in front of every stair's foot and beyond its head stay clear (2026-10-16: crew spots parked at the foot of the
# forecastle stairs and on the poop's stair heads kept the gun crews from climbing): no crew spots there, and the gun
# stores keep out (ref/galleass_keepclear.json for stores_layout.py)
STAIR_CLEAR = []                                               # (x0, x1, y0, y1, z)
for _sx0, _sx1, _ya, _yb, _up in STAIRS:
    _d = 1.0 if _yb > _ya else -1.0                            # foot -> head
    STAIR_CLEAR.append((_sx0 - 0.2, _sx1 + 0.2, min(_ya, _ya - _d * 1.5), max(_ya, _ya - _d * 1.5), Z_DECK))
    STAIR_CLEAR.append((_sx0 - 0.2, _sx1 + 0.2, min(_yb, _yb + _d * 1.0), max(_yb, _yb + _d * 1.0), LEVEL_Z[_up]))   # head: 1 m
# the forecastle platform's back strip (2026-10-16): the way from both stair heads round the fore mast to the guns -
# no gun store, no parked crew there (the store row had left 0.5 m gaps by the mast and the port gun's trail)
STAIR_CLEAR.append((-(FC_STAIR_X + 0.7), FC_STAIR_X + 0.7, FC_YB + 1.0, FC_YB + 1.7, Z_FC))   # in front of the bays by the mast
def in_stair_clear(x, y, z):
    return any(x0 <= x <= x1 and y0 <= y <= y1 and abs(z - zz) < 0.6 for x0, x1, y0, y1, zz in STAIR_CLEAR)
json.dump({'stair_clear': [[round(v, 3) for v in r] for r in STAIR_CLEAR]},
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ref', 'galleass_keepclear.json'), 'w'), indent=1)

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
    rail, else the poop deck inside its balustrade or the forecastle parapet's cap."""
    y = min(max(y, SHIP_Y0), SHIP_Y1)
    if BOX_Y0 + 0.2 <= y <= BOX_Y1 - 0.2:
        y = clear_of_boarding(y)
        if any(abs(y - w) < 0.6 for w in gun_layout.SWIVEL_WAIST_Y):     # nor on a swivel's block (2026-10-17)
            y = min((w + d for w in gun_layout.SWIVEL_WAIST_Y for d in (-0.6, 0.6)
                     if all(abs(w + d - o) >= 0.6 - 1e-6 for o in list(gun_layout.SWIVEL_WAIST_Y) + list(BOARDING_Y))), key=lambda c: abs(c - y))
        return (side * X_CAP, y, Z_CAP)
    if y < BOX_Y0:                       # poop: on the deck just inside the balustrade - its cap rail is too thin
        y = max(y, SC_Y0 + 0.4)          # for a cleat (they overhung it into the balusters, user 2026-10-13)
        if any(abs(y - w) < SW_AREA[0] + 0.2 for w in SWIVEL_POOP_Y):   # out of the swivel gunners' way
            y = min((w + d for w in SWIVEL_POOP_Y for d in (-SW_AREA[0] - 0.2, SW_AREA[0] + 0.2)
                     if SC_Y0 + 0.4 <= w + d and all(abs(w + d - o) >= SW_AREA[0] + 0.2 - 1e-6 for o in SWIVEL_POOP_Y)),
                    key=lambda c: abs(c - y))
        return (side * (sc_hw(y) - 0.40), y, Z_POOP_TOP)
    return (side * max(fc_half(y) - 0.2, 0.3), y, G['FC_Z_PARAPET'] + LIFT + 0.1)

# --- gun working areas (2026-10-16): the carriage at every traverse angle, run out to full recoil, plus the gunner's
# place on its right - kept free of cleats and crew standing spots (gunnery add-on: crews must reach and work the guns)
import gun_layout, json
_ART = os.path.dirname(os.path.abspath(__file__))
GUN_AREAS = []
for _g in gun_layout.placements(G, gun_layout.load_dims()):
    _d = json.load(open(os.path.join(_ART, 'ref', 'galleass_guns.json')))['galleass_' + _g['kind']]
    _t = json.load(open(os.path.join(_ART, 'ref', 'galleass_traverse.json')))['gun_' + _g['name']]
    GUN_AREAS.append((_g, _d, _t, {'culverin': 1.0, 'falcon': 0.8, 'falconet': 0.6}[_g['kind']]))

# swivel guns (petriere da mascolo, 2026-10-17; gun_layout.swivel_placements, limits from swivel_layout.py): their
# working area is on the deck (waist: the gunner's step) inboard of the pin - the gunner walks round it with the tail
SWIVELS = gun_layout.swivel_placements(G)
SWIVEL_POOP_Y = gun_layout.swivel_poop_y(G)
SWIVEL_LIM = json.load(open(os.path.join(_ART, 'ref', 'galleass_swivels.json')))
SW_STEP = dict(wall=0.05, depth=1.20, tread=0.30, half_len=0.75, h=gun_layout.STEP_H)   # = cannon_model build_petriera_step
SW_AREA = (1.2, 1.75)                                          # half width along the rail, depth inboard of the pin
def swivel_local(sw, x, y):
    c, s_ = math.cos(-sw['rot_z']), math.sin(-sw['rot_z'])
    dx, dy = x - sw['pos'][0], y - sw['pos'][1]
    return c * dx - s_ * dy, s_ * dx + c * dy                     # (along the rail, outboard)
def in_swivel_area(x, y, z, pad=0.0):
    for sw in SWIVELS:
        if abs(sw['deck_z'] - z) > 1.2:
            continue
        lx, ly = swivel_local(sw, x, y)
        if abs(lx) <= SW_AREA[0] + pad and -SW_AREA[1] - pad <= ly <= 0.3:
            return 'gun_' + sw['name']
    return None

def in_gun_area(x, y, z, pad=0.25):
    """name of the gun whose working area (x, y, z) is in, else None"""
    sw = in_swivel_area(x, y, z, pad)
    if sw:
        return sw
    for g, d, t, recoil in GUN_AREAS:
        if abs(g['pos'][2] - z) > 1.2:
            continue
        c, s_ = math.cos(-g['rot_z']), math.sin(-g['rot_z'])
        dx, dy = x - g['pos'][0], y - g['pos'][1]
        lx, ly = c * dx - s_ * dy, s_ * dx + c * dy
        piv = t['pivot'][1]
        for deg in (t['min_deg'], (t['min_deg'] + t['max_deg']) / 2, 0.0, t['max_deg']):
            a = math.radians(-deg)                              # into the frame of the gun turned by deg
            u, v = lx, ly - piv
            u, v = u * math.cos(a) - v * math.sin(a), u * math.sin(a) + v * math.cos(a)
            v += piv
            if -d['half_w'] - pad <= u <= d['half_w'] + 0.70 + pad and d['rear_y'] - recoil - pad <= v <= d['muzzle_y'] + pad:
                return 'gun_' + g['name']
    return None

MASTS_AT = []                                                 # (y, deck z) of the mast steps, filled with the rigs
MAST_AXES = []                                                # (y, deck z, rake) of each mast where it crosses its deck
HATCHES = [(-6.5, 0.75, 0.9), (12.0, 0.75, 0.9)]              # (y, half length, half width): the model's gratings

def deck_spot(x, y):
    """Open deck surface near (x, y) for a cleat: on the poop / forecastle platform / gun deck, clear of walls,
    stairs, mast steps, hatches and the guns' working areas (the nearest such spot, 0.1 m rings)."""
    p = _deck_spot(x, y)
    if not in_gun_area(*p):
        return p
    for r in [0.1 * i for i in range(1, 31)]:
        for k in range(16):
            q = _deck_spot(x + r * math.cos(k * math.pi / 8), y + r * math.sin(k * math.pi / 8))
            if abs(q[2] - p[2]) < 0.05 and not in_gun_area(*q):
                return q
    return p

def _deck_spot(x, y):
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

# --- belaying fittings (user 2026-10-18: galley-style pin rails and bitts, deliberately placed, instead of the 25
# vanilla cleats moved onto the cap rail plus one more per re-anchored rope end - 57 cleats, many orphans, some over
# gunports). The game ties every brace and sheet to the nearest knot_point(s) of knobs_holder each tick (SailVisual
# .TickRopesAndPulleys; replayed by rig_check.py), so every pin is a knot point and the fittings ARE the belaying plan.
# Meshes and pin positions: belay_model.py -> ref/galleass_belay_pins.json.
BELAY_PINS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ref', 'galleass_belay_pins.json')))
# pin boards on the cap rails (pins through board and rail; a rail on the bulwark's inner face put falls to a yard out
# over the side through the cap - rig_check). Waist, both sides: (y centre, pins), by mast
CAP_BOARDS = [(9.3, 4), (2.05, 3), (-3.4, 4),                  # main: forward / abeam / abaft
              (13.0, 4),                                      # fore: abaft (forward: the forecastle parapet)
              (-10.0, 4)]                                     # mizzen: forward (abaft: bitts on the poop; a board
                                                              # at -12.4 led falls through the poop's front)
FC_BOARDS = [(22.5, 3), (67.5, 3)]                            # forecastle parapet cap, bearings (deg) each side
POOP_BITTS = [(1.7, -23.0, 3)]                                # (|x|, y, pins), both sides, along the ship
SHROUD_FEET = (3.9, 0.3, -1.6, 16.8, 15.0, -14.6, -16.0)      # = standing_rig.py RIGS feet (tackles up the shrouds)
def board_clear(y, half):
    """Obstacles on the waist cap rail for a pin board of half length 'half' at y: swivels, shroud tackles, boarding
    hooks, the castles' ends."""
    bad = [(w - 0.9, w + 0.9) for w in gun_layout.SWIVEL_WAIST_Y] + [(f - 0.45, f + 0.45) for f in SHROUD_FEET] + \
          [(b - 0.6, b + 0.6) for b in BOARDING_Y] + [(FC_YB - 0.2, 99.0), (-99.0, BOX_Y0 + 0.3)]
    return [o for o in bad if o[0] < y + half + 0.03 and o[1] > y - half - 0.03]
BELAY = []                                                    # (name, mesh, (x, y, z), yaw)
for y, n in CAP_BOARDS:
    half = (n * BELAY_PINS['pin_spacing'] + 0.16) / 2
    hit = board_clear(y, half)
    assert not hit, 'pin board at y %.2f hits %s' % (y, hit)
    for side in (-1, 1):
        BELAY.append(('pinrail_%+d_%.1f' % (side, y), 'galleass_pinrail_%d' % n, (side * X_CAP, y, Z_CAP), 0.0))
R_PAR = FC_R - 0.175                                          # parapet's centre line (wall 0.35 thick)
Z_PAR = G['FC_Z_PARAPET'] + LIFT + 0.1                        # its cap's top (= rail_point)
for deg, n in FC_BOARDS:
    for s in (-1, 1):
        x, y = G['fc_point'](s * deg, R_PAR)
        BELAY.append(('pinrail_fc_%+d' % (s * deg), 'galleass_pinrail_%d' % n, (x, y, Z_PAR), -math.radians(s * deg + 90)))
for ax, y, n in POOP_BITTS:
    for side in (-1, 1):
        x = side * ax
        assert abs(x) < sc_hw(y) - 0.4 and y > SC_Y0 + 0.5, 'poop bitts off the poop'
        BELAY.append(('bitts_poop_%+d' % side, 'galleass_bitts_%d' % n, (x, y, Z_POOP_TOP), 0.0))
# braces and sheets search their pins within this distance (SailVisual 'Rope Connection Max Distance': horizontal for
# braces, 3D for sheets; vanilla 7 / 16 / 18 here). Beyond it the game takes the nearest pin anywhere, ignoring the
# side of the yard - every sheet (its sail corner 20-40 m up) and the fore braces always fell back (rig_check)
ROPE_REACH = 60.0
def set_script_var(e, script, name, value):
    sc = next(x for x in e.findall('scripts/script') if x.get('name') == script)
    vs = sc.find('variables')
    if vs is None:
        vs = ET.SubElement(sc, 'variables')
    v = next((x for x in vs if x.get('name') == name), None)
    if v is None:
        v = ET.SubElement(vs, 'variable', name=name, type_name='float')
    v.set('value', '%.3f' % value)

def belay_pins(item):
    _, mesh, (x, y, z), yaw = item
    c, s_ = math.cos(yaw), math.sin(yaw)
    return [(x + c * px - s_ * py, y + s_ * px + c * py, z + pz) for px, py, pz in BELAY_PINS['pins'][mesh]]
PINS = [p for it in BELAY for p in belay_pins(it)]
FASTENERS = PINS                                              # (rig_check / re-anchoring: ends go to the nearest pin)

kh = files['knobs_holder']
KNOT_TMPL = next(k for c in kids(kh) if c.get('name') == 'cleat_a' for k in kids(c) if k.get('name') == 'knot_point')
flatten(kh)
n_old = len(kids(kh)); drop(kh, 'children')
BELAY_MISSING = [m for m in sorted({it[1] for it in BELAY})
                 if not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Assets', m + '_geo.tpac'))]
fits = []
for i, it in enumerate(BELAY):
    name, mesh, pos, yaw = it
    seed = 'belay/%s' % name
    e = new_entity(name, seed)
    write_tf(e, pos=pos, rot=(0.0, 0.0, yaw))
    bo = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Assets', 'bo_%s_geo.tpac' % mesh)
    if mesh.startswith('galleass_bitts_') and os.path.exists(bo) and os.path.getsize(bo) > 600:
        e.append(el('physics', None, el('shape', {'type_name': 'string', 'value': 'bo_' + mesh}),
                    el('body_flags', None, el('body_flag', {'name': 'moveable'})),
                    el('move_to_batched_kinematic', {'type_name': 'bool', 'value': '1'})))
    e.append(tags('galleass_belay')); e.append(mobility())
    e.append(mesh_component(seed, mesh))
    ks = []
    for j, (px, py, pz) in enumerate(BELAY_PINS['pins'][mesh]):
        k = copy_regen(KNOT_TMPL, '%s/pin/%d' % (seed, j))
        write_tf(k, pos=(px, py, pz), rot=(0.0, 0.0, 0.0))
        ks.append(k)
    e.append(el('children', None, *ks))
    e[:] = sorted(e, key=lambda c: ORDER.index(c.tag) if c.tag in ORDER else len(ORDER))
    fits.append(e)
kh.append(el('children', None, *fits))
report.append('knobs_holder: %d vanilla cleats out; %d belaying fittings (%d pin rails, %d bitts), %d pins = knot points%s'
              % (n_old, len(BELAY), sum('pinrail' in it[1] for it in BELAY), sum('bitts' in it[1] for it in BELAY), len(PINS),
                 ('; KIT: import ' + ', '.join(BELAY_MISSING)) if BELAY_MISSING else ''))

def fasten(surface):
    """The belaying pin nearest to this point (the rope's end; the game re-picks braces / sheets at run time)."""
    return min(PINS, key=lambda p: math.dist(p, surface))

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
# our masts (mast_model.py: woolding, calcese, main gabbia) replace the vanilla mast meshes in the same frames; the
# vanilla component tints its greyscale bw_oar_wood_a per sub-mesh (factor_color) -> the same tint on our wood
# sub-meshes, read from the Kit's mesh package (so the prefab is only built once the Kit has the masts)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tpac_tools'))
import meshinfo
MAST_WOOD = '22df0162-6ee6-42a5-8218-aebb65cffd30'              # bw_oar_wood_a (vanilla mast + oar material)
def kit_submeshes(mesh, material):
    pkg = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Assets', mesh + '_geo.tpac')
    if not os.path.exists(pkg):
        raise SystemExit('Kit mesh %s missing (%s) - import it in the Modding Kit first' % (mesh, pkg))
    for tg, g, name, meta in meshinfo.assets(pkg):
        if name == mesh and str(tg).startswith('a08f8b97'):
            return [m['name'] for m in meshinfo.meshes(meta) if material is None or m['material'] == material]
    raise SystemExit('no metamesh %s in %s' % (mesh, pkg))

MAST_TINT = '0.192, 0.110, 0.063, 1.000'                        # meditheavy wood; the mizzen (from the meditlight)
                                                                # was grey - one tint for all masts and yards
def swap_mast(rig):
    for mmc in rig.iter('meta_mesh_component'):                 # the yards: same tint as the masts
        if (mmc.get('name') or '').startswith('ship_yard_lateen'):
            for f in mmc.iter('factor_color'):
                f.set('value', MAST_TINT)
    me = next(e for e in rig.iter('entity') if e.get('name') == 'mast_mesh')
    mmc = me.find('components/meta_mesh_component')
    size = mmc.get('name').rsplit('_', 1)[1]                        # ship_mast_lateen_a_<size>
    tint = MAST_TINT
    ours = 'galleass_mast_' + size
    mmc.set('name', ours)
    mmc.find('prefab_link/prefab').set('guid', ZERO)               # own component, no vanilla link
    ch = mmc.find('children')
    if ch is None:
        ch = ET.SubElement(mmc, 'children')
    ch[:] = []
    for sub in kit_submeshes(ours, MAST_WOOD):
        m = ET.SubElement(ch, 'mesh', name=sub)
        ET.SubElement(ET.SubElement(m, 'misc'), 'factor_color', type_name='vec4', value=tint)
    report.append('mast %s -> %s (wood tint %s on %d sub-meshes)' % (rig.get('name'), ours, tint, len(ch)))

# --- re-rig phase 3 (user 2026-10-13, rope plan approved): lateen galleys carried no stays -> the vanilla big_rope
# stays go (the long ropes across the ship, two of them through the other masts' sails); the vanilla shrouds (static
# ropes with no yard end) go too - ours come with the standing rig (shrouds abaft the yard, with tackles). One stay per
# mast becomes the TIE (amante): from the yard's hoist (yard_axis_shift_entity, end tagged attached_to_yard so it follows
# the yard) up to the calcese, leaving the lower sheave on the yard's side (+x). Yard lifts, flag halyard, sheets and
# braces stay vanilla.
import mast_dims as MD
def own_tags(e):
    t = inh(e, 'tags')
    return [x.get('name') for x in t.iter('tag')] if t is not None else []

def add_tag(e, name):
    t = e.find('tags')
    if t is None:
        src = inh(e, 'tags')
        t = copy.deepcopy(src) if src is not None else tags()
        e.insert(len([c for c in e if c.tag in ('prefab_link', 'transform')]), t)
    inner = t.find('tags')
    if name not in [x.get('name') for x in inner.iter('tag')]:
        ET.SubElement(inner, 'tag', name=name)

def rerig_ropes(rig, deck_z):
    srp = next(e for e in rig.iter('entity') if e.get('name') == 'static_ropes_parent')
    W = {id(e): (wm, wp, pm, pp) for e, wm, wp, pm, pp in walk(rig)}
    mm = next(e for e in rig.iter('entity') if e.get('name') == 'mast_mesh')
    size = mm.find('components/meta_mesh_component').get('name').rsplit('_', 1)[1]
    sp = MD.MASTS[size]
    yard = next(e for e in rig.iter('entity') if e.get('name') == 'yard_axis_shift_entity')   # the yard's hoist
    stays, shrouds = [], []
    for c in eff_kids(srp):                                       # (incl. the base's: the game merges them in)
        ends = [x for x in c.iter('entity') if x.get('name') in ('rope_start', 'rope_end')]
        on_yard = any('attached_to_yard' in own_tags(x) for x in ends)
        if 'big_rope' in own_tags(c):
            stays.append(c)
        elif not on_yard:
            shrouds.append(c)
    tie = next(c for c in stays if any(c is k for k in kids(srp)))
    for c in [x for x in stays if x is not tie] + shrouds:
        hide(srp, c)
    wm, wp = W[id(mm)][0], W[id(mm)][1]
    hx, _ = MD.calcese_half(sp)
    loc = (hx + 0.03, 0.0, MD.sheaves(sp)[0] - 0.05)
    top = [wp[i] + mvec(wm, loc)[i] for i in range(3)]
    low = W[id(yard)][1]
    for x in tie.iter('entity'):
        if x.get('name') == 'rope_start':
            set_world_pos(x, W[id(x)][2], W[id(x)][3], top)
        elif x.get('name') == 'rope_end':
            set_world_pos(x, W[id(x)][2], W[id(x)][3], low)
            add_tag(x, 'attached_to_yard')
    # flag halyard: lower end down to the deck by the mast foot (standing_rig.py heaps it there); the vanilla rope pile
    # mesh on its start (a 1.5 m heap) goes
    hx_, hy_ = MD.HALYARD_FOOT[size]
    zl = deck_z - wp[2]
    foot = [wp[i] + mvec(wm, (hx_, hy_, zl))[i] for i in range(3)]
    foot[2] = deck_z + MD.HALYARD_DZ
    hal = next(c for c in rig.iter('entity') if 'flag_capture_rope' in own_tags(c))
    for x in hal.iter('entity'):
        if x.get('name') == 'rope_start':
            set_world_pos(x, W[id(x)][2], W[id(x)][3], foot)
            drop(x, 'components')
    report.append('%s flag halyard down to (%.2f, %.2f, %.2f)' % (rig.get('name'), *foot))
    # the mizzen's clew lies beyond our stern: its two stability ropes (sheets, dynamic, to the clew bone) crossed the
    # stern lantern and hung in mid-air with the sail furled (user 2026-10-13); the rotator pulleys still sheet it
    n_sheets = 0
    if size == 'small':
        stp = next(e for e in rig.iter('entity') if e.get('name') == 'stability_ropes_parent')
        for c in eff_kids(stp):
            if 'simple_rope' in own_tags(c):
                hide(stp, c); n_sheets += 1
    if n_sheets:
        report.append('%s: %d stability ropes (sheets to the clew beyond the stern) removed' % (rig.get('name'), n_sheets))
    # vanilla rope hangers (rope_knot_point: peg + coil) on the mast whose rope is gone (the stays' upper ends, ~18 m up
    # on main and fore - audit 2026-10-18): no rope end within 1 m -> out
    W2 = {id(e): wp for e, _, wp, _, _ in walk(rig)}
    ends = [W2[id(x)] for x in rig.iter('entity') if re.fullmatch(r'rope_start|rope_end|free_rope\d+|fixed_rope\d+|end_point_rope|end_target_point', x.get('name') or '')]
    smast = next(e for e in rig.iter('entity') if e.get('name') == 'sail_mast')
    n_hang = 0
    for c in kids(smast):
        if c.get('name') == 'rope_knot_point' and min(math.dist(W2[id(c)], q) for q in ends) > 1.0:
            smast.find('children').remove(c); n_hang += 1
    report.append('%s: %d rope hangers without a rope removed from the mast' % (rig.get('name'), n_hang))
    report.append('%s ropes: %d stays + %d shrouds removed; tie from the yard (%.2f, %.2f, %.2f) to the calcese '
                  '(%.2f, %.2f, %.2f)' % (rig.get('name'), len(stays) - 1, len(shrouds), *low, *top))

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
    MAST_AXES.append((MASTS[mast], zd, rake))
    write_tf(rig, pos=P, rot=(rake, 0.0, 0.0))
    swap_mast(rig)
    set_script_var(rig, 'sail_visual', 'Rope Connection Max Distance', ROPE_REACH)
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
    rerig_ropes(rig, zd)

# --- spritsail (re-rig phase 4, user 2026-10-19: a WORKING sail, sized to the drawing): vanilla's small square rig
# (galley_ship_nested; 15.4 m yard) scaled by MD.SPRIT_SCALE, its yard slung under the bowsprit (mast_dims SPRIT_*).
# sail_center_3 <-> the 4th <sail> (square) in galleass_mission_ships.xml. The rig keeps its own (vertical) yaw axis
# through the sling. Its vanilla mast goes: sail_mast is shrunk to a point inside the bowsprit with its tags kept
# (SailVisual reads 'mast_entity' for the mast colour and the mast fire, not everywhere null-checked); stays, the flag
# halyard and the level-3 topsail extras are hidden; the yard lifts run up to the bowsprit; brails come to the
# forecastle pins. Braces and sheets pick their pins at run time like the lateens'
sprit = copy_regen(next(e for e in nav_file('galley_ship_nested', 'sail_holder').iter('entity')
                        if e.get('name') == 'sail_square_small_nested'), 'galleass-rig/sprit/')
if sprit.find('tags') is None:                                 # the galley's instance inherits its tags (sail_center_0)
    sprit.insert(len([c for c in sprit if c.tag in ('prefab_link', 'transform', 'physics')]), copy.deepcopy(inh(sprit, 'tags')))
for t in sprit.find('tags').iter('tag'):
    if t.get('name', '').startswith('sail_center_'):
        t.set('name', 'sail_center_3')
assert [t.get('name') for t in inh(sprit, 'tags').iter('tag') if t.get('name').startswith('sail_center_')] == ['sail_center_3']
sh.find('children').append(sprit)
S_SC = MD.SPRIT_SCALE
s_yard = next(e for e in sprit.iter('entity') if e.get('name') == 'sail_yard')
YARD_LOCAL = tf(s_yard)[0]                                    # the yard's hoist in the rig frame (yaw entity at 0)
SLING = MD.sprit_point(MD.SPRIT_SLING_Y)
YARD_AT = (0.0, SLING[1], SLING[2] - MD.SPRIT_YARD_DROP)
SPRIT_O = tuple(YARD_AT[i] - S_SC * YARD_LOCAL[i] for i in range(3))
set_transform(sprit, pos=SPRIT_O, rot=(0.0, 0.0, 0.0), scale=(S_SC, S_SC, S_SC))
set_script_var(sprit, 'sail_visual', 'Rope Connection Max Distance', ROPE_REACH)
def to_rig(p):
    return tuple((p[i] - SPRIT_O[i]) / S_SC for i in range(3))
# the vanilla mast and everything on it (bollards, hangers, blocks, mast ropes): a point at the sling, in the spar
s_mast = next(e for e in sprit.iter('entity') if e.get('name') == 'sail_mast')
hal = next(c for c in kids(s_mast) if 'flag_capture_rope' in own_tags(c))
hide(s_mast, hal)
set_transform(s_mast, pos=to_rig(SLING), rot=(0.0, 0.0, 0.0), scale=(0.001, 0.001, 0.001))
# level-3 upgrade extras of the square rig (two small topsail lateens over the yard)
s_yaw = next(e for e in sprit.iter('entity') if e.get('name') == 'yaw_rotation_entity')
n_l3 = 0
for c in kids(s_yaw):
    if 'lvl3_lateens' in own_tags(c):
        hide(s_yaw, c); n_l3 += 1
# static ropes: the two stays go; the four yard lifts run from the yard to the bowsprit (outer pair to the tip, inner
# pair to the sling)
s_srp = next(e for e in sprit.iter('entity') if e.get('name') == 'static_ropes_parent')
TIP = MD.sprit_tip()
n_stay, lifts = 0, []
for c in kids(s_srp):
    if 'big_rope' in own_tags(c):
        hide(s_srp, c); n_stay += 1
    elif 'attached_to_yard' in own_tags(c):
        lifts.append(c)
Wsp = {id(e): (wm, wp, pm, pp) for e, wm, wp, pm, pp in walk(sprit)}
for c in lifts:
    end = next(x for x in c.iter('entity') if x.get('name') == 'rope_end')
    start = next(x for x in c.iter('entity') if x.get('name') == 'rope_start')
    outer = abs(Wsp[id(end)][1][0]) > 2.0
    goal = MD.sprit_point(TIP[1] - 0.5) if outer else MD.sprit_point(MD.SPRIT_SLING_Y + 0.4)
    goal = (goal[0], goal[1], goal[2] - 0.15)                 # under the spar
    set_world_pos(start, Wsp[id(start)][2], Wsp[id(start)][3], goal)
# brails (fold pulleys): the block and its target ride on the clew; of the rope ends not on the yard, those low at the
# vanilla mast's foot belay on the nearest forecastle pin, those at its head lead from under the bowsprit's sling
n_low = n_high = 0
for fold in (e for e in sprit.iter('entity') if 'sail_fold_pulleys' in own_tags(e)):
    for e in fold.iter('entity'):
        if not re.fullmatch(r'free_rope\d+|fixed_rope\d+', e.get('name') or '') or 'attached_to_yard' in own_tags(e):
            continue
        _, wp, pm, pp = Wsp[id(e)]
        z_local = (wp[2] - SPRIT_O[2]) / S_SC
        if z_local < 10.0:
            set_world_pos(e, pm, pp, fasten(deck_spot(wp[0], wp[1]))); n_low += 1
        elif z_local > 13.0:
            set_world_pos(e, pm, pp, (SLING[0], SLING[1], SLING[2] - 0.2)); n_high += 1
for mmc in sprit.iter('meta_mesh_component'):                 # the yard: our mast wood tint
    if (mmc.get('name') or '').startswith('ship_yard_'):
        for f in mmc.iter('factor_color'):
            f.set('value', MAST_TINT)
# the braces' and sheets' forward legs need pins ahead of the yard (SailVisual picks knots on the side the yard faces;
# none there -> nearest pin anywhere): a pair at the bowsprit's end (step 2: a fitting on the bowsprit mesh)
SPRIT_END_PINS = [(s_ * 0.18, MD.sprit_tip()[1] - 0.6, MD.sprit_point(MD.sprit_tip()[1] - 0.6)[2] - 0.12) for s_ in (-1, 1)]
se = new_entity('sprit_end', 'belay/sprit_end')
write_tf(se, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0))
se.append(tags('galleass_belay')); se.append(mobility())
se.append(el('children', None, *[write_tf(k, pos=p, rot=(0.0, 0.0, 0.0)) or k for k, p in
                                  ((copy_regen(KNOT_TMPL, 'belay/sprit_end/pin/%d' % j), p) for j, p in enumerate(SPRIT_END_PINS))]))
kh.find('children').append(se)
PINS.extend(SPRIT_END_PINS)
Wsp = {id(e): wp for e, _, wp, _, _ in walk(sprit)}
_bones = [Wsp[id(e)] for e in sprit.iter('entity') if e.get('name') == 'end_target_point'
          or (e.get('name') == 'rope_end' and 'attached_to_yard' in own_tags(e))]             # yard arms + clews
report.append('spritsail: %s x%.2f, yard at (%.2f, %.2f, %.2f), rig origin (%.2f, %.2f, %.2f); sail corners z %.2f..%.2f, '
              'y %.1f..%.1f; %d stays, flag halyard, %d lvl3 extras hidden; %d lifts to the bowsprit, brail ends %d to pins + %d to the sling'
              % (sprit.get('name'), S_SC, *YARD_AT, *SPRIT_O, min(b[2] for b in _bones), max(b[2] for b in _bones),
                 min(b[1] for b in _bones), max(b[1] for b in _bones), n_stay, n_l3, len(lifts), n_low, n_high))

rc = files['rope_cosmetics_holder']
assert base(rc) is None
n = len(kids(rc)); drop(rc, 'children')
report.append('rope_cosmetics_holder: %d meditheavy hull-side ropes/cleats removed (CosmeticRopeManager kept)' % n)

# --- arrow braziers: clamped to the bulwark (box) / poop balustrade, standing on the deck --------------------
# ship_brazier_b reaches 0.65 m outboard of its origin, foot 0.69 m below it (mesh bounds)
BRAZIER_Y = [-16.3, -13.0, -11.0, -6.1, -0.65, 4.75, 10.2, 20.0]          # clear of the gunports and boarding
BRAZIER_POOP_Y = [-23.0, -20.0, -16.0]          # between the awning posts (y -17.2, -19.7, -21.9)
bh = files['brazier_holder']
# (2026-10-16) the side slot (its only piece: the fire-arrow brazier) is gone from the hull (ModuleData galleass_side
# dropped, 2026-10-15): its braziers stood in the stern chasers' working area - removed; the empty holder stays
if True:
    n = len(kids(bh)); drop(bh, 'children')
    report.append('brazier_holder: %d braziers of the removed side slot removed' % n)
by_side = {-1: [], 1: []}
for c in kids(bh):
    by_side[1 if tf(c)[0][0] > 0 else -1].append(c)
for s, lst in (by_side.items() if any(by_side.values()) else ()):
    spots = [(s * (W_IN - 0.65), y, Z_DECK + 0.69) for y in BRAZIER_Y] + \
            [(s * (sc_hw(y) - 0.06 - 0.65), y, Z_POOP + 0.69) for y in BRAZIER_POOP_Y]
    assert len(lst) == len(spots), (s, len(lst), len(spots))
    for c, p in zip(lst, spots):
        write_tf(c, pos=p, rot=(0.0, 0.0, s * math.pi / 2))
        for k in kids(c):
            write_tf(k, pos=(0, 0, 0), rot=(0, 0, 0))
if any(by_side.values()):
    report.append('brazier_holder: %d braziers on the bulwark (deck z %.2f) and the poop (z %.2f)'
                  % (sum(map(len, by_side.values())), Z_DECK, Z_POOP))

# --- deck upgrades (ammo / arrow crates, boarding weapons): base mesh 0.095 below the entity -----------------
du = files['deck_upgrade_holder']
DU_MOVES = []                                     # (meditheavy pos, ours): the burning system's crate fires follow
for c in kids(du):
    (x, y, z), _, _ = tf(c)
    if y < SC_Y1:
        p = (x, y, Z_POOP + 0.095)                # on the poop
    elif y > 10.0:
        p = (x, 9.0, Z_DECK + 0.095)              # was over the fore hatch (y 11.25..12.75)
    else:
        p = (x, y, Z_DECK + 0.095)
    write_tf(c, pos=p)
    DU_MOVES.append(((x, y, z), p))
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

# the guns are solid (carriage + barrel; physics bodies the navmesh does not know): their footprints - carriage width,
# from the fully recoiled trail to the muzzle, at rest traverse - are cut out, else men are routed through them and
# stick (2026-10-16: loaders wedged between the bulwark and the next gun). Grid lines at each footprint's bounding box
# (exact for the guns square to the ship), cells whose centre is inside a footprint dropped.
# every cut-out is PADDED by NAV_PAD (2026-10-16): the navmesh is where a man's CENTRE may go (body radius 0.37), so a
# gap narrower than a man disappears instead of luring the AI into it; the masts are cut out too
NAV_PAD = 0.25
MAST_R = 0.30
def mast_y(y0, zd, rake, z):
    return y0 + (z - zd) * -math.tan(rake)
def mast_foot(x, y, z):
    return any(math.hypot(x, y - mast_y(y0, zd, rake, z)) <= MAST_R + NAV_PAD for y0, zd, rake in MAST_AXES)
def gun_foot(x, y, z):
    for g, d, t, recoil in GUN_AREAS:
        if abs(g['pos'][2] - z) > 1.0:
            continue
        c, s_ = math.cos(-g['rot_z']), math.sin(-g['rot_z'])
        dx, dy = x - g['pos'][0], y - g['pos'][1]
        lx, ly = c * dx - s_ * dy, s_ * dx + c * dy
        # the gun at rest is padded; the strip its trail covers only while recoiled is cut without padding (a passage
        # behind the guns may narrow while one reloads, not vanish - the cabin's side guns closed it off for good)
        if abs(lx) <= d['half_w'] + 0.05 + NAV_PAD and d['rear_y'] - 0.05 - NAV_PAD <= ly <= d['muzzle_y']:
            return 'gun_' + g['name']
        if abs(lx) <= d['half_w'] + 0.05 and d['rear_y'] - recoil - 0.05 <= ly <= d['muzzle_y']:
            return 'gun_' + g['name']
    return mast_foot(x, y, z) or None
def _merge(base, extra, gap=0.08):
    out = sorted(set(base))
    for v in sorted(extra):
        if base and not (min(base) < v < max(base)):
            continue
        if all(abs(v - o) > gap for o in out):
            out.append(round(v, 4)); out.sort()
    return out
# the gun stores (stores_layout.py) are solid too
_ST = json.load(open(os.path.join(_ART, 'ref', 'galleass_stations.json')))
_SD = json.load(open(os.path.join(_ART, 'ref', 'galleass_stores.json')))
STORE_FOOT = []                                                # (x, y, z, rot, hx, hy)
for _st in _ST:
    for _it in _st['items']:
        _n = _it['name']
        if _n == 'keg': _hx, _hy = _SD['keg']['radius'] + 0.06, _SD['keg']['radius']
        elif _n.startswith('rack_'): _hx, _hy = _SD['racks'][_n[5:]]['size'][0] / 2, _SD['racks'][_n[5:]]['size'][1] / 2
        elif _n.startswith('locker_'): _hx, _hy = _SD['lockers'][_n[7:]]['size'][0] / 2, _SD['lockers'][_n[7:]]['size'][1] / 2
        else: _hx = _hy = _SD['basket']['radius']
        STORE_FOOT.append((_it['pos'][0], _it['pos'][1], _st['z'], _it['rot_z'], _hx + 0.05 + NAV_PAD, _hy + 0.05 + NAV_PAD))
def store_foot(x, y, z):
    for sx, sy, sz, rot, hx, hy in STORE_FOOT:
        if abs(sz - z) > 1.0: continue
        c, s_ = math.cos(-rot), math.sin(-rot)
        lx, ly = c * (x - sx) - s_ * (y - sy), s_ * (x - sx) + c * (y - sy)
        if abs(lx) <= hx and abs(ly) <= hy: return True
    return False
_fx, _fy = {'deck': [], 'fc': []}, {'deck': [], 'fc': []}
for sx, sy, sz, rot, hx, hy in STORE_FOOT:
    lvl = 'fc' if abs(sz - Z_FC) < 0.5 else 'deck'
    ca, sa = math.cos(rot), math.sin(rot)
    for lx in (-hx, hx):
        for ly in (-hy, hy):
            _fx[lvl].append(sx + ca * lx - sa * ly); _fy[lvl].append(sy + sa * lx + ca * ly)
for y0, zd, rake in MAST_AXES:
    for lvl, z in (('deck', Z_DECK), ('fc', Z_FC)):
        ym = mast_y(y0, zd, rake, z)
        for k in (-1, 1):
            _fx[lvl].append(k * (MAST_R + NAV_PAD)); _fy[lvl].append(ym + k * (MAST_R + NAV_PAD))
for g, d, t, recoil in GUN_AREAS:
    lvl = 'fc' if abs(g['pos'][2] - Z_FC) < 0.5 else 'deck'
    ca, sa = math.cos(g['rot_z']), math.sin(g['rot_z'])
    for lx in (-d['half_w'] - 0.05 - NAV_PAD, d['half_w'] + 0.05 + NAV_PAD, -d['half_w'] - 0.05, d['half_w'] + 0.05):
        for ly in (d['rear_y'] - 0.05 - NAV_PAD, d['rear_y'] - recoil - 0.05, d['muzzle_y']):
            _fx[lvl].append(g['pos'][0] + ca * lx - sa * ly); _fy[lvl].append(g['pos'][1] + sa * lx + ca * ly)
# the waist swivels' steps (2026-10-17): the step's top is navmesh 0.30 above the deck, the low tread a ramp up to it
# from the deck (like the stairs: its foot vertices are the deck's), the step's ends padded off the deck
STEP_IN = [(SW_STEP['wall'] + 0.25, SW_STEP['wall'] + SW_STEP['depth']),                       # top (ly, inboard)
           (SW_STEP['wall'] + SW_STEP['depth'], SW_STEP['wall'] + SW_STEP['depth'] + SW_STEP['tread'])]   # ramp
for sw in SWIVELS:
    if not sw['step']:
        continue
    sd = 1 if sw['pos'][0] > 0 else -1
    for d in (STEP_IN[0][1], STEP_IN[1][1]):
        _fx['deck'].append(sw['pos'][0] - sd * d)
    for d in (SW_STEP['half_len'], SW_STEP['half_len'] + NAV_PAD):
        _fy['deck'] += [sw['pos'][1] - d, sw['pos'][1] + d]
def step_cell(x0, x1, y0, y1):
    """('top' | 'ramp' | 'pad', swivel) for a deck cell on / beside a gunner's step, else None."""
    for sw in SWIVELS:
        if not sw['step']:
            continue
        lx, ly = swivel_local(sw, (x0 + x1) / 2, (y0 + y1) / 2)
        if -ly > STEP_IN[1][1] or abs(lx) > SW_STEP['half_len'] + NAV_PAD:
            continue
        if abs(lx) > SW_STEP['half_len']:
            return 'pad', sw
        return ('top' if -ly < STEP_IN[0][1] else 'ramp'), sw
    return None
# the poop swivels' timber stands (2026-10-17): solid, cut out (padded) like the stores; across the ship the 0.25 m
# grid below covers them (own x lines run the whole length: +1150 faces), along it the poop's own lines
SW_STAND = (0.17, 0.14)                                        # foot half width (along the rail), inboard depth
_fy_poop = []
for sw in SWIVELS:
    if not sw['stand']:
        continue
    hx, hy = SW_STAND[0] + 0.05 + NAV_PAD, SW_STAND[1] + 0.05 + NAV_PAD
    STORE_FOOT.append((sw['pos'][0], sw['pos'][1], sw['deck_z'], sw['rot_z'], hx, hy))
for _name, _mesh, _pos, _yaw in BELAY:                         # bitts (belaying fittings on the poop): solid, cut out
    if _mesh.startswith('galleass_bitts_'):
        _n = int(_mesh.rsplit('_', 1)[1]); _bt = BELAY_PINS['bitts']
        STORE_FOOT.append((_pos[0], _pos[1], _pos[2], _yaw, _bt['post'] / 2 + 0.05 + NAV_PAD,
                           (_n * BELAY_PINS['pin_spacing'] + 0.10) / 2 + _bt['post'] + 0.05 + NAV_PAD))
for sx, sy, sz, rot, hx, hy in STORE_FOOT:                     # stands, the poop's swivel locker, bitts
    if abs(sz - Z_POOP_TOP) < 0.5:
        ca, sa = math.cos(rot), math.sin(rot)
        for lx in (-hx, hx):
            for ly in (-hy, hy):
                _fy_poop.append(sy + sa * lx + ca * ly)
Y_POOP = _merge(Y_POOP, _fy_poop + [y + d for y in SWIVEL_POOP_Y for d in (-1.2, -0.6, 0.6, 1.2)])
X_LINES = _merge(X_LINES, _fx['deck'] + _fx['fc'])
# a fine grid where the guns stand at angles (forecastle platform, cabin) and across the ship: with coarse cells the
# padded cut-outs took whole metre-wide cells round the guns (2026-10-16)
X_LINES = _merge(X_LINES, [0.25 * k for k in range(-17, 18)], gap=0.06)
Y_FC = _merge(Y_FC, [FC_YB + 0.25 * k for k in range(0, 30)], gap=0.06)
Y_DECK_NAV = _merge(Y_DECK, _fy['deck'])
Y_FC = _merge(Y_FC, _fy['deck'] + _fy['fc'])

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
n_cut = 0
n_step = 0
def step_vid(sw, x, y):
    """Vertex on a step: the deck's at its inboard foot, else the step top's (own keys: no edge joins the deck)."""
    lx, ly = swivel_local(sw, x, y)
    if -ly > STEP_IN[1][1] - 1e-4:
        return vid(('deck', round(x, 4), round(y, 4)), (x, y, Z_DECK))
    return vid(('step', sw['name'], round(x, 4), round(y, 4)), (x, y, Z_DECK + SW_STEP['h']))
for level, ys in (('deck', Y_DECK_NAV), ('poop', Y_POOP), ('fc', Y_FC)):
    for y0, y1 in zip(ys, ys[1:]):
        for x0, x1 in zip(X_LINES, X_LINES[1:]):
            st = step_cell(x0, x1, y0, y1) if level == 'deck' and walkable(level, x0, x1, y0, y1) else None
            if st:
                if st[0] != 'pad':
                    faces.append(([step_vid(st[1], x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))], 0))
                    n_step += 1
                continue
            if walkable(level, x0, x1, y0, y1) and (gun_foot((x0 + x1) / 2, (y0 + y1) / 2, LEVEL_Z[level]) or store_foot((x0 + x1) / 2, (y0 + y1) / 2, LEVEL_Z[level])):
                n_cut += 1; continue
            if walkable(level, x0, x1, y0, y1):
                cells[(level, x0, x1, y0, y1)] = add_cell(level, x0, x1, y0, y1)
# forecastle ground floor (walk-in, at gun-deck level; it shares the deck's vertices along its open back)
for y0, y1 in zip(Y_FC, Y_FC[1:]):
    for x0, x1 in zip(X_LINES, X_LINES[1:]):
        if walkable('fc', x0, x1, y0, y1) and (gun_foot((x0 + x1) / 2, (y0 + y1) / 2, Z_DECK) or store_foot((x0 + x1) / 2, (y0 + y1) / 2, Z_DECK)):
            n_cut += 1; continue
        if walkable('fc', x0, x1, y0, y1):
            cells[('fcg', x0, x1, y0, y1)] = add_cell('deck', x0, x1, y0, y1)
# stairs: ramps whose foot vertices are the gun deck's and whose head vertices are the upper deck's
for sx0, sx1, ya, yb, upper in STAIRS:
    ys = sorted({ya, yb} | {y for y in Y_DECK_NAV if min(ya, yb) < y < max(ya, yb)})
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
Y_CAB = _merge(_merge(lines(SC_Y0 + SC_WALL_T, SC_Y1 - SC_WALL_T, 1.0), _fy['deck']),
               [SC_Y0 + SC_WALL_T + 0.25 * k for k in range(0, 40)], gap=0.06)
n_cab = 0
for y0, y1 in zip(Y_CAB, Y_CAB[1:]):
    for x0, x1 in zip(X_LINES, X_LINES[1:]):
        if all(abs(x) <= sc_hw(y) - SC_WALL_T - 0.15 + 1e-6 for x in (x0, x1) for y in (y0, y1)):
            if gun_foot((x0 + x1) / 2, (y0 + y1) / 2, Z_DECK) or store_foot((x0 + x1) / 2, (y0 + y1) / 2, Z_DECK):
                n_cut += 1; continue
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
# + the grid's lines inside the aft door (gun cut-out lines), so door and platform share whole edges
X_PLAT = sorted(set(X_PLAT) | {x for x in X_LINES if DOOR_A[0] - 1e-6 <= x <= DOOR_A[1] + 1e-6})
Y_PLAT = [SC_Y0 - 1.1, SC_Y0 - 0.9, SC_Y0 - 0.6, SC_Y0 - 0.3, SC_Y0]
n_plat = 0
for y0, y1 in zip(Y_PLAT, Y_PLAT[1:]):
    for x0, x1 in zip(X_PLAT, X_PLAT[1:]):
        if all(on_platform(x, y) for x in (x0, x1) for y in (y0, y1)):
            cab_cell(x0, x1, y0, y1); n_plat += 1
report.append('navmesh: cabin %d cells (incl. both door openings), stern platform %d cells; %d cells under the guns and stores cut out' % (n_cab, n_plat, n_cut))
report.append('navmesh: %d cells on the swivels\' gunner steps (top %.2f above the deck, ramp from the deck)' % (n_step, SW_STEP['h']))

# the spur rams (user 2026-10-13): a permanent MissionShipRam (no upgrade slot - the cleanup only touches 'upgrade_slot'
# entities) under a 'bow'-tagged holder (ShipWaterEffects reads the bow wave's reach from the ram under the first child
# of ram_group tagged 'bow'). Its capsule (added to the ship's body; also the spur's ship-ship collision, which the
# composite hull leaves out) runs along the spur's axis from where it leaves the stem to the bronze point; the rounded
# end reaches the point. Entity forward (+y) = ram direction, scale 1 (vanilla scales the capsule with the entity).
# Vanilla rams: radius 0.75..1.2 m (x their 1.9-2.0 scale), tier multiplier 1.0 on every one
RAM_R, RAM_Y0 = 0.9, 25.6
_zc = lambda y: G['spur_at'](y)[0] + LIFT
_p1 = (0.0, RAM_Y0, _zc(RAM_Y0))
_tip = (0.0, G['SPUR_TIP'][1], _zc(G['SPUR'][-1][0]))
_d = [b - a for a, b in zip(_p1, _tip)]; _dl = math.sqrt(sum(v * v for v in _d)); _d = [v / _dl for v in _d]
RAM_LEN = _dl - RAM_R
ram = new_entity('galleass_ram', 'ram/galleass_ram')
write_tf(ram, pos=_p1, rot=(math.atan2(_d[2], _d[1]), 0.0, 0.0))
ram.append(mobility())
ram.append(el('scripts', None, el('script', {'name': 'MissionShipRam'},
    el('prefab_link', None, el('instance', {'guid': guid('ram/galleass_ram/script')}), el('prefab', {'guid': ZERO})),
    el('variables', None, *[el('variable', {'name': k, 'type_name': t, 'value': v}) for k, t, v in (
        ('_ramAttachmentPointOffset', 'vec3', '0.000, 0.000, 0.000'), ('NavMeshPrefabName', 'string', ''),
        ('_ramLength', 'float', '%.3f' % RAM_LEN), ('_ramRadius', 'float', '%.3f' % RAM_R),
        ('_ramTierDamageMultiplier', 'float', '1.000'))]))))
bow = new_entity('galleass_bow', 'ram/galleass_bow')
bow.append(tags('bow')); bow.append(mobility()); bow.append(el('children', None, ram))
rg = files['ram_group']
rg.append(el('children', None, bow))
rg[:] = sorted(rg, key=lambda c: ORDER.index(c.tag) if c.tag in ORDER else len(ORDER))
report.append('ram: MissionShipRam capsule from %s, length %.2f, radius %.2f, pitch %.1f deg (spur point at y %.1f)'
              % (tuple(round(v, 2) for v in _p1), RAM_LEN, RAM_R, math.degrees(math.atan2(_d[2], _d[1])), _tip[1]))

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
        # as vanilla's, the id face reaches the deck edge with its outboard edge open: the bridge's navmesh joins the ship
        # there (SwapFaceConnectionsWithID). 2026-10-18: the face sat one column inboard, enclosed by the deck - enemies
        # hooked on and laid the bridge but never came over. The cells outboard of it merge into it.
        outer = [k for k in cells if k[0] == 'deck' and k[3] == key[3] and k[4] == key[4]
                 and (k[1] >= key[2] - 1e-6 if side > 0 else k[2] <= key[1] + 1e-6)]
        fx0 = key[1] if side > 0 else min([k[1] for k in outer] + [key[1]])
        fx1 = max([k[2] for k in outer] + [key[2]]) if side > 0 else key[2]
        for k in outer:
            faces[cells.pop(k)] = None
        faces[cells[key]] = ([vid(('deck', round(x, 4), round(yy, 4)), (x, yy, Z_DECK))
                              for x, yy in ((fx0, key[3]), (fx1, key[3]), (fx1, key[4]), (fx0, key[4]))], fid)
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

faces = [f for f in faces if f is not None]                      # (cells merged into the boarding faces)
os.makedirs(NAV_DIR, exist_ok=True)
# islands the gun cut-outs sealed off (e.g. the wedge between two culverins' recoiled trails): nobody could leave them
# - only the largest connected piece of each level group stays (faces joined by shared vertices)
_par = list(range(len(faces)))
def _find(a):
    while _par[a] != a:
        _par[a] = _par[_par[a]]; a = _par[a]
    return a
_byv = {}
for _i, (_vs, _) in enumerate(faces):                            # joined by shared EDGES (a corner is no way)
    for _k in range(len(_vs)):
        _a, _b = _vs[_k], _vs[(_k + 1) % len(_vs)]
        _byv.setdefault((min(_a, _b), max(_a, _b)), []).append(_i)
for _l in _byv.values():
    for _j in _l[1:]: _par[_find(_j)] = _find(_l[0])
_size = {}
for _i in range(len(faces)): _size[_find(_i)] = _size.get(_find(_i), 0) + 1
_main = max(_size, key=_size.get)
_drop = [i for i in range(len(faces)) if _find(i) != _main]
assert not any(faces[i][1] for i in _drop), 'an island holds a boarding face'
faces = [f for i, f in enumerate(faces) if _find(i) == _main]
_isl = {}
for _i in _drop:
    _isl.setdefault(_find(_i), []).extend(verts[v] for v in faces[_i][0])
report.append('navmesh: %d faces in %d island(s) cut off by the guns dropped%s' % (len(_drop), len(_size) - 1, ''.join(
    ' [%d faces at (%.1f, %.1f, %.1f)]' % (_size[r], sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps),
                                           sum(p[2] for p in ps) / len(ps)) for r, ps in _isl.items())))
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

# --- guns (cannon project, 2026-10-13): 24 guns at their ports (gun_layout.py, shared with the Blender preview), each
# with its collision body (bo_galleass_<gun>: carriage + barrel hulls). Static as art; the moving parts (2026-10-15)
# are child entities the gunnery add-on drives (no mission code here): 'barrel' on the trunnion axis (tag gun_barrel;
# elevation = its rotation about x) carrying the priming 'fuse' (tag gun_fuse, hidden after a shot), the 'quoin'
# (tag gun_quoin, slides along y by the table in galleass_guns.json 'elev') and the cascabel 'lashing' (tag
# gun_lashing, cast off in action).
import gun_layout
GUN_DIMS = gun_layout.load_dims()
for _k in ('culverin', 'falcon', 'falconet'):                   # refuses to build before the Kit has the split meshes
    for _suf in ('', '_barrel', '_quoin', '_lashing', '_fuse'):   # (GALLEASS_TEST_BUILD=1: test build without them)
        if not os.environ.get('GALLEASS_TEST_BUILD'):
            kit_submeshes('galleass_' + _k + _suf, None)
if not os.environ.get('GALLEASS_TEST_BUILD'):
    kit_submeshes('galleass_tackle_block', None)
# live gun ropes (gun_rigging.py -> ref/galleass_gun_ropes.json, 2026-10-15): vanilla rope entities between a static start
# (wall ring / standing block) and an end at the gun's rest position; on the gun an attachment entity 'rope_att_<rope>'
# (gun root or barrel) the gunnery add-on points the rope's end at, so the rope follows recoil, traverse and elevation
GUN_ROPES = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ref', 'galleass_gun_ropes.json')))
ROPE_TINT, ROPE_ARG2 = '0.932, 0.851, 0.666, 1.000', ('0.232', '0.170', '0.762')

def euler_from_axes(s_, f_):
    """Bannerlord rotation_euler (Mat3.GetEulerAngles) for local x = s_, y = f_ (parent coordinates)."""
    u_ = [s_[1] * f_[2] - s_[2] * f_[1], s_[2] * f_[0] - s_[0] * f_[2], s_[0] * f_[1] - s_[1] * f_[0]]
    n = math.sqrt(sum(v * v for v in u_)); u_ = [v / n for v in u_]
    s2 = [f_[1] * u_[2] - f_[2] * u_[1], f_[2] * u_[0] - f_[0] * u_[2], f_[0] * u_[1] - f_[1] * u_[0]]   # s = f x u
    return (math.asin(max(-1.0, min(1.0, f_[2]))), math.atan2(-s2[2], u_[2]), math.atan2(-f_[0], f_[1]))

def rope_entity(gun, r):
    seed = 'gunrope/%s/%s' % (gun, r['name'])
    grp = new_entity('gunrope_%s__%s' % (gun, r['name']), seed)
    st = new_entity('rope_start', seed + '/start'); write_tf(st, pos=r['start'], rot=(0.0, 0.0, 0.0))
    st.append(tags('simple_rope_start', 'gun_rope_start')); st.append(mobility())
    st.append(el('scripts', None, el('script', {'name': 'rope_segment'},
        el('prefab_link', None, el('instance', {'guid': guid(seed + '/script')}), el('prefab', {'guid': ZERO})),
        el('variables', None, *[el('variable', {'name': k, 'type_name': t, 'value': v}) for k, t, v in (
            ('Default Rope Length', 'float', '25.900'), ('Is Fixed', 'bool', '1'), ('Loose Amount', 'float', '%.3f' % r['loose']),
            ('Segment Index', 'int', '0'), ('Uses Physics Body', 'bool', '0'), ('Swing Multiplier', 'float', '0.300'))]))))
    length = math.dist(r['start'], r['end'])
    misc = el('misc', None, el('material', {'type_name': 'string', 'value': 'ship_ropes'}),
              el('factor_color', {'type_name': 'vec4', 'value': ROPE_TINT}),
              el('vector_argument_x', {'type_name': 'float', 'value': '%.3f' % length}),
              el('vector_argument_y', {'type_name': 'float', 'value': '25.900'}),
              el('vector_argument_z', {'type_name': 'float', 'value': '1.000'}),
              el('vector_argument_w', {'type_name': 'float', 'value': '%.3f' % r['radius']}),
              *[el('vector_argument_2_' + a, {'type_name': 'float', 'value': v}) for a, v in zip('xyz', ROPE_ARG2)])
    st.append(el('components', None, el('meta_mesh_component', {'name': 'sail_rope_pile'},
        el('prefab_link', None, el('instance', {'guid': guid(seed + '/mmc')}), el('prefab', {'guid': ZERO})),
        el('children', None, el('mesh', {'name': 'sail_rope_pile'}, misc)))))
    en = new_entity('rope_end', seed + '/end'); write_tf(en, pos=r['end'], rot=(0.0, 0.0, 0.0))
    en.append(tags('simple_rope_end', 'gun_rope_end')); en.append(mobility())
    grp.append(mobility()); grp.append(el('children', None, st, en))
    return grp
def gun_part(g, name, tag, mesh, pos, children=()):
    p = new_entity(name, 'gun/%s/%s' % (g['name'], name))
    write_tf(p, pos=pos, rot=(0.0, 0.0, 0.0))
    p.append(tags(tag)); p.append(mobility()); p.append(mesh_component('gun/%s/%s' % (g['name'], name), mesh))
    if children:
        p.append(el('children', None, *children))
    return p
def gun_entity(g):
    mesh = 'galleass_' + g['kind']
    e = new_entity('gun_' + g['name'], 'gun/' + g['name'])
    write_tf(e, pos=g['pos'], rot=(0.0, 0.0, g['rot_z']))
    e.append(el('physics', None,
                el('shape', {'type_name': 'string', 'value': 'bo_' + mesh}),
                el('body_flags', None, el('body_flag', {'name': 'moveable'})),
                el('move_to_batched_kinematic', {'type_name': 'bool', 'value': '1'})))
    e.append(tags('galleass_gun', 'galleass_gun_' + g['kind']))
    e.append(mobility()); e.append(mesh_component('gun/' + g['name'], mesh))
    ent = 'gun_' + g['name']
    def att(r):                                                # rope end attachment (no mesh)
        a = new_entity('rope_att_' + r['name'], 'gun/%s/att/%s' % (g['name'], r['name']))
        write_tf(a, pos=r['end_local'], rot=(0.0, 0.0, 0.0)); a.append(tags('gun_rope_att')); a.append(mobility())
        return a
    ropes = [r for r in GUN_ROPES['ropes'] if r['gun'] == ent]
    fz = gun_part(g, 'fuse', 'gun_fuse', mesh + '_fuse', (0.0, 0.0, 0.0))
    barrel = gun_part(g, 'barrel', 'gun_barrel', mesh + '_barrel', (0.0, 0.0, GUN_DIMS[mesh]['elev']['pivot_z']),
                      [fz] + [att(r) for r in ropes if r['on_barrel']])
    quoin = gun_part(g, 'quoin', 'gun_quoin', mesh + '_quoin', (0.0, 0.0, 0.0))
    lashing = gun_part(g, 'lashing', 'gun_lashing', mesh + '_lashing', (0.0, 0.0, 0.0))
    blocks = []
    for b in [b for b in GUN_ROPES['blocks'] if b['gun'] == ent]:   # running tackle blocks ride the carriage
        be = new_entity(b['name'], 'gun/%s/%s' % (g['name'], b['name']))
        t = ET.Element('transform')
        ET.SubElement(t, 'position', type_name='vec3', value='%.3f, %.3f, %.3f' % tuple(b['pos_local']))
        ET.SubElement(t, 'rotation_euler', type_name='vec3',
                      value='%.4f, %.4f, %.4f' % euler_from_axes(b['across_local'], b['along_local']))
        ET.SubElement(t, 'scale', type_name='vec3', value='%.3f, %.3f, %.3f' % ((b['scale'],) * 3))
        be.insert(1, t)
        be.append(tags('gun_tackle_block')); be.append(mobility())
        be.append(mesh_component('gun/%s/%s' % (g['name'], b['name']), 'galleass_tackle_block'))
        blocks.append(be)
    e.append(el('children', None, barrel, quoin, lashing, *blocks, *[att(r) for r in ropes if not r['on_barrel']]))
    return e
GUN_PLACES = gun_layout.placements(G, GUN_DIMS)

# --- swivel guns (petriere da mascolo, 2026-10-17): 10 on the rails (gun_layout.swivel_placements). gun_pe_<name> at the
# rail top under the pin (mount block, bo_galleass_petriera; tags galleass_gun, galleass_gun_petriera, galleass_swivel)
# > 'yoke' (tag gun_yoke; traverse = its rotation about z) > 'barrel' on the trunnion axis (tag gun_barrel; elevation
# about x) > 'chamber' (tag gun_chamber, the loaded mascolo) > 'fuse' (gun_fuse), and 'wedge' (gun_wedge). Two spare
# loaded chambers (tag gun_spare_chamber) lie by the gun: on the waist step against the bulwark, on the poop deck
# inside the balustrade. Waist swivels: the gunner's step (galleass_petriera_step + bo_) at deck level, own entity.
if not os.environ.get('GALLEASS_TEST_BUILD'):
    for _suf in ('', '_yoke', '_barrel', '_chamber', '_wedge', '_fuse', '_step', '_stand'):
        kit_submeshes('galleass_petriera' + _suf, None)
PE_DIMS = GUN_DIMS['galleass_petriera']
SW_SPARES = 2
def swivel_entity(sw):
    mesh, seed = 'galleass_petriera', 'swivel/' + sw['name']
    e = new_entity('gun_' + sw['name'], seed)
    write_tf(e, pos=sw['pos'], rot=(0.0, 0.0, sw['rot_z']))
    e.append(el('physics', None,
                el('shape', {'type_name': 'string', 'value': 'bo_' + mesh}),
                el('body_flags', None, el('body_flag', {'name': 'moveable'})),
                el('move_to_batched_kinematic', {'type_name': 'bool', 'value': '1'})))
    e.append(tags('galleass_gun', 'galleass_gun_petriera', 'galleass_swivel'))
    e.append(mobility()); e.append(mesh_component(seed, mesh))
    g = {'name': sw['name']}
    fz = gun_part(g, 'fuse', 'gun_fuse', mesh + '_fuse', (0.0, 0.0, 0.0))
    chamber = gun_part(g, 'chamber', 'gun_chamber', mesh + '_chamber', (0.0, PE_DIMS['chamber_y'], 0.0), [fz])
    wedge = gun_part(g, 'wedge', 'gun_wedge', mesh + '_wedge', (0.0, PE_DIMS['wedge_y'], 0.0))
    barrel = gun_part(g, 'barrel', 'gun_barrel', mesh + '_barrel', (0.0, 0.0, PE_DIMS['axis_h']), [chamber, wedge])
    yoke = gun_part(g, 'yoke', 'gun_yoke', mesh + '_yoke', (0.0, 0.0, 0.0), [barrel])
    # spare chambers lying along the rail (axis along local x, handle up): on the waist step 0.12 m inboard of the
    # bulwark, on the poop beside the stand's foot
    floor = (sw['deck_z'] + (SW_STEP['h'] if sw['step'] else 0.0)) - sw['pos'][2]
    spares = []
    for i in range(SW_SPARES):
        sp = new_entity('spare_chamber_%d' % i, seed + '/spare/%d' % i)
        write_tf(sp, pos=((0.40 if sw['step'] else 0.30) * (1 if i % 2 else -1),
                          -(SW_STEP['wall'] + 0.12) if sw['step'] else -0.30, floor + 0.050), rot=(0.0, 0.0, math.pi / 2))
        sp.append(tags('gun_spare_chamber')); sp.append(mobility())
        sp.append(mesh_component(seed + '/spare/%d' % i, mesh + '_chamber'))
        spares.append(sp)
    kids_ = [yoke, *spares]
    if sw['stand']:                                            # poop: the timber stand under the mount block
        st = new_entity('stand', seed + '/stand')
        write_tf(st, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0))
        st.append(el('physics', None,
                     el('shape', {'type_name': 'string', 'value': 'bo_galleass_petriera_stand'}),
                     el('body_flags', None, el('body_flag', {'name': 'moveable'})),
                     el('move_to_batched_kinematic', {'type_name': 'bool', 'value': '1'})))
        st.append(tags('galleass_swivel_stand')); st.append(mobility())
        st.append(mesh_component(seed + '/stand', 'galleass_petriera_stand'))
        kids_.append(st)
    e.append(el('children', None, *kids_))
    return e
def swivel_step(sw):
    mesh, seed = 'galleass_petriera_step', 'swivel/%s/step' % sw['name']
    e = new_entity('step_' + sw['name'], seed)
    write_tf(e, pos=(sw['pos'][0], sw['pos'][1], sw['deck_z']), rot=(0.0, 0.0, sw['rot_z']))
    e.append(el('physics', None,
                el('shape', {'type_name': 'string', 'value': 'bo_' + mesh}),
                el('body_flags', None, el('body_flag', {'name': 'moveable'})),
                el('move_to_batched_kinematic', {'type_name': 'bool', 'value': '1'})))
    e.append(tags('galleass_swivel_step')); e.append(mobility()); e.append(mesh_component(seed, mesh))
    return e
# the meditheavy's AI limiter walls (barrier mesh: a 1 m x 1 m quad in local x/z, scaled) that cross a gun's working
# area - carriage + full recoil + the gunner's and the loader's places beside it - fence its crew off (2026-10-16: the
# loaders of the aftmost broadside falcons and the stern chasers never reached their places): removed. Recoil per gun
# = GalleassGunnery config defaults.
def _gun_area_hits(gp, a, b):
    dims = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ref', 'galleass_guns.json')))['galleass_' + gp['kind']]
    recoil = {'culverin': 1.0, 'falcon': 0.8, 'falconet': 0.6}[gp['kind']]
    hx, y0, y1 = dims['half_w'] + 0.9, dims['rear_y'] - recoil - 0.6, dims['muzzle_y']
    c, s = math.cos(-gp['rot_z']), math.sin(-gp['rot_z'])
    def loc(p):
        dx, dy = p[0] - gp['pos'][0], p[1] - gp['pos'][1]
        return (c * dx - s * dy, s * dx + c * dy)
    (ax, ay), (bx, by) = loc(a), loc(b)
    t0, t1, dx, dy = 0.0, 1.0, bx - ax, by - ay
    for p, q in ((-dx, ax + hx), (dx, hx - ax), (-dy, ay - y0), (dy, y1 - ay)):
        if p == 0:
            if q < 0: return False
        else:
            t = q / p
            if p < 0: t0 = max(t0, t)
            else: t1 = min(t1, t)
    return t0 <= t1
cut = []
for e in list(bch):
    m, p = local_m(e)
    sx, sy = m[0][0] / 2, m[1][0] / 2                           # half the wall's width along its local x
    a, b = (p[0] - sx, p[1] - sy), (p[0] + sx, p[1] + sy)
    hit = [gp['name'] for gp in GUN_PLACES if abs(gp['pos'][2] - p[2]) < 2.5 and _gun_area_hits(gp, a, b)]
    if hit:
        cut.append(hit); bch.remove(e)
report.append('barrier_holder: %d AI barriers crossing gun working areas removed (%s)' % (len(cut), ', '.join('/'.join(h) for h in cut)))

# crew standing spots (the meditheavy's sp_troop_* spawn / placement points, remapped above) in a gun's working area,
# on a gun's loader place or at the gun stores: the men placed there stood in the recoil and blocked the loaders
# (2026-10-16) - each goes to the nearest clear spot on the navmesh (0.1 m rings), >= 0.45 m from the other spots
_LOADERS = json.load(open(os.path.join(_ART, 'ref', 'galleass_loader_spots.json'))) if os.path.exists(os.path.join(_ART, 'ref', 'galleass_loader_spots.json')) else {}
_STATIONS = json.load(open(os.path.join(_ART, 'ref', 'galleass_stations.json')))
_GSP = os.path.join(_ART, 'ref', 'galleass_gunner_spots.json')
_LOADERS = dict(_LOADERS, **{k + '/gunner': v for k, v in (json.load(open(_GSP)).items() if os.path.exists(_GSP) else [])})
def _crew_spot_bad(x, y, z):
    if in_gun_area(x, y, z) or in_stair_clear(x, y, z):
        return True
    if any(abs(sp['ship'][2] - z) < 1.2 and math.hypot(sp['ship'][0] - x, sp['ship'][1] - y) < 0.75 for sp in _LOADERS.values()):
        return True
    return any(abs(st['z'] - z) < 1.2 and math.hypot(it['pos'][0] - x, it['pos'][1] - y) < 1.25 for st in _STATIONS for it in st['items'])
def _on_nav(x, y, z):
    return any((fz := navmesh.face_z(verts, vs, x, y)) is not None and abs(fz - z) < 0.3 for vs, _ in faces)
_sps = [e for e in kids(files['spawn_point_holder'])]
_fixed, _lost = [], []
for e in _sps:
    p = tf(e)[0]
    if not _crew_spot_bad(*p):
        continue
    others = [tf(o)[0] for o in _sps if o is not e]
    best = None
    for r in [0.1 * i for i in range(1, 41)]:
        for k in range(24):
            x, y = p[0] + r * math.cos(k * math.pi / 12), p[1] + r * math.sin(k * math.pi / 12)
            if (_on_nav(x, y, p[2]) and not _crew_spot_bad(x, y, p[2])
                    and all(abs(o[2] - p[2]) > 0.5 or math.hypot(o[0] - x, o[1] - y) >= 0.45 for o in others)):
                best = (x, y, p[2]); break
        if best: break
    if best:
        write_tf(e, pos=best)
        _fixed.append('%s (%.2f, %.2f) -> (%.2f, %.2f)' % (e.get('name'), p[0], p[1], best[0], best[1]))
    else:
        _lost.append(e.get('name'))
report.append('spawn_point_holder: %d crew spots moved out of gun areas / loader places / stores%s: %s'
              % (len(_fixed), (', NO CLEAR SPOT for %s' % _lost) if _lost else '', '; '.join(_fixed)))

# forecastle crew (user 2026-10-16: the AI struggled up to the platform falconets): new outer-deck spots - outer ones
# are always manned at the start (76 deck crew; 56 + these outer spots, the rest fills inner spots from the stern) -
# two per culverin, one per platform falconet (one-man crews), near its gunner's place but off it, on the navmesh and
# clear like the moved spots above
def _tag_names(e):
    t = inh(e, 'tags')
    return [x.get('name') for x in t.iter('tag')] if t is not None else []
_tmpl = next(e for e in kids(files['spawn_point_holder']) if 'sp_troop_outer_deck' in _tag_names(e))
_GUNNERS = json.load(open(_GSP)) if os.path.exists(_GSP) else {}
_spot_xyz = [tf(o)[0] for o in kids(files['spawn_point_holder'])]
_added = []
for _gname, _gsp in sorted(_GUNNERS.items()):
    if not (_gname.startswith('gun_ft_fc_') or _gname.startswith('gun_cv_')):
        continue
    gx, gy, gz = _gsp['ship']
    want = 1 if _gname.startswith('gun_ft_fc_') else 2          # falconets: one-man crews (user 2026-10-16)
    n = 0
    for r in [0.8 + 0.1 * i for i in range(23)]:
        for k in range(24):
            x, y = gx + r * math.cos(k * math.pi / 12), gy + r * math.sin(k * math.pi / 12)
            if (_on_nav(x, y, gz) and not _crew_spot_bad(x, y, gz)
                    and all(abs(o[2] - gz) > 0.5 or math.hypot(o[0] - x, o[1] - y) >= 0.6 for o in _spot_xyz)):
                c = copy_regen(_tmpl, 'galleass-fc-crew/%s/%d/' % (_gname, n))
                write_tf(c, pos=(x, y, gz), rot=(0.0, 0.0, 0.0))
                files['spawn_point_holder'].find('children').append(c)
                _spot_xyz.append((x, y, gz)); _added.append('%s (%.2f, %.2f, %.2f)' % (_gname, x, y, gz))
                n += 1
                if n == want: break
        if n == want: break
report.append('spawn_point_holder: %d forecastle crew spots added (outer deck): %s' % (len(_added), '; '.join(_added)))
gg = new_entity('galleass_guns', 'guns')
# ship-side rigging of all 24 guns (gun_rigging.py: breechings, side tackles, ringbolts), one mesh in the ship's
# frame, no collision; tagged so the gun add-on can hide it and rig the guns live
rig = new_entity('gun_rigging', 'guns/rigging')
write_tf(rig, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0))
rig.append(tags('galleass_gun_rigging')); rig.append(mobility())
rig.append(mesh_component('guns/rigging', 'galleass_gun_rigging'))
# gun stores (2026-10-15, stores_model.py meshes, stores_layout.py placement -> ref/galleass_stations.json): five
# stations, each a powder keg, shot rack(s) with their balls and (falcon / falconet) scattershot baskets with their
# bags. Balls and bags are child entities so the gunnery add-on can empty the racks as the ship's supplies run low.
# Tags: gun_store + gun_store_<station>; powder_keg / shot_rack_<gun> / shot_basket_<gun>; store_ball / store_bag.
if not os.environ.get('GALLEASS_TEST_BUILD'):
    for _m in ('galleass_powder_keg', 'galleass_shot_rack_culverin', 'galleass_shot_rack_falcon', 'galleass_shot_rack_falconet',
               'galleass_shot_basket', 'galleass_scatter_bag_falcon', 'galleass_scatter_bag_falconet',
               'galleass_shot', 'galleass_shot_falcon', 'galleass_shot_falconet'):
        kit_submeshes(_m, None)
    for _m in ('galleass_locker_falconet', 'galleass_locker_petriera'):
        if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Assets', _m + '_geo.tpac')):
            kit_submeshes(_m, None)
        else:
            report.append('KIT TODO: import %s (+ bo_%s with Import physics shapes)' % (_m, _m))
STATIONS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ref', 'galleass_stations.json')))
STORE_BODIES, STORE_NO_BODY = [], set()
def store_entity(st, it):
    seed = 'store/%s/%s' % (st['name'], it['name'])
    e = new_entity(it['name'], seed)
    write_tf(e, pos=it['pos'], rot=(0.0, 0.0, it['rot_z']))
    kind = it['name'].split('_', 1)
    tag = 'powder_keg' if it['name'] == 'keg' else ('shot_' + it['name']) if kind[0] in ('rack', 'basket') else it['name']
    # collision (2026-10-16): the store's convex hull from stores_model.py, once the Kit has it with its physics shape
    bo = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Assets', 'bo_%s_geo.tpac' % it['mesh'])
    if os.path.exists(bo) and os.path.getsize(bo) > 600:            # (empty stubs ~320 bytes; a box ~860)
        e.append(el('physics', None,
                    el('shape', {'type_name': 'string', 'value': 'bo_' + it['mesh']}),
                    el('body_flags', None, el('body_flag', {'name': 'moveable'})),
                    el('move_to_batched_kinematic', {'type_name': 'bool', 'value': '1'})))
        STORE_BODIES.append(it['mesh'])
    else:
        STORE_NO_BODY.add(it['mesh'])
    e.append(tags('gun_store', 'gun_store_' + st['name'], tag)); e.append(mobility())
    e.append(mesh_component(seed, it['mesh']))
    kids = []
    for i, b in enumerate(it.get('balls', [])):
        c = new_entity('ball_%d' % i, seed + '/ball/%d' % i); write_tf(c, pos=b, rot=(0.0, 0.0, 0.0))
        c.append(tags('store_ball')); c.append(mobility()); c.append(mesh_component(seed + '/ball/%d' % i, it['ball_mesh']))
        kids.append(c)
    for i, b in enumerate(it.get('bags', [])):
        c = new_entity('bag_%d' % i, seed + '/bag/%d' % i)
        write_tf(c, pos=b[:3], rot=tuple(b[3:6]) if len(b) >= 6 else (0.0, 0.0, (i * 2.399) % (2 * math.pi)))   # heaped, askew
        c.append(tags('store_bag')); c.append(mobility()); c.append(mesh_component(seed + '/bag/%d' % i, it['bag_mesh']))
        kids.append(c)
    if kids:
        e.append(el('children', None, *kids))
    return e
gstores = new_entity('galleass_stores', 'guns/stores')
write_tf(gstores, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0))
gstores.append(tags('galleass_stores')); gstores.append(mobility())
gstores.append(el('children', None, *[store_entity(st, it) for st in STATIONS for it in st['items']]))
report.append('gun stores: %d stations, %d stores, %d with collision%s' % (len(STATIONS), sum(len(st['items']) for st in STATIONS), len(STORE_BODIES), ('; KIT: import ' + ', '.join('bo_' + m for m in sorted(STORE_NO_BODY)) + ' (Import physics shapes)') if STORE_NO_BODY else ''))

# the live ropes, in the ship's frame under one holder; vanilla's CosmeticRopeManager hides them beyond 100 m and
# draws them straight beyond 45 m (as for the ships' own cosmetic ropes)
gropes = new_entity('galleass_gun_ropes', 'guns/ropes')
write_tf(gropes, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0))
gropes.append(tags('galleass_gun_ropes')); gropes.append(mobility())
gropes.append(el('scripts', None, el('script', {'name': 'CosmeticRopeManager'},
    el('prefab_link', None, el('instance', {'guid': guid('guns/ropes/script')}), el('prefab', {'guid': ZERO})))))
gropes.append(el('children', None, *[rope_entity(r['gun'], r) for r in GUN_ROPES['ropes']]))
gg.append(mobility()); gg.append(el('children', None, *[gun_entity(g) for g in GUN_PLACES],
                                    *[swivel_entity(sw) for sw in SWIVELS], *[swivel_step(sw) for sw in SWIVELS if sw['step']],
                                    rig, gropes, gstores))
report.append('gun ropes: %d live ropes, %d running blocks' % (len(GUN_ROPES['ropes']), len(GUN_ROPES['blocks'])))

# standing rigging (re-rig phase 2, standing_rig.py): shrouds abaft the masts with tackles + the tie tackles, one mesh
# in the ship's frame, no collision
kit_submeshes('galleass_standing_rigging', None)                # refuses to build before the Kit has the mesh
srig = new_entity('galleass_standing_rigging', 'rig/standing')
write_tf(srig, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0))
srig.append(tags('galleass_standing_rigging')); srig.append(mobility())
srig.append(mesh_component('rig/standing', 'galleass_standing_rigging'))
files['torch_holder'].find('children').append(srig)
files['torch_holder'].find('children').append(gg)          # ship frame (like the banners)
from collections import Counter
report.append('swivels: %d (%s), %d gunner steps, %d spare chambers' % (len(SWIVELS), ', '.join(
    '%s %+.0f..%+.0f' % (sw['name'], SWIVEL_LIM[sw['name']]['min_deg'], SWIVEL_LIM[sw['name']]['max_deg']) for sw in SWIVELS),
    sum(1 for sw in SWIVELS if sw['step']), SW_SPARES * len(SWIVELS)))
report.append('guns: %d (%s)' % (len(GUN_PLACES), ', '.join('%s %d' % kv for kv in sorted(Counter(g['kind'] for g in GUN_PLACES).items()))))

# --- burning system (2026-10-19): still the meditheavy's nodes (masts at its y -7 / 8.4, rails at x 4, deck nodes under
# our deck). ShipBurningSystem: a hit lights every node within 6 m (RegisterBlow), flames burn AT the nodes, each group
# spreads along its children as a ring (prev/next; its NodeIndex sort compares a node with itself = child order). The
# vanilla nodes (flame variants a..i) are kept and moved: rails = one loop (starboard waist, forecastle parapet, port
# waist, poop balustrade) in vanilla's loop order; deck = our three decks in vanilla's fore-and-aft order; masts = the
# meditheavy's rings round its two masts on our three; crates follow their deck upgrade (DU_MOVES). Mast/yard/sail fire
# is SailVisual's own (not these nodes).
bs = {name_of(c): c for c in kids(files['ship_burning_system'])}
def loop_angle(x, y, half_len, half_w):
    return math.atan2(y / half_len, x / half_w)              # starboard 0, bow +pi/2, port pi, stern -pi/2

RAIL_DZ = 0.7                                                  # vanilla rail nodes: ~0.7 above their deck
def rail_loop():
    """Polylines (points, z) round the ship inside the bulwarks."""
    xw = W_IN - 0.15
    waist = [(xw, y) for y in (SC_Y1 + 0.3, FC_YB - 0.3)]
    fc = [(FC_R_IN, FC_YB + 0.3)] + [(FC_R_IN * math.cos(a), FC_CY + FC_R_IN * math.sin(a))
                                     for a in [math.radians(d) for d in range(0, 181, 15)]] + [(-FC_R_IN, FC_YB + 0.3)]
    ys = [SC_Y1 - 0.3 - k * (SC_Y1 - SC_Y0 - 0.6) / 8 for k in range(9)]
    poop = [(-(sc_hw(y) - 0.3), y) for y in ys] + [((sc_hw(y) - 0.3), y) for y in reversed(ys)]
    return [(waist, Z_DECK + RAIL_DZ), (fc, Z_FC + RAIL_DZ), ([(-x, y) for x, y in reversed(waist)], Z_DECK + RAIL_DZ),
            (poop, Z_POOP_TOP + RAIL_DZ)]

def sample(lines, n):
    """n points spread evenly (by length) over the polylines, with the rail's direction."""
    segs = [(a, b, z) for pts, z in lines for a, b in zip(pts, pts[1:])]
    total = sum(math.dist(a, b) for a, b, _ in segs)
    out, step = [], total / n
    for k in range(n):
        s = (k + 0.5) * step
        for a, b, z in segs:
            l = math.dist(a, b)
            if s <= l:
                t = s / l
                out.append(((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, z), math.atan2(b[1] - a[1], b[0] - a[0])))
                break
            s -= l
    return out

def move_group(group, spots):
    """The group's nodes in vanilla loop/fore-and-aft order (key) onto spots in the same order."""
    nodes = kids(bs[group])
    assert len(nodes) == len(spots), (group, len(nodes), len(spots))
    for c, (p, yaw) in zip(nodes, spots):
        write_tf(c, pos=p, rot=(0.0, 0.0, yaw) if yaw is not None else (0.0, 0.0, tf(c)[1][2]))

def order(group, key):
    ch = bs[group].find('children')
    ch[:] = sorted(ch, key=lambda c: key(tf(c)[0]))

# rails: vanilla's 49 sorted round the meditheavy (half length 23, beam 4), ours round our loop
order('railing_parent', lambda p: loop_angle(p[0], p[1], 23.0, 4.0))
spots = sorted(sample(rail_loop(), len(kids(bs['railing_parent']))), key=lambda s: loop_angle(s[0][0], s[0][1], 25.0, 6.0))
move_group('railing_parent', [(p, yaw) for p, yaw in spots])

# deck: 3 on the poop, the rest on the gun deck between the castles, 3 on the forecastle platform (deck_spot keeps them off
# stairs, hatches, mast steps and the guns' working areas)
n_deck = len(kids(bs['ship_deck_parent']))
n_gd = n_deck - 6
deck_spots = [deck_spot(s * 1.2, y) for s, y in zip((1, -1, 1), (-22.5, -19.5, -16.5))]
deck_spots += [deck_spot((1 if k % 2 else -1) * 1.6, SC_Y1 + 1.5 + k * (FC_YB - SC_Y1 - 3.0) / (n_gd - 1)) for k in range(n_gd)]
deck_spots += [deck_spot(s * 1.0, y) for s, y in zip((-1, 1, -1), (19.8, 21.6, 23.2))]
order('ship_deck_parent', lambda p: p[1])
move_group('ship_deck_parent', [(p, None) for p in sorted(deck_spots, key=lambda p: p[1])])

# masts: the meditheavy's two rings (10 nodes each, round y ~-7 and ~8.4); the aft ring goes to our main mast, the fore
# ring's nodes alternately to the fore and mizzen masts. Offsets that would leave the mast's deck (forecastle platform
# behind the fore mast, gun deck under the poop behind the mizzen) are turned forward
mn = kids(bs['mast_parent'])
rings = [[c for c in mn if tf(c)[0][1] < 0], [c for c in mn if tf(c)[0][1] >= 0]]
def ring_centre(r):
    ps = [tf(c)[0] for c in r]
    return [sum(p[i] for p in ps) / len(ps) for i in range(2)] + [min(p[2] for p in ps)]
CENTRES = [ring_centre(r) for r in rings]                       # before any node moves (fore + mizzen share a ring)
steps = {round(y, 1): (y, z) for y, z in MASTS_AT}
by_mast = {'main': rings[0], 'fore': rings[1][0::2], 'mizzen': rings[1][1::2]}
mast_spots = []
for mast, nodes in by_mast.items():
    my, mz = next(v for k, v in steps.items() if abs(k - MASTS[mast]) < 0.2)
    cx, cy, cz = CENTRES[0 if mast == 'main' else 1]
    for c in nodes:
        (x, y, z), r, _ = tf(c)
        dx, dy = x - cx, y - cy
        if (mast == 'fore' and my + dy < FC_YB + 0.3) or (mast == 'mizzen' and my + dy < SC_Y1 + 0.3):
            dy = abs(dy)
        write_tf(c, pos=(dx, my + dy, mz + max(z - cz, 0.0)))
        mast_spots.append(mast)

# crates: each node moves with its nearest deck upgrade
for c in kids(bs['deck_upgrade_parent']):
    (x, y, z), r, _ = tf(c)
    (ox, oy, oz), (nx, ny, nz) = min(DU_MOVES, key=lambda m: math.hypot(m[0][0] - x, m[0][1] - y))
    write_tf(c, pos=(x + nx - ox, y + ny - oy, z + nz - oz))

# fire light (shown with the average fire progress): over the gun deck between the masts; sound nodes (each plays for
# the nodes within 5 m) along both sides and over both castles
for c, y in zip(kids(bs['light_parent']), (11.0, -6.5)):
    write_tf(c, pos=(0.0, y, Z_DECK + 1.2))
xs = W_IN - 0.6
snd = [((xs, -6.0, Z_DECK + 0.8), None), ((xs, 7.0, Z_DECK + 0.8), None), ((0.0, 21.6, Z_FC + 0.8), None),
       ((-xs, 7.0, Z_DECK + 0.8), None), ((-xs, -6.0, Z_DECK + 0.8), None), ((0.0, -19.5, Z_POOP_TOP + 0.8), None)]
order('sound_parent', lambda p: loop_angle(p[0], p[1], 23.0, 4.0))
move_group('sound_parent', sorted(snd, key=lambda s: loop_angle(s[0][0], s[0][1], 25.0, 6.0)))
report.append('burning system: %d rail nodes round the bulwarks/parapet/balustrade, %d deck nodes (poop/gun deck/fc), '
              '%d mast nodes (%s), %d crate nodes with their deck upgrades, %d lights, %d sound nodes' % (
              len(kids(bs['railing_parent'])), n_deck, len(mast_spots), dict(Counter(mast_spots)),
              len(kids(bs['deck_upgrade_parent'])), len(kids(bs['light_parent'])), len(kids(bs['sound_parent']))))

# --- hull water: the simulation box = 2 x the largest |x|, |y|, |z| of the 'render_to_depth' meshes in the ship frame
# (ShipWaterEffects.RecomputeWaterSimulationBoundingBox, only run by the editor button, so the stored value counts).
# Ours is galleass_deckwater: x +-6.01, y -25.29..25.40, z 3.80..6.92 (the Kit's import, mesh_extract.py)
DECKWATER_MAX = (6.01, 25.40, 6.92)
for sc in files['ship_water_effects'].iter('script'):
    for v in sc.iter('variable'):
        if v.get('name') == 'Water Simulation Bounding Box':
            v.set('value', '%.3f, %.3f, %.3f' % tuple(2 * m for m in DECKWATER_MAX))
report.append('hull water box: %s (meditheavy 8.07 x 41.05 x 14.89)' % (tuple(2 * m for m in DECKWATER_MAX),))

# --- water clip: the sea surface is cut away inside the volume of the SDF texture, placed by the entity's frame
# (signed_distance_field.SetSDFParams: texture bbox frame -> entity global frame, so the entity's scale stretches it).
# The meditheavy's ended at y -20 / +18 on the waterline - water inside our stern (user 2026-10-19). Fitted over all
# vanilla SDFs against our hull's waterline (z -0.5..1, inside the hull + outrigger, never past them): the Sturgian
# heavy longship's, x/y scaled 1.225, follows it to within ~0.2 m except the last metre or two at each end
WATER_CLIP_SDF, WATER_CLIP_SCALE = 'sdf_ship_sturgian_heavy_long', (1.225, 1.225, 1.0)
wc = files['ship_water_clip']
for v in wc.iter('variable'):
    if v.get('name') == 'SDF Texture':
        v.set('value', WATER_CLIP_SDF)
set_transform(wc, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0), scale=WATER_CLIP_SCALE)
wc[:] = sorted(wc, key=lambda c: ORDER.index(c.tag) if c.tag in ORDER else len(ORDER))
report.append('water clip: %s scaled %s' % (WATER_CLIP_SDF, WATER_CLIP_SCALE))

# --- wetness decals (wet patches on the hull sides, projected from outside): the meditheavy's six, moved out to our
# beam and along our length (its hull: half beam ~4.0, waterline y -23..24; ours 4.55 + the outrigger, -25..25)
for c in kids(files['wetness_decals']):
    (x, y, z), r, s = tf(c)
    write_tf(c, pos=(x * G['HB_WL'] / 4.0, y * 25.0 / 23.5, z))
report.append('wetness decals: %d moved to our hull sides' % len(kids(files['wetness_decals'])))

# --- port screen cameras: a selected slot's camera looks at '<slot tag>_point' (GauntletPortScreen; azimuth from its
# side offset). Our slots: hull (origin), deck, oars, sail, roof; bow_point at the spur's tip. The thumbnail camera
# (side view from +x, horizontal) backs off by our length ratio (deck water 50.8 / 41.05) and moves to our centre
cam = {name_of(c): c for c in kids(files['cam_holder_nested'])}
du_mid = min(DU_MOVES, key=lambda m: abs(m[1][1]))[1]                       # the waist's deck upgrade
CAM_POINTS = {'deck_point': (du_mid[0], du_mid[1], du_mid[2] + 1.1),
              'oars_point': (OAR_X - 2.7, (G['_OAR_FIRST'] + G['_OAR_LAST']) / 2, OAR_H + 0.5),
              'sail_point': (0.0, sum(MASTS.values()) / 3, 20.5),          # about the yards (fore 21.0, main 24.3, mizzen 16.3)
              'roof_point': (0.0, R_ORIGIN[1] + 3.66 * RSY, R_ORIGIN[2] + 1.66),   # over the middle of the roof
              'ram_point': _tip}
for c in kids(files['cam_holder_nested']):
    nm = (inh(c, 'tags') is not None and [t.get('name') for t in inh(c, 'tags').iter('tag')]) or []
    key = 'ram_point' if 'bow_point' in nm else next((t for t in nm if t in CAM_POINTS), None)
    if key:
        write_tf(c, pos=CAM_POINTS[key])
    elif 'thumbnail_cam' in nm:
        (x, y, z), r, _ = tf(c)
        k = 50.8 / 41.05
        write_tf(c, pos=(x * k, y + 2.5, z * k))
report.append('port cameras: %s' % {k: tuple(round(v, 2) for v in p) for k, p in CAM_POINTS.items()})

# --- write --------------------------------------------------------------------------------------------------------
if BELAY_MISSING and not os.environ.get('GALLEASS_ALLOW_MISSING'):   # (=1: a trial build for rig_check, not installed)
    raise SystemExit('Kit meshes missing: %s - import them in the Modding Kit first' % ', '.join(BELAY_MISSING))
ET.indent(folder, '\t', level=1)
body = ET.tostring(folder, encoding='unicode').replace(' />', '/>')   # the editor's style
with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
    f.write('<?xml version="1.0"?>\n<prefab_files>\n</prefab_files>\n<prefab_folders>\n\t' + body + '\n</prefab_folders>\n')
for line in report:
    print('PREFAB', line)
