"""Bronze texture atlas of the galleass guns (Kit material galleass_gun_bronze): diffuse, normal and specular maps.

    python3 gun_texture.py <out dir> [preview dir]

The layout is gun_uv.py's (culverin strip, falcon strip shared by the falconet, plain misc strip). The metal itself is
the vanilla ram bronze (galleass_ram_bronze_d/_n/_s, the textures galleass_gilt uses), resampled at its own scale in
surface metres, so the guns keep the look they had. On top, cast reliefs placed in surface metres (arc length from
the top line, distance along the barrel) and turned into normals with the true pixel size of every row:
  culverin: winged lion (andante, the hand drawing via relief_art.lion_relief_drawn) on the plain band of the chase,
            founder's initials M * W under it, the date on the base ring's broad fillet;
  falcon:   oval cartouche with scrolls round the lion on the chase, M * W on the reinforce behind the trunnions,
            the date on the base ring (the falconet shares the strip, scaled).
Inscriptions read from behind the breech (letter tops toward the muzzle). The lion is the user's own pencil drawing
(_art/tex_src/lion_drawn.png), the Roman capitals own outlines (relief_art.py); no third-party image or font. Dirt and dark patina collect round the
reliefs and in the culverin's spiral ribs and flutes (gun_profiles.culverin_mod).
NORMAL_GREEN_DOWN flips the green channel (DirectX convention) should the reliefs look sunken in game.
"""
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gun_profiles as gp
import gun_uv
import relief_art

OUT = sys.argv[1]
PREVIEW = sys.argv[2] if len(sys.argv) > 2 else None
SRC = os.path.join(HERE, '..', 'AssetSources')            # the Kit's copies of the vanilla ram bronze
A = gun_uv.ATLAS
DETAIL_PX_PER_M = 1024                                   # vanilla ram bronze: 2048 px at 0.5 UV/m (old gilt UVs)
NORMAL_GREEN_DOWN = False
DATE = 'MDLXX'                                           # 1570, the Lepanto years
INITIALS = ('M', 'W')                                    # founder's initials (user's choice)

def load(name):
    return np.asarray(Image.open(os.path.join(SRC, name)).convert('RGB')).astype(np.float32) / 255.0

DET_D, DET_N, DET_S = load('galleass_ram_bronze_d.png'), load('galleass_ram_bronze_n.png'), load('galleass_ram_bronze_s.png')

def sample(img, x, y):
    """Bilinear, wrapping, img[row, col]: x = column, y = row (pixels, any float arrays)."""
    h, w = img.shape[:2]
    x0 = np.floor(x).astype(np.int64); y0 = np.floor(y).astype(np.int64)
    fx = (x - x0)[..., None] if img.ndim == 3 else x - x0
    fy = (y - y0)[..., None] if img.ndim == 3 else y - y0
    x0 %= w; y0 %= h; x1 = (x0 + 1) % w; y1 = (y0 + 1) % h
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy) +
            img[y1, x0] * (1 - fx) * fy + img[y1, x1] * fx * fy)

def sample_clamped(img, x, y):
    """Bilinear, zero outside (relief patches)."""
    h, w = img.shape
    pad = np.pad(img, 1)
    x = np.clip(x + 1, 0, w + 0.999); y = np.clip(y + 1, 0, h + 0.999)
    x0 = np.minimum(np.floor(x).astype(np.int64), w); y0 = np.minimum(np.floor(y).astype(np.int64), h)
    fx, fy = x - x0, y - y0
    return (pad[y0, x0] * (1 - fx) * (1 - fy) + pad[y0, x0 + 1] * fx * (1 - fy) +
            pad[y0 + 1, x0] * (1 - fx) * fy + pad[y0 + 1, x0 + 1] * fx * fy)

def _box(a, k, axis):
    """Running mean of width 2k+1 along axis, edges clamped."""
    p = np.pad(a, [(k + 1, k) if i == axis else (0, 0) for i in range(a.ndim)], mode='edge')
    c = np.cumsum(p, axis=axis, dtype=np.float64)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * k + 1, 2 * k + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return ((hi - lo) / (2 * k + 1)).astype(np.float32)

