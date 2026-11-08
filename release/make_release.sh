#!/bin/sh
# Builds the public release / War Sails contest entry: release/out/Galleass/ (the module) and
# release/out/Galleass-<version>.zip (Galleass/ at the zip root, for Nexus).
#   sh release/make_release.sh [<published Galleass folder>]     (default: <game>/Dev modules/GalleassPublished/Galleass)
#
# The published folder is what the Modding Kit's Publish Module (Client + Editor) produced: AssetPackages/pack0.tpac
# (client) and EmAssetPackages/Assets.tpac (editor). NOTE: the Kit writes them into the dev module and deletes our
# prefab there - move them to the published folder and rerun _art/install_prefab.sh (2026-11-08).
# Everything else comes from this dev module: SubModule.xml, ModuleData (+ XSLT), GUI, NavMeshPrefabs, the prefab
# (nested_prefabs_packed.xml, into both package folders) and the FBX/PNG sources the contest asks for
# (AssetSources/export, AssetSources/anim). Left out: .git, _art (generator scripts: on GitHub), Assets/ and
# RuntimeDataCache (editor working data; the editor package replaces them), backups. No DLL: the entry has no code.
set -e
cd "$(dirname "$0")/.."
PUB=${1:-"../../Dev modules/GalleassPublished/Galleass"}
for f in AssetPackages/pack0.tpac EmAssetPackages/Assets.tpac; do
    [ -f "$PUB/$f" ] || { echo "missing $PUB/$f (publish Galleass in the Modding Kit, Client + Editor)"; exit 1; }
done
[ -f AssetPackages/nested_prefabs_packed.xml ] || { echo "no installed prefab: run sh _art/install_prefab.sh"; exit 1; }
cmp -s AssetPackages/nested_prefabs_packed.xml EmAssetPackages/nested_prefabs_packed.xml || {
    echo "AssetPackages and EmAssetPackages prefabs differ: run sh _art/install_prefab.sh"; exit 1; }
# stale packages: an asset imported after the publish is not in them
NEWER=$(find Assets -name '*.tpac' -newer "$PUB/AssetPackages/pack0.tpac" | head -5)
[ -z "$NEWER" ] || { echo "Assets changed after the publish (re-publish first):"; echo "$NEWER"; exit 1; }

VER=$(sed -n 's/.*<Version value="\([^"]*\)".*/\1/p' SubModule.xml | head -1)
OUT=release/out; M=$OUT/Galleass
rm -rf "$OUT"; mkdir -p "$M/AssetPackages" "$M/EmAssetPackages" "$M/AssetSources"

cp SubModule.xml "$M/"
cp -r ModuleData GUI NavMeshPrefabs "$M/"
cp "$PUB/AssetPackages/pack0.tpac" "$M/AssetPackages/"
cp "$PUB/EmAssetPackages/Assets.tpac" "$M/EmAssetPackages/"
cp AssetPackages/nested_prefabs_packed.xml "$M/AssetPackages/"
cp AssetPackages/nested_prefabs_packed.xml "$M/EmAssetPackages/"
cp -r AssetSources/export AssetSources/anim "$M/AssetSources/"
# every texture's source image (the contest wants them as PNG/TIF), from the path the Kit recorded at import -
# mostly the Kit's copies in the AssetSources root (the vanilla-derived planks/deck/pattern were never in export/)
python3 - "$M" <<'EOF'
import glob, os, shutil, sys
sys.path.insert(0, '_art/tpac_tools'); import tpac
out, n = sys.argv[1], 0
for p in sorted(glob.glob('Assets/*_tex.tpac')):
    for m in tpac.scan(p):
        rel = m['source'].split('/Modules/Galleass/', 1)[1]
        if not os.path.exists(rel):
            sys.exit('texture %s: source %s missing' % (m['name'], rel))
        os.makedirs(os.path.dirname(os.path.join(out, rel)), exist_ok=True)
        shutil.copy2(rel, os.path.join(out, rel)); n += 1
print('texture sources:', n)
EOF
for f in README.txt AI_DISCLOSURE.txt; do [ -f "release/$f" ] && cp "release/$f" "$M/"; done

find "$M" \( -name '*.pre-*' -o -name '*.orig' -o -name '*.bak*' -o -name '*.blend*' -o -name '__pycache__' \) -exec rm -rf {} +
find "$M" -type d -exec chmod 755 {} +; find "$M" -type f -exec chmod 644 {} +

# checks: nothing private, no code, the prefab as installed, sources present
BAD=$(find "$M" \( -iname '*drawing*' -o -iname '*overlay*' -o -iname '*.dll' -o -name '.git' -o -name '_art' \
      -o -name 'RuntimeDataCache' -o -iname 'ref_*' \) | head -5)
[ -z "$BAD" ] || { echo "must not ship:"; echo "$BAD"; exit 1; }
grep -q '<DLLName' "$M/SubModule.xml" && { echo "SubModule.xml declares a DLL"; exit 1; }
cmp -s "$M/AssetPackages/nested_prefabs_packed.xml" AssetPackages/nested_prefabs_packed.xml
[ "$(find "$M/AssetSources" -name '*.fbx' | wc -l)" -gt 0 ] && [ "$(find "$M/AssetSources" -name '*.png' | wc -l)" -gt 0 ] || {
    echo "no FBX/PNG sources"; exit 1; }

(cd "$OUT" && rm -f "Galleass-$VER.zip" && zip -qr "Galleass-$VER.zip" Galleass)
echo "Release $VER: $(find "$M" -type f | wc -l) files, $(find "$M/AssetSources" -name '*.fbx' | wc -l) FBX, $(find "$M/AssetSources" -name '*.png' | wc -l) PNG"
du -sh "$M" "$OUT/Galleass-$VER.zip"
