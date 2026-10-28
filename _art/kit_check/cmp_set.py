"""Exports vs the Kit copies, ORDER-INDEPENDENT (per object: multiset of polygons as (position, UV) loops + material).
cmp_kit-style per-index compares flag polygon reordering as changes (shot balls, 2026-10-28); this does not.
Prints SET <name> SAME | CHANGED <objects> - the CHANGED ones are the Kit delete + re-import list.

    cd Galleass && blender -b --python _art/kit_check/cmp_set.py -- AssetSources galleass_hull galleass_culverin ...
"""
import bpy, sys, os
from collections import Counter
args = sys.argv[sys.argv.index('--') + 1:]; d = args[0]
def load(p):
    bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.fbx(filepath=p)
    out = {}
    for o in bpy.data.objects:
        if o.type != 'MESH': continue
        me = o.data; uv = me.uv_layers[0].data if me.uv_layers else None
        polys = []
        for p in me.polygons:
            loops = tuple(sorted((tuple(round(x, 3) for x in (o.matrix_world @ me.vertices[me.loops[i].vertex_index].co)),
                                  tuple(round(x, 3) for x in uv[i].uv) if uv else ()) for i in p.loop_indices))
            polys.append((me.materials[p.material_index].name if me.materials else '', loops))
        out[o.name] = Counter(polys)
    return out
for n in args[1:]:
    a, b = load(os.path.join(d, 'export', n + '.fbx')), load(os.path.join(d, n + '.fbx'))
    diff = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
    print('SET', n, 'SAME' if not diff else 'CHANGED ' + ' '.join(sorted(diff)))
