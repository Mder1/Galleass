"""Barrel elevation of the galleass guns, without Blender: shared by cannon_model.py (quoin + bed geometry) and the
gunnery add-on (via ref/galleass_guns.json: 'elev').

The barrel turns on its trunnions; the breech rests on the quoin (cuneo), a wedge with its thick end to the rear lying
on the bed. Pulling the quoin back lowers the breech (muzzle up), pushing it in raises it. For each elevation the
quoin's slide is solved so the wedge just touches the barrel's underside (profile incl. base ring and cascabel), so
the add-on only interpolates a table. Profile coordinates: y from the base ring's rear face forward, z above the deck.

QUOIN per gun: zb = bed top under the quoin (culverin: a stool block on its bed plank; falcons: under_base - zb_below), s = slope of
the wedge's top (rise per metre towards the thick end), L = length, yt = thick end's y at zero elevation, elevation
range in degrees (culverin: the round port leaves only ~+-2.3 deg; falcons: carriage clearance)."""
import math

QUOIN = {
    'galleass_culverin': dict(zb=0.45, s=0.30, L=0.55, yt=-0.22, emin=-2.0, emax=2.0),
    'galleass_falcon': dict(zb_below=0.11, s=0.35, L=0.40, yt=-0.16, emin=-2.0, emax=4.0),
    'galleass_falconet': dict(zb_below=0.098, s=0.35, L=0.30, yt=-0.10, emin=-2.0, emax=5.0),
}
STEP_DEG = 0.5

def prof_r(prof, y):
    """Largest profile radius at y (profiles have vertical steps)."""
    best = 0.0
    for (y0, r0), (y1, r1) in zip(prof, prof[1:]):
        if abs(y1 - y0) < 1e-9:
            if abs(y - y0) < 1e-9: best = max(best, r0, r1)
        elif min(y0, y1) <= y <= max(y0, y1):
            best = max(best, r0 + (r1 - r0) * (y - y0) / (y1 - y0))
    return best

def underside(prof, ah, ty, tz, e, n=800):
    """Barrel underside points (y, z) after elevating by e (radians, muzzle up) about the trunnion axis (ty, tz)."""
    c, s = math.cos(e), math.sin(e)
    y0 = min(p[0] for p in prof); y1 = max(p[0] for p in prof)
    out = []
    for i in range(n + 1):
        y = y0 + (y1 - y0) * i / n
        dy, dz = y - ty, ah - prof_r(prof, y) - tz
        out.append((ty + dy * c - dz * s, tz + dy * s + dz * c))
    return out

def _gap(pts, top, ya, yb):
    g = 1e9
    for y, z in pts:
        if ya <= y <= yb:
            g = min(g, z - top(y))
    return g

class Quoin:
    """Wedge of one gun: thick end height ht (above zb) is chosen so it touches the barrel at zero elevation."""
    def __init__(self, gun, prof, ah, ty, tz, zb):
        q = QUOIN[gun]
        self.gun, self.prof, self.ah, self.ty, self.tz = gun, prof, ah, ty, tz
        self.zb, self.s, self.L, self.yt = zb, q['s'], q['L'], q['yt']
        self.emin, self.emax = q['emin'], q['emax']
        pts = underside(prof, ah, ty, tz, 0.0)
        self.ht = _gap(pts, lambda y: zb - self.s * (y - self.yt), self.yt, self.yt + self.L)
        self.hthin = self.ht - self.s * self.L
        assert self.hthin > 0.015, '%s: quoin thin end %.3f m - shorter or flatter wedge' % (gun, self.hthin)

    def top(self, y, slide):
        """Wedge top at y with the wedge pulled back by slide."""
        return self.zb + self.ht - self.s * (y - (self.yt - slide))

    def slide_for(self, e_deg):
        """Slide (m, + = pulled back) at which the wedge touches the barrel at elevation e_deg."""
        pts = underside(self.prof, self.ah, self.ty, self.tz, math.radians(e_deg))
        def g(d):
            return _gap(pts, lambda y: self.top(y, d), self.yt - d, self.yt - d + self.L)
        # g grows with d near the contact (pulling back lowers the wedge); bracket the root by stepping from 0
        lo = hi = 0.0
        if g(0.0) < 0:
            while g(hi) < 0:
                hi += 0.01
                assert hi < 0.6, '%s: quoin cannot drop the breech to %.1f deg' % (self.gun, e_deg)
            lo = hi - 0.01
        else:
            while g(lo) >= 0:
                lo -= 0.01
                assert lo > -0.4, '%s: quoin cannot lift the breech to %.1f deg' % (self.gun, e_deg)
            hi = lo + 0.01
        for _ in range(50):
            m = (lo + hi) / 2
            if g(m) < 0: lo = m
            else: hi = m
        return hi

    def bed_clearance(self, e_deg, y0, y1):
        """Lowest barrel point above the bed top between y0 and y1 at elevation e_deg (must stay > 0)."""
        pts = underside(self.prof, self.ah, self.ty, self.tz, math.radians(e_deg))
        return min(z for y, z in pts if y0 <= y <= y1) - self.zb

    def table(self):
        """[(deg, slide)] from emin to emax; asserts that the slide is monotonic and the barrel clears the bed."""
        out = []
        n = int(round((self.emax - self.emin) / STEP_DEG))
        for i in range(n + 1):
            e = self.emin + i * STEP_DEG
            out.append((e, round(self.slide_for(e), 4)))
        for (e0, d0), (e1, d1) in zip(out, out[1:]):
            assert d1 > d0, '%s: quoin slide not monotonic at %.1f deg' % (self.gun, e1)
        y0 = min(p[0] for p in self.prof)
        assert self.bed_clearance(self.emax, y0, self.ty) > 0.005, '%s: breech hits the bed at %.1f deg' % (self.gun, self.emax)
        return out