def blur(a, radius_px):
    """Gaussian-like blur (three box passes, sigma ~ radius_px) of a float array (PIL can't blur mode 'F')."""
    if radius_px <= 0.3:
        return a.astype(np.float32)
    k = max(int(round(radius_px * 0.93)), 1)               # 3 boxes of 2k+1: sigma = sqrt(3 * ((2k+1)^2 - 1) / 12)
    out = a.astype(np.float32)
    for _ in range(3):
        out = _box(_box(out, k, 0), k, 1)
    return out

# ---------------------------------------------------------------- relief patches (height in metres, RES m/px)
RES = 0.0002                                             # 0.2 mm per patch pixel

def px(m):
    return max(int(round(m / RES)), 1)

def bevel(mask, height, soft):
    """Raised plateau from a 0..1 mask: rounded shoulders 'soft' metres wide."""
    b = blur(mask, px(soft) * 0.5)
    t = np.clip((b - 0.15) / 0.7, 0.0, 1.0)
    return height * t * t * (3 - 2 * t)

def lion_patch(width, height=0.0022):
    """The winged lion (relief_art.lion_relief_drawn: the hand drawing, relative 0..1) as heights in metres,
    'width' metres wide."""
    return relief_art.lion_relief_drawn(px(width)) * height

def text_patch(text, cap_h, height=0.0012, spacing=0.25):
    """Raised capitals (cap height cap_h) with rounded shoulders; letters spaced 'spacing' x cap height."""
    glyphs = [relief_art.glyph(ch, px(cap_h)) for ch in text]
    return hstack(glyphs, px(cap_h * spacing), height)

def rosette_patch(d, height=0.0012, petals=6):
    n = px(d) + 4
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    c = (n - 1) / 2; r = np.hypot(xx - c, yy - c) / (px(d) / 2); ang = np.arctan2(yy - c, xx - c)
    petal = 0.62 + 0.38 * np.cos(petals * ang)          # flower outline radius
    m = (r < petal).astype(np.float32)
    h = bevel(m, height, d * 0.12)
    h = h - 0.4 * height * (r < 0.22) * (1 - r / 0.22) + 0.25 * height * (r < 0.16)   # seeded centre
    return np.maximum(h, 0)

def hstack(parts, gap, height=None):
    """Side by side, centred vertically; masks (height=None means parts are already heights)."""
    H = max(p.shape[0] for p in parts)
    W = sum(p.shape[1] for p in parts) + gap * (len(parts) - 1)
    out = np.zeros((H, W), np.float32); x = 0
    for p in parts:
        y = (H - p.shape[0]) // 2
        out[y:y + p.shape[0], x:x + p.shape[1]] = np.maximum(out[y:y + p.shape[0], x:x + p.shape[1]], p)
        x += p.shape[1] + gap
    if height is not None:
        out = bevel(out, height, 0.0006)
    return out

def initials_patch(cap_h):
    l, r = (text_patch(c, cap_h) for c in INITIALS)
    return hstack([l, rosette_patch(cap_h * 0.55), r], px(cap_h * 0.3))

def dome(xx, yy, cx, cy, ra, rb, rot=0.0):
    """Rounded lobe: height 0..1 of an elliptical cushion (semi-axes ra, rb px, rotated rot rad)."""
    c, s_ = math.cos(rot), math.sin(rot)
    dx, dy = xx - cx, yy - cy
    e2 = ((dx * c + dy * s_) / ra) ** 2 + ((-dx * s_ + dy * c) / rb) ** 2
    return np.sqrt(np.clip(1 - e2, 0, 1))

def volute_mask(W, H, cx, cy, r0, turns, sense, w0, w1):
    """Spiral scroll drawn as a band tapering from w0 to w1 px, unwinding from radius r0 toward its eye."""
    img = Image.new('L', (W, H), 0); d = ImageDraw.Draw(img)
    n = 90; prev = None
    for k in range(n + 1):
        t = k / n
        th = sense * t * turns * 2 * math.pi
        rr = r0 * (1 - 0.82 * t)
        p = (cx + rr * math.cos(th), cy + rr * math.sin(th))
        w = w0 + (w1 - w0) * t
        if prev: d.line([prev, p], fill=255, width=max(int(w), 1))
        d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=255)
        prev = p
    return np.asarray(img).astype(np.float32) / 255.0

