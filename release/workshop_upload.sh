#!/bin/sh
# Uploads the Galleass to the Steam Workshop (Bannerlord = app 261550) with steamcmd.
#   sh release/workshop_upload.sh <steam login name> "<change note>"
# Stages release/out/workshop/Galleass from release/out/Galleass (run release/make_release.sh first): the CLIENT part
# only (SubModule, ModuleData, GUI, NavMeshPrefabs, AssetPackages, README, AI_DISCLOSURE) - the editor package and the
# FBX/PNG sources stay in the Nexus zip. Preview: release/screens/entry_1_broadside.jpg (< 1 MB).
# First upload: publishedfileid in workshop_item.vdf is 0 -> a new PRIVATE item is created with the title, the
# description from workshop_description.txt and visibility 2; the id is written back into workshop_item.vdf, and
# later runs only update files + change note (description, visibility and screenshots are edited on the Steam page).
# Login: cached in /opt/steamcmd/home (user mder1); without the cache steamcmd asks for password + Steam Guard. Tags: release/workshop_tags.sh afterwards.
set -e
cd "$(dirname "$0")"
LOGIN=${1:?usage: sh release/workshop_upload.sh <steam login> "<change note>"}
NOTE=${2:?change note missing}
SRC=out/Galleass; W=out/workshop/Galleass; PREVIEW=screens/entry_1_broadside.jpg
[ -f $SRC/SubModule.xml ] || { echo "run release/make_release.sh first"; exit 1; }
[ "$(stat -c %s $PREVIEW)" -lt 1000000 ] || { echo "$PREVIEW is 1 MB or larger"; exit 1; }

rm -rf out/workshop; mkdir -p $W
cp -r $SRC/SubModule.xml $SRC/ModuleData $SRC/GUI $SRC/NavMeshPrefabs $SRC/AssetPackages $W/
for f in README.txt AI_DISCLOSURE.txt; do cp $SRC/$f $W/; done
# this copy has no AssetSources/: point the README to the full release instead
sed -i 's#The FBX and PNG sources are in AssetSources/\.#The FBX and PNG sources are in the full release on Nexus Mods (AssetSources/).#' $W/README.txt
grep -q 'full release on Nexus' $W/README.txt || { echo "README sources line not found"; exit 1; }
[ -f $W/AssetPackages/pack0.tpac ] && [ -f $W/AssetPackages/nested_prefabs_packed.xml ] || { echo "client package incomplete"; exit 1; }
echo "Workshop content: $(find $W -type f | wc -l) files, $(du -sh $W | cut -f1)"

# The game path has spaces and '&': fill the template in Python and keep the vdf in a path without spaces.
WORK="$HOME/.cache/galleass-workshop"
mkdir -p "$WORK"
python3 - "$(pwd)" "$NOTE" "$WORK/item.vdf" "$PREVIEW" "$W" <<'PY'
import re, sys
here, note, out, preview, content = sys.argv[1:]
q = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
s = open(here + "/workshop_item.vdf").read()
first = ""
if re.search(r'"publishedfileid"\s*"0"', s):
    desc = open(here + "/workshop_description.txt").read().strip()
    first = '\t"visibility"\t\t"2"\n\t"description"\t\t"%s"\n' % q(desc)
s = (s.replace("@CONTENT@", q(here + "/" + content)).replace("@PREVIEW@", q(here + "/" + preview))
      .replace("@NOTE@", q(note)).replace("@FIRST@", first))
open(out, "w").write(s)
PY
# Call steamcmd.sh at its real location: through the /usr/local/bin symlink it looks for linux32/ next to the link.
STEAMCMD=/opt/steamcmd/steamcmd.sh
[ -x "$STEAMCMD" ] || STEAMCMD=steamcmd
# Private steamcmd home (shared with the EU5 upload script): the desktop client rewrites ~/.local/share/Steam/config
# on every start and wipes the cached login there. With the cache in place this runs without a password prompt.
mkdir -p /opt/steamcmd/home
HOME=/opt/steamcmd/home "$STEAMCMD" +login "$LOGIN" +workshop_build_item "$WORK/item.vdf" +quit | tee "$WORK/steamcmd.log"

# steamcmd writes the item id into the vdf it was given (and prints 'PublishFileID <n>'); keep it for the next
# upload and the tags task.
ID=$(sed -n 's/.*"publishedfileid"[[:space:]]*"\([0-9]*\)".*/\1/p' "$WORK/item.vdf")
[ -n "$ID" ] && [ "$ID" != 0 ] || ID=$(grep -oiE 'publish(ed)?fileid[^0-9]*[0-9]{6,}' "$WORK/steamcmd.log" | grep -oE '[0-9]{6,}' | tail -1 || true)
if [ -n "$ID" ] && [ "$ID" != 0 ]; then
	sed -i "s/\"publishedfileid\"\([[:space:]]*\)\"0\"/\"publishedfileid\"\1\"$ID\"/" workshop_item.vdf
	sed -i "s/<ItemId Value=\"[0-9]*\"\/>/<ItemId Value=\"$ID\"\/>/" workshop_tags.xml
	echo "Workshop item: https://steamcommunity.com/sharedfiles/filedetails/?id=$ID"
fi
