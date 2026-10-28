"""Wood grain UVs shared by the generators (UV audit 2026-10-28). The ship wood (galleass_ship_meditheavy_plank_a_d, used by
trim / hull / dark) has its grain along U and is a sheet of 14 planks across V with dark gaps between them; the deck wood
has its grain along V; the oar wood of the masts along V (mast_model.py handles those).
- plank_fit: a narrow part goes inside one plank, so no gap line runs along it (user 2026-10-27: dark streak down the
  stern post, gap rings round the lantern post).
- mirrored(): V round a part goes 0 -> half the circumference -> 0, so it meets itself without a seam.
- piece_uvs: per connected piece, grain along the piece (PCA axis); long pieces get V round them (mirrored), the rest
  planar per face (the per-generator dominant-axis projections put the grain across pins, posts, legs and staffs).
- follow_quads: quad strips unrolled like Blender's 'Follow Active Quads' (edge-ring average lengths): U along the strip,
  V round its section, no jump at every facet (the per-face projection did that on the curved castle bands and the spur).
"""
import math, zlib
from collections import defaultdict
from mathutils import Vector

PLANK_N = 14                         # planks per tile across V; gaps at PLANK_GAP + k / 14 (measured on the 4k map, the
PLANK_GAP = -0.001                   # same within 0.004 whether the engine flips V or not)
PLANK_BAND = 0.046                   # usable height of one plank (0.071) clear of the gap lines

def plank_fit(vmin, vmax, key):
    """(offset, scale) for v -> v * scale + offset: [vmin, vmax] centred in one plank (picked by key), squeezed into it
    up to 1.5 planks' height; wider pieces keep their scale and read as several boards."""
    span = vmax - vmin
    if span > 1.5 * PLANK_BAND:
        return 0.0, 1.0
    sc = min(1.0, PLANK_BAND / span) if span > 1e-9 else 1.0
    k = zlib.crc32(key.encode()) % PLANK_N
    vc = PLANK_GAP + (k + 0.5) / PLANK_N
    return vc - (vmin + vmax) / 2 * sc, sc

def mirrored(f):
    """0..1 round a part -> 0..1..0: continuous where the part meets itself."""
    f %= 1.0
    return 1.0 - abs(2.0 * f - 1.0)

def _pieces(me, polys):
    parent = {}
    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for pi in polys:
        vs = me.polygons[pi].vertices
        for v in vs[1:]:
            ra, rb = find(vs[0]), find(v)
            if ra != rb: parent[ra] = rb
    out = defaultdict(list)
    for pi in polys:
        out[find(me.polygons[pi].vertices[0])].append(pi)
    return list(out.values())

def _axis(cos):
    import numpy as np
    co = np.array([c[:] for c in cos])
    c = co.mean(0)
    w, vec = np.linalg.eigh((co - c).T @ (co - c))
    w = np.sqrt(np.maximum(w, 1e-12))
    return Vector(c), Vector(vec[:, -1]).normalized(), float(w[-1] / max(w[-2], 1e-9)), Vector(vec[:, 0]).normalized(), \
        float(w[-2] / max(w[0], 1e-9))

def piece_uvs(me, uv, polys, scale, plank, key, round_min=2.0):
    """UVs for the polygons `polys` of mesh me (uv: its uv layer data), piece by piece. scale(pi): UV units per metre;
    plank(pi): True for the plank wood (fit into one plank)."""
    for n_piece, piece in enumerate(_pieces(me, polys)):
        vids = {v for pi in piece for v in me.polygons[pi].vertices}
        c, a, elong, a3, flat = _axis([me.vertices[v].co for v in vids])
        # long piece: round its long axis (U along, V round); flat round piece (hoop, band, ring): round its short axis
        # (U round, along the band; V across); else planar per face
        mode = 'long' if elong >= round_min else 'ring' if flat >= round_min else None
        ax = a if mode == 'long' else a3
        w = (Vector((0, 0, 1)) if abs(ax.z) < 0.9 else Vector((1, 0, 0)))
        w = (w - ax * w.dot(ax)).normalized(); w2 = ax.cross(w)
        rad = sum(((me.vertices[v].co - c) - ax * (me.vertices[v].co - c).dot(ax)).length for v in vids) / len(vids)
        groups = defaultdict(list)                      # loops that are fitted into a plank together
        for pi in piece:
            p = me.polygons[pi]; n = p.normal; s = scale(pi)
            if mode and abs(n.dot(ax)) < (0.85 if mode == 'long' else 0.6):   # (long: bevels too, no seam at them)
                for li in p.loop_indices:
                    d = me.vertices[me.loops[li].vertex_index].co - c
                    th = mirrored(math.atan2(d.dot(w2), d.dot(w)) / (2 * math.pi)) * math.pi * rad * s
                    uv[li].uv = (d.dot(ax) * s, th) if mode == 'long' else (th, d.dot(ax) * s)
                groups['round'].append(pi)
                continue
            u = a - n * a.dot(n)                            # planar, U along the piece's axis (end faces: across)
            if u.length < 0.3:
                for alt in (Vector((0, 0, 1)), Vector((0, 1, 0)), Vector((1, 0, 0))):
                    u = alt - n * alt.dot(n)
                    if u.length >= 0.3: break
            u.normalize(); v = n.cross(u).normalized()
            for li in p.loop_indices:
                d = me.vertices[me.loops[li].vertex_index].co - c
                uv[li].uv = (d.dot(u) * s, d.dot(v) * s)
            groups[tuple(round(x, 2) for x in (*u, *v))].append(pi)
        for g, pis in groups.items():
            if not plank(pis[0]):
                continue
            lis = [li for pi in pis for li in me.polygons[pi].loop_indices]
            off, sc = plank_fit(min(uv[li].uv[1] for li in lis), max(uv[li].uv[1] for li in lis), f'{key}:{n_piece}')
            for li in lis:
                uv[li].uv = (uv[li].uv[0], uv[li].uv[1] * sc + off)

