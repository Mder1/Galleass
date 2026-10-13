"""Preview: the 24 guns (cannon_model.py output) placed at their ports in the galleass model, review renders.
Placement only for checking fit; the prefab places the real guns later.

    blender -b ref/galleass_model.blend --python gun_preview.py -- ref/galleass_guns.blend <render dir> [<out.blend>]

With <out.blend> the ship with the placed guns is saved there (visualization only, not used by the pipeline).

Guns stand run out: muzzle where the gun's axis leaves the port's outer face. Final list (user 2026-10-13):
3 culverins (forecastle ground floor), 9 falconets (platform 5, cabin sides 2, cabin stern 2), 12 falcons
(broadside 10, stern chasers 2).
"""
import bpy, math, os, sys
from mathutils import Vector
argv = sys.argv[sys.argv.index('--') + 1:]
GUNS_BLEND, OUT = argv[0], argv[1]
SAVE = argv[2] if len(argv) > 2 else None
os.makedirs(OUT, exist_ok=True)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model_geom
G = model_geom.load()
LIFT = G['Z_LIFT']

with bpy.data.libraries.load(GUNS_BLEND, link=False) as (src, dst):
    dst.objects = [n for n in src.objects if n.startswith('galleass_')]
GUN = {o.name: o for o in dst.objects}
coll = bpy.data.collections.new('gun_preview'); bpy.context.scene.collection.children.link(coll)

import gun_layout
placed = []
for g in gun_layout.placements(G, gun_layout.load_dims()):
    src = GUN['galleass_' + g['kind']]
    o = bpy.data.objects.new(g['name'], src.data); coll.objects.link(o)
    o.location = g['pos']; o.rotation_euler = (0, 0, g['rot_z'])
    fz = GUN.get(src.name + '_fuse')                # the priming fuse is its own object (same origin)
    if fz:
        f = bpy.data.objects.new(g['name'] + '_fuse', fz.data); coll.objects.link(f)
        f.location = o.location; f.rotation_euler = o.rotation_euler
    placed.append(o)
print('placed %d guns' % len(placed))
if SAVE:
    bpy.ops.wm.save_as_mainfile(filepath=SAVE, copy=True)
    print('saved', SAVE)

# renders (hide the masters, the markers and the faction paint overlay)
for o in GUN.values(): o.hide_render = True
sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.color_type = 'MATERIAL'
sc.display.shading.show_cavity = True; sc.display.shading.show_shadows = True
for o in bpy.data.objects:
    if o.type == 'MESH' and o.name in ('galleass_faction_paint', 'galleass_hull_plate'):
        o.hide_render = True
cam = bpy.data.objects.new('pv_cam', bpy.data.cameras.new('pv_cam')); sc.collection.objects.link(cam); sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
hidden = []
def shot(fname, loc, tgt, lens=30, hide=()):
    for o in hidden: o.hide_render = False
    hidden.clear()
    for o in bpy.data.objects:
        if o.type == 'MESH' and any(o.name.startswith(h) for h in hide) and not o.hide_render:
            o.hide_render = True; hidden.append(o)
    cam.location = loc; cam.data.lens = lens
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(OUT, fname); bpy.ops.render.render(write_still=True)

zfc, zgd = G['FC_Z_PLATFORM'] + LIFT, G['Z_GUN_DECK'] + LIFT
shot('pv_fc_platform.png', (0.0, 15.5, zfc + 5.5), (0.0, 21.5, zfc), lens=28)
shot('pv_fc_lower.png', (1.3, 16.2, zgd + 1.9), (0.0, 23.0, zgd + 0.5), lens=22)
shot('pv_cabin.png', (0.0, -16.0, zgd + 2.0), (0.0, -22.5, zgd + 0.4), lens=20)
shot('pv_fc_bow_out.png', (9.0, 33.0, zgd + 2.5), (0.0, 23.0, zgd + 1.5), lens=35)
shot('pv_waist.png', (0.0, -9.0, zgd + 6.5), (0.0, 2.0, zgd), lens=24)
shot('pv_stern_out.png', (-10.0, -34.0, zgd + 5.0), (0.0, -20.0, zgd + 1.0), lens=30)
shot('pv_top.png', (0.0, 0.0, 95.0), (0.0, 0.001, 0.0), lens=35)
print('preview done')
