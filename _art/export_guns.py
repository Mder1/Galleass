"""Export the guns (cannon_model.py output) for the Modding Kit: UVs, LODs, collision bodies, one FBX per Kit mesh.

    blender -b ref/galleass_guns.blend --python export_guns.py -- ../AssetSources/export

Kit materials: bronze (barrel + trunnions/vent boss) -> galleass_gun_bronze (own atlas, gun_uv.py / gun_texture.py:
arms, initials, date), wood and the fuse cord -> galleass_trim, lashings / breeching collar -> galleass_rope (UVs from
rope_geom.py), iron -> galleass_iron, bore/vent -> galleass_dark. Settings as export_fbx.py (metres,
forward Y, up Z, '<name>_lodN' objects in the same FBX, no dots in names, import from the export/ subfolder).

Per gun (moving parts for the gunnery add-on, 2026-10-15; split by cannon_model.py's face attribute 'part'):
galleass_<gun>.fbx = carriage, galleass_<gun>_barrel.fbx (barrel, trunnions, vent, breeching collar; ORIGIN ON THE
TRUNNION AXIS, so the prefab entity turns it for elevation), galleass_<gun>_quoin.fbx (slides along y),
galleass_<gun>_lashing.fbx (cascabel lashing, hidden in action), each with _lod1.._lod3; galleass_<gun>_fuse.fbx
(origin on the trunnion axis too: a child of the barrel, hidden after a shot), bo_galleass_<gun>.fbx (2 convex
pieces: carriage, barrel; physics material 'wood'). galleass_shot.fbx: the add-on's round shot.
"""
import bpy, bmesh, math, os, sys
from mathutils import Matrix, Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gun_uv

out = sys.argv[sys.argv.index('--') + 1]
os.makedirs(out, exist_ok=True)

KIT_MAT = {'galleass_gun_bronze': 'galleass_gun_bronze', 'galleass_gun_bronze_trim': 'galleass_gun_bronze', 'galleass_gun_wood': 'galleass_trim',
           'galleass_gun_fuse': 'galleass_trim', 'galleass_gun_iron': 'galleass_iron', 'galleass_gun_rope': 'galleass_rope', 'galleass_gun_dark': 'galleass_dark'}
UV_S = {'galleass_iron': 0.5, 'galleass_trim': 0.135, 'galleass_dark': 0.135}   # as the hull
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
    uniq = []                                                  # one slot per Kit material (bronze + bronze_trim)
    for m in me.materials:
        if m not in uniq: uniq.append(m)
    idx = [uniq.index(m) for m in me.materials]
    old = [p.material_index for p in me.polygons]
    me.materials.clear()
    for m in uniq: me.materials.append(m)
    for p, i in zip(me.polygons, old): p.material_index = idx[i]

def add_uvs(o):
    """Bronze: the barrel's lathe faces go into the gun's strip of the bronze atlas (gun_uv.py: unrolled round the
    bore, seam underneath), trunnions / vent boss / faces across the axis into the atlas's plain misc strip. Everything
    else per-face planar with U along the part's long direction (the hull's way). Call before remap_materials."""
    me = o.data; ah = o.get('axis_h', 0.8)
    uv = me.uv_layers.new(name='UVMap') if not me.uv_layers else me.uv_layers[0]
    for poly in me.polygons:
        mat = me.materials[poly.material_index].name
        n = poly.normal
        pts = [me.vertices[me.loops[li].vertex_index].co for li in poly.loop_indices]
        if mat == 'galleass_gun_rope':                             # lashings / breeching collar: rope_geom's UVs
            continue
        if mat == 'galleass_gun_bronze' and abs(n.y) <= 0.85:
            c = sum(pts, Vector()) / len(pts)
            a0 = math.atan2(c.x, c.z - ah)
            for li, p in zip(poly.loop_indices, pts):
                if math.hypot(p.x, p.z - ah) < 1e-4:               # cascabel tip: no angle of its own
                    p = Vector((math.sin(a0) * 1e-3, p.y, ah + math.cos(a0) * 1e-3))
                uv.data[li].uv = gun_uv.gun_barrel_uv(o.name, p.x, p.y, p.z, ref_angle=a0)
            continue
        if mat in ('galleass_gun_bronze', 'galleass_gun_bronze_trim'):
            ax = max(range(3), key=lambda i: abs(n[i]))            # project along the dominant normal axis
            i, j = [k for k in range(3) if k != ax]
            for li, p in zip(poly.loop_indices, pts):
                uv.data[li].uv = gun_uv.misc_uv(p[i], p[j] - (ah if j == 2 else 0.0))
            continue
        s = UV_S.get(KIT_MAT.get(mat, mat), 0.5)
        a = Vector((0, 1, 0))                                # grain along the gun, else across
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
        if n0 < 100:                                           # tiny parts (the quoin) stay whole
            lods.append(lo); continue
        d1 = lo.modifiers.new('flat', 'DECIMATE'); d1.decimate_type = 'DISSOLVE'
        d1.angle_limit = math.radians(2 + 3 * lvl); d1.delimit = {'MATERIAL', 'UV'}
        dg = bpy.context.evaluated_depsgraph_get()
        tmp = bpy.data.meshes.new_from_object(lo.evaluated_get(dg))
        n1 = sum(len(p.vertices) - 2 for p in tmp.polygons); bpy.data.meshes.remove(tmp)
        md = lo.modifiers.new('dec', 'DECIMATE')
        md.ratio = min(1.0, ratio * n0 / max(n1, 1))
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
        if mat == 'galleass_rope':
            continue
        key = 'barrel' if mat in ('galleass_gun_bronze', 'galleass_dark') else 'carriage'
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

