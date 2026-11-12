"""Cast-relief artwork of the galleass guns (no font, no third-party image):

  lion_relief_drawn(width_px)
                           the lion the guns carry: the user's own pencil drawing of the winged lion (andante, halo,
                           book with PAX TIBI MARCE EVANGELISTA MEVS), scanned at 600 dpi (tex_src/lion_drawn.png),
                           turned into a relief: raised silhouette, the drawn lines as grooves, hatching as recesses.
  lion_relief(width_px)    earlier lion drawn here from own curves (no longer used by gun_texture):
                           winged lion walking left (andante): beaded halo, mane of three rows of flame locks, open book
                           (page edges, ribbon) under the raised fore paw, wing with scale coverts, secondaries and
                           flight feathers, S-curved tail with a flame tuft. Every part is its own cushion at its own
                           depth (far legs low, near legs, mane and head high); toes, shoulder, whisker pad and chin
                           modelled; grooves for eye, lid, mouth, lock and feather centres.
  glyph(ch, cap_px)        Roman capital (thick and thin strokes, bracketed serifs) for the letters the guns carry:
                           M, W (founder's initials) and D, L, X (the date MDLXX).

Both return float32 arrays, rows = down the picture (top = toward the muzzle on the gun). The lion is relative height
0..1, the glyph a 0..1 coverage mask (gun_texture bevels it). Coordinates: the lion is drawn on a 100 x 64 grid, the
letters on a cap height of 1, y down.

    python3 relief_art.py <preview dir>      writes lion + alphabet previews
"""
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw

SS = 3                                                    # supersampling of the polygon rasteriser

# ---------------------------------------------------------------- small numeric helpers
def _box(a, k, axis):
    p = np.pad(a, [(k + 1, k) if i == axis else (0, 0) for i in range(a.ndim)], mode='edge')
    c = np.cumsum(p, axis=axis, dtype=np.float64)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * k + 1, 2 * k + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return ((hi - lo) / (2 * k + 1)).astype(np.float32)

def blur(a, radius_px):
    if radius_px <= 0.3:
        return a.astype(np.float32)
    k = max(int(round(radius_px * 0.93)), 1)
    out = a.astype(np.float32)
    for _ in range(3):
        out = _box(_box(out, k, 0), k, 1)
    return out

def catmull(points, closed=True, n=14):
    """Smooth curve through the points (centripetal-ish uniform Catmull-Rom), n samples per span."""
    p = [np.asarray(q, np.float64) for q in points]
    m = len(p)
    out = []
    spans = m if closed else m - 1
    for i in range(spans):
        p0 = p[(i - 1) % m] if closed or i > 0 else 2 * p[0] - p[1]
        p1, p2 = p[i], p[(i + 1) % m]
        p3 = p[(i + 2) % m] if closed or i + 2 < m else 2 * p[-1] - p[-2]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(p[-1])
    return np.array(out)