def cartouche_patch(ws, hy, height=0.0020):
    """Oval cartouche round the lion (Alberghetti falcon, drawing 1): a double frame moulding (broad rounded torus,
    fine bead outside), a scallop shell on top (toward the muzzle), a pendant of three leaves below, and a scroll
    ear on each side curling down. ws, hy: overall width (round the barrel) and height (along it), metres."""
    W, H = px(ws), px(hy)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = (W - 1) / 2, (H - 1) / 2
    ea, eb = W * 0.30, H * 0.31                          # frame centre line, semi-axes (px)
    e = np.hypot((xx - cx) / ea, (yy - cy) / eb)
    tw = 0.075
    torus = np.sqrt(np.clip(1 - ((e - 1) / tw) ** 2, 0, 1))
    bead = np.sqrt(np.clip(1 - ((e - 1 - tw * 1.75) / (tw * 0.38)) ** 2, 0, 1))
    inner = blur((e < 1 - tw).astype(np.float32), 3)
    h = np.maximum(height * 0.85 * torus, height * 0.45 * bead) + height * 0.12 * inner
    # scallop shell above the frame (rows decrease toward the muzzle): fan of ribs in a half-disc
    sx, sy, sr = cx, cy - eb * (1 + tw * 2.2), H * 0.105
    rr = np.hypot(xx - sx, (yy - sy) * 1.05) / sr
    ang = np.arctan2(-(yy - sy), xx - sx)                # 0..pi above the hinge
    fan = (rr < 1) & (ang > 0.05) & (ang < math.pi - 0.05)
    ribs = 0.30 + 0.70 * np.abs(np.cos(ang * 4.5)) ** 0.7
    shell = np.where(fan, np.sqrt(np.clip(1 - rr ** 2, 0, 1)) * 0.6 + 0.4 * (rr < 1), 0) * ribs
    shell = blur(shell.astype(np.float32), 2.5)
    shell += 0.8 * dome(xx, yy, sx, sy, sr * 0.28, sr * 0.18)            # hinge boss
    h = np.maximum(h, height * 0.8 * shell)
    # pendant below the frame: a middle leaf and two side leaves, turned out
    py0 = cy + eb * (1 + tw * 1.8)
    leaves = dome(xx, yy, cx, py0 + H * 0.06, W * 0.05, H * 0.075)
    for s_ in (-1, 1):
        leaves = np.maximum(leaves, 0.85 * dome(xx, yy, cx + s_ * W * 0.075, py0 + H * 0.03, W * 0.04, H * 0.06,
                                                rot=s_ * 0.75))
    leaves = np.maximum(leaves, 0.9 * dome(xx, yy, cx, py0 - H * 0.005, W * 0.05, H * 0.025))   # binding knot
    h = np.maximum(h, height * 0.8 * leaves)
    # ears: scroll from the frame's side, curling outward and down
    ears = np.zeros_like(h)
    for s_ in (-1, 1):
        vx = cx + s_ * (ea * (1 + tw) + W * 0.065)
        m = volute_mask(W, H, vx, cy + H * 0.02, W * 0.07, 1.25, -s_, W * 0.032, W * 0.013)
        ears = np.maximum(ears, m)
    h = np.maximum(h, bevel(ears, height * 0.75, 0.0007))
    lion = lion_patch(ws * 0.52, height * 0.9)
    ly, lx = int(cy - lion.shape[0] / 2), int(cx - lion.shape[1] / 2)
    h[ly:ly + lion.shape[0], lx:lx + lion.shape[1]] = np.maximum(h[ly:ly + lion.shape[0], lx:lx + lion.shape[1]],
                                                                lion + height * 0.12)
    return h

# ---------------------------------------------------------------- strips
def strip_grid(strip):
    u0, u1 = gun_uv.REGIONS[strip]
    i0, i1 = int(round(u0 * A)), int(round(u1 * A))
    u = (np.arange(i0, i1) + 0.5) / A
    v = 1 - (np.arange(A) + 0.5) / A                     # image row 0 = top of the texture = v 1
    U, V = np.meshgrid(u, v)
    ang, y = gun_uv.strip_inverse(strip, U, V)
    return i0, i1, ang.astype(np.float32), y.astype(np.float32)

