"""Dump world positions of the gameplay entities of a ship prefab from NavalDLC's packed nested
prefabs, resolving prefab inheritance (an entity without its own transform/tags/scripts takes them
from the base entity its <prefab guid> points to; children: own overrides plus the base's not overridden). Rotation order follows TaleWorlds
Mat3.ApplyEulerAngles (z, then x, then y).

usage: python3 prefab_layout.py <packed xml>[,<base packed xml>...] <ship prefab> <out json>
(several packed files, comma separated: the first holds the ship, the others resolve its base prefabs - e.g. our
galleass prefab on top of NavalDLC's)
"""
import json, math, re, sys
import xml.etree.ElementTree as ET

roots, root, by_guid = [], None, {}
def load(packed):
    """Read the packed file(s) (comma separated; the first holds the ship) - also for importers (rig_check.py)."""
    global root
    roots.clear(); by_guid.clear()
    for path in packed.split(','):
        s = re.sub(r'^<\?xml[^>]*\?>', '', open(path, encoding='utf-8').read())
        roots.append(ET.fromstring('<r>' + s + '</r>'))
    root = roots[0]
    for r in reversed(roots):                 # the ship's own file wins
        for e in r.iter('entity'):
            g = e.find('prefab_link/instance')
            if g is not None:
                by_guid[g.get('guid')] = e

ZERO = '{00000000-0000-0000-0000-000000000000}'
def base(e):
    p = e.find('prefab_link/prefab')
    return by_guid.get(p.get('guid')) if p is not None and p.get('guid') != ZERO else None

def inherited(e, path):
    seen = 0
    while e is not None and seen < 20:
        x = e.find(path)
        if x is not None:
            return x
        e = base(e); seen += 1
    return None

def vec(x, default):
    return [float(v) for v in x.get('value').split(',')] if x is not None else default

def rot(eu):
    x, y, z = eu
    def mul(a, b): return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    cz, sz, cx, sx, cy, sy = math.cos(z), math.sin(z), math.cos(x), math.sin(x), math.cos(y), math.sin(y)
    Rz = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]
    Rx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
    Ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
    return mul(mul(Rz, Rx), Ry)

def local(e):
    p = vec(inherited(e, 'transform/position'), [0, 0, 0])
    r = rot(vec(inherited(e, 'transform/rotation_euler'), [0, 0, 0]))
    sc = vec(inherited(e, 'transform/scale'), [1, 1, 1])
    m = [[r[i][j] * sc[j] for j in range(3)] for i in range(3)]
    return m, p

def compose(pm, pp, m, p):
    wm = [[sum(pm[i][k] * m[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    wp = [pp[i] + sum(pm[i][k] * p[k] for k in range(3)) for i in range(3)]
    return wm, wp

def tags(e):
    t = inherited(e, 'tags')
    return [x.get('name') for x in t.iter('tag')] if t is not None else []

def scripts(e):
    t = inherited(e, 'scripts')
    return [x.get('name') for x in t.findall('script')] if t is not None else []

def meshes(e):
    t = inherited(e, 'components')
    return [x.get('name') for x in t.findall('meta_mesh_component')] if t is not None else []

def children(e, depth=0):
    """The children the game builds: e's own (overrides, each linked to the base child it replaces) plus every child
    of its base that none of them overrides - NavalDLC's packs leave unchanged children out (804 entities), so an entity
    that is still linked gets back whatever was deleted from its list (2026-10-18: the mizzen's vanilla backstay)."""
    own = e.findall('children/entity')
    b = base(e)
    if b is None or depth > 20:
        return own
    taken = {c.find('prefab_link/prefab').get('guid') for c in own if c.find('prefab_link/prefab') is not None}
    return own + [c for c in children(b, depth + 1) if c.find('prefab_link/instance').get('guid') not in taken]

def script_vars(e, script):
    """Variables of one script, the instance's own values over its bases'."""
    out, seen = {}, 0
    while e is not None and seen < 20:
        for sc in e.findall('scripts/script'):
            if sc.get('name') == script:
                for v in sc.iter('variable'):
                    out.setdefault(v.get('name'), v.get('value'))
        e = base(e); seen += 1
    return out

rows = []
def walk(e, path, wm, wp, depth=0):
    m, p = local(e)
    wm, wp = compose(wm, wp, m, p)
    name = e.get('name') or (base(e).get('name') if base(e) is not None else '?')
    fwd = [wm[0][1], wm[1][1], wm[2][1]]
    rows.append({'path': path + '/' + name, 'name': name, 'pos': [round(v, 3) for v in wp],
                 'fwd': [round(v, 3) for v in fwd], 'mat': [[round(v, 5) for v in row] for row in wm],
                 'tags': tags(e), 'scripts': scripts(e), 'meshes': meshes(e), 'el': e})
    if depth < 12:
        for c in children(e):
            walk(c, path + '/' + name, wm, wp, depth + 1)

I = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
def layout(ship):
    """Rows (world frames, tags, ...) of every entity of the ship prefab; row['el'] is the XML element."""
    rows.clear()
    folder = next(f for f in root.find('prefab_folders') if f.get('name') == ship)
    for pf in folder:
        walk(pf.find('entity'), '', I, [0, 0, 0])
    return rows

if __name__ == '__main__':
    packed, ship, out = sys.argv[1:4]
    load(packed)
    layout(ship)
    json.dump([{k: v for k, v in r.items() if k != 'el'} for r in rows], open(out, 'w'), indent=0)
    print(len(rows), 'entities ->', out)
