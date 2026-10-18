"""Navmesh viewer: the galleass model with its navmesh prefab laid over it (user 2026-10-18: see the navmesh; the Kit
does not show a ship's NavMeshPrefabs mesh). Faces coloured by deck: gun deck, forecastle, poop, steps / stairs
between them, boarding faces (ids 1..44) red. Also writes an OBJ + MTL beside the .blend.
    blender -b ref/galleass_model.blend --python navmesh_view.py -- ../NavMeshPrefabs/galleass_ship_navmesh.bin ref/galleass_navmesh_view.blend
"""
import bpy, bmesh, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import navmesh

argv = sys.argv[sys.argv.index('--') + 1:]
nav_path, out_blend = argv[0], argv[1]
V, E, F = navmesh.read(nav_path)
LIFT = 0.03                                                          # above the planks, so it is not z-fighting

# (name, colour, test on the face's mean z, mean y (bow +y) and id)
CLASSES = [
    ('nav_boarding', (0.90, 0.10, 0.10), lambda z, y, i: 1 <= i <= 44),
    ('nav_gun_deck', (0.15, 0.55, 0.95), lambda z, y, i: z < 3.95),
    ('nav_forecastle', (0.20, 0.80, 0.30), lambda z, y, i: 6.2 <= z < 6.5 and y > 0),   # (the poop stairs pass 6.3 too)
    ('nav_poop', (0.95, 0.75, 0.10), lambda z, y, i: z >= 6.8),
    ('nav_steps_stairs', (0.85, 0.35, 0.90), lambda z, y, i: True),
]

mats = []
for name, c, _ in CLASSES:
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*c, 0.75)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (*c, 1)
        bsdf.inputs['Alpha'].default_value = 0.75
    mats.append(m)

def classify(vs, fid):
    z = sum(V[v][2] for v in vs) / len(vs)
    y = sum(V[v][1] for v in vs) / len(vs)
    for k, (_, _, test) in enumerate(CLASSES):
        if test(z, y, fid):
            return k

me = bpy.data.meshes.new('galleass_navmesh')
bm = bmesh.new()
bv = [bm.verts.new((x, y, z + LIFT)) for x, y, z in V]
counts = [0] * len(CLASSES)
for vs, _, fid in F:
    try:
        f = bm.faces.new([bv[v] for v in vs])
    except ValueError:                                               # (a duplicate face: skip it)
        continue
    f.material_index = classify(vs, fid)
    counts[f.material_index] += 1
bm.to_mesh(me); bm.free()
for m in mats:
    me.materials.append(m)
ob = bpy.data.objects.new('galleass_navmesh', me)
bpy.context.scene.collection.objects.link(ob)
ob.show_wire = True
ob.show_in_front = True
for area in getattr(bpy.context.screen, 'areas', []):
    for sp in area.spaces:
        if sp.type == 'VIEW_3D':
            sp.shading.color_type = 'MATERIAL'

bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_blend))

# OBJ + MTL (Blender's OBJ export handles the axes: Z up, +Y forward as in the ship)
obj_path = os.path.splitext(out_blend)[0] + '.obj'
with open(os.path.splitext(obj_path)[0] + '.mtl', 'w') as f:
    for name, c, _ in CLASSES:
        f.write('newmtl %s\nKd %.3f %.3f %.3f\nd 0.75\n\n' % (name, *c))
with open(obj_path, 'w') as f:
    f.write('mtllib %s\no galleass_navmesh\n' % os.path.basename(os.path.splitext(obj_path)[0] + '.mtl'))
    for x, y, z in V:                                                # OBJ is Y up: (x, z, -y)
        f.write('v %.4f %.4f %.4f\n' % (x, z + LIFT, -y))
    groups = [[] for _ in CLASSES]
    for vs, _, fid in F:
        groups[classify(vs, fid)].append(vs)
    for k, (name, _, _) in enumerate(CLASSES):
        f.write('g %s\nusemtl %s\n' % (name, name))
        for vs in groups[k]:
            f.write('f %s\n' % ' '.join(str(v + 1) for v in vs))
print('navmesh view: %d verts, %d faces (%s) -> %s, %s' % (len(V), len(F),
      ', '.join('%s %d' % (CLASSES[k][0], counts[k]) for k in range(len(CLASSES))), out_blend, obj_path))
