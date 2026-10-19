"""Bannerlord skeletons and skeletal animations from .tpac packages (gunnery animations, 2026-10-19).

    python3 anim_read.py <package.tpac> skeleton <name>          # bones: index, name, parent, local frame
    python3 anim_read.py <package.tpac> anim <name>              # tracks summary of a source animation
    python3 anim_read.py <package.tpac> clip <name>              # an animation clip's settings + source animation guid

Formats:
  skeleton (asset type c635a3d5, segment 11d07d37): name, int32 bone count, per bone: name, int32 parent (-1 root),
    4 vec4 = local frame rows s, f, u (the images of the bone's local x, y, z: column-vector rotation R = [s f u];
    the bone points along its local x) and origin (parent space; w unused).
  source animation (animations.tpac, type bafab007; data segment d07d816d, as TpacTool AnimationDefinitionData): name,
    int32 bone count, per bone: [uint32, uint32, int32 n, n float times (frames), n quaternions stored (w, x, y, z)] rotation
    track then the
    same for positions (vec4), then root position (vec4) and root scale (vec4) tracks. Rotations are the bones' full
    local rotations (parent space, the same convention as the skeleton's rest rows), positions their local origins.
  clip (animation_clips.tpac, type 506509c8): the asset metadata holds duration, source frame range, the source
    animation's guid, the next action and flags; the segment holds a compressed copy (not read here).
"""
import os, struct, sys, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tpac, mesh_extract

SKELETON = uuid.UUID('c635a3d5-eabb-45dd-883e-aa57e4196113')
ANIM = uuid.UUID('bafab007-7e3f-453f-bac6-e7640043112b')
CLIP = uuid.UUID('506509c8-e563-4ca4-b166-a53b92e913a7')
SEG_SKEL = '11d07d37'
SEG_ANIM = 'd07d816d'

def assets(path):
    """[(name, type guid, asset guid, metadata bytes, segments)]"""
    out = []
    with open(path, 'rb') as f:
        r = tpac.R(f)
        if r.u32() != 0x43415054:
            return out
        ver = r.u32(); r.guid(); n = r.u32(); r.u32(); r.u32()
        for _ in range(n):
            tg = r.guid(); g = r.guid()
            if ver > 1: r.u32()
            name = r.str(); ms = r.u64(); meta = f.read(ms); r.u64()
            segs = []
            for _ in range(r.i32()):
                off, act, sto = r.u64(), r.u64(), r.u64(); r.guid(); st = r.guid(); r.u64(); r.u32(); fmt = r.b()
                segs.append((st, off, act, sto, fmt))
            for _ in range(r.i32()): f.read(48)
            out.append((name, tg, g, meta, segs))
    return out

def segment(path, segs, prefix):
    for st, off, act, sto, fmt in segs:
        if str(st).startswith(prefix):
            return mesh_extract.segment(path, off, act, sto, fmt)
    return None

class Reader:
    def __init__(self, d): self.d, self.o = d, 0
    def i32(self): v = struct.unpack_from('<i', self.d, self.o)[0]; self.o += 4; return v
    def u32(self): v = struct.unpack_from('<I', self.d, self.o)[0]; self.o += 4; return v
    def f(self, n=1): v = struct.unpack_from('<%df' % n, self.d, self.o); self.o += 4 * n; return v
    def s(self): n = self.i32(); v = self.d[self.o:self.o + n].decode('latin1'); self.o += n; return v

def read_skeleton(data):
    """[(name, parent, ((sx,sy,sz), (fx,fy,fz), (ux,uy,uz), (ox,oy,oz)))]"""
    r = Reader(data)
    r.s(); n = r.i32()
    bones = []
    for _ in range(n):
        name = r.s(); parent = r.i32()
        rows = [r.f(4)[:3] for _ in range(4)]
        bones.append((name, parent, tuple(rows)))
    return bones

def read_anim(data):
    """{'name', 'bones': [{'rot': [(t, (x,y,z,w))], 'pos': [(t, (x,y,z))]}], 'root_pos': [...], 'root_scale': [...]}"""
    r = Reader(data)
    def track(width):
        r.u32(); r.u32(); n = r.i32()
        times = r.f(n)
        vals = [r.f(4) for _ in range(n)]
        if width == 4:                                    # stored w, x, y, z (TpacTool ReadQuat) -> (x, y, z, w)
            return [(t, (v[1], v[2], v[3], v[0])) for t, v in zip(times, vals)]
        return [(t, v[:3]) for t, v in zip(times, vals)]
    name = r.s(); n = r.i32()
    bones = [{'rot': track(4), 'pos': track(3)} for _ in range(n)]
    return {'name': name, 'bones': bones, 'root_pos': track(3), 'root_scale': track(3)}

def read_clip_meta(meta):
    """Duration, source frame range and source animation guid (layout seen in Native clips, 2026-10-19)."""
    dur, f0, f1 = struct.unpack_from('<3f', meta, 4)
    src = uuid.UUID(bytes_le=meta[32:48])
    return {'duration': dur, 'source_frames': (f0, f1), 'source_guid': src}

def find(path, name, type_guid):
    for a in assets(path):
        if a[0] == name and a[1] == type_guid:
            return a
    return None

def dump_json(native_dir, anim_name=None):
    """{'skeleton': [...], 'anim': {...} or None} for Blender (its Python has no lz4: tw_rig.py runs this)."""
    p = os.path.join(native_dir, 'core_game.tpac')
    a = find(p, 'human_skeleton', SKELETON)
    out = {'skeleton': read_skeleton(segment(p, a[4], SEG_SKEL)), 'anim': None}
    if anim_name:
        p = os.path.join(native_dir, 'animations.tpac')
        a = find(p, anim_name, ANIM)
        out['anim'] = read_anim(segment(p, a[4], SEG_ANIM)) if a else None
    return out

if __name__ == '__main__':
    if sys.argv[1] == 'json':                                 # anim_read.py json <Native AssetPackages dir> [<anim>]
        import json
        print(json.dumps(dump_json(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)))
        sys.exit(0)
    path, what, name = sys.argv[1:4]
    if what == 'skeleton':
        a = find(path, name, SKELETON)
        for i, (n, p, rows) in enumerate(read_skeleton(segment(path, a[4], SEG_SKEL))):
            print(i, n, p, [tuple(round(v, 4) for v in row) for row in rows])
    elif what == 'anim':
        a = find(path, name, ANIM)
        an = read_anim(segment(path, a[4], SEG_ANIM))
        print(an['name'], 'bones', len(an['bones']), 'root pos keys', len(an['root_pos']))
        for i, b in enumerate(an['bones'][:4]):
            print(' bone', i, 'rot keys', len(b['rot']), b['rot'][:2], 'pos keys', len(b['pos']))
    elif what == 'clip':
        a = find(path, name, CLIP)
        print(read_clip_meta(a[3]))
