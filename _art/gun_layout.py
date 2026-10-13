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