def profile_radius(strip, y):
    if strip == 'culverin':
        prof = gp.culverin_profile()[:-2]
    else:
        prof = gp.falcon_profile(gp.FALCON)[0][:-2]
    ys = np.array([p[0] for p in prof]); rs = np.array([p[1] for p in prof])
    return np.interp(y, ys, rs).astype(np.float32)

def groove_depth(strip, ang, y, r):
    """Depth of the cast flutes / spiral grooves (metres, >0 in a groove) on a coarse grid, upsampled."""
    if strip != 'culverin':
        return np.zeros_like(y)
    k = 4
    a_c, y_c, r_c = ang[::k, ::k], y[::k, ::k], r[::k, ::k]
    f = np.vectorize(lambda yy, aa, rr: rr - gp.culverin_mod(float(yy), float(aa), float(rr)), otypes=[np.float32])
    g = f(y_c, a_c, r_c)
    im = Image.fromarray(g, 'F').resize((y.shape[1], y.shape[0]), Image.BILINEAR)
    return np.asarray(im, dtype=np.float32)

def place(height, patch, ang, y, r, s_c, y_c):
    """Stamp a patch (rows = along the barrel, top toward the muzzle; columns = round it toward +x) centred at arc
    s_c, barrel y y_c (profile metres of this strip). Keeps the higher of both heights. Also wraps the angle once
    so a patch can sit across the seam padding."""
    hp, wp = patch.shape
    s = ang * r
    col = (s - s_c) / RES + wp / 2
    row = (y_c - y) / RES + hp / 2
    sel = (col > -1) & (col < wp) & (row > -1) & (row < hp)
    if sel.any():
        height[sel] = np.maximum(height[sel], sample_clamped(patch, col[sel], row[sel]))

def decorate(strip, height, ang, y, r):
    if strip == 'culverin':
        ty, L = gp.CV['trunnion_y'], gp.CV['length']
        band0, band1 = ty + 0.62, ty + 1.02              # culverin_mod's plain band
        lion = lion_patch(0.235)
        lion_h = lion.shape[0] * RES
        y_l = band1 - 0.03 - lion_h / 2
        place(height, lion, ang, y, r, 0.0, y_l)
        ini = initials_patch(0.045)
        place(height, ini, ang, y, r, 0.0, (band0 + y_l - lion_h / 2) / 2)
        place(height, text_patch(DATE, 0.026), ang, y, r, 0.0, 0.021)      # base ring fillet 0 .. 0.042
    else:
        _, ty, _ = gp.falcon_profile(gp.FALCON)
        L = gp.FALCON['length']
        place(height, cartouche_patch(0.19, 0.25), ang, y, r, 0.0, ty + 0.075 + 0.36)
        place(height, initials_patch(0.040), ang, y, r, 0.0, 0.33)
        place(height, text_patch(DATE, 0.021), ang, y, r, 0.0, 0.016)      # base ring fillet 0 .. 0.032

def to_normal(h, ang, y, r, strip):
    """Tangent-space normal of the height field: tangent = +u (round the barrel toward +x), bitangent = +v (toward
    the muzzle). Pixel sizes: arc per column r * dangle, along per row from the strip's y range."""
    i0, i1 = [int(round(x * A)) for x in gun_uv.REGIONS[strip]]
    dang = 2 * math.pi / ((i1 - i0) - 2 * gun_uv.PAD_U * A)
    y0, y1 = gun_uv.Y_RANGE[strip]
    dy = (y1 - y0) / (A * (1 - 2 * gun_uv.PAD_V))
    ds = np.maximum(r * dang, 1e-5)
    dh_ds = np.gradient(h, axis=1) / ds
    dh_dy = -np.gradient(h, axis=0) / dy                 # rows run toward -y
    n = np.stack([-dh_ds, -dh_dy, np.ones_like(h)], -1)
    return n / np.linalg.norm(n, axis=-1, keepdims=True)

def blend_normals(base, det):
    """Detail normal (0..1 encoded) on top of a base normal (unit vectors): whiteout blend."""
    d = det * 2 - 1
    n = np.stack([base[..., 0] + d[..., 0], base[..., 1] + d[..., 1], base[..., 2] * d[..., 2]], -1)
    return n / np.linalg.norm(n, axis=-1, keepdims=True)