PART_SUFFIX = {0: '', 1: '_barrel', 2: '_quoin', 3: '_lashing'}

def split_parts(o, base, pivot_z):
    """Separate objects per 'part' group (UVs, materials kept); the barrel's origin moves to the trunnion axis."""
    res = []
    for grp, suf in PART_SUFFIX.items():
        bm = bmesh.new(); bm.from_mesh(o.data)
        lay = bm.faces.layers.int.get('part')
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f[lay] != grp], context='FACES')
        if grp == 1:
            bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, -pivot_z))
        me = bpy.data.meshes.new(base + suf); bm.to_mesh(me); bm.free()
        used = sorted({p.material_index for p in me.polygons})  # only the slots in use (the Kit warns about the rest)
        idx = [used.index(p.material_index) for p in me.polygons]
        for i in used: me.materials.append(o.data.materials[i])
        for p, i in zip(me.polygons, idx): p.material_index = i
        x = bpy.data.objects.new(base + suf, me); bpy.context.scene.collection.objects.link(x)
        res.append(x)
    return res

import json
ELEV = {g: v['elev'] for g, v in json.load(open(os.path.join(os.path.dirname(bpy.data.filepath), 'galleass_guns.json'))).items()}

for c in bpy.data.collections:
    c.hide_viewport = False
for g in GUNS:
    o = bpy.data.objects[g]
    o.hide_set(False); o.location = (0, 0, 0)
    add_uvs(o); remap_materials(o.data)
    bo = body(o)                                               # from the whole gun at zero elevation
    o.name = g + '_whole'; o.data.name = g + '_whole'
    pz = ELEV[g]['pivot_z']
    done = [bo]
    # the guns' masters keep auto-smooth sharp edges from cannon_model; the FBX carries face smoothing
    for x in split_parts(o, g, pz):
        lods = make_lods(x)
        export(x.name, [x] + lods)
        done += [x] + lods
    f = bpy.data.objects[g + '_fuse']
    f.hide_set(False); f.location = (0, 0, 0)
    f.data.transform(Matrix.Translation((0, 0, -pz)))          # rides the barrel: same origin
    add_uvs(f); remap_materials(f.data)
    export(g + '_fuse', [f])
    export(bo.name, [bo])
    for x in done + [f]:
        x.data.name = x.name                                   # FBX geometry names = datablock names, no dots
# round shot for the gunnery add-on's shot items, one iron ball per calibre (material galleass_iron):
# culverin da 14 ~12 cm (galleass_shot, the first one), falcon da 6 ~7.6 cm, falconet ~5.3 cm (bores 12.4 / 8.0 / 5.6)
for name, r, segs in (('galleass_shot', 0.06, (16, 10)), ('galleass_shot_falcon', 0.038, (14, 9)),
                      ('galleass_shot_falconet', 0.0265, (12, 8))):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=segs[0], v_segments=segs[1], radius=r)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    me.materials.append(kit_mat('galleass_iron'))
    uv = me.uv_layers.new(name='UVMap')
    for poly in me.polygons:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (math.atan2(co.y, co.x) / (2 * math.pi) * 0.2, co.z / r * 0.12)
    col = me.color_attributes.new('Col', 'BYTE_COLOR', 'CORNER')
    for d in col.data: d.color = (1, 1, 1, 1)
    for poly in me.polygons: poly.use_smooth = True
    shot = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(shot)
    export(name, [shot])
print('guns exported to', out)
