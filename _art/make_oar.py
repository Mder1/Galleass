"""Galleass oars: vanilla's 8 m oars (NavalDLC ship_oars) with a longer shaft - 11.5 m overall (user 2026-10-08).
The base oar and the six upgrade oars of the 'oars' slot (Light = narrow_oar_l1..3, Wide = wide_oar_l1..3).

    sh _art/extract_oars.sh                                         (OBJ + sub-mesh table into _art/ref/oar/)
    blender -b --python _art/make_oar.py -- _art/ref/oar AssetSources/export

Vanilla oars run along +y from the handle (y -1.15) past the oar-port fittings (to ~0.6) and one long plain shaft
section to the 2 m blade (~6.0 .. 8.0). Everything beyond y 3 moves out by STRETCH, so only that shaft section gets
longer; handle, fittings and blade keep their shape. The game reads the oar length from the base oar's bounding box
(ShipOarDeck.UpdateOarLength). Per oar: the parts of each LOD (vanilla lod 0/4/6) are joined into one object with
one material slot per part material (vanilla material names - link them in the Kit, as the hull plates'); exported
as '<name>', '<name>_lod1', '<name>_lod2'. mesh_extract writes OBJ texture coordinates as (u, 1 - v): undone here,
or the Kit gets the texture mirrored along the oar (2026-10-08).
"""
import bpy, bmesh, json, os, sys
src, out = sys.argv[sys.argv.index('--') + 1:][:2]
OVERALL, VANILLA = 11.5, 9.15
STRETCH = OVERALL - VANILLA                                        # 2.35 m more shaft
OARS = {'base_oar_8m': 'galleass_oar_11m'}
for lvl in (1, 2, 3):
    OARS[f'narrow_oar_l{lvl}_8m'] = f'galleass_oar_light_l{lvl}'
    OARS[f'wide_oar_l{lvl}_8m'] = f'galleass_oar_wide_l{lvl}'
LOD_SUFFIX = {0: '', 4: '_lod1', 6: '_lod2'}
table = json.load(open(os.path.join(src, 'meshes.json')))
os.makedirs(out, exist_ok=True)

for vanilla, name in OARS.items():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.obj_import(filepath=os.path.join(src, vanilla + '.obj'), forward_axis='Y', up_axis='Z')
    parts = {o.name: o for o in bpy.context.selected_objects}                # '<vanilla>.<k>' in metamesh order
    by_lod = {}
    for sub in table[vanilla]:
        o = parts['%s.%d' % (vanilla, sub['index'])]
        for v in o.data.vertices:
            if v.co.y > 3.0:
                v.co.y += STRETCH
        for d in o.data.uv_layers[0].data:
            d.uv = (d.uv[0], 1.0 - d.uv[1])
        mat = bpy.data.materials.get(sub['material_name']) or bpy.data.materials.new(sub['material_name'])
        o.data.materials.clear(); o.data.materials.append(mat)
        by_lod.setdefault(sub['lod'], []).append(o)
    for lod, objs in sorted(by_lod.items()):
        bpy.ops.object.select_all(action='DESELECT')
        for o in objs: o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        if len(objs) > 1:
            bpy.ops.object.join()
        o = bpy.context.view_layer.objects.active
        o.name = o.data.name = name + LOD_SUFFIX[lod]
        ys = [v.co.y for v in o.data.vertices]
        print('OAR %-26s %5d verts  y %.2f .. %.2f  materials %s'
              % (o.name, len(ys), min(ys), max(ys), [m.name for m in o.data.materials]))
    # same settings as export_fbx.py (proven in the Kit)
    bpy.ops.export_scene.fbx(filepath=os.path.join(out, name + '.fbx'), use_selection=False, object_types={'MESH'},
                             mesh_smooth_type='FACE', use_tspace=False, axis_forward='Y', axis_up='Z',
                             apply_unit_scale=True, global_scale=1.0, bake_anim=False, path_mode='STRIP',
                             add_leaf_bones=False)