def lowfreq(shape, seed, scale):
    rng = np.random.default_rng(seed)
    small = rng.random((max(shape[0] // scale, 2), max(shape[1] // scale, 2))).astype(np.float32)
    im = Image.fromarray(small, 'F').resize((shape[1], shape[0]), Image.BICUBIC)
    return np.asarray(im, dtype=np.float32) - 0.5

def build():
    D = np.zeros((A, A, 3), np.float32); N = np.zeros((A, A, 3), np.float32); S = np.zeros((A, A, 3), np.float32)
    heights = {}
    for strip in ('culverin', 'falcon'):
        i0, i1, ang, y, = strip_grid(strip)
        r = profile_radius(strip, y)
        s = ang * r
        tx, ty_ = s * DETAIL_PX_PER_M, -y * DETAIL_PX_PER_M
        d, nd, sp = sample(DET_D, tx, ty_), sample(DET_N, tx, ty_), sample(DET_S, tx, ty_)
        h = np.zeros_like(y)
        decorate(strip, h, ang, y, r)
        heights[strip] = h
        n = blend_normals(to_normal(h, ang, y, r, strip), nd)
        if NORMAL_GREEN_DOWN:
            n[..., 1] *= -1
        # dirt / patina: round the reliefs (blurred height above the local height) and in the cast grooves
        hb = blur(h, 14)
        cav = np.clip((hb - h) / 0.0008, 0, 1) * (h < 0.0021)
        cav = np.maximum(cav, np.clip((blur(h, 4) - h) / 0.0004, 0, 1) * 0.8)
        g = np.clip(groove_depth(strip, ang, y, r) / 0.012, 0, 1)
        dirt = np.clip(cav + 0.55 * g, 0, 1)
        patina = np.array([0.50, 0.55, 0.42], np.float32)  # dark green-brown in the recesses
        var = 1 + 0.10 * lowfreq(y.shape, 7 if strip == 'culverin' else 11, 96)
        d = d * var[..., None]
        d = d * (1 - 0.45 * dirt[..., None]) * (1 - dirt[..., None] * 0.5 + dirt[..., None] * 0.5 * patina)
        crest = np.clip((h - hb) / 0.0006, 0, 1)         # worn, brighter high points of the relief
        d = np.clip(d * (1 + 0.18 * crest[..., None]), 0, 1)
        sp = sp.copy()
        sp[..., 0] *= 1 - 0.30 * dirt; sp[..., 1] *= 1 - 0.40 * dirt
        sp[..., 1] = np.clip(sp[..., 1] * (1 + 0.10 * crest), 0, 1)
        D[:, i0:i1], N[:, i0:i1], S[:, i0:i1] = d, n * 0.5 + 0.5, sp
    # misc strip: plain metal, misc UV metres -> detail texels
    i0, i1 = [int(round(x * A)) for x in gun_uv.REGIONS['misc']]
    cols, rows = np.meshgrid(np.arange(i0, i1, dtype=np.float32), np.arange(A, dtype=np.float32))
    k = DETAIL_PX_PER_M / (gun_uv.MISC_SCALE * A)
    D[:, i0:i1] = sample(DET_D, cols * k, rows * k)
    N[:, i0:i1] = sample(DET_N, cols * k, rows * k)
    S[:, i0:i1] = sample(DET_S, cols * k, rows * k)
    N[..., 2] = np.maximum(N[..., 2], 0.5)
    return D, N, S, heights

def save(a, path):
    Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), 'RGB').save(path)
    print('wrote', path)

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    D, N, S, heights = build()
    for suf, a in (('d', D), ('n', N), ('s', S)):
        save(a, os.path.join(OUT, f'galleass_gun_bronze_{suf}.png'))
    if PREVIEW:
        os.makedirs(PREVIEW, exist_ok=True)
        Image.fromarray((np.clip(D, 0, 1) * 255).astype(np.uint8)).resize((1024, 1024)).save(
            os.path.join(PREVIEW, 'tex_atlas_d.png'))
        for strip, h in heights.items():
            Image.fromarray((np.clip(h / 0.0025, 0, 1) * 255).astype(np.uint8)).save(
                os.path.join(PREVIEW, f'tex_height_{strip}.png'))
