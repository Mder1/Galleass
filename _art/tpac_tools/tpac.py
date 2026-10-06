import struct, uuid, sys, os, lz4.block
TEX = uuid.UUID('c974cbcb-5f1c-49f6-9a32-2b5b6c92c2e8')
PIX = uuid.UUID('70ee4e2c-79e4-4b2d-8d54-d53ecd2a559c')
class R:
    def __init__(s, f): s.f = f
    def u32(s): return struct.unpack('<I', s.f.read(4))[0]
    def i32(s): return struct.unpack('<i', s.f.read(4))[0]
    def u64(s): return struct.unpack('<Q', s.f.read(8))[0]
    def u16(s): return struct.unpack('<H', s.f.read(2))[0]
    def b(s): return s.f.read(1)[0]
    def guid(s): return uuid.UUID(bytes_le=s.f.read(16))
    def str(s):
        n = s.i32(); return s.f.read(n).decode('utf8', 'replace') if n else ''
    def strlist(s): return [s.str() for _ in range(s.i32())]

def read_tex_meta(r, size):
    p = r.f.tell(); m = {}
    ver = r.u32(); r.guid(); r.u32(); m['source'] = r.str(); r.u64(); r.b(); r.u32()
    m['flags'] = r.strlist(); u3 = r.u32(); r.b()
    m['w'] = r.u32(); m['h'] = r.u32(); r.u32(); m['mips'] = r.b(); m['arr'] = r.u16()
    m['fmt'] = r.str(); r.u32(); m['sysflags'] = r.strlist()
    r.f.seek(p + size); return m

def scan(path):
    out = []
    with open(path, 'rb') as f:
        r = R(f)
        if r.u32() != 0x43415054: return out
        ver = r.u32(); r.guid(); n = r.u32(); r.u32(); r.u32()
        for _ in range(n):
            tg = r.guid(); g = r.guid()
            if ver > 1: r.u32()
            name = r.str(); ms = r.u64(); p = f.tell()
            meta = read_tex_meta(r, ms) if tg == TEX else None
            f.seek(p + ms); r.u64()
            segs = []
            for _ in range(r.i32()):
                off, act, sto = r.u64(), r.u64(), r.u64(); r.guid(); st = r.guid(); r.u64(); r.u32(); fmt = r.b()
                segs.append((st, off, act, sto, fmt))
            for _ in range(r.i32()): f.read(48)
            if meta is not None:
                meta.update(name=name, path=path, segs=segs); out.append(meta)
    return out

def pixels(meta):
    for st, off, act, sto, fmt in meta['segs']:
        if st == PIX:
            with open(meta['path'], 'rb') as f:
                f.seek(off); d = f.read(sto)
            return lz4.block.decompress(d, uncompressed_size=act) if fmt == 1 else d

BPP = {'DXT1': 4, 'BC4': 4, 'DXT3': 8, 'DXT5': 8, 'BC5': 8, 'BC7': 8, 'BC6H_UF16': 8, 'R8G8B8A8_UNORM': 32, 'B8G8R8A8_UNORM': 32}
def mip_chain(meta, data):
    bpp = BPP[meta['fmt']]; blk = meta['fmt'] not in ('R8G8B8A8_UNORM', 'B8G8R8A8_UNORM')
    w, h, o, res = meta['w'], meta['h'], 0, []
    for m in range(meta['mips']):
        aw = (w + 3) // 4 * 4 if blk else w; ah = (h + 3) // 4 * 4 if blk else h
        sz = aw * ah * bpp // 8; res.append((w, h, data[o:o + sz])); o += sz
        w, h = max(w >> 1, 1), max(h >> 1, 1)
    return res
