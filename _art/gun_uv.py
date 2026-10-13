"""UV atlas of the guns' bronze (Kit material galleass_gun_bronze, textures galleass_gun_bronze_d/_n/_s), without
Blender: export_guns.py assigns the UVs with it and gun_texture.py paints the atlas with it, so both agree.

Atlas (ATLAS px square, u right, v up as in Blender/FBX):
  culverin  u 0     .. 0.5    barrel unrolled: u = angle round the bore axis (0 = top, seam underneath), v = along
  falcon    u 0.5   .. 0.875  the barrel from the cascabel to the muzzle. The falconet is the falcon scaled
                              (gun_profiles.FALCONET k_len / k_r), so it shares the falcon's strip.
  misc      u 0.875 .. 1      plain bronze for the trunnions, vent boss and the faces across the axis (muzzle face,
                              cascabel end) - planar, overlapping is fine there.
Each barrel strip is padded: the texture keeps running round the bore into the padding, so seam faces whose corners
unwrap a little past +-180 deg still sample the right metal.
"""
import math
import gun_profiles as gp

ATLAS = 4096
PAD_U = 24 / ATLAS                       # seam padding each side of a strip
PAD_V = 16 / ATLAS
REGIONS = {'culverin': (0.0, 0.5), 'falcon': (0.5, 0.875), 'misc': (0.875, 1.0)}
# barrel extent in profile y (falcon family: divided by k_len), cascabel end -> muzzle face
Y_RANGE = {'culverin': (-0.28, gp.CV['length']), 'falcon': (-0.20, gp.FALCON['length'])}
MISC_SCALE = 0.1                          # UV per metre in the misc strip

def _gun_table():
    t = {'galleass_culverin': ('culverin', gp.CV['trunnion_y'], 1.0, 1.0, gp.AXIS_H)}
    for name, sp in (('galleass_falcon', gp.FALCON), ('galleass_falconet', gp.FALCONET)):
        _, ty, _ = gp.falcon_profile(sp)
        t[name] = ('falcon', ty, sp['k_len'], sp['k_r'], sp['axis_h'])
    return t

GUNS = _gun_table()                       # name -> (strip, trunnion y in profile coords, k_len, k_r, axis height)

def strip_uv(strip, angle, y_norm):
    """Barrel strip: angle in radians (0 = top, +x side positive; may run past +-pi on seam faces), y_norm in the
    strip's profile coordinates."""
    u0, u1 = REGIONS[strip]
    y0, y1 = Y_RANGE[strip]
    u = u0 + PAD_U + (u1 - u0 - 2 * PAD_U) * (0.5 + angle / (2 * math.pi))
    v = PAD_V + (1 - 2 * PAD_V) * (y_norm - y0) / (y1 - y0)
    return u, v

def strip_inverse(strip, u, v):
    """Atlas (u, v) inside a strip -> (angle, y_norm); the angle runs on through the padding (periodic texture)."""
    u0, u1 = REGIONS[strip]
    y0, y1 = Y_RANGE[strip]
    angle = ((u - u0 - PAD_U) / (u1 - u0 - 2 * PAD_U) - 0.5) * 2 * math.pi
    y = y0 + (v - PAD_V) / (1 - 2 * PAD_V) * (y1 - y0)
    return angle, y

def gun_barrel_uv(gun, x, y, z, ref_angle=None):
    """UV of a barrel vertex in the gun's exported frame (trunnions at y 0, axis at z = axis height). ref_angle:
    the face's centre angle - the vertex angle is unwrapped next to it so a face never spans the seam."""
    strip, ty, kl, _, ah = GUNS[gun]
    a = math.atan2(x, z - ah)
    if ref_angle is not None:
        while a - ref_angle > math.pi: a -= 2 * math.pi
        while a - ref_angle < -math.pi: a += 2 * math.pi
    return strip_uv(strip, a, (y + ty) / kl)

def misc_uv(a, b):
    """Planar coordinates (metres) -> the misc strip (clamped inside it; the strip is plain bronze)."""
    u0, u1 = REGIONS['misc']
    cu, hw = (u0 + u1) / 2, (u1 - u0) / 2 - PAD_U
    hv = 0.5 - PAD_V
    return (cu + max(-hw, min(hw, a * MISC_SCALE)), 0.5 + max(-hv, min(hv, b * MISC_SCALE)))
