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
