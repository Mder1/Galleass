"""Dimensions of the galleass masts (mast_model.py) without Blender, shared with build_prefab.py (the tie runs from
the calcese's sheave). Mast-local frame = the vanilla mast_mesh frame: z up from the heel, the yard hangs on +x."""
Z_HEEL = -0.484
# vanilla profiles (ref/rig/*.obj): heel radius, masthead radius, masthead z; yard roll pivot (tie) height; deck
# crossing in mast-local z (main + mizzen: gun deck 3.8, fore: forecastle platform 5.4, against the rig frames)
MASTS = {
    'large':  dict(r0=0.278, r1=0.224, top=32.604, yard=24.735, deck=3.56, gabbia=True),
    'medium': dict(r0=0.241, r1=0.208, top=24.988, yard=18.304, deck=0.59, gabbia=False),
    'small':  dict(r0=0.248, r1=0.212, top=22.492, yard=16.968, deck=3.71, gabbia=False),
}

def rad(sp, z):
    t = (z - Z_HEEL) / (sp['top'] - Z_HEEL)
    return sp['r0'] + (sp['r1'] - sp['r0']) * t

def calcese_span(sp):
    """(z0, z1) of the calcese block."""
    if sp['gabbia']:
        return sp['yard'] + 2.6, sp['yard'] + 4.3
    z1 = sp['top'] - 0.25
    return z1 - 1.9, z1

def calcese_half(sp):
    """Half widths (x athwartships, y fore-and-aft) of the calcese."""
    r = rad(sp, calcese_span(sp)[1])
    return r * 1.18, r * 1.55

SHEAVE_DZ = (0.30, 0.74)                 # sheave centres as fractions of the calcese height

def sheaves(sp):
    z0, z1 = calcese_span(sp)
    return [z0 + f * (z1 - z0) for f in SHEAVE_DZ]

# flag halyard (vanilla flag_capture_rope): its lower end comes down to the deck beside the mast foot, where
# standing_rig.py lays its hauling end in a heap (user 2026-10-13: it ended in mid-air on a coil 2.4 m up the mast).
# Mast-local (x, y) at the deck; main/mizzen on the starboard quarter (tie tackle to port aft, lanterns at +-x 0.75
# up at deck + 3.2), fore to starboard (lantern aft, tie tackle forward to port)
HALYARD_FOOT = {'large': (0.55, -0.55), 'medium': (0.65, -0.15), 'small': (0.55, -0.55)}
HALYARD_DZ = 0.10                        # the rope's end above the deck, where the heap begins

# spritsail (re-rig phase 4, user 2026-10-19: a working sail, vanilla's small square rig scaled to the drawing). The
# bowsprit (ship frame) runs out through the forecastle parapet where the centre falconet's embrasure was (user
# 2026-10-19: that gun goes, its port becomes a hole that just takes the spar), its heel stepped on a chock on the
# platform behind it; it rises at SPRIT_RISE over the spur, the yard hanging under it at SPRIT_SLING_Y
SPRIT_WALL = (0.0, 25.275, 7.05)         # the axis in the middle of the parapet wall (old embrasure 6.7..7.4)
SPRIT_RISE = 0.4363                      # 25 deg: the fore lateen yard's lower end (fore and aft, yaw ~85) clears it
                                         # by 1.45 m, axis to axis (30 deg: 0.68)
SPRIT_HEEL_Z = 6.65                      # heel axis: platform 6.3 + chock 0.15 + spar radius
SPRIT_HEEL = (0.0, SPRIT_WALL[1] - (SPRIT_WALL[2] - SPRIT_HEEL_Z) / __import__('math').tan(SPRIT_RISE), SPRIT_HEEL_Z)
SPRIT_CHOCK = (0.28, 0.35, 0.15)         # step chock on the platform (half x, half y, height)
SPRIT_LEN = 11.7                         # end at y ~35
SPRIT_R0, SPRIT_R1 = 0.20, 0.13          # heel / end radius
SPRIT_HOLE = 0.02                        # the parapet's hole: spar radius + this (galleass_model.py)
SPRIT_SLING_Y = 33.0
SPRIT_YARD_DROP = 0.6
SPRIT_SCALE = 0.58                       # of sail_square_small_nested (15.4 m yard, ~15 x 9 m sail): 8.9 m
                                         # yard, sail foot ~4.7 (spur tip 3.07)
# belaying pin through the spar near its end (the braces' / sheets' forward legs; knot points at its ends)
SPRIT_PIN_BACK, SPRIT_PIN_DROP, SPRIT_PIN_X, SPRIT_PIN_HALF = 0.6, 0.12, 0.18, 0.27

def sprit_point(y):
    """The bowsprit's axis at ship y."""
    import math
    x0, y0, z0 = SPRIT_HEEL
    return (x0, y, z0 + (y - y0) * math.tan(SPRIT_RISE))

def sprit_tip():
    import math
    x0, y0, z0 = SPRIT_HEEL
    return (x0, y0 + SPRIT_LEN * math.cos(SPRIT_RISE), z0 + SPRIT_LEN * math.sin(SPRIT_RISE))

def sprit_pins():
    """The knot points on the two ends of the bowsprit's belaying pin (ship frame): two a side, as a square sail's
    brace wants two knots on its own side (fixed and free leg)."""
    y = sprit_tip()[1] - SPRIT_PIN_BACK
    z = sprit_point(y)[2] - SPRIT_PIN_DROP
    return [(s * x, y, z) for s in (-1, 1) for x in (SPRIT_PIN_X, SPRIT_PIN_HALF - 0.02)]
