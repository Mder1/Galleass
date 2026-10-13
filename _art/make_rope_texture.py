"""Rope textures for the gun rigging (Kit material galleass_rope): the vanilla NavalDLC ship_ropes_d/_n/_s (native
textures, allowed in the contest), the greyscale diffuse tinted to tarred hemp.

    python3 make_rope_texture.py ../AssetSources/export

Layout of ship_ropes (512 x 4096): braided rope u 0..0.5, thin cord 0.5..0.75, laid three-strand rope 0.76..0.99
(rope_geom.ROPE_U), strands along v.
"""
import io, os, struct, sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tpac_tools'))
import tpac

OUT = sys.argv[1]
PKG = os.path.join(HERE, '..', '..', 'NavalDLC', 'EmAssetPackages', 'ship_ropes', 'ship_ropes.tpac')
HEMP = np.array([1.22, 1.02, 0.74], np.float32)          # grey 115 -> ~(140, 117, 85): tarred hemp
FCC = {'DXT1': b'DXT1', 'DXT3': b'DXT3', 'DXT5': b'DXT5', 'BC5': b'ATI2', 'BC4': b'ATI1'}

def dds(w, h, fmt, data):
    return struct.pack('<4sIIIIIII44xII4s20xI16x', b'DDS ', 124, 0x1007 | 0x80000, h, w, len(data), 0, 1, 32, 4,
                       FCC[fmt], 0x1000) + data

os.makedirs(OUT, exist_ok=True)
for m in tpac.scan(PKG):
    w, h, d = tpac.mip_chain(m, tpac.pixels(m))[0]
    im = Image.open(io.BytesIO(dds(w, h, m['fmt'], d))); im.load()
    a = np.asarray(im.convert('RGB')).astype(np.float32) / 255
    suffix = m['name'].rsplit('_', 1)[1]
    if m['fmt'] == 'BC5':                                  # two-channel normal: rebuild blue
        xy = a[..., :2] * 2 - 1
        a[..., 2] = np.sqrt(np.clip(1 - (xy ** 2).sum(-1), 0, 1)) * 0.5 + 0.5
    if suffix == 'd':
        a = np.clip(a * HEMP, 0, 1)
    path = os.path.join(OUT, 'galleass_rope_%s.png' % suffix)
    Image.fromarray((a * 255 + 0.5).astype(np.uint8)).save(path)
    print('wrote', path, w, h)
