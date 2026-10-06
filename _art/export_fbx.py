"""Export the galleass meshes for the Modding Kit (settings as for GreekFire: metres, forward Y, up Z).

blender -b ref/galleass_model.blend --python export_fbx.py -- <out dir>

One FBX per Kit mesh, each with its LODs ('<name>.lodN' objects). Material names are the Kit material names
(create those materials in the Kit BEFORE importing - binding happens at import). The rudder is exported in its
own frame (pivot = hinge); its placement in the prefab is printed.
"""
import bpy, sys, os, math

out = sys.argv[sys.argv.index('--') + 1]
os.makedirs(out, exist_ok=True)
for c in bpy.data.collections:
    c.hide_viewport = False
for o in bpy.data.objects:
    o.hide_viewport = False; o.hide_set(False)

def objs(base, lods=True):
    names = [base] + ([f'{base}.lod{i}' for i in (1, 2, 3)] if lods else [])
    return [bpy.data.objects[n] for n in names if n in bpy.data.objects]

ROLES = ['hull', 'paint', 'deck', 'trim', 'gilt', 'iron', 'dark', 'glass']
GROUPS = {
    'galleass_hull': [o for r in ROLES for o in objs(f'galleass_{r}')],
    'galleass_faction_paint': objs('galleass_faction_paint'),
    'galleass_interior': objs('galleass_interior'),
    'galleass_rudder': objs('galleass_rudder'),
    'galleass_deckwater': objs('galleass_deckwater', False),
    'bo_composite_conv_galleass': objs('bo_composite_conv_galleass', False),
    'bo_galleass': objs('bo_galleass', False),
}
# physics materials, as on the vanilla shapes
for name, pm in (('bo_composite_conv_galleass', 'wood_ship'), ('bo_galleass', 'wood')):
    me = bpy.data.objects[name].data
    me.materials.clear(); me.materials.append(bpy.data.materials.get(pm) or bpy.data.materials.new(pm))

# rudder: export in its own frame (mesh data is already local to the hinge)
rud = [o for o in GROUPS['galleass_rudder']]
rud_frames = {o.name: o.matrix_world.copy() for o in rud}
r0 = bpy.data.objects['galleass_rudder']
loc, rot = r0.matrix_world.to_translation(), r0.matrix_world.to_euler()
for o in rud:
    o.matrix_world.identity()

report = []
for fbx, group in GROUPS.items():
    bpy.ops.object.select_all(action='DESELECT')
    for o in group:
        o.select_set(True)
    bpy.context.view_layer.objects.active = group[0]
    path = os.path.join(out, fbx + '.fbx')
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'MESH'}, use_mesh_modifiers=True,
                             mesh_smooth_type='FACE', use_tspace=False, axis_forward='Y', axis_up='Z',
                             apply_unit_scale=True, global_scale=1.0, bake_anim=False, path_mode='STRIP',
                             add_leaf_bones=False)
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in group if '.lod' not in o.name)
    mats = sorted({m.name for o in group for m in o.data.materials if m})
    report.append('%-30s objects %2d  LOD0 tris %6d  materials %s' % (fbx + '.fbx', len(group), tris, mats))

for o in rud:
    o.matrix_world = rud_frames[o.name]
for r in report:
    print('EXPORT', r)
print('EXPORT rudder entity: position (%.3f, %.3f, %.3f), rotation_euler (%.4f, %.4f, %.4f) rad' % (*loc, *rot))
