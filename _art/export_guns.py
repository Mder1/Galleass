"""Export the guns (cannon_model.py output) for the Modding Kit: UVs, LODs, collision bodies, one FBX per Kit mesh.

    blender -b ref/galleass_guns.blend --python export_guns.py -- ../AssetSources/export

Kit materials are the galleass's own (no new textures): bronze -> galleass_gilt (vanilla ram_bronze), wood and the
fuse cord -> galleass_trim, iron -> galleass_iron, bore/vent -> galleass_dark. Settings as export_fbx.py (metres,
forward Y, up Z, '<name>_lodN' objects in the same FBX, no dots in names, import from the export/ subfolder).

Per gun: galleass_<gun>.fbx (+ _lod1.._lod3), galleass_<gun>_fuse.fbx (separate so the game can hide it after a
shot), bo_galleass_<gun>.fbx (2 convex pieces: carriage, barrel; physics material 'wood').
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector

out = sys.argv[sys.argv.index('--') + 1]
os.makedirs(out, exist_ok=True)

KIT_MAT = {'galleass_gun_bronze': 'galleass_gilt', 'galleass_gun_wood': 'galleass_trim',
           'galleass_gun_fuse': 'galleass_trim', 'galleass_gun_iron': 'galleass_iron', 'galleass_gun_dark': 'galleass_dark'}
UV_S = {'galleass_gilt': 0.5, 'galleass_iron': 0.5, 'galleass_trim': 0.135, 'galleass_dark': 0.135}   # as the hull
LOD_RATIO = {1: 0.40, 2: 0.15, 3: 0.05}
GUNS = ['galleass_culverin', 'galleass_falcon', 'galleass_falconet']

def kit_mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = False
    return m

def remap_materials(me):
    for i, m in enumerate(me.materials):
        if m is not None and m.name in KIT_MAT:
            me.materials[i] = kit_mat(KIT_MAT[m.name])

def add_uvs(o):
    """Bronze barrel faces: cylindrical about the barrel axis (u around in metres of arc, v along the barrel) so the
    metal reads continuous; everything else per-face planar with U along the part's long direction (the hull's way)."""
    me = o.data; ah = o.get('axis_h', 0.8)
    uv = me.uv_layers.new(name='UVMap') if not me.uv_layers else me.uv_layers[0]
    for poly in me.polygons:
        mat = me.materials[poly.material_index].name
        s = UV_S.get(mat, 0.5)
        n = poly.normal
        pts = [me.vertices[me.loops[li].vertex_index].co for li in poly.loop_indices]
        if mat == 'galleass_gilt' and abs(n.x) < 0.95:
            c = sum(pts, Vector()) / len(pts)
            r_ref = 0.18
            a0 = math.atan2(c.x, c.z - ah)
            for li, p in zip(poly.loop_indices, pts):
                a = math.atan2(p.x, p.z - ah)
                while a - a0 > math.pi: a -= 2 * math.pi       # no wrap inside a face (seam)
                while a - a0 < -math.pi: a += 2 * math.pi
                uv.data[li].uv = (a * r_ref * s, p.y * s)
            continue
        a = Vector((0, 1, 0))                                  # grain along the gun, else across
        u = a - n * a.dot(n)
        if u.length < 0.3:
            for alt in (Vector((1, 0, 0)), Vector((0, 0, 1))):
                u = alt - n * alt.dot(n)
                if u.length >= 0.3: break
        u.normalize(); v = n.cross(u).normalized()
        for li, p in zip(poly.loop_indices, pts):
            uv.data[li].uv = (p.dot(u) * s, p.dot(v) * s)
    col = me.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER') if 'Col' not in me.color_attributes else me.color_attributes['Col']
    for d in col.data: d.color = (1, 1, 1, 1)                  # vanilla materials use vertex colours

def make_lods(o):
    lods = []
    n0 = sum(len(p.vertices) - 2 for p in o.data.polygons)
    for lvl, ratio in LOD_RATIO.items():
        me = o.data.copy(); me.name = f'{o.name}_lod{lvl}'
        lo = bpy.data.objects.new(me.name, me); bpy.context.scene.collection.objects.link(lo)
        d1 = lo.modifiers.new('flat', 'DECIMATE'); d1.decimate_type = 'DISSOLVE'
        d1.angle_limit = math.radians(2 + 3 * lvl); d1.delimit = {'MATERIAL', 'UV'}
        dg = bpy.context.evaluated_depsgraph_get()
        tmp = bpy.data.meshes.new_from_object(lo.evaluated_get(dg))
        n1 = sum(len(p.vertices) - 2 for p in tmp.polygons); bpy.data.meshes.remove(tmp)
        md = lo.modifiers.new('dec', 'DECIMATE'); md.ratio = min(1.0, ratio * n0 / max(n1, 1))
        md.use_collapse_triangulate = True; md.delimit = {'MATERIAL'} if hasattr(md, 'delimit') else set()
        dg = bpy.context.evaluated_depsgraph_get()
        nm = bpy.data.meshes.new_from_object(lo.evaluated_get(dg))
        lo.modifiers.clear(); old = lo.data; lo.data = nm; nm.name = me.name; bpy.data.meshes.remove(old)
        lods.append(lo)
    return lods

def body(o):
    """Two convex pieces: the carriage (wood + iron) and the barrel (bronze), as one 'bo_' mesh."""
    me = o.data
    groups = {'carriage': [], 'barrel': []}
    for poly in me.polygons:
        mat = me.materials[poly.material_index].name
        key = 'barrel' if mat in ('galleass_gilt', 'galleass_dark') else 'carriage'
        groups[key].extend(me.vertices[i].co.copy() for i in poly.vertices)
    bm = bmesh.new()
    for key, pts in groups.items():
        if not pts: continue
        b2 = bmesh.new()
        for p in pts[::3] if len(pts) > 3000 else pts: b2.verts.new(p)
        bmesh.ops.convex_hull(b2, input=b2.verts)
        bmesh.ops.delete(b2, geom=[v for v in b2.verts if not v.link_faces], context='VERTS')
        # reduce to a light hull
        if len(b2.faces) > 60:
            bmesh.ops.dissolve_limit(b2, angle_limit=math.radians(12), verts=b2.verts, edges=b2.edges)
            bmesh.ops.triangulate(b2, faces=b2.faces)
        tmp = bpy.data.meshes.new('tmp'); b2.to_mesh(tmp); b2.free()
        bm.from_mesh(tmp); bpy.data.meshes.remove(tmp)
    name = 'bo_' + o.name
    bme = bpy.data.meshes.new(name); bm.to_mesh(bme); bm.free()
    bme.materials.append(kit_mat('wood'))
    bo = bpy.data.objects.new(name, bme); bpy.context.scene.collection.objects.link(bo)
    return bo

def export(name, objs):
    bpy.ops.object.select_all(action='DESELECT')
    for x in objs:
        x.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    path = os.path.join(out, name + '.fbx')
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'MESH'}, use_mesh_modifiers=True,
                             mesh_smooth_type='FACE', use_tspace=False, axis_forward='Y', axis_up='Z',
                             apply_unit_scale=True, global_scale=1.0, bake_anim=False, path_mode='STRIP',
                             add_leaf_bones=False)
    tris = [sum(len(p.vertices) - 2 for p in x.data.polygons) for x in objs]
    mats = sorted({m.name for x in objs for m in x.data.materials if m})
    print('EXPORT %-34s tris %s  materials %s' % (name + '.fbx', tris, mats))

for c in bpy.data.collections:
    c.hide_viewport = False
for g in GUNS:
    o = bpy.data.objects[g]
    o.hide_set(False); o.location = (0, 0, 0)
    remap_materials(o.data); add_uvs(o)
    # the guns' masters keep auto-smooth sharp edges from cannon_model; the FBX carries face smoothing
    lods = make_lods(o)
    export(g, [o] + lods)
    f = bpy.data.objects[g + '_fuse']
    f.hide_set(False); f.location = (0, 0, 0)
    remap_materials(f.data); add_uvs(f)
    export(g + '_fuse', [f])
    bo = body(o)
    export(bo.name, [bo])
    for x in [o, f, bo] + lods:
        x.data.name = x.name                                   # FBX geometry names = datablock names, no dots
print('guns exported to', out)
