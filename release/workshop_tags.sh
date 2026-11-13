#!/bin/sh
# Sets the Workshop tags from release/workshop_tags.xml with TaleWorlds' uploader (Modding Kit,
# bin/Win64_Shipping_wEditor), run under the game's Proton in the Kit's prefix. Steam must be running and logged in.
# The tag XML takes no comments: the uploader reads the FIRST node as the task list (no <?xml?>, nothing between tasks).
set -e
cd "$(dirname "$0")"
G=$(cd ../../.. && pwd)
STEAM="$HOME/.local/share/Steam"
PROTON="$STEAM/compatibilitytools.d/GE-Proton11-7-x86_64/proton"
WORK="$HOME/.cache/galleass-workshop"
mkdir -p "$WORK"
grep -q '<ItemId Value="0"/>' workshop_tags.xml && { echo "no item id yet: run release/workshop_upload.sh first"; exit 1; }
cp workshop_tags.xml "$WORK/tags.xml"
cd "$G/bin/Win64_Shipping_wEditor"
STEAM_COMPAT_DATA_PATH="/mnt/Games/SteamLibrary/steamapps/compatdata/1393600" STEAM_COMPAT_CLIENT_INSTALL_PATH="$STEAM" \
SteamAppId=261550 SteamGameId=261550 \
	"$PROTON" run "$(pwd)/TaleWorlds.MountAndBlade.SteamWorkshop.exe" "Z:$(echo "$WORK/tags.xml" | tr / '\\')"
