"""Bannerlord navmesh prefab files (NavMeshPrefabs/<name>.bin, magic NMG9), as used by ship prefabs
(MissionShip.NavMeshPrefabName -> Scene.ImportNavigationMeshPrefab). Layout, reverse-engineered from NavalDLC's files:

    int32 size (file length - 4), 'NMG9'
    int32 nV, nV x float3 position
    int32 nE, nE x int32[6] (-1, v0, v1, -1, -1, 0)              edge k of a face runs vert k -> k+1
    int32 nF, per face: int32 n, n x vertex, n x edge, int32[5] (2, 0, face id, 0, -1), byte 0
    260-byte tail: int32 32 + 256 zero bytes

Faces are convex 3/4-gons, counter-clockwise seen from above. Face ids (the 3rd extra int) are 0 for plain deck; ship
code adds DynamicNavmeshIdStart: ids 1..44 are the faces boarding machines attach to (RelatedShipNavmeshOffset;
unique, each with an unshared edge), 45+ belong to the naval-raid deactivator mesh.
"""
import struct

TAIL = struct.pack('<i', 32) + bytes(256)

def read(path):
    d = open(path, 'rb').read()
    I = lambda o: struct.unpack_from('<i', d, o)[0]
    assert d[4:8] == b'NMG9'
    o = 8
    nv = I(o); o += 4
    V = [struct.unpack_from('<3f', d, o + 12 * i) for i in range(nv)]; o += 12 * nv
    ne = I(o); o += 4
    E = [struct.unpack_from('<6i', d, o + 24 * i) for i in range(ne)]; o += 24 * ne
    nf = I(o); o += 4
    F = []
    for _ in range(nf):
        n = I(o)
        vs = [I(o + 4 + 4 * k) for k in range(n)]
        es = [I(o + 4 + 4 * n + 4 * k) for k in range(n)]
        extra = [I(o + 4 + 8 * n + 4 * k) for k in range(5)]
        F.append((vs, es, extra[2]))
        o += 4 + 8 * n + 21
    assert d[o:] == TAIL, 'unexpected tail'
    return V, E, F

def write(path, verts, faces):
    """verts: [(x, y, z)], faces: [([vertex indices, CCW from above], face id)]."""
    edges, index = [], {}
    face_edges = []
    for vs, _ in faces:
        es = []
        for k in range(len(vs)):
            a, b = vs[k], vs[(k + 1) % len(vs)]
            key = (min(a, b), max(a, b))
            if key not in index:
                index[key] = len(edges); edges.append((a, b))
            es.append(index[key])
        face_edges.append(es)
    out = bytearray(b'NMG9')
    out += struct.pack('<i', len(verts))
    for v in verts:
        out += struct.pack('<3f', *v)
    out += struct.pack('<i', len(edges))
    for a, b in edges:
        out += struct.pack('<6i', -1, a, b, -1, -1, 0)
    out += struct.pack('<i', len(faces))
    for (vs, fid), es in zip(faces, face_edges):
        out += struct.pack('<i', len(vs)) + struct.pack('<%di' % len(vs), *vs) + struct.pack('<%di' % len(es), *es)
        out += struct.pack('<5i', 2, 0, fid, 0, -1) + b'\0'
    out += TAIL
    with open(path, 'wb') as f:
        f.write(struct.pack('<i', len(out)) + out)
    return len(verts), len(edges), len(faces)

def face_z(V, vs, x, y):
    """z of the face plane at (x, y), or None if (x, y) is outside the (convex, CCW) face."""
    P = [V[i] for i in vs]
    for k in range(len(P)):
        (x0, y0, _), (x1, y1, _) = P[k], P[(k + 1) % len(P)]
        if (x1 - x0) * (y - y0) - (y1 - y0) * (x - x0) < -1e-6:
            return None
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = P[0], P[1], P[2]
    ux, uy, uz, vx, vy, vz = bx - ax, by - ay, bz - az, cx - ax, cy - ay, cz - az
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    if abs(nz) < 1e-9:
        return None
    return az - (nx * (x - ax) + ny * (y - ay)) / nz
