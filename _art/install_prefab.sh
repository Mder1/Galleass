#!/bin/sh
# Build the galleass prefab and install it where BOTH readers look: the game loads AssetPackages/, the Modding Kit
# (editor) loads EmAssetPackages/ - a copy only in one of them leaves the other on an old version.
# Installs nothing unless the build succeeded and produced a non-trivial file.
#   sh _art/install_prefab.sh        (from Modules/Galleass)
set -e
cd "$(dirname "$0")/.."
tmp=$(mktemp); log=$(mktemp)
if ! python3 _art/build_prefab.py ../NavalDLC/AssetPackages/nested_prefabs_packed.xml _art/ref/clone.xml "$tmp" > "$log" 2>&1; then
    cat "$log"; rm -f "$tmp" "$log"; echo "BUILD FAILED - nothing installed"; exit 1
fi
# the running rigging as the game will tie it (rig_check.py replays SailVisual's pin choice over the yards' swing):
# no fallbacks, no rope through the ship
if ! python3 _art/rig_check.py "$tmp",../NavalDLC/AssetPackages/nested_prefabs_packed.xml --strict > "$log" 2>&1; then
    grep -E '^(ERROR|WARN)|errors' "$log"; rm -f "$tmp" "$log"; echo "RIG CHECK FAILED - nothing installed"; exit 1
fi
size=$(wc -c < "$tmp")
if [ "$size" -lt 1000000 ]; then
    rm -f "$tmp" "$log"; echo "BUILD OUTPUT TOO SMALL ($size bytes) - nothing installed"; exit 1
fi
cp "$tmp" AssetPackages/nested_prefabs_packed.xml
cp "$tmp" EmAssetPackages/nested_prefabs_packed.xml
rm -f "$tmp" "$log"
cmp AssetPackages/nested_prefabs_packed.xml EmAssetPackages/nested_prefabs_packed.xml && echo "installed: AssetPackages + EmAssetPackages ($size bytes)"
# a fresh Kit import of galleass_hull drops the mesh tag that gives the painted planking the faction colour
# (2026-10-27: three imports went out untagged)
if [ "$(grep -ac faction_color Assets/galleass_hull_geo.tpac)" = "0" ]; then
    echo "WARNING: galleass_hull has NO faction_color tag - in the Kit tag galleass_paint (LOD 0-3) 'faction_color' and save"
fi
