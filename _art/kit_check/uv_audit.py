"""UV audit of the hull PARTS (2026-10-28): replays add_uvs + grain_uv.follow_quads per part of the built model and prints
per part: elongation, grain alignment, smooth-edge UV seams (patch %, worst jump in mm). Columns in the AUDIT header line.

    cd Galleass && blender -b _art/ref/galleass_model.blend --python _art/kit_check/uv_audit.py | grep ^AUDIT
"""
import bpy, ast, math, sys, os
import numpy as np
from mathutils import Vector
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'galleass_model.py')).read()
tree = ast.parse(src)
ns = {'Vector': Vector, 'math': math, 'bpy': bpy}
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in ('long_axis', 'add_uvs'):
        exec(ast.get_source_segment(src, node), ns)
    if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', None) == 'UV_SCALE':
        exec(ast.get_source_segment(src, node), ns)
rows = []
dg = bpy.context.evaluated_depsgraph_get()
for o in bpy.data.collections['parts'].objects:
    if o.type != 'MESH': continue
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg)); me.transform(o.matrix_world)
    role = (o.data.materials[0].name.replace('galleass_', '') if o.data.materials and o.data.materials[0] else '?')
    if role not in ns['UV_SCALE']: bpy.data.meshes.remove(me); continue
    own = bool(o.get('own_uvs'))
    if not own:
        ns['add_uvs'](me, role)
        if o.get('strip_uv'):
            import bmesh; sys.path.insert(0, '/mnt/Games/SteamLibrary/steamapps/common/Mount & Blade II Bannerlord/Modules/Galleass/_art'); import grain_uv
            bs = bmesh.new(); bs.from_mesh(me)
            grain_uv.follow_quads(bs, bs.loops.layers.uv.active, ns['UV_SCALE'][role], o.name if role in ('trim', 'hull', 'dark') else None)
            bs.to_mesh(me); bs.free()
    uv = me.uv_layers[0].data
    co = np.array([v.co[:] for v in me.vertices]);
    c = co - co.mean(0); w, vec = np.linalg.eigh(c.T @ c); w = np.sqrt(np.maximum(w, 1e-12))
    a = Vector(vec[:, -1]); elong = w[-1] / w[-2]
    # grain direction per face (3D direction of increasing U; deck: V)
    al_w = al_s = 0.0; area = 0.0
    for p in me.polygons:
        li = list(p.loop_indices)[:3]; vs = [me.vertices[me.loops[i].vertex_index].co for i in li]
        uvs = [uv[i].uv for i in li]
        e1, e2 = vs[1] - vs[0], vs[2] - vs[0]; d1, d2 = uvs[1] - uvs[0], uvs[2] - uvs[0]
        det = d1.x * d2.y - d2.x * d1.y
        if abs(det) < 1e-12: continue
        g = (e1 * d2.y - e2 * d1.y) / det if role != 'deck' else (e2 * d1.x - e1 * d2.x) / det   # dP/dU (deck: dP/dV)
        if g.length < 1e-9: continue
        n = p.normal
        if abs(n.dot(a)) > 0.5: continue                     # end faces: the long axis is not in them
        al_w += abs(g.normalized().dot(a)) * p.area; area += p.area
    align = al_w / area if area else 1.0
    # patchwork: smooth edges whose UVs differ on the two sides
    edge_loops = {}
    for p in me.polygons:
        lis = list(p.loop_indices)
        for k, li in enumerate(lis):
            l = me.loops[li]; ln = lis[(k + 1) % len(lis)]
            edge_loops.setdefault(l.edge_index, []).append((p.index, l.vertex_index, uv[li].uv.copy()))
            edge_loops[l.edge_index].append((p.index, me.loops[ln].vertex_index, uv[ln].uv.copy()))
    sm = cut = 0; worst = 0.0
    for e in me.edges:
        fs = {}
        for pi, vi, u in edge_loops.get(e.index, []):
            fs.setdefault(pi, {})[vi] = u
        if len(fs) != 2: continue
        (fa, ua), (fb, ub) = fs.items()
        if me.polygons[fa].normal.angle(me.polygons[fb].normal, 0) > math.radians(30): continue
        sm += 1
        mm = max([(ua[v] - ub[v]).length / ns['UV_SCALE'][role] * 1000 for v in ua if v in ub] or [0])
        worst = max(worst, mm)
        if mm > 5: cut += 1
    ext = co.max(0) - co.min(0)
    rows.append((o.name, role, own, len(me.polygons), elong, align, sm, cut / sm if sm else 0.0, tuple(round(float(x), 1) for x in co.mean(0)), round(float(ext.max()), 2), worst))
    bpy.data.meshes.remove(me)
import collections
def base(n): return n.split('.')[0]
grp = collections.OrderedDict()
for r in rows: grp.setdefault((base(r[0]), r[1], r[2]), []).append(r)
print('AUDIT name role own n faces elong align smoothEdges patch% size example_at')
for (n, role, own), rs in grp.items():
    f = sum(r[3] for r in rs); el = max(r[4] for r in rs); al = sum(r[5] for r in rs) / len(rs); sm = sum(r[6] for r in rs)
    pc = sum(r[7] * r[6] for r in rs) / sm if sm else 0
    print('AUDIT %-28s %-6s %d %4d %6d %5.1f %4.2f %6d %5.0f%% worst %7.0fmm %6.2f %s' % (n, role, own, len(rs), f, el, al, sm, 100 * pc, max(r[10] for r in rs), max(r[9] for r in rs), rs[0][8]))
