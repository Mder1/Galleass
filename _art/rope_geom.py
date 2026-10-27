"""Rope geometry for the gun rigging (Blender bmesh): laid rope tubes with their own UVs, rope rings, sagging spans,
iron ringbolts and wooden tackle blocks. Used by cannon_model.py (lashings and breeching collars on the guns) and
gun_rigging.py (breechings and side tackles from the guns to the ship).

Rope UVs: the laid-rope strip of the vanilla ship_ropes texture (Kit material galleass_rope, textures
galleass_rope_d/_n/_s): U round the rope inside ROPE_U, V along it at V_PER_M, so the strands keep their proportions
(the strip is ~120 px wide for one turn; 4096 px tall). export_guns.py / gun_rigging.py keep these UVs.
"""
import math
import bmesh
from mathutils import Vector

ROPE_U = (0.765, 0.985)                   # laid-rope strip of ship_ropes_d (u), one turn round the rope
UV_NAME = 'UVMap'

def v_per_m(r):
    """V per metre for a rope of radius r: keep the texel aspect (strip ~120 px round, texture 4096 px tall)."""
    circ = 2 * math.pi * r
    return (120.0 / circ) / 4096.0

def uv_layer(bm):
    return bm.loops.layers.uv.get(UV_NAME) or bm.loops.layers.uv.new(UV_NAME)

def catmull(points, step):
    """Catmull-Rom through points, resampled to about 'step' spacing (keeps the end points)."""
    P = [Vector(p) for p in points]
    if len(P) < 3:
        out = [P[0]]
        L = (P[1] - P[0]).length
        n = max(int(math.ceil(L / step)), 1)
        return [P[0].lerp(P[1], k / n) for k in range(n + 1)]
    ext = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = [P[0]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        n = max(int(math.ceil((p2 - p1).length / step)), 1)
        for k in range(1, n + 1):
            t = k / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return out

def sag_span(p0, p1, sag, n=10):
    """Points of a rope hanging between p0 and p1 (parabola, 'sag' metres down at mid-span)."""
    p0, p1 = Vector(p0), Vector(p1)
    return [p0.lerp(p1, k / n) - Vector((0, 0, sag * 4 * (k / n) * (1 - k / n))) for k in range(n + 1)]

def rope(bm, pts, r, segs=6, caps=True, v0=0.0, u_range=None, vpm=None):
    """Tube along pts (Vectors) with parallel-transported frames (no twisting) and rope UVs (u_range: the texture's
    rope strip, default ROPE_U; vpm: V per metre along the rope, default v_per_m(r)). Returns the V at the end (to
    continue a rope seamlessly)."""
    uvl = uv_layer(bm)
    pts = [Vector(p) for p in pts]
    n = len(pts)
    tans = []
    for i in range(n):
        t = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        tans.append(t.normalized() if t.length > 1e-9 else Vector((0, 1, 0)))
    ref = Vector((0, 0, 1)) if abs(tans[0].z) < 0.9 else Vector((1, 0, 0))
    u = (ref - tans[0] * ref.dot(tans[0])).normalized()
    rings, vs = [], []
    v = v0; vpm = vpm if vpm is not None else v_per_m(r)
    for i, p in enumerate(pts):
        if i:
            t0, t1 = tans[i - 1], tans[i]
            ax = t0.cross(t1)
            if ax.length > 1e-9:
                ang = t0.angle(t1)
                from mathutils import Matrix
                u = (Matrix.Rotation(ang, 3, ax.normalized()) @ u)
            u = (u - t1 * u.dot(t1)).normalized()
            v += (p - pts[i - 1]).length * vpm
        w = tans[i].cross(u)
        rings.append([bm.verts.new(p + (u * math.cos(2 * math.pi * k / segs) + w * math.sin(2 * math.pi * k / segs)) * r)
                      for k in range(segs)])
        vs.append(v)
    u0, u1 = u_range or ROPE_U
    for i in range(n - 1):
        ra, rb = rings[i], rings[i + 1]
        for k in range(segs):
            f = bm.faces.new((ra[k], ra[(k + 1) % segs], rb[(k + 1) % segs], rb[k]))
            uk0, uk1 = u0 + (u1 - u0) * k / segs, u0 + (u1 - u0) * (k + 1) / segs
            for loop, uv in zip(f.loops, ((uk0, vs[i]), (uk1, vs[i]), (uk1, vs[i + 1]), (uk0, vs[i + 1]))):
                loop[uvl].uv = uv
    if caps:
        for ring, vv in ((rings[0][::-1], vs[0]), (rings[-1], vs[-1])):
            f = bm.faces.new(ring)
            for loop in f.loops:
                loop[uvl].uv = (u0 + 0.02, vv)
    return v

def ring(bm, c, axis, R, r, segs=12, tube=6, role_uv='rope', u_range=None, vpm=None):
    """Torus centred at c, its axis 'axis' (normal of the ring's plane), radius R, tube radius r. role_uv 'rope':
    rope UVs (a seized rope collar); anything else: planar-ish UVs (iron ring, the export remaps them)."""
    c, axis = Vector(c), Vector(axis).normalized()
    a = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))
    e1 = (a - axis * a.dot(axis)).normalized(); e2 = axis.cross(e1)
    pts = [c + (e1 * math.cos(2 * math.pi * i / segs) + e2 * math.sin(2 * math.pi * i / segs)) * R for i in range(segs)]
    pts.append(pts[0])
    if role_uv == 'rope':
        rope(bm, catmull(pts, 2 * math.pi * R / segs), r, segs=tube, caps=False, u_range=u_range, vpm=vpm)
    else:
        rope(bm, pts, r, segs=tube, caps=False)

