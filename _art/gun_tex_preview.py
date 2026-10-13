"""Check renders of the textured guns straight from the exported FBXs (so the UVs are the ones the Kit gets).

    blender -b --factory-startup --python gun_tex_preview.py -- <fbx + texture dir> <render dir>

Bronze = Principled BSDF with galleass_gun_bronze_d/_n/_s (spec: R ~ metallic, G ~ gloss, as an approximation of
the game's pbr_metallic); other materials flat colours. Cycles, CPU.
"""
import bpy, math, os, sys
from mathutils import Vector

src, out = sys.argv[sys.argv.index('--') + 1:][:2]
os.makedirs(out, exist_ok=True)
for o in list(bpy.data.objects): bpy.data.objects.remove(o)

def img(name, non_color):
    im = bpy.data.images.load(os.path.join(src, name), check_existing=True)
    if non_color: im.colorspace_settings.name = 'Non-Color'
    return im

def bronze_material():
    m = bpy.data.materials.new('bronze_preview'); m.use_nodes = True
    nt = m.node_tree; bs = nt.nodes['Principled BSDF']
    td = nt.nodes.new('ShaderNodeTexImage'); td.image = img('galleass_gun_bronze_d.png', False)
    tn = nt.nodes.new('ShaderNodeTexImage'); tn.image = img('galleass_gun_bronze_n.png', True)
    ts = nt.nodes.new('ShaderNodeTexImage'); ts.image = img('galleass_gun_bronze_s.png', True)
    nm = nt.nodes.new('ShaderNodeNormalMap'); nt.links.new(tn.outputs['Color'], nm.inputs['Color'])
    nt.links.new(nm.outputs['Normal'], bs.inputs['Normal'])
    # vanilla diffuse is dark and desaturated; the game's gilt factor brightens it - approximate with a tint
    mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
    mix.inputs['Factor'].default_value = 1.0; mix.inputs['B'].default_value = (1.6, 1.25, 0.8, 1)
    nt.links.new(td.outputs['Color'], mix.inputs['A']); nt.links.new(mix.outputs['Result'], bs.inputs['Base Color'])
    sep = nt.nodes.new('ShaderNodeSeparateColor'); nt.links.new(ts.outputs['Color'], sep.inputs['Color'])
    nt.links.new(sep.outputs['Red'], bs.inputs['Metallic'])
    inv = nt.nodes.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 0.85
    nt.links.new(sep.outputs['Green'], inv.inputs[1]); nt.links.new(inv.outputs[0], bs.inputs['Roughness'])
    return m

FLAT = {'galleass_rope': (0.55, 0.45, 0.32, 1), 'galleass_trim': (0.30, 0.20, 0.12, 1), 'galleass_iron': (0.08, 0.08, 0.09, 1), 'galleass_dark': (0.01, 0.01, 0.01, 1)}
bronze = bronze_material()
guns = {}
for g in ('galleass_culverin', 'galleass_falcon', 'galleass_falconet'):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=os.path.join(src, g + '.fbx'))
    for o in set(bpy.data.objects) - before:
        if '_lod' in o.name:
            bpy.data.objects.remove(o); continue
        guns[g] = o
        for i, m in enumerate(o.data.materials):
            if m.name.startswith('galleass_gun_bronze'):
                o.data.materials[i] = bronze
            else:
                m.use_nodes = True
                m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = FLAT.get(m.name.split('.')[0], (0.5, 0.5, 0.5, 1))

sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 48; sc.cycles.use_denoising = True
sc.world = bpy.data.worlds.new('w'); sc.world.use_nodes = True
sc.world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.55, 0.6, 0.7, 1)
sc.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.6
sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); sc.collection.objects.link(sun)
sun.data.energy = 4.0; sun.rotation_euler = (math.radians(40), math.radians(-25), math.radians(30))
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam

def shot(fname, loc, tgt, lens, res=(1400, 900)):
    sc.render.resolution_x, sc.render.resolution_y = res
    cam.location = loc; cam.data.lens = lens
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(out, fname)
    bpy.ops.render.render(write_still=True)

def only(g):
    for k, o in guns.items(): o.hide_render = k != g

# frames: trunnions at y 0; profile y = final y + trunnion y
only('galleass_culverin'); ty = 1.782; ah = 0.8
shot('tx_cv_lion.png', (0.0, 2.62 - ty - 0.35, ah + 0.75), (0.0, 2.62 - ty, ah), 60)
shot('tx_cv_lion_side.png', (0.55, 2.62 - ty - 0.25, ah + 0.45), (0.0, 2.62 - ty, ah + 0.05), 55)
shot('tx_cv_breech.png', (0.25, -ty - 0.55, ah + 0.55), (0.0, 0.03 - ty, ah + 0.1), 50)
shot('tx_cv_trunnion.png', (0.75, -0.45, ah + 0.45), (0.27, 0.0, ah - 0.05), 50)
shot('tx_cv_full.png', (2.2, 1.6, 1.8), (0.0, 0.2, 0.7), 32)
only('galleass_falcon'); ty = 1.1395; ah = 0.85
shot('tx_fa_cart.png', (0.0, 1.57 - ty - 0.3, ah + 0.55), (0.0, 1.57 - ty, ah), 60)
shot('tx_fa_breech.png', (0.2, -ty - 0.45, ah + 0.5), (0.0, 0.15 - ty, ah + 0.05), 50)
shot('tx_fa_trunnion.png', (0.6, -0.4, ah + 0.35), (0.25, 0.0, ah - 0.05), 50)
shot('tx_fa_full.png', (1.6, 1.2, 1.4), (0.0, 0.0, 0.6), 32)
only('galleass_falconet'); ty = 0.6966; ah = 0.80
shot('tx_ft_trunnion.png', (0.45, -0.3, ah + 0.28), (0.2, 0.0, ah - 0.05), 50)
shot('tx_ft_full.png', (1.1, 0.8, 1.1), (0.0, 0.0, 0.6), 32)
print('previews in', out)
