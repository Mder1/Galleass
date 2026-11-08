"""Horn panes for the mast lanterns (lantern_model.py, user 2026-10-28): horn boiled and pressed flat - honey-tinted,
clouded, with the fine layered streaks of the horn and a few darker flecks; each pane has the whole texture (u across
the side, v up), a little darker towards the frame.

    python3 make_horn_texture.py ../AssetSources/export

galleass_horn_d.png for the Kit material galleass_horn, ALPHA BLENDED (two sided). Target (user 2026-10-28: a Murano
glass vase of ~1600): semi-translucent - a strong colour of its own, what is behind seen only dimly. Modulate (the
other modder's clear window glass) can only tint what is behind, so: own honey-amber colour, alpha ~0.5 (~0.45 in the
middle, denser in the streaks and towards the frame).
"""
import os, sys
import numpy as np
from PIL import Image

OUT = sys.argv[1]
N = 256
rng = np.random.default_rng(1588)
y, x = np.mgrid[0:N, 0:N] / N

def noise(sx, sy):
    """Smooth noise with correlation lengths ~N/sx across, ~N/sy up (unit variance)."""
    f = np.fft.fft2(rng.standard_normal((N, N))) * np.exp(-0.5 * ((np.fft.fftfreq(N)[None, :] * N / sx) ** 2 +
                                                                    (np.fft.fftfreq(N)[:, None] * N / sy) ** 2))
    n = np.real(np.fft.ifft2(f))
    return (n - n.mean()) / n.std()

layers = noise(2.0, 24.0)            # the horn's layers: long streaks, slightly wavy
cloud = noise(5.0, 5.0)              # clouding
fleck = np.clip(noise(40.0, 40.0) - 2.4, 0, None)    # sparse darker flecks
rim = np.clip(np.minimum.reduce([x, 1 - x, y, 1 - y]) / 0.08, 0, 1)

t = 0.45 + 0.12 * layers + 0.10 * cloud              # 0 = light honey, 1 = deep amber
t = np.clip(t + 0.30 * (1 - rim) + 0.5 * fleck, 0, 1)
pale, deep = np.array([0.95, 0.74, 0.38]), np.array([0.66, 0.38, 0.12])
rgb = pale[None, None, :] * (1 - t[..., None]) + deep[None, None, :] * t[..., None]
a = np.clip(0.42 + 0.10 * t + 0.08 * cloud * 0.5 + 0.18 * (1 - rim), 0.3, 0.85)
Image.fromarray((np.dstack([rgb, a]) * 255 + 0.5).astype(np.uint8), 'RGBA').save(os.path.join(OUT, 'galleass_horn_d.png'))
print('horn colour mean %s, alpha mean %.2f (%.2f..%.2f)' % (np.round(rgb.reshape(-1, 3).mean(0), 2), a.mean(), a.min(), a.max()))
