"""Elevation check: every gun split into its moving parts (cannon_model.py's face attribute 'part'), the barrel turned
on its trunnions and the quoin slid as the add-on will (ref/galleass_guns.json 'elev'), side views at the lowest,
zero and highest elevation -> <render dir>/elev_<gun>.png (three rows, close-up of the breech on the right).

    blender -b ref/galleass_guns.blend --python elev_preview.py -- renders/guns
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Matrix, Vector

out = sys.argv[sys.argv.index('--') + 1]
os.makedirs(out, exist_ok=True)
info = json.load(open(os.path.join(os.path.dirname(bpy.data.filepath), 'galleass_guns.json')))
GUNS = ['galleass_culverin', 'galleass_falcon', 'galleass_falconet']
sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'MATERIAL'
sc.render.resolution_x, sc.render.resolution_y = 1600, 700

def split(o):
    """{group: object} copies of o, one per 'part' value."""
    res = {}
    for grp in range(4):
        bm = bmesh.new(); bm.from_mesh(o.data)
        lay = bm.faces.layers.int.get('part')
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f[lay] != grp], context='FACES')
        if not bm.faces:
            bm.free(); continue
        me = bpy.data.meshes.new(f'{o.name}_p{grp}'); bm.to_mesh(me); bm.free()
        for m in o.data.materials: me.materials.append(m)
        x = bpy.data.objects.new(me.name, me); sc.collection.objects.link(x)
        res[grp] = x
    return res

def pose(parts, fuse, el, deg):
    pz = el['pivot_z']
    slide = interp(el['quoin'], deg)
    rot = Matrix.Translation((0, 0, pz)) @ Matrix.Rotation(math.radians(deg), 4, 'X') @ Matrix.Translation((0, 0, -pz))
    parts[1].matrix_world = rot
    if fuse: fuse.matrix_world = rot
    if 2 in parts: parts[2].matrix_world = Matrix.Translation((0, -slide, 0))

def interp(table, deg):
    for (e0, d0), (e1, d1) in zip(table, table[1:]):
        if e0 <= deg <= e1:
            return d0 + (d1 - d0) * (deg - e0) / (e1 - e0)
    return table[0][1] if deg < table[0][0] else table[-1][1]

cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = 'ORTHO'
for g in GUNS:
    o = bpy.data.objects[g]; el = info[g]['elev']
    for x in bpy.data.objects:
        x.hide_render = True
    parts = split(o)
    fuse = bpy.data.objects.get(g + '_fuse')
    for x in list(parts.values()) + ([fuse] if fuse else []):
        x.hide_render = False
    cam.hide_render = False
    frames = []
    for deg in (el['min_deg'], 0.0, el['max_deg']):
        pose(parts, fuse, el, deg)
        for name, (loc, scale) in (('full', ((-1.0, info[g]['cascabel_y'] * 0.5 + 0.4, 0.6), 4.8)),
                                    ('breech', ((-1.0, info[g]['cascabel_y'] + 0.4, 0.55), 1.4))):
            cam.location = Vector(loc) + Vector((-4, 0, 0)) * 0 + Vector((-5, 0, 0))
            cam.location.y = loc[1]; cam.location.z = loc[2]
            cam.rotation_euler = (math.pi / 2, 0, -math.pi / 2)
            cam.data.ortho_scale = scale
            path = os.path.join(out, f'_elev_{g}_{deg:+.1f}_{name}.png')
            sc.render.filepath = path; bpy.ops.render.render(write_still=True)
            frames.append(path)
    for x in parts.values():
        bpy.data.objects.remove(x)
    print('ELEV', g, el['min_deg'], el['max_deg'], 'slides', el['quoin'][0][1], el['quoin'][-1][1])
print('elev preview done')
