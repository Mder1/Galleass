"""Sacking for the scattershot bags (Kit material galleass_sack): the vanilla NavalDLC awning canvas ship_roof_cloth_a
(_d/_n/_s, native textures, allowed in the contest; a tileable coarse weave), the diffuse tinted a little towards raw
hessian. User 2026-10-15: the rope texture made the bags look like striped bottles.

    python3 make_sack_texture.py ../AssetSources/export
"""
import io, os, struct, sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'tpac_tools'))
import tpac

OUT = sys.argv[1]
PKG = os.path.join(HERE, '..', '..', 'NavalDLC', 'EmAssetPackages', 'ship_roofs', 'ship_roofs.tpac')
HESSIAN = np.array([0.98, 0.90, 0.74], np.float32)
FCC = {'DXT1': b'DXT1', 'DXT3': b'DXT3', 'DXT5': b'DXT5', 'BC5': b'ATI2', 'BC4': b'ATI1'}

def dds(w, h, fmt, data):
    return struct.pack('<4sIIIIIII44xII4s20xI16x', b'DDS ', 124, 0x1007 | 0x80000, h, w, len(data), 0, 1, 32, 4,
                       FCC[fmt], 0x1000) + data

os.makedirs(OUT, exist_ok=True)
for m in tpac.scan(PKG):
    if not m['name'].startswith('ship_roof_cloth_a_'):
        continue
    w, h, d = tpac.mip_chain(m, tpac.pixels(m))[0]
    im = Image.open(io.BytesIO(dds(w, h, m['fmt'], d))); im.load()
    suffix = m['name'].rsplit('_', 1)[1]
    a = np.asarray(im.convert('RGBA')).astype(np.float32) / 255
    if m['fmt'] == 'BC5':                                  # two-channel normal: rebuild blue
        xy = a[..., :2] * 2 - 1
        a[..., 2] = np.sqrt(np.clip(1 - (xy ** 2).sum(-1), 0, 1)) * 0.5 + 0.5
    if suffix == 'd':
        a[..., :3] = np.clip(a[..., :3] * HESSIAN, 0, 1)
    mode = 'RGB'                                            # the normal is plain RGB (alpha ~unused)
    out = (a * 255 + 0.5).astype(np.uint8)
    path = os.path.join(OUT, 'galleass_sack_%s.png' % suffix)
    Image.fromarray(out if mode == 'RGBA' else out[..., :3], mode).save(path)
    print('wrote', path, w, h, m['fmt'])
