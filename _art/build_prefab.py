"""Build the galleass ship prefab from the meditheavy clone (make_packed_clone.py output).

python3 build_prefab.py <NavalDLC packed xml> <clone xml> <out xml>

Stage 1 (hull swap): our meshes + physics shapes replace the meditheavy ones, the meditheavy-only geometry is
removed, the rudder becomes a centreline stern rudder and the figureheads move to the beak. Everything else (oars,
sails, slots, spawn/boarding points, ...) still sits where the meditheavy has it; stage 2 relays it out.

Nested prefab entities inherit missing elements (transform, tags, components, physics, children, ...) from the
entity their <prefab guid> points to (NavalDLC base prefabs). Before removing something from such an entity it is
flattened: the inherited elements are copied in and the base link is cut, so nothing comes back through inheritance.
"""
import copy, re, sys
import xml.etree.ElementTree as ET

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
set_transform(fg, pos=(0.0, 26.7 - FIG_S * 21.24, 1.75 - FIG_S * 3.05), scale=(FIG_S, FIG_S, FIG_S))
report.append('figurehead_group: scale %.2f, figureheads at (0, 26.7, 1.75)' % FIG_S)

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

# --- write --------------------------------------------------------------------------------------------------------
ET.indent(folder, '\t', level=1)
body = ET.tostring(folder, encoding='unicode').replace(' />', '/>')   # the editor's style
with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
    f.write('<?xml version="1.0"?>\n<prefab_files>\n</prefab_files>\n<prefab_folders>\n\t' + body + '\n</prefab_folders>\n')
for line in report:
    print('PREFAB', line)
