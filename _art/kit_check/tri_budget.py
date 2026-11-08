"""Triangle budget of the galleass as the game draws it: every meta-mesh instance of the installed prefab (vanilla prefab
links resolved like the game does, see prefab_layout.children), times the triangles of that meta-mesh at LOD 0-3
(a mesh without a level falls back to its last one). Hidden entities (build_prefab hide(): tag galleass_hidden, scale
0.001) and editor-only entities are reported apart, not counted. Triangles per meta-mesh come from the editor
packages' edit data (Galleass/Assets, NavalDLC + Native EmAssetPackages), cached in _art/ref/mesh_tris.json.

    cd Galleass && python3 _art/kit_check/tri_budget.py [--rebuild] [--top N] [--ship <vanilla prefab, e.g. meditheavy_ship_nested>]

The War Sails contest (2026-11) suggests ~250k triangles at LOD0 as a sensible maximum (vanilla heavy ~120k).
"""
import glob, io, json, os, re, struct, sys, uuid
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.dirname(HERE); MOD = os.path.dirname(ART); GAME = os.path.dirname(os.path.dirname(MOD))
sys.path.insert(0, ART); sys.path.insert(0, os.path.join(ART, 'tpac_tools'))
import lz4.block
import prefab_layout as PL
import meshinfo

META = uuid.UUID('a08f8b97-0000-0000-0000-000000000000')    # (prefix compare below)
EDIT = uuid.UUID('3d41985f-24d2-4fc1-82e4-6a6e0da3f4e2')
CACHE = os.path.join(ART, 'ref', 'mesh_tris.json')
LODS = range(4)

def face_count(data):
    """Faces of one MeshEditData segment (int32-counted arrays: positions 16 B, unused 16 B, vertices 92 B, faces 12 B)."""
    o = 0
    for size in (16, 16, 92):
        n = struct.unpack_from('<i', data, o)[0]; o += 4 + n * size
    return struct.unpack_from('<i', data, o)[0]

def scan(path, want, out):
    """Meta-mesh assets of one package that are wanted and not yet known -> out[name] = [tris at LOD 0..3]."""
    with open(path, 'rb') as f:
        def u32(): return struct.unpack('<I', f.read(4))[0]
        def i32(): return struct.unpack('<i', f.read(4))[0]
        def u64(): return struct.unpack('<Q', f.read(8))[0]
        def guid(): return uuid.UUID(bytes_le=f.read(16))
        def sstr(): n = i32(); return f.read(n).decode('utf8', 'replace') if n else ''
        if u32() != 0x43415054: return
        ver = u32(); guid(); n = u32(); u32(); u32()
        for _ in range(n):
            tg = guid(); guid()
            if ver > 1: u32()
            name = sstr(); ms = u64()
            take = str(tg).startswith('a08f8b97') and name in want and name not in out
            meta = f.read(ms) if take else (f.seek(ms, 1), None)[1]
            u64(); segs = []
            for _ in range(i32()):
                off, act, sto = u64(), u64(), u64(); guid(); st = guid(); u64(); u32(); fmt = f.read(1)[0]
                segs.append((st, off, act, sto, fmt))
            f.seek(48 * i32(), 1)
            if not take:
                continue
            try:
                subs = meshinfo.meshes(meta)
            except Exception:
                continue
            edits = [s for s in segs if s[0] == EDIT]
            if len(edits) != len(subs):
                continue
            per = defaultdict(int)
            here = f.tell()
            for sub, (st, off, act, sto, fmt) in zip(subs, edits):
                f.seek(off); d = f.read(sto)
                if fmt == 1: d = lz4.block.decompress(d, uncompressed_size=act)
                per[sub['lod']] += face_count(d)
            f.seek(here)
            levels = sorted(per)
            out[name] = [per[max([l for l in levels if l <= k] or levels[:1])] for k in LODS]
            out[name + '#src'] = os.path.relpath(path, GAME)

