"""Particle system tpac -> raw decompressed segment (layout notes: memory tpac-texture-extraction).
    python3 psys_dump.py <tpac_tools dir> <..._psys.tpac> <out.bin>"""
import sys, struct, re, lz4.block
sys.path.insert(0, sys.argv[1]); import tpac
p = sys.argv[2]
d = open(p, 'rb').read()
with open(p, 'rb') as f:
    r = tpac.R(f); r.u32(); ver = r.u32(); r.guid(); n = r.u32(); r.u32(); r.u32()
    for _ in range(n):
        r.guid(); r.guid(); r.u32(); name = r.str(); ms = r.u64(); f.read(ms); r.u64()
        segs = []
        for _ in range(r.i32()):
            o, a, s = r.u64(), r.u64(), r.u64(); r.guid(); r.guid(); r.u64(); r.u32(); fmt = r.b(); segs.append((o, a, s, fmt))
        f.read(48 * r.i32())
for o, a, s, fmt in segs:
    raw = lz4.block.decompress(d[o:o + s], uncompressed_size=a) if fmt == 1 else d[o:o + a]
    open(sys.argv[3], 'wb').write(raw)
    print(name, 'segment', a, 'bytes')
