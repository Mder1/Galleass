"""LODs for the Kit meshes (Blender): '<name>_lod1.._lod3' objects exported into the same FBX as the mesh, the convention
the Modding Kit reads. Planar DISSOLVE first (flat areas lose their extra edges), then a collapse DECIMATE down to the
level's ratio of the original triangle count; meshes under min_tris stay whole. Shared by export_guns.py (the guns, since
2026-10-15) and, since the performance pass of 2026-10-27, the stores, belaying fittings, desk and gun tackle blocks.
"""
import math
import bpy, bmesh

LOD_RATIO = {1: 0.40, 2: 0.15, 3: 0.05}

def tris(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)

def make_lods(o, ratios=LOD_RATIO, min_tris=100, drop=None):
    """LOD objects for o (linked to the scene, data named like the objects). drop: {material name: first level without
    its faces} (e.g. the rope turns on the belaying pins go from LOD 2)."""
    lods = []
    n0 = tris(o.data)
    for lvl, ratio in ratios.items():
        me = o.data.copy(); me.name = f'{o.name}_lod{lvl}'
        lo = bpy.data.objects.new(me.name, me); bpy.context.scene.collection.objects.link(lo)
        gone = [i for i, m in enumerate(me.materials) if m is not None and drop and lvl >= drop.get(m.name, 99)]
        if gone:
            bm = bmesh.new(); bm.from_mesh(me)
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in gone], context='FACES')
            bm.to_mesh(me); bm.free()
            used = sorted({p.material_index for p in me.polygons})   # no empty slots (the Kit warns about them)
            idx = [used.index(p.material_index) for p in me.polygons]
            mats = [me.materials[i] for i in used]
            me.materials.clear()
            for m in mats: me.materials.append(m)
            for p, i in zip(me.polygons, idx): p.material_index = i
        if n0 < min_tris or tris(me) <= ratio * n0:            # tiny parts (the quoin) stay whole; so does what is
            lods.append(lo); continue                          # already under the level's budget after a drop
        d1 = lo.modifiers.new('flat', 'DECIMATE'); d1.decimate_type = 'DISSOLVE'
        d1.angle_limit = math.radians(2 + 3 * lvl); d1.delimit = {'MATERIAL', 'UV'}
        dg = bpy.context.evaluated_depsgraph_get()
        tmp = bpy.data.meshes.new_from_object(lo.evaluated_get(dg))
        n1 = tris(tmp); bpy.data.meshes.remove(tmp)
        md = lo.modifiers.new('dec', 'DECIMATE')
        md.ratio = min(1.0, ratio * n0 / max(n1, 1))
        md.use_collapse_triangulate = True; md.delimit = {'MATERIAL'} if hasattr(md, 'delimit') else set()
        dg = bpy.context.evaluated_depsgraph_get()
        nm = bpy.data.meshes.new_from_object(lo.evaluated_get(dg))
        lo.modifiers.clear(); old = lo.data; lo.data = nm; nm.name = me.name; bpy.data.meshes.remove(old)
        lods.append(lo)
    return lods