def follow_quads(bm, uvl, scale, plank_key=None, faces=None):
    """Unroll the quads of bm (or of `faces`) island by island: each quad a rectangle whose sides are the average
    lengths of its edge rings, U along the longer extent of the island (the grain), V across; non-quads keep their
    UVs. plank_key: fit each island's V into one plank."""
    quads = [f for f in (faces if faces is not None else bm.faces) if len(f.verts) == 4]
    qs = set(quads)
    parent = {}
    def find(e):
        while parent.setdefault(e, e) is not e:
            parent[e] = parent[parent[e]]; e = parent[e]
        return e
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra is not rb: parent[ra] = rb
    for f in quads:
        es = [l.edge for l in f.loops]
        union(es[0], es[2]); union(es[1], es[3])
    tot = defaultdict(lambda: [0.0, 0])
    for f in quads:
        for l in f.loops:
            r = tot[find(l.edge)]; r[0] += l.edge.calc_length(); r[1] += 1
    L = {k: t / n for k, (t, n) in tot.items()}
    size = {k: n for k, (t, n) in tot.items()}
    seen = set(); islands = []
    for seed in quads:
        if seed in seen:
            continue
        l0, l1, l2, l3 = seed.loops
        a, b = L[find(l0.edge)], L[find(l1.edge)]
        for l, q in zip((l0, l1, l2, l3), ((0, 0), (a, 0), (a, b), (0, b))):
            l[uvl].uv = q
        # rings round the section (the seed's shorter ring) are crossed only in the seed's own column: every other quad is
        # reached along the strip, so the unrolled grid has one straight seam instead of a zigzag (or a spiral that made V
        # the long side and turned the grain across)
        col = min(size[find(l0.edge)], size[find(l1.edge)])
        around_v = size[find(l0.edge)] <= size[find(l1.edge)]   # crossing l0's edge (along U) goes round: V is round
        closed = False
        seen.add(seed); isl = [seed]; queue = [(seed, True)]
        while queue:
            f, in_col = queue.pop(0)
            fuv = {l.vert: l[uvl].uv.copy() for l in f.loops}
            fc = sum(fuv.values(), Vector((0, 0))) / 4
            for l in f.loops:
                for g in l.edge.link_faces:
                    if g is f or g not in qs:
                        continue
                    around = size[find(l.edge)] <= col
                    if g in seen:
                        closed = closed or (around and in_col and g in isl)   # the seed's column closes round
                        continue
                    if around and not in_col:
                        continue
                    gl = next(x for x in g.loops if x.edge is l.edge)
                    gn = gl.link_loop_next
                    ua, ub = fuv[gl.vert], fuv[gn.vert]
                    d = ub - ua
                    if d.length < 1e-12:
                        continue
                    perp = Vector((-d.y, d.x)).normalized()
                    if perp.dot(fc - ua) > 0:
                        perp = -perp
                    step = L[find(gn.edge)]
                    g2 = gn.link_loop_next; g3 = g2.link_loop_next
                    gl[uvl].uv = ua; gn[uvl].uv = ub
                    g2[uvl].uv = ub + perp * step; g3[uvl].uv = ua + perp * step
                    seen.add(g); isl.append(g); queue.append((g, in_col and around))
        islands.append((isl, closed, around_v))
    for k, (isl, closed, around_v) in enumerate(islands):
        ls = [l for f in isl for l in f.loops]
        us = [l[uvl].uv[0] for l in ls]; vs = [l[uvl].uv[1] for l in ls]
        swap = max(vs) - min(vs) > max(us) - min(us)
        s = scale
        for l in ls:
            x, y = l[uvl].uv
            l[uvl].uv = ((y, x) if swap else (x, y))
            l[uvl].uv = (l[uvl].uv[0] * s, l[uvl].uv[1] * s)
        if closed and around_v != swap:                      # closed section round V: mirrored, no seam where it meets
            vs = [l[uvl].uv[1] for l in ls]; v0, P = min(vs), max(vs) - min(vs)
            if P > 1e-9:
                for l in ls:
                    l[uvl].uv = (l[uvl].uv[0], v0 + mirrored((l[uvl].uv[1] - v0) / P) * P / 2)
        if plank_key is not None:
            vs = [l[uvl].uv[1] for l in ls]
            off, sc = plank_fit(min(vs), max(vs), f'{plank_key}:{k}')
            for l in ls:
                l[uvl].uv = (l[uvl].uv[0], l[uvl].uv[1] * sc + off)
    return len(islands)
