#!/bin/sh
# Build the galleass prefab and install it where BOTH readers look: the game loads AssetPackages/, the Modding Kit
# (editor) loads EmAssetPackages/ - a copy only in one of them leaves the other on an old version.
#   sh _art/install_prefab.sh        (from Modules/Galleass)
set -e
cd "$(dirname "$0")/.."
tmp=$(mktemp)
python3 _art/build_prefab.py ../NavalDLC/AssetPackages/nested_prefabs_packed.xml _art/ref/clone.xml "$tmp" | grep -v '^PREFAB' || true
cp "$tmp" AssetPackages/nested_prefabs_packed.xml
cp "$tmp" EmAssetPackages/nested_prefabs_packed.xml
rm -f "$tmp"
cmp AssetPackages/nested_prefabs_packed.xml EmAssetPackages/nested_prefabs_packed.xml && echo "installed: AssetPackages + EmAssetPackages"
