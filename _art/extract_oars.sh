#!/bin/sh
# Pull vanilla's oars (base + the six upgrade oars) out of NavalDLC for make_oar.py: OBJ per metamesh (one object per
# sub-mesh, in metamesh order) + a JSON table of the sub-meshes' LODs and material names.
#   sh _art/extract_oars.sh          (from Modules/Galleass; writes _art/ref/oar/)
set -e
cd "$(dirname "$0")/.."
PKG=../NavalDLC/EmAssetPackages/ship_oars/ship_oars.tpac
NAMES="base_oar_8m narrow_oar_l1_8m narrow_oar_l2_8m narrow_oar_l3_8m wide_oar_l1_8m wide_oar_l2_8m wide_oar_l3_8m"
mkdir -p _art/ref/oar
python3 _art/tpac_tools/mesh_extract.py $PKG _art/ref/oar $NAMES > /dev/null
python3 _art/tpac_tools/meshinfo.py $PKG '../*/EmAssetPackages/**/*.tpac' $NAMES --json > _art/ref/oar/meshes.json
echo "extracted: $NAMES"
