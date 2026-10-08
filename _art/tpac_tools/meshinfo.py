"""List the sub-meshes of metamesh assets in a .tpac: index, name, LOD, material (resolved by name across the given
material packages). Layout per TpacTool (Model/Metamesh.cs, Model/Mesh.cs, Model/ClothingMaterial.cs).

    python3 meshinfo.py <pkg.tpac> '<glob of packages to resolve material names>' name [name ...]   (--json for JSON)
"""
import glob, io, json, struct, sys, uuid, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tpac import R

def _s(b): n = struct.unpack('<i', b.read(4))[0]; return b.read(n).decode('utf8', 'replace') if n else ''
def _sl(b): return [_s(b) for _ in range(struct.unpack('<i', b.read(4))[0])]
def _g(b): return uuid.UUID(bytes_le=b.read(16))
def _u(b): return struct.unpack('<I', b.read(4))[0]
def _i(b): return struct.unpack('<i', b.read(4))[0]

def assets(path):
    with open(path, 'rb') as f:
        r = R(f)
        if r.u32() != 0x43415054: return
        ver = r.u32(); r.guid(); n = r.u32(); r.u32(); r.u32()
        for _ in range(n):
            tg = r.guid(); g = r.guid()
            if ver > 1: r.u32()
            name = r.str(); ms = r.u64(); meta = f.read(ms); r.u64()
            for _ in range(r.i32()): r.u64(); r.u64(); r.u64(); r.guid(); r.guid(); r.u64(); r.u32(); r.b()
            f.seek(48 * r.i32(), 1)
            yield tg, g, name, meta

def meshes(meta):
    b = io.BytesIO(meta)
    v = _u(b); _g(b); b.read(4); _s(b); _g(b)
    if v >= 1:
        _u(b)
        if _u(b) > 0: _s(b)
    out = []
    for k in range(_i(b)):
        b.read(1); lod = _i(b); _u(b); _g(b); sub = _u(b); _g(b); name = _s(b); _u(b); flags = _sl(b)
        mat = _g(b); b.read(64); b.read(20); b.read(4); b.read(52); b.read(4); _sl(b); b.read(4)
        _s(b); b.read(36); b.read(4); b.read(2)                       # clothing material, unknowns
        if sub >= 1: b.read(8); b.read(1)
        out.append(dict(index=k, name=name, lod=lod, material=str(mat), flags=flags))
    return out

if __name__ == '__main__':
    pkg, matglob, names = sys.argv[1], sys.argv[2], [a for a in sys.argv[3:] if a != '--json']
    matnames = {}
    for p in glob.glob(matglob, recursive=True):
        try:
            for tg, g, name, meta in assets(p):
                if str(tg).startswith('1db01393'): matnames[str(g)] = name
        except Exception: pass
    res = {}
    for tg, g, name, meta in assets(pkg):
        if name in names and str(tg).startswith('a08f8b97'):
            res[name] = [dict(m, material_name=matnames.get(m['material'], '?')) for m in meshes(meta)]
    if '--json' in sys.argv: print(json.dumps(res, indent=1))
    else:
        for n, ms in res.items():
            print(n); [print('   %2d %-26s lod %d  %s' % (m['index'], m['name'], m['lod'], m['material_name'])) for m in ms]
