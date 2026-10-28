"""UV audit of exported FBXs, per loose piece: grain alignment (AUDGRAIN lines: grain across a piece) and seams (AUD lines).

    blender -b --python uv_audit_fbx.py -- <folder with .fbx files>
"""
import bpy, bmesh, sys, os, math, glob, collections
import numpy as np
from mathutils import Vector
d = sys.argv[sys.argv.index('--') + 1]
for fbx in sorted(glob.glob(os.path.join(d, '*.fbx'))):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try: bpy.ops.import_scene.fbx(filepath=fbx)
    except Exception as e: print('AUD', os.path.basename(fbx), 'import failed', e); continue
    for o in bpy.data.objects:
        if o.type != 'MESH' or '_lod' in o.name or o.name.startswith('bo_') or not o.data.uv_layers: continue
        bm = bmesh.new(); bm.from_mesh(o.data); bm.transform(o.matrix_world)
        bm.verts.ensure_lookup_table(); bm.faces.ensure_lookup_table()
        uvl = bm.loops.layers.uv[0]
        seen = set(); comps = []
        for f in bm.faces:
            if f.index in seen: continue
            stack = [f]; comp = []; seen.add(f.index)
            while stack:
                g = stack.pop(); comp.append(g)
                for e in g.edges:
                    for h in e.link_faces:
                        if h.index not in seen: seen.add(h.index); stack.append(h)
            comps.append(comp)
        res = collections.defaultdict(lambda: [0, 0, 0.0, 0.0, 0, 0.0, 0.0, None, 0.0])
        for comp in comps:
            mat = o.data.materials[comp[0].material_index].name if o.data.materials else '?'
            vs = {v for f in comp for v in f.verts}
            co = np.array([v.co[:] for v in vs]); c = co - co.mean(0)
            w, vec = np.linalg.eigh(c.T @ c); w = np.sqrt(np.maximum(w, 1e-12)); a = Vector(vec[:, -1]); el = w[-1] / max(w[-2], 1e-9)
            al = ar = 0.0; dens = []
            for f in comp:
                ls = f.loops[:3]; p = [l.vert.co for l in ls]; t = [l[uvl].uv for l in ls]
                e1, e2 = p[1] - p[0], p[2] - p[0]; d1, d2 = t[1] - t[0], t[2] - t[0]
                det = d1.x * d2.y - d2.x * d1.y
                A3 = e1.cross(e2).length / 2
                if abs(det) < 1e-14 or A3 < 1e-9: continue
                dens.append(math.sqrt(abs(det) / 2 / A3))            # UV units per metre
                g = (e1 * d2.y - e2 * d1.y) / det
                if g.length < 1e-9 or abs(f.normal.dot(a)) > 0.5: continue
                al += abs(g.normalized().dot(a)) * f.calc_area(); ar += f.calc_area()
            dn = float(np.median(dens)) if dens else 1.0
            sm = bad = 0; worst = 0.0
            for f in comp:
                for e in f.edges:
                    lf = e.link_faces
                    if len(lf) != 2 or lf[0] is not f or lf[0].normal.angle(lf[1].normal, 0) > math.radians(30): continue
                    sm += 1
                    mm = 0.0
                    for v in e.verts:
                        uu = [l[uvl].uv for g in lf for l in g.loops if l.vert is v]
                        if len(uu) == 2: mm = max(mm, (uu[0] - uu[1]).length / dn * 1000)
                    worst = max(worst, mm)
                    if mm > 5: bad += 1
            r = res[(o.name, mat)]
            r[0] += 1; r[1] += len(comp); r[2] = max(r[2], el); r[4] += sm; r[5] += bad; r[6] = max(r[6], worst)
            if ar: r[3] += al / ar * len(comp); r[8] += len(comp)
            if el > 2.5 and ar and al / ar < 0.75:
                print('AUDGRAIN %-28s %-28s %-24s elong %.1f align %.2f at %s size %.2f' % (os.path.basename(fbx), o.name, mat, el, al / ar,
                      tuple(round(float(x), 2) for x in co.mean(0)), float((co.max(0) - co.min(0)).max())))
        for (on, mat), r in res.items():
            print('AUD %-28s %-28s %-24s comps %4d faces %6d maxElong %5.1f align %.2f smooth %6d seams>5mm %5.1f%% worst %6.0fmm' % (
                os.path.basename(fbx), on, mat, r[0], r[1], r[2], r[3] / r[8] if r[8] else 1, r[4], 100 * r[5] / max(r[4], 1), r[6]))
        bm.free()