def index(names, rebuild):
    known = {} if rebuild or not os.path.exists(CACHE) else json.load(open(CACHE))
    want = {n for n in names if n not in known}
    if want:
        pkgs = (sorted(glob.glob(os.path.join(MOD, 'Assets', '*.tpac'))) +
                sorted(glob.glob(os.path.join(GAME, 'Modules', 'NavalDLC', 'EmAssetPackages', '**', '*.tpac'), recursive=True)) +
                sorted(glob.glob(os.path.join(GAME, 'Modules', 'Native', 'EmAssetPackages', '**', '*.tpac'), recursive=True)))
        for p in pkgs:
            if not (want - known.keys()):
                break
            try:
                scan(p, want, known)
            except Exception as e:
                print('  (skip %s: %s)' % (os.path.basename(p), e), file=sys.stderr)
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump(known, open(CACHE, 'w'), indent=0)
    return known

def editor_only(e):
    fl = PL.inherited(e, 'flags')
    return fl is not None and any(m.get('name') == 'visible_only_when_editing' and m.get('value') == 'true'
                                  for m in fl.iter('visibility_mask'))

GROUPS = [   # (group, regex on mesh name) - first match wins
    ('ship body (hull mesh, all materials)', r'^galleass_(hull|paint|deck|gilt|dark|trim|iron|faction_paint)$|^ship_(meditheavy|dromon)|^dromon_0'),
    ('hull plating (upgrade)', r'^galleass_hull_plate|^hull_plate'),
    ('rudder', r'rudder'),
    ('guns', r'^galleass_(culverin|falcon|falconet|petriera)(?!_lashing)|_quoin|_fuse|swivel'),
    ('gun lashings/rigging', r'_lashing|gun_rigging'),
    ('gun ropes (vanilla coil)', r'^sail_rope_pile_d$'),
    ('stores + shot', r'powder_keg|shot_|locker|ladle|_bag|_ball|basket|rack'),
    ('lanterns', r'lantern'),
    ('own rig: masts/bowsprit/standing/pins', r'^galleass_(mast|bowsprit|standing|pinrail|bitts|belay)'),
    ('desk + props', r'desk|book|inkwell|chart|quill'),
    ('other own meshes', r'^galleass_'),
    ('vanilla sails', r'sail(?!_rope)|_lateen|square_sail'),
    ('vanilla rig ropes', r'rope'),
    ('vanilla masts/yards', r'mast|yard'),
    ('vanilla oars', r'oar'),
]
def group(name):
    for g, rx in GROUPS:
        if re.search(rx, name):
            return g
    return 'other vanilla'

