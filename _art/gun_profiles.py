"""Barrel profiles and surface reliefs of the galleass guns, without Blender: shared by cannon_model.py (meshes) and
gun_texture.py (the bronze texture atlas has to know the same radii, flutes and decoration zones).
Profiles are (y, r) with y from the rear face of the base ring forward (cascabel at negative y)."""
import math

AXIS_H = 0.80

# ---------------------------------------------------------------- culverin (colubrina da 14 libbre)
# 14 Venetian pounds (libbra grossa 0.477 kg) of iron = 6.7 kg ball, 12.0 cm; bore 12.4 cm. Bore ~32 calibres
# (Museo Storico Navale), so 4.05 m from the base ring to the muzzle; the ground floor takes it with 1 m recoil
# (fc_gun_layout.py, layout_H). Trunnions at 0.44 of the length, on a raised ring (Alberghetti drawings).
CV = dict(
    bore=0.124,
    length=4.05,                      # base ring rear face -> muzzle face
    trunnion_y=0.44 * 4.05,
    trunnion_r=0.062, trunnion_len=0.12, trunnion_dz=-0.01,
    flutes=16, flute_depth=0.006,
    # spiral on the first reinforce: dominant in the plates - 12 broad ribs, ~30 deg twist (0.75 turns), deep grooves
    spiral_ribs=12, spiral_depth=0.016, spiral_turns=0.75,
    # slender like the plates: ~3 calibres over the breech, ~2 at the muzzle (length / breech diameter ~11)
    r_breech=0.190, r_reinforce_end=0.172, r_ring=0.186, r_chase_start=0.164, r_chase_end=0.124,
)

def culverin_profile():
    L, ty = CV['length'], CV['trunnion_y']
    rb, rt, rc, rm = CV['r_breech'], CV['r_reinforce_end'], CV['r_chase_start'], CV['r_chase_end']
    rr = CV['r_ring']
    return [
        # cascabel: pear-shaped button on a neck, then the rounded breech (Gasparoni plates)
        (-0.28, 0.0), (-0.28, 0.016), (-0.273, 0.030), (-0.258, 0.041), (-0.235, 0.047), (-0.21, 0.048),
        (-0.188, 0.043), (-0.17, 0.034), (-0.156, 0.030), (-0.143, 0.032), (-0.134, 0.041), (-0.125, 0.041),
        (-0.116, 0.055), (-0.093, 0.103), (-0.065, 0.145), (-0.035, 0.175), (-0.014, 0.190), (0.0, rb + 0.004),
        # base ring: broad fillet, step, small astragal
        (0.0, rb + 0.016), (0.042, rb + 0.016), (0.047, rb + 0.009), (0.07, rb + 0.009), (0.078, rb + 0.004),
        (0.094, rb + 0.004), (0.099, rb),
        # first reinforce (fluted) up to the trunnion ring
        (ty - 0.10, rt),
        (ty - 0.095, rr - 0.008), (ty - 0.07, rr - 0.008), (ty - 0.065, rr), (ty + 0.065, rr), (ty + 0.07, rr - 0.008),
        (ty + 0.095, rr - 0.008), (ty + 0.10, rc),
        # chase (fluted, plain band for the arms / inscription) to the muzzle astragal
        (L - 0.25, rm),
        (L - 0.245, rm + 0.010), (L - 0.218, rm + 0.010), (L - 0.213, rm + 0.003), (L - 0.195, rm + 0.001),
        # muzzle: gentle swell (acanthus leaves) and lip
        (L - 0.14, rm + 0.006), (L - 0.08, rm + 0.014), (L - 0.045, rm + 0.022), (L - 0.03, rm + 0.026),
        (L - 0.026, rm + 0.030), (L, rm + 0.030), (L, CV['bore'] / 2 + 0.012), (L - 0.008, CV['bore'] / 2),
    ]

def smooth01(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)

def flute_cut(y, a, y0, y1, n, depth, turns=0.0, fade=0.035):
    """Concave flutes between y0 and y1 (rounded ends), optionally spiralling 'turns' times over the zone."""
    if y <= y0 or y >= y1:
        return 0.0
    u = (a / (2 * math.pi) + turns * (y - y0) / (y1 - y0)) * n
    u -= math.floor(u)
    land = 0.22                                            # fillet between the flutes, fraction of a pitch
    if u > 1 - land:
        return 0.0
    s = math.sin(math.pi * u / (1 - land))
    return depth * s ** 0.8 * smooth01((y - y0) / fade) * smooth01((y1 - y) / fade)

def spiral_ribs(y, a, y0, y1, n, depth, turns, fade=0.05):
    """Twisted convex ribs (rope-like spiral fluting of the colubrina da 30): broad rounded ribs, narrow deep
    grooves between them; returns the cut below the profile radius (0 on the rib crests)."""
    if y <= y0 or y >= y1:
        return 0.0
    u = (a / (2 * math.pi) + turns * (y - y0) / (y1 - y0)) * n
    u -= math.floor(u)
    rib = math.sin(math.pi * u) ** 0.6                  # 1 on the crest, 0 in the groove
    return depth * (1 - rib) * smooth01((y - y0) / fade) * smooth01((y1 - y) / fade)

