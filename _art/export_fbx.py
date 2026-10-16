"""Export the galleass meshes for the Modding Kit (settings as for GreekFire: metres, forward Y, up Z).

blender -b ref/galleass_model.blend --python export_fbx.py -- ../AssetSources/export

Import from a SUBFOLDER of AssetSources (export/): the Kit copies each imported source into the AssetSources root,
and a file that already sits there silently fails to import (copy onto itself). The root copies are the Kit's.

One FBX per Kit mesh, each with its LODs ('<name>.lodN' objects). Material names are the Kit material names
(create those materials in the Kit BEFORE importing - binding happens at import). The rudder is exported in its
own frame (pivot = hinge); its placement in the prefab is printed.
"""
import bpy, bmesh, sys, os, math

out = sys.argv[sys.argv.index('--') + 1]
os.makedirs(out, exist_ok=True)
for c in bpy.data.collections:
    c.hide_viewport = False
for o in bpy.data.objects:
    o.hide_viewport = False; o.hide_set(False)

# the Kit takes '<name>_lodN' objects in the same FBX as LODs of '<name>' (tested with the rudder: one mesh
# results); the '.lodN' names from the model script are renamed for export
for o in list(bpy.data.objects):
    if '.lod' in o.name:
        o.name = o.name.replace('.lod', '_lod')
# 'galleass_rudder' stays blocked in the Kit after the deleted rudder_a test import (a fresh import of that name
# silently fails, the same file renamed imports), so the Kit mesh is galleass_rudder_a
for o in list(bpy.data.objects):
    if o.name == 'galleass_rudder' or o.name.startswith('galleass_rudder_lod'):
        o.name = o.name.replace('galleass_rudder', 'galleass_rudder_a')
# FBX geometry names = mesh datablock names: no dots anywhere (the Kit's importer silently fails on them)
for o in bpy.data.objects:
    if o.type == 'MESH':
        o.data.name = o.name

# no texture references in the FBX (the preview images live in _art/ref/tex, so the paths dangle next to the
# FBX); the Kit materials carry the real textures. GreekFire's FBX had none either.
for m in bpy.data.materials:
    m.use_nodes = False

def objs(base, lods=True):
    names = [base] + ([f'{base}_lod{i}' for i in (1, 2, 3)] if lods else [])
    return [bpy.data.objects[n] for n in names if n in bpy.data.objects]

ROLES = ['hull', 'paint', 'deck', 'trim', 'gilt', 'iron', 'dark']
GROUPS = {
    'galleass_hull': [o for r in ROLES for o in objs(f'galleass_{r}')],
    'galleass_faction_paint': objs('galleass_faction_paint'),
    'galleass_hull_plate': objs('galleass_hull_plate'),
    'galleass_rudder_a': objs('galleass_rudder_a'),
    'galleass_deckwater': objs('galleass_deckwater', False),
    'bo_composite_conv_galleass': objs('bo_composite_conv_galleass', False),
    'bo_galleass': objs('bo_galleass', False),
}
# physics materials, as on the vanilla shapes
for name, pm in (('bo_composite_conv_galleass', 'wood_ship'), ('bo_galleass', 'wood')):
    me = bpy.data.objects[name].data
    me.materials.clear(); me.materials.append(bpy.data.materials.get(pm) or bpy.data.materials.new(pm))

# the Kit builds a 'bo_composite_*' shape from the plain 'bo_' bodies parented to it and ignores the composite
# object's own geometry (a single mesh imports as an empty shape; tested 2026-10-07, test_composite_fbx.py): split the
# convex pieces into children of an empty
def split_composite(name, child_fmt):
    src = bpy.data.objects[name]
    bm = bmesh.new(); bm.from_mesh(src.data); bm.verts.ensure_lookup_table()
    parts, seen = [], set()
    for v in bm.verts:
        if v.index in seen: continue
        stack, comp = [v], set()
        while stack:
            x = stack.pop()
            if x.index in comp: continue
            comp.add(x.index); stack.extend(e.other_vert(x) for e in x.link_edges)
        seen |= comp; parts.append(comp)
    mats = list(src.data.materials)
    src.name = name + '_src'
    root = bpy.data.objects.new(name, None); root.matrix_world = src.matrix_world
    bpy.context.scene.collection.objects.link(root)
    out = [root]
    for i, comp in enumerate(parts):
        b2 = bm.copy()
        bmesh.ops.delete(b2, geom=[v for v in b2.verts if v.index not in comp], context='VERTS')
        me = bpy.data.meshes.new(child_fmt % i); b2.to_mesh(me); b2.free()
        for m in mats: me.materials.append(m)
        o = bpy.data.objects.new(child_fmt % i, me); o.parent = root
        bpy.context.scene.collection.objects.link(o); out.append(o)
    bm.free()
    return out

GROUPS['bo_composite_conv_galleass'] = split_composite('bo_composite_conv_galleass', 'bo_galleass_conv_part%d')

# the painted planking keeps its own material galleass_paint (grey plank texture galleass_painted_plank_d, from
# make_painted_plank_texture.py); its mesh carries the 'faction_color' tag, so the game tints the wood itself. The
# solid overlay galleass_faction_paint is no longer exported (it hid the wood - user 2026-10-16).
del GROUPS['galleass_faction_paint']

# rudder: export in its own frame (mesh data is already local to the hinge)
rud = [o for o in GROUPS['galleass_rudder_a']]
rud_frames = {o.name: o.matrix_world.copy() for o in rud}
r0 = bpy.data.objects['galleass_rudder_a']
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
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'MESH', 'EMPTY'}, use_mesh_modifiers=True,
                             mesh_smooth_type='FACE', use_tspace=False, axis_forward='Y', axis_up='Z',
                             apply_unit_scale=True, global_scale=1.0, bake_anim=False, path_mode='STRIP',
                             add_leaf_bones=False)
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in group if o.type == 'MESH' and '_lod' not in o.name)
    mats = sorted({m.name for o in group if o.type == 'MESH' for m in o.data.materials if m})
    report.append('%-30s objects %2d  LOD0 tris %6d  materials %s' % (fbx + '.fbx', len(group), tris, mats))

for o in rud:
    o.matrix_world = rud_frames[o.name]
for r in report:
    print('EXPORT', r)
print('EXPORT rudder entity: position (%.3f, %.3f, %.3f), rotation_euler (%.4f, %.4f, %.4f) rad' % (*loc, *rot))
