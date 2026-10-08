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
size=$(wc -c < "$tmp")
if [ "$size" -lt 1000000 ]; then
    rm -f "$tmp" "$log"; echo "BUILD OUTPUT TOO SMALL ($size bytes) - nothing installed"; exit 1
fi
cp "$tmp" AssetPackages/nested_prefabs_packed.xml
cp "$tmp" EmAssetPackages/nested_prefabs_packed.xml
rm -f "$tmp" "$log"
cmp AssetPackages/nested_prefabs_packed.xml EmAssetPackages/nested_prefabs_packed.xml && echo "installed: AssetPackages + EmAssetPackages ($size bytes)"