def eyebolt(bm, base, out, length, r):
    """Short round bar from base along 'out' (into a wall / cheek face: base on the surface)."""
    base, out = Vector(base), Vector(out).normalized()
    rope(bm, [base - out * 0.02, base + out * length], r, segs=8, caps=True)

def block(bm, c, along, across, length, width, thick):
    """Wooden tackle block: a rounded shell (ellipsoid-like, flattened) centred at c, long axis 'along', the sheave
    axis 'across' (its thin direction)."""
    c, along, across = Vector(c), Vector(along).normalized(), Vector(across).normalized()
    side = along.cross(across).normalized()
    across = side.cross(along).normalized()
    segs_u, segs_v = 8, 4
    rows = []
    for i in range(segs_v + 1):
        th = math.pi * i / segs_v - math.pi / 2
        row = []
        for k in range(segs_u):
            ph = 2 * math.pi * k / segs_u
            x = math.cos(th) * math.cos(ph); y = math.cos(th) * math.sin(ph); z = math.sin(th)
            # squarer sides than an ellipsoid
            sx = math.copysign(abs(x) ** 0.7, x); sy = math.copysign(abs(y) ** 0.7, y)
            row.append(bm.verts.new(c + side * sx * width / 2 + along * sy * length / 2 + across * z * thick / 2))
        rows.append(row)
    uvl = uv_layer(bm)
    for i in range(segs_v):
        for k in range(segs_u):
            f = bm.faces.new((rows[i][k], rows[i][(k + 1) % segs_u], rows[i + 1][(k + 1) % segs_u], rows[i + 1][k]))
            for loop in f.loops:
                p = loop.vert.co - c
                loop[uvl].uv = (p.dot(along) * 0.6 + 0.3, p.dot(side) * 0.6 + 0.3)
    bmesh.ops.remove_doubles(bm, verts=[v for row in rows for v in row], dist=1e-6)

def coil_points(c, r_rope, r_in, r_out, turns=2.5, step=0.06, start_dir=None):
    """Flat (Flemish) coil lying on the deck centred at c (z = deck + rope radius), from the outside in. Returns the
    spiral's points; start_dir points from the centre to where the coil begins."""
    c = Vector(c)
    a0 = math.atan2(start_dir.y, start_dir.x) if start_dir is not None else 0.0
    pts = []
    total = turns * 2 * math.pi
    n = max(int(total * (r_in + r_out) / 2 / step), 8)
    for k in range(n + 1):
        t = k / n
        a = a0 + t * total
        rr = r_out + (r_in - r_out) * t
        pts.append(c + Vector((math.cos(a) * rr, math.sin(a) * rr, 0.0)))
    return pts

def heap_points(c, r_rope, seed, scale=1.0, step=0.05, start_dir=None, max_h=None):
    """Hauling end left lying in a loose heap of loops on the deck (user 2026-10-13: not a neat flat coil, and no two
    alike): 5-8 irregular loops, each a wobbly ellipse with its own centre drift, size and tilt, rising by a rope's
    thickness per loop so the loops lie on each other instead of through each other. Deterministic per seed.
    max_h: cap the heap's height - a thick rope makes fewer loops (2026-10-27: thick heaps stood up like springs)."""
    import random
    rnd = random.Random(seed)
    c = Vector(c)
    a = math.atan2(start_dir.y, start_dir.x) if start_dir is not None else rnd.uniform(0, 2 * math.pi)
    turns = rnd.uniform(5.5, 8.0)
    if max_h is not None:
        turns = max(min(turns, max_h / (2.15 * r_rope)), 2.0)
    sense = rnd.choice((-1, 1))
    total = turns * 2 * math.pi
    rise = 2.15 * r_rope / (2 * math.pi)                  # per radian: one rope diameter (+) per loop
    # slow random walk of the loop centre, radius and ellipse shape along the rope
    knots = int(turns * 2) + 3
    walk = [(rnd.uniform(-0.06, 0.06), rnd.uniform(-0.06, 0.06), rnd.uniform(0.65, 1.3), rnd.uniform(0.5, 1.0),
             rnd.uniform(0, math.pi)) for _ in range(knots)]
    wob_f, wob_ph = rnd.uniform(3.0, 5.0), rnd.uniform(0, 2 * math.pi)
    def at(t):
        x = t * (knots - 1); i = min(int(x), knots - 2); f = x - i
        f = f * f * (3 - 2 * f)
        return [walk[i][j] + (walk[i + 1][j] - walk[i][j]) * f for j in range(5)]
    r0 = 0.10 * scale
    pts = []
    n = max(int(total * r0 / step), 12)
    tilt_amp = 0.35 * 2.15 * r_rope                       # tilt stays under the rise, so loops never cut each other
    tilt_ph = rnd.uniform(0, 2 * math.pi)
    for k in range(n + 1):
        t = k / n
        th = a + sense * t * total
        dx, dy, rs, ecc, rot = at(t)
        rr = r0 * rs * (1.0 - 0.25 * t) * (1 + 0.09 * math.sin(wob_f * th + wob_ph))   # kinks of a used rope
        ex, ey = math.cos(th - rot) * rr, math.sin(th - rot) * rr * ecc
        x = ex * math.cos(rot) - ey * math.sin(rot) + dx * scale
        y = ex * math.sin(rot) + ey * math.cos(rot) + dy * scale
        z = r_rope + rise * t * total + tilt_amp * math.sin(th + tilt_ph) * min(t * 4, 1.0)
        pts.append(c + Vector((x, y, z)))
    return pts
