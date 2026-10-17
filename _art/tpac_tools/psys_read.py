"""Summarise emitters of a decoded psys segment: python3 psys_read.py seg.bin"""
import struct, re, sys
d = open(sys.argv[1], 'rb').read()
F = lambda o: struct.unpack_from('<f', d, o)[0]
I = lambda o: struct.unpack_from('<i', d, o)[0]
names = [(m.start(), m.group().decode()) for m in re.finditer(rb'(?<=[\x00-\x1f])[A-Z][A-Za-z _-]{2,}(?=\x00)', d)]
bounds = [s for s, _ in names] + [len(d)]
def curve(o, n):
    segs = [[round(F(o + 32 * k + 4 * j), 3) for j in range(8)] for k in range(n)]
    keys = [(s[0], s[1]) for s in segs] + ([(segs[-1][4], segs[-1][5])] if segs else [])
    return keys, o + 32 * n
for idx, (st, nm) in enumerate(names):
    end = bounds[idx + 1]
    flags = [x.decode() for x in re.findall(rb'[a-z_]{4,}', d[st:d.find(b'particle_spawn', st) + 14])]
    print(f'== {nm}  material {d[st-20:st-4].hex()}  flags {flags}')
    def parse(o):
        recs = []
        try:
            while o + 32 <= end and F(o + 8) == 0 and F(o + 12) == 1 and F(o + 16) == 1 and 0 <= I(o + 20) < 20:
                base, bias = round(F(o), 4), round(F(o + 4), 4)
                ec = I(o + 20); o += 24
                ek, o = curve(o, ec)
                o += 4; flag = F(o); o += 4
                pk = None
                if flag == 1:
                    mult, pc = round(F(o), 3), I(o + 4); o += 8
                    if not 0 < pc < 30: break
                    pk, o = curve(o, pc); pk = (mult, pk); o += 8
                recs.append((base, bias, ek if ec else None, pk))
        except struct.error:
            pass
        return recs, o
    s0 = d.find(b'particle_spawn', st) + 14
    recs, o = max((parse(q) for q in range(s0, min(end, s0 + 700))), key=lambda r: len(r[0]))
    for i, r in enumerate(recs):
        s = f'  r{i:02d} {r[0]} ± {r[1]}'
        if r[2]: s += f'  emitterCurve {r[2]}'
        if r[3]: s += f'  particleCurve x{r[3][0]} {r[3][1]}'
        print(s)
    m = next(m for m in range(o, end - 8) if I(m) in (868, 869) and F(m + 8) == 0)
    c = I(m + 12); p = m + 16
    print('  colour', [[round(F(p + 20 * k + 4 * j), 3) for j in range(5)] for k in range(c)]); p += 20 * c
    a = I(p); p += 4
    print('  alpha', [(round(F(p + 8 * k), 3), round(F(p + 8 * k + 4), 3)) for k in range(a)]); p += 8 * a
    print('  after alpha', [round(F(p + 4 * k), 3) for k in range(20)])
    hits = [(q - st, round(F(q), 3)) for q in range(st, end - 4) if abs(F(q) + 2.6) < 1e-4 or abs(F(q) + 0.15) < 1e-4]
    print('  -2.6/-0.15 found at', hits)
