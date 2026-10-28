"""Kit packages vs the last commit: per <name>_geo.tpac in Assets/, the sub-meshes (name, LOD, material, flags) against
git HEAD's copy, plus the faction_color tag count on the hull (4 = LOD 0-3 tagged; count matches, NOT lines:
grep -c on the binary says 1). Run after a Kit import, before committing.

    cd Galleass && python3 _art/kit_check/pkgcmp.py galleass_hull galleass_culverin ...
"""
import os, subprocess, sys, tempfile, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tpac_tools'))
from meshinfo import assets, meshes

mat = {}
for p in glob.glob('Assets/*_mtl.tpac'):
    for tg, g, name, meta in assets(p):
        if str(tg).startswith('1db01393'): mat[str(g)] = name
def info(p):
    out = {}
    for tg, g, name, meta in assets(p):
        if str(tg).startswith('a08f8b97'):
            out[name] = [(m['name'], m['lod'], mat.get(m['material'], m['material'][:8]), tuple(m['flags'])) for m in meshes(meta)]
    return out
tmp = tempfile.mkdtemp()
for n in sys.argv[1:]:
    p = f'Assets/{n}_geo.tpac'; h = os.path.join(tmp, n)
    if not os.path.exists(p): print(f'{n:34s} MISSING package'); continue
    open(h, 'wb').write(subprocess.run(['git', 'show', f'HEAD:{p}'], capture_output=True).stdout)
    a, b = info(p), info(h) if os.path.getsize(h) else {}
    if a == b: print(f'{n:34s} ok  ({sum(len(v) for v in a.values())} sub-meshes, lods {sorted({m[1] for v in a.values() for m in v})})')
    else:
        print(f'{n:34s} DIFFERS' + (' (new package)' if not b else ''))
        for k in sorted(set(a) | set(b)):
            for m in sorted(set(b.get(k, [])) - set(a.get(k, []))): print('     HEAD only:', k, m)
            for m in sorted(set(a.get(k, [])) - set(b.get(k, []))): print('     NOW  only:', k, m)
print('faction_color on galleass_hull:', open('Assets/galleass_hull_geo.tpac', 'rb').read().count(b'faction_color'), '(want 4)')