def acanthus(y, a, y0, y1, n=8, height=0.009):
    """Raised leaves rising up the muzzle flare: wide at the neck, pointed tips."""
    if y <= y0 or y >= y1:
        return 0.0
    t = (y - y0) / (y1 - y0)
    u = a / (2 * math.pi) * n
    u = u - math.floor(u) - 0.5                            # -0.5..0.5 around a leaf's centre line
    hw = 0.42 * (1 - t) ** 0.8 + 0.03
    if abs(u) >= hw:
        return 0.0
    lobe = math.cos(math.pi / 2 * u / hw)
    return height * lobe * math.sin(math.pi * min(t * 1.15, 1.0)) ** 0.6

def culverin_mod(y, a, r):
    L, ty = CV['length'], CV['trunnion_y']
    if 0.16 < y < ty - 0.12:                               # first reinforce: spiral ribs (colubrina da 30, lower)
        r -= spiral_ribs(y, a, 0.16, ty - 0.12, CV['spiral_ribs'], CV['spiral_depth'], CV['spiral_turns'])
    elif ty + 0.12 < y < L - 0.29:                         # chase: straight flutes, plain band for the arms
        band0, band1 = ty + 0.62, ty + 1.02
        r -= flute_cut(y, a, ty + 0.12, band0, CV['flutes'], CV['flute_depth'] * 0.85)
        r -= flute_cut(y, a, band1, L - 0.29, CV['flutes'], CV['flute_depth'] * 0.85)
    elif L - 0.19 < y < L - 0.035:
        r += acanthus(y, a, L - 0.19, L - 0.035, height=0.007)
    return r

# ---------------------------------------------------------------- falcon / falconet (two-wheel carriage)
# Plain service pieces after the Alberghetti drawings (user's reference 1, piece 1: ~2.85 m overall, trunnions at
# ~47 % from the cascabel, one raised ring, plain chase, short muzzle band, conical cascabel button). Arms, founder's
# initials (Z.A) and date go into the texture. Falcon da 6 (libbra sottile, ~1.8 kg ball): bore 8 cm, for the
# broadside / stern / cabin ports (centred 0.85 m above the deck); the falconet is the same design scaled to fit the
# forecastle platform and the cabin (layout_G: <= 2.2 m muzzle -> trail); axis 0.80 suits both the platform
# embrasures (0.4..1.1 above the floor) and the cabin's gunports (0.55..1.15).
FALCON = dict(bore=0.080, length=2.65, axis_h=0.85, k_len=1.0, k_r=1.0, wheel_r=0.36)
FALCONET = dict(bore=0.056, length=1.62, axis_h=0.80, k_len=1.62 / 2.65, k_r=0.70, wheel_r=0.30)

def falcon_profile(sp):
    L, kl, kr = sp['length'], sp['k_len'], sp['k_r']
    ty = 0.43 * L
    rb, rt, rr, rc, rm = 0.112 * kr, 0.100 * kr, 0.110 * kr, 0.094 * kr, 0.072 * kr
    def Y(v): return v * kl                                       # fixed details (fillets, button) scale with length
    def R(v): return v * kr
    prof = [
        # conical cascabel button with a fillet, short neck, rounded breech
        (Y(-0.20), 0.0), (Y(-0.20), R(0.026)), (Y(-0.194), R(0.032)), (Y(-0.118), R(0.050)), (Y(-0.112), R(0.054)),
        (Y(-0.104), R(0.054)), (Y(-0.100), R(0.046)), (Y(-0.090), R(0.046)),
        (Y(-0.080), R(0.064)), (Y(-0.058), R(0.086)), (Y(-0.034), R(0.101)), (Y(-0.013), R(0.110)), (0.0, rb + R(0.004)),
        # base ring: flared fillet + step + astragal
        (0.0, rb + R(0.015)), (Y(0.032), rb + R(0.015)), (Y(0.037), rb + R(0.009)), (Y(0.060), rb + R(0.009)),
        (Y(0.065), rb + R(0.004)), (Y(0.076), rb + R(0.004)), (Y(0.080), rb),
        # reinforce to the trunnion ring
        (ty - Y(0.075), rt), (ty - Y(0.070), rr - R(0.006)), (ty - Y(0.050), rr - R(0.006)), (ty - Y(0.046), rr),
        (ty + Y(0.046), rr), (ty + Y(0.050), rr - R(0.006)), (ty + Y(0.070), rr - R(0.006)), (ty + Y(0.075), rc),
        # plain chase, muzzle astragal, slight swell, muzzle band
        (L - Y(0.17), rm), (L - Y(0.165), rm + R(0.008)), (L - Y(0.145), rm + R(0.008)), (L - Y(0.140), rm + R(0.003)),
        (L - Y(0.10), rm + R(0.004)), (L - Y(0.07), rm + R(0.008)), (L - Y(0.066), rm + R(0.017)),
        (L - Y(0.012), rm + R(0.017)), (L - Y(0.006), rm + R(0.012)), (L, rm + R(0.012)),
        (L, sp['bore'] / 2 + R(0.008)), (L - 0.006, sp['bore'] / 2),
    ]
    return prof, ty, dict(rb=rb, rr=rr, cascabel=Y(-0.20))
