"""Faction paint texture for the galleass: seamless, mostly solid paint (the game tints it with the owner's colours
through the 'faction_color' mesh tag). Vanilla's ship_liburna_pattern_a is a narrow strip of heavily worn brush
strokes (45-75 % coverage), right for thin stripes but blotchy over whole walls.

U = fore and aft (brush strokes run along the planks), V = up; one tile = 1/0.135 m (the planking's UV scale).
RGB: near-white with faint streaks; alpha: ~0.95 with faint streaks and a few small chips where wood shows.

usage: python3 make_paint_texture.py <out.png> [preview.png <wood texture>]
"""
import sys
import numpy as np
from PIL import Image

N = 2048
rng = np.random.default_rng(1571)

def periodic_noise(sig_u, sig_v):
    """Seamless noise: white noise low-passed in the frequency domain (wraps on both axes); sig in cycles/tile."""
    f = np.fft.fft2(rng.standard_normal((N, N)))
    fu = np.fft.fftfreq(N) * N                   # cycles per tile along U (image x)
    fv = np.fft.fftfreq(N) * N
    FU, FV = np.meshgrid(fu, fv)
    g = np.exp(-0.5 * ((FU / sig_u) ** 2 + (FV / sig_v) ** 2))
    n = np.real(np.fft.ifft2(f * g))
    return (n - n.mean()) / n.std()

streak = 0.6 * periodic_noise(6, 260) + 0.4 * periodic_noise(25, 600)     # long strokes along U
cloud = periodic_noise(10, 10)                                               # broad, uneven coverage
chips = periodic_noise(90, 70) + 0.6 * cloud

alpha = 0.955 + 0.022 * streak + 0.012 * cloud
t = np.quantile(chips, 0.988)                                                # ~1 % worn chips
alpha -= 0.6 * np.clip((chips - t) / 0.35, 0, 1)
alpha = np.clip(alpha, 0.0, 1.0)
rgb = np.clip(0.95 + 0.03 * streak - 0.015 * cloud, 0, 1)

img = np.dstack([rgb, rgb, rgb, alpha])
Image.fromarray((img * 255 + 0.5).astype(np.uint8), 'RGBA').save(sys.argv[1])
print('coverage mean %.3f, min %.3f, chips %.2f %%' % (alpha.mean(), alpha.min(), 100 * (alpha < 0.8).mean()))

if len(sys.argv) > 3:   # preview: paint in an example faction colour over the wood
    wood = np.asarray(Image.open(sys.argv[3]).convert('RGB').resize((N, N)), dtype=float) / 255
    colour = np.array([0.55, 0.08, 0.07])
    a = alpha[..., None]
    out = wood * (1 - a) + (rgb[..., None] * colour) * a
    tile = np.tile(out[:N // 2, :], (1, 2, 1))[:, ::2]
    Image.fromarray((out[:1024, :1024] * 255).astype(np.uint8)).save(sys.argv[2])