def main():
    rebuild = '--rebuild' in sys.argv
    top = int(sys.argv[sys.argv.index('--top') + 1]) if '--top' in sys.argv else 25
    ship = sys.argv[sys.argv.index('--ship') + 1] if '--ship' in sys.argv else 'galleass_ship_nested'
    navals = os.path.join(GAME, 'Modules', 'NavalDLC', 'AssetPackages', 'nested_prefabs_packed.xml')
    PL.load(navals if ship != 'galleass_ship_nested' else
            os.path.join(MOD, 'AssetPackages', 'nested_prefabs_packed.xml') + ',' + navals)
    rows = PL.layout(ship)
    # rows come depth-first (prefab_layout.walk): the subtree of row i is i .. end(i); paths are NOT unique
    dep = [r['path'].count('/') for r in rows]
    end = [0] * len(rows)
    for i in range(len(rows)):
        j = i + 1
        while j < len(rows) and dep[j] > dep[i]:
            j += 1
        end[i] = j
    hidden = [i for i, r in enumerate(rows) if 'galleass_hidden' in r['tags']]
    names = {m for r in rows for m in r['meshes']}
    tris = index(names, rebuild)
    t0 = lambda i: sum(tris.get(m, [0] * 4)[0] for k in range(i, end[i]) for m in rows[k]['meshes'])

    # upgrade slots: an entity tagged upgrade_slot holds every alternative piece as a child (tag = piece id); the game
    # keeps the equipped one. 'base' = the child tagged base (no upgrade), 'max' = the heaviest child at LOD0.
    skip = {'base': [], 'max': []}
    slot_tot = defaultdict(lambda: {'base': 0, 'max': 0, 'n': 0})
    for i, s_ in enumerate(rows):
        if 'upgrade_slot' not in s_['tags']:
            continue
        kids = [k for k in range(i + 1, end[i]) if dep[k] == dep[i] + 1]
        cost = {k: t0(k) for k in kids}
        keep_b = [k for k in kids if 'base' in rows[k]['tags']]
        keep_m = [max(cost, key=cost.get)] if cost else []
        skip['base'] += [k for k in kids if k not in keep_b]
        skip['max'] += [k for k in kids if k not in keep_m]
        kind = s_['tags'][1] if len(s_['tags']) > 1 else s_['name']
        st = slot_tot[kind]; st['n'] += 1
        st['base'] += sum(cost[k] for k in keep_b); st['max'] += sum(cost[k] for k in keep_m)
    def masked(lst):
        m = [False] * len(rows)
        for i in lst:
            for k in range(i, end[i]): m[k] = True
        return m
    hid = masked(hidden)

    f = lambda v: '{:>9,}'.format(v)
    for cfg in ('base', 'max'):
        inst, nhid, ned = defaultdict(int), 0, 0
        off = masked(skip[cfg])
        for i, r in enumerate(rows):
            if off[i]:
                continue
            if hid[i]: nhid += len(r['meshes']); continue
            if editor_only(r['el']): ned += len(r['meshes']); continue
            for m in r['meshes']:
                inst[m] += 1
        tot, own_tot, by_group, lines = [0] * 4, [0] * 4, defaultdict(lambda: [0] * 4), []
        for m, n in inst.items():
            t = tris.get(m)
            if t is None:
                continue
            own = tris.get(m + '#src', '').startswith(os.path.join('Modules', 'Galleass'))
            for k in LODS:
                v = t[k] * n; tot[k] += v; by_group[group(m)][k] += v
                if own: own_tot[k] += v
            lines.append((t[0] * n, m, n, t, own))
        title = {'base': 'BASE ship (no upgrades: every slot on its base piece)',
                 'max': 'WORST CASE (the heaviest piece in every upgrade slot)'}[cfg]
        print('\n=== %s ===' % title)
        print('%-40s %9s %9s %9s %9s' % ('group', 'LOD0', 'LOD1', 'LOD2', 'LOD3'))
        for g, v in sorted(by_group.items(), key=lambda x: -x[1][0]):
            print('%-40s %s %s %s %s' % (g, *map(f, v)))
        print('%-40s %s %s %s %s' % ('TOTAL drawn', *map(f, tot)))
        print('%-40s %s %s %s %s' % ('  of which own meshes', *map(f, own_tot)))
        print('Top %d meshes (triangles x instances at LOD0):' % top)
        for v, m, n, t, own in sorted(lines, reverse=True)[:top]:
            print('  %s  %-38s x%-4d per mesh %s  %s' % (f(v), m, n, '/'.join(str(x) for x in t), 'own' if own else 'vanilla'))
        print('not counted: %d hidden mesh instances (scale 0.001), %d editor-only' % (nhid, ned))
    print('\nupgrade slots, LOD0 triangles  (slot x count: base piece / heaviest piece)')
    for kind, st in slot_tot.items():
        print('  %-12s x%-3d %s / %s' % (kind, st['n'], f(st['base']), f(st['max'])))
    missing = sorted(m for m in names if m not in tris)
    if missing:
        print('NO triangle data for %d meshes: %s' % (len(missing), ', '.join(missing[:20])))

if __name__ == '__main__':
    main()