def stroke_outline(points, widths, n=14):
    """Closed outline of a smooth open stroke through 'points' whose width runs through 'widths' (one per point)."""
    c = catmull(points, closed=False, n=n)
    w = np.interp(np.linspace(0, len(points) - 1, len(c)), np.arange(len(points)), widths)
    d = np.gradient(c, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-12
    nrm = np.stack([-d[:, 1], d[:, 0]], 1)
    left, right = c + nrm * w[:, None] / 2, c - nrm * w[:, None] / 2
    cap0 = [c[0] - d[0] * w[0] * 0.35 * math.cos(a) + nrm[0] * w[0] / 2 * math.sin(a)
            for a in np.linspace(math.pi / 2, -math.pi / 2, 7)[1:-1]][::-1]
    cap1 = [c[-1] + d[-1] * w[-1] * 0.35 * math.cos(a) + nrm[-1] * w[-1] / 2 * math.sin(a)
            for a in np.linspace(-math.pi / 2, math.pi / 2, 7)[1:-1]][::-1]
    return np.concatenate([left, np.array(cap1).reshape(-1, 2), right[::-1], np.array(cap0).reshape(-1, 2)])

class Canvas:
    """Rasterises outlines given in design units onto a pixel grid (scale px per unit), antialiased."""
    def __init__(self, w_units, h_units, scale):
        self.s = scale
        self.W, self.H = int(math.ceil(w_units * scale)), int(math.ceil(h_units * scale))

    def mask(self, polys, holes=()):
        im = Image.new('L', (self.W * SS, self.H * SS), 0)
        d = ImageDraw.Draw(im)
        for poly in polys:
            d.polygon([(x * self.s * SS, y * self.s * SS) for x, y in poly], fill=255)
        for poly in holes:
            d.polygon([(x * self.s * SS, y * self.s * SS) for x, y in poly], fill=0)
        im = im.resize((self.W, self.H), Image.BOX)
        return np.asarray(im).astype(np.float32) / 255.0

    def ellipse(self, cx, cy, rx, ry, rot=0.0, n=48):
        a = np.linspace(0, 2 * math.pi, n, endpoint=False)
        x, y = rx * np.cos(a), ry * np.sin(a)
        c, s = math.cos(rot), math.sin(rot)
        return np.stack([cx + x * c - y * s, cy + x * s + y * c], 1)

def cushion(m, radius_px, edge=0.35):
    """Rounded relief cushion 0..1 over a coverage mask: rises from 'edge' at the outline to 1 within radius_px."""
    b = blur(m, radius_px * 0.5)
    t = np.clip((b - 0.5) * 2, 0, 1)
    return m * (edge + (1 - edge) * np.sqrt(t))

# ---------------------------------------------------------------- the lion
LION_W, LION_H = 100.0, 64.0

def _feather(root, tip, w):
    """Long flight feather from root to tip: tapered stroke, slightly bowed."""
    root, tip = np.asarray(root, float), np.asarray(tip, float)
    d = tip - root
    nrm = np.array([-d[1], d[0]]) / (np.linalg.norm(d) + 1e-9)
    mid = root + d * 0.55 + nrm * np.linalg.norm(d) * 0.04
    return stroke_outline([root, mid, tip], [w * 0.8, w, w * 0.35]), (root, mid, tip)

class _Grooves(list):
    """Groove list that tags every groove with the parts it may cut (set .owner before adding): a mane lock must not
    run on across the head drawn over the mane."""
    owner = ()
    def append(self, g):
        super().append(tuple(g) + (self.owner,))
    def __iadd__(self, gs):
        for g in gs:
            self.append(g)
        return self

def lion_parts():
    """[(name, polygons, level, amp, radius units)] back to front, plus grooves [(polyline, width, depth, owners)]."""
    parts, grooves = [], _Grooves()
    cv = Canvas(1, 1, 1)                                  # only for its ellipse helper

    def lock(name, base, tip, w, level, bend, amp=0.14, groove=True):
        """Flame lock / feather: tapered stroke from base to a pointed tip, bowed by 'bend' (units, + = left of
        the direction base -> tip), with a groove down its middle."""
        base, tip = np.asarray(base, float), np.asarray(tip, float)
        d = tip - base
        n = np.array([-d[1], d[0]]) / (np.linalg.norm(d) + 1e-9)
        mid = base + d * 0.5 + n * bend
        parts.append((name, [stroke_outline([base, mid, tip], [w, w * 0.8, w * 0.12])], level, amp, w * 0.45))
        if groove:
            grooves.owner = (name,)
            grooves.append((catmull([base + (mid - base) * 0.35, mid, mid + (tip - mid) * 0.7], False, 6),
                            max(0.3, w * 0.09), 0.10))

    def toes(paw, cx, cy, rx, rot, level):
        """Three toe pads along the front of a paw (lion faces left: front = -x), knuckled up a little."""
        c, s_ = math.cos(rot), math.sin(rot)
        for k, dx in enumerate((-0.62, -0.18, 0.26)):
            x, y = dx * rx, -0.15
            parts.append(('%s_toe%d' % (paw, k), [cv.ellipse(cx + x * c - y * s_, cy + x * s_ + y * c, rx * 0.25,
                                                             rx * 0.42, rot=rot)], level + 0.03, 0.08, 0.7))

    # halo behind the head: low disc with a beaded rim
    parts.append(('halo', [cv.ellipse(18, 15, 12.5, 12.5)], 0.22, 0.08, 6.0))
    ring = list(cv.ellipse(18, 15, 11.6, 11.6, n=24))
    parts.append(('halo_rim', [stroke_outline(ring + ring[:2], [0.7] * 26)], 0.28, 0.06, 0.4))
    for k, (bx, by) in enumerate(cv.ellipse(18, 15, 11.6, 11.6, n=36)):           # beads on the rim
        parts.append(('halo_bead%d' % k, [cv.ellipse(bx, by, 0.75, 0.75, n=12)], 0.36, 0.1, 0.5))

    # far legs (lower, behind the body)
    parts.append(('far_fore', [stroke_outline([(31, 38), (31.5, 48), (31, 56), (30, 60)], [9.5, 6.8, 5.6, 5.4])],
                  0.42, 0.22, 2.5))
    parts.append(('far_fore_paw', [cv.ellipse(28.0, 61, 5.0, 2.6)], 0.42, 0.22, 1.5))
    toes('far_fore_paw', 28.0, 61, 5.0, 0.0, 0.42)
    parts.append(('far_hind', [stroke_outline([(70, 36), (68, 46), (70.5, 53.5), (70.0, 60)], [12, 8.0, 5.6, 5.4])],
                  0.42, 0.22, 2.5))
    parts.append(('far_hind_paw', [cv.ellipse(68.2, 61, 4.9, 2.6)], 0.42, 0.22, 1.5))
    toes('far_hind_paw', 68.2, 61, 4.9, 0.0, 0.42)

    # tail: S-curve rising from the rump, ending in a flame tuft
    parts.append(('tail', [stroke_outline([(83.5, 33), (91, 32), (94.5, 26), (93, 19), (95.3, 14.5)],
                                          [3.8, 2.8, 2.3, 2.0, 1.9])], 0.55, 0.2, 1.3))
    parts.append(('tail_tuft', [catmull([(95.4, 15.0), (98.4, 12.2), (99.2, 8.0), (97.8, 4.2), (96.2, 1.8),
                                         (95.0, 4.6), (93.4, 8.0), (93.2, 11.8)])], 0.58, 0.22, 1.8))
    grooves.owner = ('tail_tuft',)
    grooves += [(catmull([(95.6, 13.5), (97.4, 9.5), (96.6, 4.0)], False, 6), 0.4, 0.10),
                (catmull([(94.6, 13.0), (94.6, 9.0), (95.6, 5.0)], False, 6), 0.4, 0.10),
                (catmull([(96.4, 13.8), (98.2, 10.2), (98.0, 7.0)], False, 6), 0.32, 0.07)]

    # book: open, standing on its lower edge, leaning back toward the lion; the near fore paw rests on it
    book = [(2.5, 60.5), (3.5, 41), (8.5, 38.5), (13.5, 40.5), (14.5, 60.5), (8.5, 58.6)]
    parts.append(('book', [catmull(book, True, 3)], 0.5, 0.12, 2.0))
    parts.append(('book_cover', [stroke_outline([(2.6, 61.2), (8.5, 59.4), (14.6, 61.2)], [1.4, 1.4, 1.4])],
                  0.56, 0.08, 0.6))
    grooves.owner = ('book',)
    grooves.append((np.array([(8.5, 38.8), (8.5, 58.4)]), 0.6, 0.16))               # gutter
    parts.append(('ribbon', [stroke_outline([(8.6, 58.8), (9.4, 61.2), (8.8, 63.0), (9.8, 63.8)], [0.9, 0.9, 0.85, 0.7])],
                  0.6, 0.06, 0.4))
    for k in range(3):                                                                # page edges at the top
        grooves.append((catmull([(3.7 + k * 0.05, 41.6 + k * 0.7), (8.4, 39.2 + k * 0.7)], False, 4), 0.25, 0.06))
        grooves.append((catmull([(8.6, 39.2 + k * 0.7), (13.3, 41.2 + k * 0.7)], False, 4), 0.25, 0.06))
    for k in range(5):                                                                # lines of the text
        y = 44 + k * 3.2
        grooves.append((np.array([(4.3, y + 0.4), (7.2, y - 0.3)]), 0.42, 0.07))
        grooves.append((np.array([(9.8, y - 0.3), (12.9, y + 0.3)]), 0.42, 0.07))

    # body: deep chest, lean belly tucked up toward the flank, rounded haunch
    body = [(20, 31), (28, 24.5), (40, 26), (55, 28), (70, 27.5), (81, 28), (87.5, 32.5), (88.5, 39.5),
            (85, 45), (77, 44.5), (70, 41.5), (58, 42), (45, 43.5), (33, 45.5), (24, 45), (18.5, 40)]
    parts.append(('body', [catmull(body)], 0.66, 0.3, 7.0))
    parts.append(('haunch', [cv.ellipse(79, 37, 8.7, 8.4)], 0.72, 0.18, 4.5))
    parts.append(('shoulder', [cv.ellipse(30.5, 34.5, 7.0, 8.5, rot=0.25)], 0.7, 0.14, 4.0))
    parts.append(('chest', [cv.ellipse(19.5, 42.0, 4.2, 3.6)], 0.68, 0.12, 2.0))       # under the raised forearm
    grooves.owner = ('body', 'haunch', 'shoulder')
    grooves.append((catmull([(73, 30), (71, 36.5), (72.5, 43)], False, 8), 0.7, 0.07))   # haunch fold
    grooves.append((catmull([(38, 42.0), (50, 39.8), (62, 39.6), (68, 41.0)], False, 8), 0.8, 0.05))   # ribcage
    grooves.append((catmull([(35.5, 28.5), (37.5, 35), (36.5, 42)], False, 8), 0.6, 0.05))  # back of the shoulder

    # near hind leg: thigh, hock thrown back, paw planted
    parts.append(('near_hind', [stroke_outline([(80, 40), (83.5, 48), (86.5, 52.5), (84, 57), (81.5, 60)],
                                               [12, 8.2, 6.0, 5.4, 5.2])], 0.82, 0.24, 2.5))
    parts.append(('near_hind_paw', [cv.ellipse(79.4, 61.2, 5.2, 2.6)], 0.84, 0.22, 1.5))
    toes('near_hind_paw', 79.4, 61.2, 5.2, 0.0, 0.84)
    # near fore leg: raised, forearm reaching forward, paw on the book's upper edge
    parts.append(('near_fore', [stroke_outline([(25, 38.5), (22, 45.5), (18.5, 48), (13.5, 44), (11.6, 41.4)],
                                               [11, 8.0, 6.4, 5.6, 5.4])], 0.84, 0.24, 2.5))
    parts.append(('near_fore_paw', [cv.ellipse(10.4, 40.2, 5.0, 2.9, rot=-0.5)], 0.88, 0.22, 1.5))
    toes('near_fore_paw', 10.4, 40.2, 5.0, -0.5, 0.88)

    # wing: rising from the shoulder, swept up and back; coverts in a scalloped band, then the long flight feathers
    root = (36, 27)
    tips = [(84, 1.4), (80.5, 6.4), (76, 11.4), (71, 16.0), (65.5, 20.2), (59.5, 23.8), (53.5, 26.8)]
    feathers = []
    for i, tip in enumerate(tips):
        r = (root[0] + 3.0 + i * 1.4, root[1] - 6.5 + i * 1.6)
        poly, spine = _feather(r, tip, 6.2 - i * 0.35)
        feathers.append((poly, spine))
    # backing under the feathers' inner part, so no pin-holes open between them (their tips stay free)
    back = [(32, 30.5), (33.5, 21), (40, 11.5), (50, 5.5), (61, 2.8), (70, 2.2)]
    back += [tuple(sp[0] + (sp[2] - sp[0]) * 0.8) for _, sp in feathers] + [(42, 30.5)]
    parts.append(('wing_back', [np.array(back)], 0.7, 0.06, 2.0))
    for i, (poly, spine) in enumerate(feathers[::-1]):                               # lowest first, top one in front
        parts.append(('feather%d' % i, [poly], 0.74 + i * 0.012, 0.16, 1.5))
    grooves.owner = tuple('feather%d' % i for i in range(len(feathers)))
    for poly, spine in feathers:
        grooves.append((catmull([spine[0] + (spine[2] - spine[0]) * 0.15, spine[1], spine[2] - (spine[2] - spine[0])
                                 * 0.12], False, 8), 0.35, 0.10))
    for i, (poly, spine) in enumerate(feathers):                                     # secondaries over them
        r0, t0 = spine[0], spine[2]
        lock('second%d' % i, r0 + (t0 - r0) * 0.12, r0 + (t0 - r0) * 0.6, 5.0 - i * 0.25, 0.84 + i * 0.006, -0.5,
             amp=0.12)
    leading = [(32, 30.5), (33.5, 21), (40, 11.5), (50, 5.5), (61, 2.8), (70, 2.2)]
    coverts = catmull(leading + [(66, 6.5), (58, 11.5), (51, 16.5), (45.5, 23), (42, 30.5)], True, 8)
    parts.append(('coverts', [coverts], 0.86, 0.16, 3.0))
    lead_curve = catmull(leading, False, 10)
    grooves.owner = ('coverts',)
    grooves.append((catmull([(35, 27), (39, 18), (47, 10.5), (57, 6), (66, 4.6)], False, 10), 0.5, 0.11))
    tang = np.gradient(lead_curve, axis=0)
    tang /= np.linalg.norm(tang, axis=1, keepdims=True)
    inward = np.stack([tang[:, 1], -tang[:, 0]], 1)                                   # into the wing (down-back)
    if inward[len(inward) // 2][1] < 0:
        inward = -inward
    for row, (off, n, rs) in enumerate(((2.6, 16, 1.25), (4.6, 14, 1.35), (6.6, 12, 1.45))):   # covert scales
        for k in range(n):
            t = (k + 0.5 * row + 0.5) / (n + 0.5)
            i = int(t * (len(lead_curve) - 1))
            c = lead_curve[i] + inward[i] * off
            a = math.atan2(inward[i][1], inward[i][0])
            parts.append(('covert%d_%d' % (row, k), [cv.ellipse(c[0], c[1], rs * 1.3, rs, rot=a)],
                          0.9 - row * 0.012, 0.04, 0.6))

    # mane: a low ruff under three rows of flame locks sweeping back, longest outside (they make the outline)
    c0 = np.array([19.5, 22.0])
    mane_out = [(10.5, 9.5), (15, 4.5), (22, 3.5), (28.5, 7.5), (32.5, 14), (35, 21.5), (34.5, 29.5), (30.5, 36.5),
                (25, 42), (19, 43), (14.5, 38.5), (12, 33), (10.5, 28.5)]
    mo = c0 + (catmull(mane_out, True, 10) - c0) * 0.95
    parts.append(('mane', [mo], 0.78, 0.12, 4.0))
    for row, (n, rb, rt, w, level, a0, a1) in enumerate(((18, 9.5, 18.6, 5.4, 0.8, -2.2, 2.05),
                                                         (15, 8.0, 15.6, 4.8, 0.85, -2.1, 1.9),
                                                         (12, 6.5, 12.2, 4.0, 0.9, -2.0, 1.75))):
        for k in range(n):
            a = a0 + (a1 - a0) * (k + 0.5 * (row % 2)) / (n - 1 + 0.5 * (row % 2))
            d = np.array([math.cos(a), math.sin(a)])
            rt_k = rt - 4.0 * max(0.0, -(a + 1.9))                                    # shorter toward the brow
            rt_k += 1.5 * max(0.0, math.sin(a))                                       # longer down the chest
            bend = 2.0 if a < 0.6 else -2.0                                           # all sweep back (+x)
            lock('mane%d_%d' % (row, k), c0 + d * rb, c0 + d * rt_k, w, level + k * 0.002, bend)

    # head in profile, facing left: brow, muzzle, open jaw, ear
    parts.append(('ear', [cv.ellipse(22.4, 9.6, 2.5, 2.1, rot=-0.5)], 0.93, 0.1, 1.0))
    grooves.owner = ('ear',)
    grooves.append((catmull([(21.4, 10.6), (21.6, 8.9), (23.0, 8.4), (23.6, 9.4)], False, 6), 0.45, 0.14))
    head = [(10.5, 12.0), (14, 9.5), (19.5, 10.0), (24, 13.5), (25, 19.5), (23.5, 25.5), (19, 29.8), (13, 30.3),
            (9.2, 28.2), (8.6, 26.4), (6.0, 25.4), (4.3, 22.6), (4.0, 20.0), (5.4, 17.0), (8.2, 14.6)]
    parts.append(('head', [catmull(head)], 0.96, 0.22, 3.0))
    parts.append(('brow', [cv.ellipse(12.5, 15.3, 3.4, 1.4, rot=-0.25)], 1.0, 0.08, 0.8))
    parts.append(('muzzle', [cv.ellipse(8.2, 22.2, 3.6, 2.3, rot=0.15)], 0.99, 0.07, 1.2))
    parts.append(('chin', [cv.ellipse(11.0, 27.6, 2.8, 1.7, rot=0.2)], 0.97, 0.06, 0.8))
    parts.append(('nose', [cv.ellipse(5.4, 19.6, 1.8, 1.3, rot=-0.3)], 1.0, 0.08, 0.7))
    grooves.owner = ('muzzle',)
    for (wx, wy) in ((7.4, 21.6), (9.0, 21.9), (10.6, 22.3), (7.8, 23.0), (9.4, 23.3)):   # whisker dots
        grooves.append((np.array([(wx, wy), (wx + 0.15, wy + 0.1)]), 0.42, 0.12))
    grooves.owner = ('head', 'brow', 'nose', 'muzzle', 'chin')
    grooves += [(catmull([(10.6, 17.6), (12.3, 16.9), (14.2, 17.4), (12.3, 18.3), (10.6, 17.6)], False, 6), 0.4, 0.2),
                (catmull([(4.9, 23.4), (7.2, 24.3), (10.0, 24.1), (13.0, 25.8)], False, 6), 0.45, 0.2),   # mouth
                (catmull([(7.0, 21.1), (8.6, 21.6)], False, 4), 0.35, 0.1),                               # nostril
                (catmull([(14.5, 21.0), (16.5, 25.0), (16.0, 28.5)], False, 6), 0.4, 0.08),               # cheek
                (catmull([(10.2, 16.9), (12.3, 16.0), (14.6, 16.8)], False, 6), 0.35, 0.1),               # upper lid
                (np.array([(12.0, 17.5), (12.2, 17.6)]), 0.6, 0.18)]                                     # pupil
    return parts, grooves

def lion_relief(width_px):
    """Relative height 0..1 of the lion, width_px wide (height in proportion, LION_H / LION_W)."""
    s = width_px / LION_W
    cv = Canvas(LION_W, LION_H, s)
    parts, grooves = lion_parts()
    h = np.zeros((cv.H, cv.W), np.float32)
    owner = np.full((cv.H, cv.W), -1, np.int32)           # which part is on top
    names = [p[0] for p in parts]
    for i, (name, polys, level, amp, radius) in enumerate(parts):
        m = cv.mask(polys)
        part = ((level - amp) + amp * cushion(m, radius * s) / np.maximum(m, 1e-6)) * np.clip(m * 1.5, 0, 1)
        wins = (m > 0.02) & (part > h)
        h = np.where(wins, part, h)
        owner = np.where(wins, i, owner)
    for line, width, depth, owners in grooves:
        ids = [names.index(n) for n in owners]
        inside = blur(np.isin(owner, ids).astype(np.float32), max(s * 0.15, 0.5))   # soft at the part's edge
        im = Image.new('L', (cv.W * SS, cv.H * SS), 0)
        ImageDraw.Draw(im).line([(x * s * SS, y * s * SS) for x, y in line], fill=255,
                                width=max(int(round(width * s * SS)), 1), joint='curve')
        g = np.asarray(im.resize((cv.W, cv.H), Image.BOX)).astype(np.float32) / 255.0
        h = np.maximum(h - inside * depth * blur(g, width * s * 0.35), 0.0)
    h = blur(h, max(s * 0.12, 0.5))                       # cast softness
    return (h / max(h.max(), 1e-6)).astype(np.float32)

# ---------------------------------------------------------------- the hand-drawn lion (the one the guns use)
DRAWN_LION = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tex_src', 'lion_drawn.png')
DRAWN_WORK_W = 1500                                       # working width (px): radii below are in these pixels

def _grow(m, r):
    """Dilate a bool mask by ~r px with an octagon (alternating 3x3 square and cross steps): round, not boxy."""
    m = m.copy()
    for i in range(int(r)):
        p = np.pad(m, 1)
        if i % 2:
            m = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
        else:
            m = np.zeros_like(m)
            for dy in range(3):
                for dx in range(3):
                    m |= p[dy:dy + m.shape[0], dx:dx + m.shape[1]]
    return m

def _fill_from(mask, seed):
    """Region of 'mask' (bool) 4-connected to seed (x, y) as a bool array."""
    im = Image.fromarray((mask * 255).astype(np.uint8)).copy()   # copy: arrays from fromarray are read-only
    ImageDraw.floodfill(im, seed, 128)
    return np.asarray(im) == 128

def lion_relief_drawn(width_px, path=DRAWN_LION):
    """Relative height 0..1 of the hand-drawn lion (pencil drawing, 600 dpi scan, cropped and despeckled), width_px
    wide, cropped to the lion. The outer contour becomes a raised silhouette with rounded shoulders and a broad dome,
    every field between the drawn lines a low cushion of its own, so the pencil lines read as cut grooves and the
    dense hatching (thigh, leg shadows, ears) as shallow recesses."""
    g = Image.open(path).convert('L')
    h0 = round(g.height * DRAWN_WORK_W / g.width)
    pad = 40
    a = np.pad(np.asarray(g.resize((DRAWN_WORK_W, h0), Image.BOX), np.float32), pad, constant_values=255)
    ink = np.clip((200 - a) / 120, 0, 1)                  # pencil coverage 0..1
    lines = ink > 0.3
    # silhouette: everything the outside can't reach once gaps up to ~40 px in the pencil outline are bridged
    outside = _fill_from(~_grow(lines, 20), (0, 0))
    sil = ~_grow(outside, 20)
    sil = blur(sil.astype(np.float32), 1.5) > 0.5
    core = blur(sil.astype(np.float32), 30)               # keep only the lion (stray specks would stand as islands)
    sil = _fill_from(sil, tuple(int(v) for v in np.unravel_index(np.argmax(core), core.shape)[::-1]))
    S = sil.astype(np.float32)
    fields = S * (1 - np.clip(blur(lines.astype(np.float32), 1.0) * 2, 0, 1))
    h = (S * (0.35 + 0.25 * cushion(S, 22, edge=0.3) + 0.20 * blur(S, 45))
         + 0.22 * cushion(fields, 7, edge=0.2)
         - S * (0.10 * blur(ink, 0.8) + 0.18 * np.clip(blur(ink, 7) * 1.6, 0, 1)))
    h = blur(np.clip(h, 0, None), 0.8)
    ys, xs = np.where(sil)
    m = 4
    h = h[max(ys.min() - m, 0):ys.max() + m + 1, max(xs.min() - m, 0):xs.max() + m + 1]
    out_h = max(int(round(h.shape[0] * width_px / h.shape[1])), 1)
    h = np.asarray(Image.fromarray(h.astype(np.float32), 'F').resize((int(width_px), out_h), Image.BOX))
    h = np.clip(h, 0, None)
    return (h / max(h.max(), 1e-6)).astype(np.float32)

# ---------------------------------------------------------------- Roman capitals
T, t = 0.15, 0.062                                        # thick and thin stroke (cap heights)
SERIF_L, SERIF_H, BRACKET = 0.15, 0.045, 0.14             # half-length, slab thickness, bracket height

def _bar(x0, y0, x1, y1, w):
    d = np.array([x1 - x0, y1 - y0], float)
    d /= np.linalg.norm(d)
    n = np.array([-d[1], d[0]]) * w / 2
    e = d * 0.2 if abs(d[1]) > 0.5 else d * 0.0           # overshoot past cap / base line (clipped there)
    a, b = np.array([x0, y0]) - e, np.array([x1, y1]) + e
    return [a + n, b + n, b - n, a - n]

def _serif(x, w, top, left=True, right=True):
    """Slab serif with brackets at x on the cap line (top) or base line: centred on a stroke of width w."""
    y0 = 0.0 if top else 1.0
    sg = 1 if top else -1
    l = SERIF_L if left else 0.0
    r = SERIF_L if right else 0.0
    pts = [(x - w / 2 - l, y0), (x + w / 2 + r, y0), (x + w / 2 + r, y0 + sg * SERIF_H),
           (x + w / 2 + r * 0.25, y0 + sg * (SERIF_H + 0.02)), (x + w / 2, y0 + sg * BRACKET),
           (x - w / 2, y0 + sg * BRACKET), (x - w / 2 - l * 0.25, y0 + sg * (SERIF_H + 0.02)),
           (x - w / 2 - l, y0 + sg * SERIF_H)]
    return [np.array(p) for p in pts]

def _ellipse_arc(cx, cy, rx, ry, a0, a1, n=40):
    a = np.linspace(a0, a1, n)
    return [np.array([cx + rx * math.cos(q), cy + ry * math.sin(q)]) for q in a]

def letter_shapes(ch):
    """(width, [polygons], [holes]) in cap heights, y down, 0 = cap line, 1 = base line."""
    if ch == 'M':
        return 1.02, [_bar(0.13, 1, 0.19, 0, t), _bar(0.19, 0, 0.51, 1, T), _bar(0.51, 1, 0.83, 0, t),
                      _bar(0.83, 0, 0.89, 1, T), _serif(0.13, t, False), _serif(0.89, T, False),
                      _serif(0.19, t, True, right=False), _serif(0.83, T, True, left=False)], []
    if ch == 'W':
        return 1.14, [_bar(0.08, 0, 0.32, 1, T), _bar(0.32, 1, 0.57, 0, t), _bar(0.57, 0, 0.81, 1, T),
                      _bar(0.81, 1, 1.06, 0, t), _serif(0.08, T, True), _serif(0.57, T, True, right=False),
                      _serif(0.57, t, True, left=False), _serif(1.06, t, True)], []
    if ch == 'L':
        return 0.66, [_bar(0.15, 0, 0.15, 1, T), _bar(0.15, 1 - t / 2, 0.62, 1 - t / 2, t),
                      _bar(0.60, 1, 0.61, 0.79, t * 0.9), _serif(0.15, T, True), _serif(0.15, T, False, right=False)], []
    if ch == 'X':
        return 0.78, [_bar(0.08, 0, 0.70, 1, T), _bar(0.68, 0, 0.10, 1, t), _serif(0.08, T, True),
                      _serif(0.70, T, False), _serif(0.68, t, True), _serif(0.10, t, False)], []
    if ch == 'D':
        x0 = 0.15
        outer = [np.array([x0 - T / 2, 0.0]), np.array([0.40, 0.0])] + _ellipse_arc(0.40, 0.5, 0.43, 0.5, -math.pi / 2,
                                                                                    math.pi / 2) + \
                [np.array([x0 - T / 2, 1.0])]
        inner = [np.array([x0 + T / 2, t]), np.array([0.40, t])] + _ellipse_arc(0.40, 0.5, 0.43 - T, 0.5 - t,
                                                                                 -math.pi / 2, math.pi / 2) + \
                [np.array([x0 + T / 2, 1 - t])]
        return 0.88, [outer, _serif(x0, T, True, right=False), _serif(x0, T, False, right=False)], [inner]
    raise ValueError('no Roman capital drawn for %r' % ch)

def glyph(ch, cap_px):
    """Coverage mask of one capital, cap height cap_px pixels, cropped to its ink + 2 px."""
    w, polys, holes = letter_shapes(ch)
    pad = SERIF_L + 0.05
    cv = Canvas(w + 2 * pad, 1.0, cap_px)
    sh = lambda poly: [(p[0] + pad, p[1]) for p in poly]
    m = cv.mask([sh(p) for p in polys], [sh(p) for p in holes])
    cols = np.where(m.max(0) > 0.01)[0]
    m = m[:, cols[0]:cols[-1] + 1]
    return np.pad(m, 2).astype(np.float32)

# ---------------------------------------------------------------- previews
if __name__ == '__main__':
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for name, l in (('lion', lion_relief(1175)), ('lion_drawn', lion_relief_drawn(1175))):
        Image.fromarray((l * 255).astype(np.uint8)).save(os.path.join(out, name + '_height.png'))
        # lit like a cast relief (light from the upper left) to judge the modelling
        gy, gx = np.gradient(l * 60)
        shade = np.clip(0.35 + (gx * 0.6 + gy * 0.6) * 0.6 + 0.4 * l, 0, 1)      # slopes lit + height tint
        Image.fromarray((shade * 255).astype(np.uint8)).save(os.path.join(out, name + '_lit.png'))
    gs = [glyph(c, 120) for c in 'MWDLX']
    H = max(g.shape[0] for g in gs)
    row = np.zeros((H, sum(g.shape[1] for g in gs) + 30 * len(gs)), np.float32)
    x = 0
    for g in gs:
        row[:g.shape[0], x:x + g.shape[1]] = g
        x += g.shape[1] + 30
    Image.fromarray((row * 255).astype(np.uint8)).save(os.path.join(out, 'letters.png'))
    print('previews in', out)
