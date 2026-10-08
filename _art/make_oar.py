"""Galleass oar: vanilla base_oar_8m (NavalDLC ship_oars) with a longer shaft - 11.5 m overall (user 2026-10-08).

    python3 _art/tpac_tools/mesh_extract.py ../NavalDLC/EmAssetPackages/ship_oars/ship_oars.tpac _art/ref/oar base_oar_8m
    blender -b --python _art/make_oar.py -- _art/ref/oar/base_oar_8m.obj AssetSources/export

The vanilla oar runs along +y from the handle (y -1.15) past the oar-port collar (to ~0.3) and one long plain shaft
section to the blade (~6.0 .. 8.0). Everything beyond y 3 moves out by STRETCH, so only that shaft section gets
longer; handle, collar and blade keep their shape. The game reads the oar length from the mesh's bounding box
(ShipOarDeck.UpdateOarLength), so the longer mesh is all it needs. Material: vanilla bw_oar_wood_a (link it in the
Kit, as the hull plates' materials). LODs: the vanilla mesh's three, exported as '<name>_lodN' for the Kit.
"""
import bpy, sys, os
src, out = sys.argv[sys.argv.index('--') + 1:][:2]
NAME, OVERALL, VANILLA = 'galleass_oar_11m', 11.5, 9.15
STRETCH = OVERALL - VANILLA                                    # 2.35 m more shaft
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=src, forward_axis='Y', up_axis='Z')
objs = sorted(bpy.context.selected_objects, key=lambda o: -len(o.data.vertices))   # LOD0 = most vertices
mat = bpy.data.materials.get('bw_oar_wood_a') or bpy.data.materials.new('bw_oar_wood_a')
for i, o in enumerate(objs):
    for v in o.data.vertices:
        if v.co.y > 3.0:
            v.co.y += STRETCH
    # mesh_extract writes OBJ texture coordinates as (u, 1 - v); undo it, or the Kit gets the texture mirrored along
    # the oar (user 2026-10-08: whitish oars beside vanilla's brown ones; vanilla handle v -1.071, ours was 2.071)
    for d in o.data.uv_layers[0].data:
        d.uv = (d.uv[0], 1.0 - d.uv[1])
    o.data.update()
    o.name = o.data.name = NAME if i == 0 else f'{NAME}_lod{i}'
    o.data.materials.clear(); o.data.materials.append(mat)
    ys = [v.co.y for v in o.data.vertices]
    print('OAR %-24s %5d verts  y %.2f .. %.2f (%.2f m)' % (o.name, len(ys), min(ys), max(ys), max(ys) - min(ys)))
os.makedirs(out, exist_ok=True)
# same settings as export_fbx.py (proven in the Kit)
bpy.ops.export_scene.fbx(filepath=os.path.join(out, NAME + '.fbx'), use_selection=False, object_types={'MESH'},
                         mesh_smooth_type='FACE', use_tspace=False, axis_forward='Y', axis_up='Z',
                         apply_unit_scale=True, global_scale=1.0, bake_anim=False, path_mode='STRIP', add_leaf_bones=False)
