"""Kit test: how does a 'bo_composite_conv_*' physics shape get its pieces? (2026-10-07)
blender -b ref/galleass_model.blend --python test_composite_fbx.py -- <out dir>
Variant 1: empty 'bo_composite_conv_gtest1' + 7 child meshes 'gtest1_part<i>' (wood_ship).
Variant 2: empty 'bo_composite_conv_gtest2' + 7 child meshes 'bo_composite_conv_gtest2_<i>'."""
import bpy, bmesh, sys, os
out = sys.argv[sys.argv.index('--') + 1]; os.makedirs(out, exist_ok=True)
src = bpy.data.objects['bo_composite_conv_galleass']
mat = bpy.data.materials.get('wood_ship') or bpy.data.materials.new('wood_ship')
for m in bpy.data.materials:
    m.use_nodes = False
bm = bmesh.new(); bm.from_mesh(src.data)
bm.verts.ensure_lookup_table()
# loose parts = the convex pieces
parts, seen = [], set()
for v in bm.verts:
    if v.index in seen: continue
    stack, comp = [v], set()
    while stack:
        x = stack.pop()
        if x.index in comp: continue
        comp.add(x.index); stack.extend(e.other_vert(x) for e in x.link_edges)
    seen |= comp; parts.append(comp)
print('TEST pieces', len(parts))
for variant, child_name in ((1, 'gtest1_part%d'), (2, 'bo_composite_conv_gtest2_%d')):
    bpy.ops.object.select_all(action='DESELECT')
    root = bpy.data.objects.new('bo_composite_conv_gtest%d' % variant, None)
    bpy.context.scene.collection.objects.link(root); objs = [root]
    for i, comp in enumerate(parts):
        b2 = bm.copy()
        bmesh.ops.delete(b2, geom=[v for v in b2.verts if v.index not in comp], context='VERTS')
        me = bpy.data.meshes.new(child_name % i); b2.to_mesh(me); b2.free()
        me.materials.append(mat)
        o = bpy.data.objects.new(child_name % i, me); o.parent = root
        bpy.context.scene.collection.objects.link(o); objs.append(o)
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = root
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, 'bo_composite_conv_gtest%d.fbx' % variant), use_selection=True,
                             object_types={'MESH', 'EMPTY'}, mesh_smooth_type='FACE', use_tspace=False, axis_forward='Y',
                             axis_up='Z', apply_unit_scale=True, global_scale=1.0, bake_anim=False, path_mode='STRIP',
                             add_leaf_bones=False)
