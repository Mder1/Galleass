"""Painted planking texture for the galleass: the hull plank diffuse turned into a light, neutral grey that keeps the
wood grain and plank seams. The painted planking mesh (galleass_paint) carries the 'faction_color' mesh tag, so the
game multiplies this texture with the owner's colour: paint that still reads as painted wood (replaces the solid
faction overlay galleass_faction_paint, whose near-white texture hid the wood - user 2026-10-16).

Same size and UVs as ship_meditheavy_plank_a_d, so the painted planking keeps the hull's plank UVs and normal map.

usage: python3 make_painted_plank_texture.py <plank_d.png> <out.png> [preview.png]
"""
import sys
import numpy as np
from PIL import Image

MEAN, GRAIN = 0.80, 0.10          # grey level under the colour; grain contrast (std); the raw wood has std/mean ~0.17
rng = np.random.default_rng(1571)

src = np.asarray(Image.open(sys.argv[1]).convert('RGB'), dtype=float) / 255
N = src.shape[0]
lum = src @ np.array([0.2126, 0.7152, 0.0722])
g = (lum - lum.mean()) / lum.std()

def periodic_noise(sig_u, sig_v):
    """Seamless noise: white noise low-passed in the frequency domain (wraps on both axes); sig in cycles/tile."""
    f = np.fft.fft2(rng.standard_normal((N, N)))
    FU, FV = np.meshgrid(np.fft.fftfreq(N) * N, np.fft.fftfreq(N) * N)
    n = np.real(np.fft.ifft2(f * np.exp(-0.5 * ((FU / sig_u) ** 2 + (FV / sig_v) ** 2))))
    return (n - n.mean()) / n.std()

streak = 0.6 * periodic_noise(6, 260) + 0.4 * periodic_noise(25, 600)       # brush strokes along U (the planks)
cloud = periodic_noise(10, 10)                                                 # uneven coats
out = np.clip(MEAN + GRAIN * g + 0.015 * streak - 0.02 * cloud, 0, 1)
Image.fromarray((np.dstack([out] * 3) * 255 + 0.5).astype(np.uint8), 'RGB').save(sys.argv[2])
print('%s: %dx%d mean %.3f std %.3f min %.3f max %.3f' % (sys.argv[2], N, N, out.mean(), out.std(), out.min(), out.max()))

if len(sys.argv) > 3:   # preview: raw wood, then the texture times a few clan colours
    c = N // 4
    tiles = [src[:c, :c]] + [out[:c, :c, None] * np.array(col) for col in
                             ((0.55, 0.08, 0.07), (0.10, 0.20, 0.55), (0.45, 0.15, 0.40), (0.85, 0.70, 0.20),
                              (0.15, 0.40, 0.15), (1.0, 1.0, 1.0))]
    Image.fromarray((np.hstack(tiles) * 255).astype(np.uint8)).resize((7 * 512, 512)).save(sys.argv[3])
