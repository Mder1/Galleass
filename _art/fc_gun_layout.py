"""Forecastle gun layout study: to-scale top views (PIL, no Blender) of the platform and the ground floor with the
fore mast, stairs and gun footprints (run out = solid, recoiled = dashed) for candidate arrangements.

    python3 fc_gun_layout.py <out dir>
"""
import math, os, sys
from PIL import Image, ImageDraw, ImageFont
import model_geom
G = model_geom.load()

OUT = sys.argv[1] if len(sys.argv) > 1 else 'renders'
os.makedirs(OUT, exist_ok=True)
R = G['fc_radius'](G['FC_Z_PLATFORM'])            # outer face of the forecastle wall
WALL = 0.35
CY, YB = G['FC_CY'], G['FC_Y_BACK']
HEEL = G['FORE_HEEL_R']
MAST_PLATFORM = G['fore_mast_y'](G['FC_Z_PLATFORM'])
MAST_LOWER = G['fore_mast_y'](G['Z_GUN_DECK'] + 0.8)
STAIR_X = G['FC_STAIR_X']

# footprints (m): length from the muzzle back to the end of the carriage/sledge, width, recoil travel
CULVERIN = dict(name='culverin', length=float(os.environ.get('CV_LEN', 3.6 + 0.3)), width=0.8, recoil=1.0, col=(150, 95, 30))
FALCON = dict(name='falcon', length=2.4 + 0.5, width=0.9, recoil=0.8, col=(60, 110, 160))

PX = 70
X0, X1, Y0, Y1 = -6.0, 6.0, 14.6, 26.2
W, H = int((X1 - X0) * PX), int((Y1 - Y0) * PX)
def P(x, y): return ((x - X0) * PX, (Y1 - y) * PX)

def horseshoe(r, yb=YB, n=64):
    pts = [(-r, yb)] + [(r * math.cos(math.pi - math.pi * i / n), CY + r * math.sin(math.pi - math.pi * i / n))
                        for i in range(n + 1)] + [(r, yb)]
    return pts

def rect(cx, cy, heading, back0, back1, width):
    """Rectangle along the axis through (cx, cy) pointing at heading (rad, 0 = +y), from back0 to back1 behind it."""
    dx, dy = math.sin(heading), math.cos(heading)
    nx, ny = dy, -dx
    pts = []
    for b, s in ((back0, -1), (back0, 1), (back1, 1), (back1, -1)):
        pts.append((cx - dx * b + s * nx * width / 2, cy - dy * b + s * ny * width / 2))
    return pts

def dashed_poly(d, pts, col, w=2, dash=8):
    pts = [P(*p) for p in pts] + [P(*pts[0])]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        L = math.hypot(bx - ax, by - ay); n = max(int(L / dash), 1)
        for k in range(0, n, 2):
            t0, t1 = k / n, min((k + 1) / n, 1)
            d.line([(ax + (bx - ax) * t0, ay + (by - ay) * t0), (ax + (bx - ax) * t1, ay + (by - ay) * t1)], fill=col, width=w)

def polys_overlap(a, b):
    """Separating axis test for two convex quads."""
    for poly in (a, b):
        for i in range(len(poly)):
            x0, y0 = poly[i]; x1, y1 = poly[(i + 1) % len(poly)]
            nx, ny = y1 - y0, x0 - x1
            pa = [nx * x + ny * y for x, y in a]; pb = [nx * x + ny * y for x, y in b]
            if max(pa) <= min(pb) or max(pb) <= min(pa):
                return False
    return True

def circle_hits(poly, cx, cy, r):
    # coarse: sample the circle
    pts = [(cx + r * math.cos(2 * math.pi * k / 24), cy + r * math.sin(2 * math.pi * k / 24)) for k in range(24)] + [(cx, cy)]
    def inside(px, py):
        s = None
        for i in range(4):
            x0, y0 = poly[i]; x1, y1 = poly[(i + 1) % 4]
            c = (x1 - x0) * (py - y0) - (y1 - y0) * (px - x0)
            if s is None: s = c > 0
            elif (c > 0) != s: return False
        return True
    return any(inside(*p) for p in pts)

def muzzle_on_wall(deg, offset_x=0.0, heading_deg=None, back=0.0):
    """Gun whose muzzle sits at the wall's outer face at bearing deg (0 ahead, +90 starboard); returns (x, y, heading)."""
    h = math.radians(deg if heading_deg is None else heading_deg)
    if abs(deg) >= 90:
        return math.copysign(R, deg), CY - back, h
    a = math.radians(deg)
    return R * math.sin(a) + offset_x, CY + R * math.cos(a), h

