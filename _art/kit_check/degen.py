"""Faces with real area but zero UV area (texture smeared into a line), per object, LOD0 only. The hull has 23 known
small ones (iron 18, trim 5); more than that = a UV bug (2026-10-28: a mirror fold inside faces gave 780).

    blender -b --python degen.py -- a.fbx [b.fbx ...]
"""
import bpy, sys
from mathutils import Vector
for p in sys.argv[sys.argv.index('--') + 1:]:
    bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.fbx(filepath=p)
    print('FILE', p.split('/')[-2])
    for o in bpy.data.objects:
        if o.type != 'MESH' or '_lod' in o.name or not o.data.uv_layers: continue
        me = o.data; uv = me.uv_layers[0].data; bad = []
        for poly in me.polygons:
            if poly.area < 1e-4: continue
            u = [Vector(uv[i].uv) for i in poly.loop_indices]
            a = 0.0
            for k in range(1, len(u) - 1):
                d1, d2 = u[k] - u[0], u[k + 1] - u[0]; a += abs(d1.x * d2.y - d1.y * d2.x) / 2
            if a < 1e-6: bad.append(poly)
        if bad:
            ys = [(o.matrix_world @ p.center) for p in bad]
            print('  DEGEN', o.name, len(bad), 'of', len(me.polygons), 'y %.1f..%.1f' % (min(c.y for c in ys), max(c.y for c in ys)))
