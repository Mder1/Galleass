# Export Bannerlord editor meshes (MeshEditData segments of Geometry assets) from a .tpac to OBJ.
#   python3 mesh_extract.py <package.tpac> <out dir> [asset name ...]
# Format per TpacTool (TpacTool.Lib/Model/MeshEditData.cs): int32-counted arrays of Vector4 positions, Vector4 unused,
# 92-byte vertices (position index, normal, tangent, binormal, padding, uv, uv2, color, color2), int32x3 faces.
import os, struct, sys, uuid, lz4.block
import tpac

EDIT = uuid.UUID('3d41985f-24d2-4fc1-82e4-6a6e0da3f4e2')

def scan_assets(path):
    out = []
    with open(path, 'rb') as f:
        r = tpac.R(f)
        if r.u32() != 0x43415054: return out
        ver = r.u32(); r.guid(); n = r.u32(); r.u32(); r.u32()
        for _ in range(n):
            tg = r.guid(); g = r.guid()
            if ver > 1: r.u32()
            name = r.str(); ms = r.u64(); f.seek(f.tell() + ms); r.u64()
            segs = []
            for _ in range(r.i32()):
                off, act, sto = r.u64(), r.u64(), r.u64(); r.guid(); st = r.guid(); r.u64(); r.u32(); fmt = r.b()
                segs.append((st, off, act, sto, fmt))
            for _ in range(r.i32()): f.read(48)
            out.append((name, tg, segs))
    return out

def segment(path, off, act, sto, fmt):
    with open(path, 'rb') as f:
        f.seek(off); d = f.read(sto)
    return lz4.block.decompress(d, uncompressed_size=act) if fmt == 1 else d

def read_edit(data):
    o = 0
    def arr(size):
        nonlocal o
        n = struct.unpack_from('<i', data, o)[0]; o += 4
        chunk = data[o:o + n * size]; o += n * size
        return n, chunk
    n, p = arr(16); pos = [struct.unpack_from('<3f', p, i * 16) for i in range(n)]
    arr(16)
    n, v = arr(92)
    verts = []
    for i in range(n):
        b = i * 92
        pi = struct.unpack_from('<I', v, b)[0]
        nx, ny, nz = struct.unpack_from('<3f', v, b + 4)
        u, w = struct.unpack_from('<2f', v, b + 68)
        verts.append((pi, (nx, ny, nz), (u, w)))
    n, fc = arr(12); faces = [struct.unpack_from('<3i', fc, i * 12) for i in range(n)]
    return pos, verts, faces

def main():
    pkg, outdir = sys.argv[1], sys.argv[2]
    want = set(sys.argv[3:])
    os.makedirs(outdir, exist_ok=True)
    for name, tg, segs in scan_assets(pkg):
        if want and name not in want: continue
        edits = [s for s in segs if s[0] == EDIT]
        if not edits: continue
        lines = ['# %s from %s' % (name, os.path.basename(pkg))]
        vbase = 1
        for k, (st, off, act, sto, fmt) in enumerate(edits):
            pos, verts, faces = read_edit(segment(pkg, off, act, sto, fmt))
            if not verts:                                       # (empty sub-mesh, e.g. lib_book_open_b)
                continue
            lines.append('o %s.%d' % (name, k))
            for pi, nrm, uv in verts:
                x, y, z = pos[pi]
                lines.append('v %.5f %.5f %.5f' % (x, y, z))
            for pi, nrm, uv in verts:
                lines.append('vt %.5f %.5f' % (uv[0], 1 - uv[1]))
            for pi, nrm, uv in verts:
                lines.append('vn %.5f %.5f %.5f' % nrm)
            for a, b, c in faces:
                a += vbase; b += vbase; c += vbase
                lines.append('f %d/%d/%d %d/%d/%d %d/%d/%d' % (a, a, a, b, b, b, c, c, c))
            xs = [pos[v[0]] for v in verts]
            lo = [min(p[i] for p in xs) for i in range(3)]; hi = [max(p[i] for p in xs) for i in range(3)]
            print('%s.%d: %d verts, %d faces, box %s .. %s' % (name, k, len(verts), len(faces),
                  tuple(round(x, 2) for x in lo), tuple(round(x, 2) for x in hi)))
            vbase += len(verts)
        open(os.path.join(outdir, name + '.obj'), 'w').write('\n'.join(lines) + '\n')

if __name__ == '__main__':
    main()
