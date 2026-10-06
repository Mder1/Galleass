"""Phase 0: write AssetPackages/nested_prefabs_packed.xml with a copy of a vanilla ship's
prefab folder under a new name. Instance GUIDs are globally unique in vanilla, so every
instance GUID in the copy is regenerated (uuid5 of the old one, so reruns are stable).
References to NavalDLC's shared base prefabs (<prefab guid>) are kept as they are.

usage: python3 make_packed_clone.py <NavalDLC packed xml> <source prefab> <new prefab> <out xml>
"""
import re, sys, uuid

src_path, src, dst, out = sys.argv[1:5]
s = open(src_path, encoding='utf-8').read()
folders = s[s.find('<prefab_folders>'):]
a = folders.find(f'<prefab_folder name="{src}">')
if a < 0:
    sys.exit(f'prefab folder {src} not found')
b = folders.find('</prefab_folder>', a) + len('</prefab_folder>')
folder = folders[a:b]

NS = uuid.UUID('6a1e7c52-9c1f-4f0e-9b5a-3d1a2f5e0c11')
def new_guid(m):
    return '<instance guid="{%s}"' % str(uuid.uuid5(NS, dst + m.group(1))).upper()
folder, n = re.subn(r'<instance guid="\{([0-9A-F-]{36})\}"', new_guid, folder)

# The folder, its root prefab_file and the root entity all carry the ship prefab name.
folder = folder.replace(f'<prefab_folder name="{src}">', f'<prefab_folder name="{dst}">', 1)
folder = folder.replace(f'<prefab_file name="{src}">', f'<prefab_file name="{dst}">', 1)
folder = folder.replace(f'<entity name="{src}" ', f'<entity name="{dst}" ', 1)
assert folder.count(f'name="{dst}"') == 3, 'root names not replaced'

with open(out, 'w', encoding='utf-8', newline='\n') as f:
    f.write('<?xml version="1.0"?>\n<prefab_files>\n</prefab_files>\n<prefab_folders>\n\t')
    f.write(folder)
    f.write('\n</prefab_folders>\n')
print(f'{dst}: {n} instance GUIDs regenerated, {len(folder)//1024} KB -> {out}')
