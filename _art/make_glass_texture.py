"""Stern-lantern glass: warm amber, partly transparent (the flame and its light shine through), with faint streaks and
a slightly darker rim so the panes still read as glass. RGBA 256^2; alpha ~0.4.

usage: python3 make_glass_texture.py <out.png>
"""
import sys
import numpy as np
from PIL import Image

N = 256
rng = np.random.default_rng(24)
y, x = np.mgrid[0:N, 0:N] / N
streak = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((N, N))) *
                              np.exp(-0.5 * ((np.fft.fftfreq(N)[None, :] * N / 3) ** 2 + (np.fft.fftfreq(N)[:, None] * N / 40) ** 2))))
streak = (streak - streak.mean()) / streak.std()
rim = np.clip(np.minimum.reduce([x, 1 - x, y, 1 - y]) / 0.06, 0, 1)
r = np.clip(1.00 + 0.03 * streak, 0, 1)
g = np.clip(0.78 + 0.04 * streak - 0.08 * (1 - rim), 0, 1)
b = np.clip(0.42 + 0.04 * streak - 0.10 * (1 - rim), 0, 1)
a = np.clip(0.40 + 0.04 * streak + 0.25 * (1 - rim), 0, 1)
Image.fromarray((np.dstack([r, g, b, a]) * 255 + 0.5).astype(np.uint8), 'RGBA').save(sys.argv[1])
print('alpha mean %.2f' % a.mean())
