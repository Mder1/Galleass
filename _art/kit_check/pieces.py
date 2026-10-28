"""Per material piece of an FBX: extents, elongation, cross-section ratio and the grain_uv.piece_uvs mode its
proportions alone would give (debug for "is this part treated as round?").

    blender -b --python pieces.py -- a.fbx [b.fbx ...]
"""
import bpy, sys
sys.path.insert(0, '/mnt/Games/SteamLibrary/steamapps/common/Mount & Blade II Bannerlord/Modules/Galleass/_art')
import grain_uv
import numpy as np
for f in sys.argv[sys.argv.index('--') + 1:]:
    bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.fbx(filepath=f)
    for o in bpy.data.objects:
        if o.type != 'MESH' or '_lod' in o.name or o.name.startswith('bo_'): continue
        me = o.data
        for mi, m in enumerate(me.materials):
            polys = [p.index for p in me.polygons if p.material_index == mi]
            for pc in grain_uv._pieces(me, polys):
                vids = {v for pi in pc for v in me.polygons[pi].vertices}
                co = np.array([me.vertices[v].co[:] for v in vids]); ext = co.max(0) - co.min(0)
                c, a, el, a3, fl = grain_uv._axis([me.vertices[v].co for v in vids])
                w = np.sqrt(np.maximum(np.linalg.eigvalsh(np.cov((co - co.mean(0)).T)), 0))
                mode = 'long' if el >= 2 else 'ring' if fl >= 2 else 'planar'
                print('PC %-22s %-16s faces %4d ext %s elong %.1f flat %.1f xsec %.1f -> %s' % (o.name, m.name, len(pc), np.round(ext, 2), el, fl, w[1] / max(w[0], 1e-9), mode))
