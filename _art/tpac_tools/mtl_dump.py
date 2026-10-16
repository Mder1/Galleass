"""Material tpac -> shader/texture GUIDs resolved against Galleass/Native/NavalDLC packages, plus raw metadata.
    python3 mtl_dump.py <tpac_tools dir> <game dir> <..._mtl.tpac>..."""
import sys, os, glob, uuid, struct
sys.path.insert(0, sys.argv[1]); import meshinfo
G = sys.argv[2]
idx = {}
pk = glob.glob(G + '/Modules/Galleass/Assets/*.tpac') + glob.glob(G + '/Modules/Native/EmAssetPackages/**/*.tpac', recursive=True) + glob.glob(G + '/Modules/NavalDLC/EmAssetPackages/**/*.tpac', recursive=True)
for p in pk:
    try:
        for tg, g, name, meta in meshinfo.assets(p): idx[g] = (name, os.path.basename(p), tg)
    except Exception as e: pass
for m in sys.argv[3:]:
    for tg, g, name, meta in meshinfo.assets(m):
        print('==', name, 'type', tg, 'metasize', len(meta))
        i = 0
        while i <= len(meta) - 16:
            u = uuid.UUID(bytes_le=meta[i:i+16])
            if u in idx:
                slot = struct.unpack('<i', meta[i-4:i])[0] if i >= 4 else None
                print('  @%d guid -> %s (%s)  prev-int %s' % (i, idx[u][0], idx[u][1], slot)); i += 16; continue
            i += 1
        print(meta.hex(' ', 4))
