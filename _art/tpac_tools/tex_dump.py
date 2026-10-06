"""Dump named textures from .tpac packages to PNG (downscaled to <= max size).
usage: python3 tex_dump.py <outdir> <maxsize> <pkg.tpac> [<pkg.tpac> ...] -- <texture names...>"""
import sys, io, struct, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tpac
from PIL import Image
args = sys.argv[1:]; i = args.index('--')
out, mx, pkgs, names = args[0], int(args[1]), args[2:i], set(args[i + 1:])
FCC = {'DXT1': b'DXT1', 'DXT3': b'DXT3', 'DXT5': b'DXT5', 'BC5': b'ATI2', 'BC4': b'ATI1'}
def dds(w, h, fmt, data):
    if fmt == 'BC7':
        hdr = struct.pack('<4sIIIIIII44xII4s20xI16x', b'DDS ', 124, 0x1007 | 0x80000, h, w, len(data), 0, 1, 32, 4, b'DX10', 0x1000)
        return hdr + struct.pack('<IIIII', 98, 3, 0, 1, 0) + data
    return struct.pack('<4sIIIIIII44xII4s20xI16x', b'DDS ', 124, 0x1007 | 0x80000, h, w, len(data), 0, 1, 32, 4, FCC[fmt], 0x1000) + data
for p in pkgs:
    for m in tpac.scan(p):
        if m['name'] not in names: continue
        chain = tpac.mip_chain(m, tpac.pixels(m))
        w, h, d = next(c for c in chain if max(c[0], c[1]) <= mx)
        im = Image.open(io.BytesIO(dds(w, h, m['fmt'], d))); im.load()
        im.save(os.path.join(out, m['name'] + '.png'))
        print(m['name'], m['fmt'], m['w'], m['h'], '->', w, h)
