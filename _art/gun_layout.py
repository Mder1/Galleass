"""Gun positions on the galleass, shared by gun_preview.py (Blender) and build_prefab.py (prefab).

Final list (user 2026-10-13): 3 culverins (forecastle ground floor), 9 falconets (platform 5, cabin sides 2, cabin
stern 2), 12 falcons (broadside 10, stern chasers 2). Guns stand run out: the muzzle where the gun's axis leaves the
port's outer face. Gun dimensions (muzzle_y = muzzle ahead of the gun's origin) come from cannon_model.py's
ref/galleass_guns.json.
"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))

def load_dims(path=os.path.join(HERE, 'ref', 'galleass_guns.json')):
    return json.load(open(path))

def placements(G, dims):
    """[{'kind', 'name', 'pos' (x, y, z; z LIFTED, on the floor), 'heading' (deg, 0 = +y, + = starboard),
    'rot_z' (rad, Blender/prefab yaw)}]"""
    LIFT = G['Z_LIFT']
    out = []
    def add(kind, name, mx, my, z_floor, heading):
        h = math.radians(heading)
        m = dims['galleass_' + kind]['muzzle_y']
        out.append({'kind': kind, 'name': name, 'heading': heading, 'rot_z': -h,
                    'pos': (mx - math.sin(h) * m, my - math.cos(h) * m, z_floor + LIFT)})
    R = G['fc_radius'](G['FC_Z_PLATFORM'])
    for deg, hd in G['FC_LOWER_PORTS']:                      # forecastle ground floor, round ports
        x, y = G['fc_point'](deg, R)
        add('culverin', 'cv_%+d' % deg, x, y, G['Z_GUN_DECK'], hd)
    for deg in G['FC_GUN_DEGS']:                             # platform embrasures (side ones 0.6 m aft)
        x, y = G['fc_point'](deg, R, back=0.6)
        add('falconet', 'ft_fc_%+d' % deg, x, y, G['FC_Z_PLATFORM'], deg)
    for i in range(G['GUNPORTS_PER_SIDE']):                  # broadside
        for s in (-1, 1):
            add('falcon', 'fa_bs_%d_%+d' % (i, s), s * G['WING_HW'], G['gunport_y'](i), G['Z_GUN_DECK'], s * 90)
    for s in (-1, 1):                                        # stern chasers in the box's aft end walls
        add('falcon', 'fa_stern_%+d' % s, s * G['STERN_GP_X'], G['WING_Y0'], G['Z_GUN_DECK'], 180)
    for s in (-1, 1):                                        # cabin: side ports (tapering wall's normal), stern ports
        y = G['SC_GP_Y']; hw = G['sc_hw']
        slope = (hw(y + 0.05) - hw(y - 0.05)) / 0.1
        add('falconet', 'ft_cabin_%+d' % s, s * hw(y), y, G['Z_GUN_DECK'], math.degrees(math.atan2(s * 1.0, -slope)))
        add('falconet', 'ft_cabin_stern_%+d' % s, s * G['SC_AGP_X'], G['SC_Y_AFT'], G['Z_GUN_DECK'], 180)
    return out

# ---------------------------------------------------------------- swivel guns (petriere da mascolo, user 2026-10-17)
# Kept apart from placements(): they sit on the rails, not at ports, and have their own pipeline (swivel_layout.py).
# 10 swivels: 3 a side on the waist bulwark's cap rail, between the falcon ports, each with a wooden step for the gunner (the rail top is 1.5 m above the gun deck); 2 a side on the poop
# balustrade, between its big posts and the awning posts (y -17.24 / -19.69 / -21.93).
# (2026-10-17 swivel_layout.py scan: the other gaps hold the banner holders (-6.08 / 10.18 on the rail) or the steps
# meet the falcons' tackle heaps / the main and fore shroud tackles)
SWIVEL_WAIST_Y = (-12.0, 5.0, 10.85)
SWIVEL_IN = 0.15                                   # pin inboard of the waist bulwark's outer face (cap rail 0.4 wide)
# poop (user 2026-10-17: the turned balustrade is too frail for a gun): each swivel on its own timber stand (post + foot,
# cannon_model.build_petriera_stand) set INTO the balustrade in place of two balusters (galleass_model
# POOP_SWIVEL_GAPS), its top level with the rail
STAND_H = 1.03                                     # stand top above the poop deck = the rail's top (square sweep r 0.07)
STEP_H = 0.30                                      # gunner's step (two treads)

def swivel_poop_y(G):
    """y of the poop stands: midway between the two balusters each replaces."""
    return tuple((G['poop_baluster_y'](g) + G['poop_baluster_y'](g + 1)) / 2 for g in sorted(G['POOP_SWIVEL_GAPS'], reverse=True))

def swivel_placements(G, waist_y=SWIVEL_WAIST_Y, poop_y=None):
    """[{'kind': 'petriera', 'name', 'pos' (rail / stand top under the pin, LIFTED), 'heading', 'rot_z', 'deck_z',
    'step' (bool: waist gunner's step), 'stand' (bool: poop timber stand)}]; heading 0 = +y, + = starboard, outward normal of the rail."""
    LIFT = G['Z_LIFT']
    out = []
    def add(name, x, y, z, heading, deck_z, step):
        out.append({'kind': 'petriera', 'name': name, 'heading': heading, 'rot_z': -math.radians(heading),
                    'pos': (x, y, z + LIFT), 'deck_z': deck_z + LIFT, 'step': step, 'stand': not step})
    z_cap = G['BANDS']['cap_rail'][1]
    for i, y in enumerate(waist_y):
        for s in (-1, 1):
            add('pe_waist_%d_%+d' % (i, s), s * (G['WING_HW'] - SWIVEL_IN), y, z_cap, s * 90.0, G['Z_GUN_DECK'], True)
    z_rail = G['SC_Z_FLOOR'] + 0.12 + STAND_H             # stand top, level with the poop rail's top
    hw = lambda y: G['sc_hw'](y) - G['POOP_INSET']
    for i, y in enumerate(swivel_poop_y(G) if poop_y is None else poop_y):
        for s in (-1, 1):
            slope = (hw(y + 0.05) - hw(y - 0.05)) / 0.1
            h = math.atan2(s * 1.0, -slope)                         # outward normal: (sin h, cos h)
            add('pe_poop_%d_%+d' % (i, s), s * hw(y), y, z_rail, math.degrees(h), G['SC_Z_FLOOR'] + 0.12, False)
    return out
