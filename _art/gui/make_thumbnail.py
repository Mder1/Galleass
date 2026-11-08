"""Ship card thumbnail (port ship list, order of battle, encyclopedia, custom battle): the Naval DLC shows
the sprite of the brush layer named after the ship's prefab (Naval.ShipThumbnails, layer galleass_ship_nested,
added by GUI/Brushes/GalleassBrushes.xml). Vanilla's are 400 x 225 engine shots: the ship broadside, bow to the
LEFT (meditheavy: beak left, stern castle right), sails set, on open sea under a light sky, horizon about 70 % down,
~6 px per metre of hull.

    python3 make_thumbnail.py <screenshot.png> [x0 y0 x1 y1]

Crops the screenshot (the box, or the largest centred 16:9 area), scales it to 400 x 225 and writes the sprite sheet
../../AssetSources/export/ui_galleass_1.png (512 x 256, sprite at 4,4 = GalleassSpriteData.xml) plus a preview
beside vanilla's cards. Kit: import that PNG as texture ui_galleass_1, NO mipmaps,
dont_degrade, dont_delay_loading, format UNCOMPRESSED RGBA (2026-11-08: DXT5 as vanilla's sheet came out posterised -
values < 128 -> ~50, > 144 -> ~200 - from the Kit under Wine; check the compiled data in RuntimeDataCache); then copy GalleassSpriteData.xml to GUI/ and GalleassBrushes.xml to
GUI/Brushes/.
"""
import os, sys
from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', '..', 'AssetSources', 'export', 'ui_galleass_1.png')
W, H, PAD, SHEET = 400, 225, 4, (512, 256)

src = Image.open(sys.argv[1]).convert('RGB')
if len(sys.argv) >= 6:
    box = tuple(int(v) for v in sys.argv[2:6])
else:
    sw, sh = src.size
    cw, ch = (sw, sw * 9 // 16) if sw * 9 <= sh * 16 else (sh * 16 // 9, sh)
    box = ((sw - cw) // 2, (sh - ch) // 2, (sw - cw) // 2 + cw, (sh - ch) // 2 + ch)
thumb = ImageOps.fit(src.crop(box), (W, H), Image.LANCZOS)

sheet = Image.new('RGBA', SHEET, (0, 0, 0, 0))
sheet.paste(thumb.convert('RGBA'), (PAD, PAD))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
sheet.save(OUT)
prev = os.path.join(HERE, 'thumbnail_preview.png')
cards = [thumb] + [Image.open(os.path.join(HERE, 'ref', n)).convert('RGB') for n in ('v_meditheavy.png', 'v_dromon.png')
                   if os.path.exists(os.path.join(HERE, 'ref', n))]
pv = Image.new('RGB', (W * len(cards) + 8 * (len(cards) - 1), H), (40, 40, 40))
for i, c in enumerate(cards):
    pv.paste(c, (i * (W + 8), 0))
pv.save(prev)
print('crop', box, '->', OUT, '; preview', prev)