def straight_ahead(x, heading_deg=0.0):
    """Gun at lateral offset x pointing (nearly) ahead; muzzle where its axis meets the outer wall face."""
    h = math.radians(heading_deg)
    # walk along the axis from inside until outside the semicircle
    y = CY
    while math.hypot(x, y - CY) < R: y += 0.01
    return x, y, h

def draw(fname, title, guns, mast_y, lower=False, notes=()):
    img = Image.new('RGB', (W, H + 120), 'white'); d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype('/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf', 15)
        fb = ImageFont.truetype('/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf', 18)
    except OSError:
        f = fb = ImageFont.load_default()
    # 1 m grid
    for gx in range(math.ceil(X0), math.floor(X1) + 1):
        d.line([P(gx, Y0), P(gx, Y1)], fill=(235, 235, 235))
    for gy in range(math.ceil(Y0), math.floor(Y1) + 1):
        d.line([P(X0, gy), P(X1, gy)], fill=(235, 235, 235))
        d.text((4, P(0, gy)[1] - 8), f'y {gy}', fill=(170, 170, 170), font=f)
    outer, inner = horseshoe(R), horseshoe(R - WALL)
    d.polygon([P(*p) for p in outer], fill=(225, 215, 200))
    d.polygon([P(*p) for p in inner], fill=(250, 246, 238))
    if lower:     # the ground floor opens aft onto the gun deck (side walls of the waist further out)
        d.rectangle([P(-R + WALL, YB), P(R - WALL, Y0)], fill=(250, 246, 238))
        d.text(P(-1.3, YB - 0.3), 'gun deck continues aft', fill=(120, 120, 120), font=f)
    else:
        d.line([P(-R + WALL, YB), P(R - WALL, YB)], fill=(120, 90, 60), width=3)
        d.text(P(-0.9, YB - 0.1), 'back rail', fill=(120, 90, 60), font=f)
    for s in (-1, 1):   # stairs (gun deck -> platform) behind the platform
        x = s * STAIR_X
        d.rectangle([P(x - 0.5, YB), P(x + 0.5, YB - 3.0)], outline=(150, 150, 150), width=2)
        d.text(P(x - 0.35, YB - 1.4), 'stair', fill=(150, 150, 150), font=f)
    d.ellipse([P(-HEEL, mast_y + HEEL), P(HEEL, mast_y - HEEL)], fill=(90, 60, 40))
    d.text(P(0.35, mast_y + 0.15), f'fore mast (y {mast_y:.1f})', fill=(90, 60, 40), font=f)
    # guns
    shapes = []
    for g in guns:
        kind, (x, y, h) = g
        run = rect(x, y, h, 0.0, kind['length'], kind['width'])
        rec = rect(x, y, h, kind['recoil'], kind['length'] + kind['recoil'], kind['width'])
        swept = rect(x, y, h, 0.0, kind['length'] + kind['recoil'], kind['width'])
        shapes.append((kind, swept))
        d.polygon([P(*p) for p in run], fill=tuple(int(c + (255 - c) * 0.55) for c in kind['col']), outline=kind['col'])
        dashed_poly(d, rec, kind['col'])
        # barrel axis
        d.line([P(x, y), P(x - math.sin(h) * kind['length'], y - math.cos(h) * kind['length'])], fill=kind['col'], width=2)
    clashes = []
    for i in range(len(shapes)):
        if circle_hits(shapes[i][1], 0.0, mast_y, HEEL):
            clashes.append(f'{shapes[i][0]["name"]} #{i + 1} hits the mast')
        for j in range(i + 1, len(shapes)):
            if polys_overlap(shapes[i][1], shapes[j][1]):
                clashes.append(f'#{i + 1} and #{j + 1} overlap')
    for i, (kind, sh) in enumerate(shapes):
        cx = sum(p[0] for p in sh) / 4; cy = sum(p[1] for p in sh) / 4
        d.text(P(cx - 0.1, cy + 0.15), str(i + 1), fill=(0, 0, 0), font=fb)
    d.text((10, H + 8), title, fill=(0, 0, 0), font=fb)
    ty = H + 34
    for n in notes:
        d.text((10, ty), n, fill=(60, 60, 60), font=f); ty += 19
    d.text((10, ty), 'CLASHES: ' + ('; '.join(clashes) if clashes else 'none'), fill=(190, 0, 0) if clashes else (0, 130, 0), font=f)
    img.save(os.path.join(OUT, fname))
    print(fname, clashes or 'ok')

legend = (f'culverin footprint {CULVERIN["length"]:.1f} x {CULVERIN["width"]} m, recoil {CULVERIN["recoil"]} m; '
          f'falcon {FALCON["length"]:.1f} x {FALCON["width"]} m, recoil {FALCON["recoil"]} m; '
          'solid = run out, dashed = recoiled; 1 m grid')

