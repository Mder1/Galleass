"""Dump world positions of the gameplay entities of a ship prefab from NavalDLC's packed nested
prefabs, resolving prefab inheritance (an entity without its own transform/tags/scripts takes them
from the base entity its <prefab guid> points to). Rotation order follows TaleWorlds
Mat3.ApplyEulerAngles (z, then x, then y).

usage: python3 prefab_layout.py <packed xml> <ship prefab> <out json>
"""
import json, math, re, sys
import xml.etree.ElementTree as ET

packed, ship, out = sys.argv[1:4]
s = re.sub(r'^<\?xml[^>]*\?>', '', open(packed, encoding='utf-8').read())
root = ET.fromstring('<r>' + s + '</r>')
by_guid = {}
for e in root.iter('entity'):
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

def children(e):
    own = e.findall('children/entity')
    if own:
        return own
    b = base(e)
    return children(b) if b is not None else []

folder = next(f for f in root.find('prefab_folders') if f.get('name') == ship)
rows = []
def walk(e, path, wm, wp, depth=0):
    m, p = local(e)
    wm, wp = compose(wm, wp, m, p)
    name = e.get('name') or (base(e).get('name') if base(e) is not None else '?')
    fwd = [wm[0][1], wm[1][1], wm[2][1]]
    rows.append({'path': path + '/' + name, 'name': name, 'pos': [round(v, 3) for v in wp],
                 'fwd': [round(v, 3) for v in fwd], 'tags': tags(e), 'scripts': scripts(e), 'meshes': meshes(e)})
    if depth < 12:
        for c in children(e):
            walk(c, path + '/' + name, wm, wp, depth + 1)

I = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
for pf in folder:
    walk(pf.find('entity'), '', I, [0, 0, 0])
json.dump(rows, open(out, 'w'), indent=0)
print(len(rows), 'entities ->', out)