# A: what was planned - radial guns at 0/+-45 (culverins) and +-90 (falcons), mast where it is
guns = [(CULVERIN, muzzle_on_wall(d)) for d in (-45, 0, 45)] + [(FALCON, muzzle_on_wall(d, back=0.6)) for d in (-90, 90)]
draw('layout_A_radial_platform.png', 'A  platform, radial embrasures 0/+-45 culverins, +-90 falcons (current model)',
     guns, MAST_PLATFORM, notes=(legend,))

# B: culverins side by side pointing ahead / slightly out, mast where it is
guns = [(CULVERIN, straight_ahead(-1.55, -5)), (CULVERIN, straight_ahead(1.55, 5)),
        (FALCON, (-R, 19.35, math.radians(-90))), (FALCON, (R, 19.35, math.radians(90)))]
draw('layout_B_parallel_mast_stays.png', 'B  platform, 2 culverins side by side (5 deg out), mast stays at y 20.9',
     guns, MAST_PLATFORM, notes=(legend, 'centre gun impossible (mast on its axis); +-90 falcons: embrasures moved aft to y 19.35'))

# C: mast moved aft behind the forecastle, three culverins side by side, falcons at +-90 moved aft
mast_c = 17.2
guns = [(CULVERIN, straight_ahead(-1.55, -5)), (CULVERIN, straight_ahead(0.0, 0)), (CULVERIN, straight_ahead(1.55, 5)),
        (FALCON, (-R, 19.35, math.radians(-90))), (FALCON, (R, 19.35, math.radians(90)))]
draw('layout_C_parallel_mast_aft.png', f'C  platform, 3 culverins side by side, fore mast moved aft to y {mast_c}',
     guns, mast_c, notes=(legend, '+-90 falcons: embrasures moved aft to y 19.35'))

# D: ground floor, three culverins side by side through the round ports, mast where it is (heel lower down)
guns = [(CULVERIN, straight_ahead(-1.55, -5)), (CULVERIN, straight_ahead(0.0, 0)), (CULVERIN, straight_ahead(1.55, 5))]
guns_lo2 = [(CULVERIN, straight_ahead(-1.55, -5)), (CULVERIN, straight_ahead(1.55, 5))]
draw('layout_F_lower_two_mast_stays.png', 'F  ground floor, 2 culverins (round ports at ~+-24 deg), mast stays', guns_lo2, MAST_LOWER, lower=True, notes=(legend,))
draw('layout_D_lower_mast_stays.png', 'D  ground floor, 3 culverins side by side, mast stays', guns, MAST_LOWER, lower=True,
     notes=(legend,))
draw('layout_E_lower_mast_aft.png', f'E  ground floor, 3 culverins side by side, mast at y {mast_c}', guns, mast_c, lower=True,
     notes=(legend,))

# --- 2026-10-13 (user): culverins only on the ground floor, falconets on the platform, fore mast stays in the
# forecastle but may move aft to the platform's rear edge
FALCONET = dict(name='falconet', length=float(os.environ.get('FT_LEN', 1.85 + 0.35)), width=0.75,
                recoil=float(os.environ.get('FT_REC', 0.6)), col=(60, 140, 90))
MAST_AFT = float(os.environ.get('MAST_AFT', 19.0))
mast_aft_lower = MAST_AFT + (G['Z_GUN_DECK'] + 0.8 - G['FC_Z_PLATFORM']) * math.tan(G['FORE_RAKE'])
ft_legend = (f'falconet {FALCONET["length"]:.1f} x {FALCONET["width"]} m, recoil {FALCONET["recoil"]} m; '
             'solid = run out, dashed = recoiled; 1 m grid')
guns = [(FALCONET, muzzle_on_wall(d)) for d in (-45, 0, 45)] + [(FALCONET, muzzle_on_wall(d, back=0.6)) for d in (-90, 90)]
draw('layout_G_platform_falconets.png', f'G  platform, 5 falconets on the current embrasures, mast aft to y {MAST_AFT}',
     guns, MAST_AFT, notes=(ft_legend,))
for brg, out in ((24, 5), (30, 10)):
    xo = R * math.sin(math.radians(brg))
    guns = [(CULVERIN, straight_ahead(-xo, -out)), (CULVERIN, straight_ahead(0.0, 0)), (CULVERIN, straight_ahead(xo, out))]
    draw(f'layout_H_lower_culverins_{brg}.png', f'H  ground floor, 3 culverins, side ports at +-{brg} deg ({out} deg out), '
         f'mast y {mast_aft_lower:.2f} at this level', guns, mast_aft_lower, lower=True, notes=(legend,))
