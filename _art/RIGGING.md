# Galleass rigging: how it works and how to redo it

All paths are relative to `Modules/Galleass`. Run Blender steps from `_art/`.

## How the game places the ropes

The galleass uses the three vanilla lateen sail rigs (`lateen_sail_large/medium/small_nested`). NavalDLC's `SailVisual.TickRopesAndPulleys` (BLSource v1.5.5) moves their running rigging every tick:

| Rope | Prefab parent | Deck end at runtime |
|---|---|---|
| Braces | `sail_rotate_pulleys` | the 2 nearest `knot_point`s of `knobs_holder`, on one side of the yard (index 0: the side the yard's forward axis points to; index 1: the other) |
| Sheets | `stability_ropes_parent` | the nearest `knot_point` on that side |
| Fold pulley (brail) | `sail_fold_pulleys` | runs from the mast hangers to the sail corner bone; no deck end |
| Lifts, tie, flag halyard | `static_ropes_parent`, `sail_mast` | static; ends tagged `attached_to_yard` follow the yard |

- **The pick is ship-wide.** Any knot point can take any rope, so every knot point must be a sensible belaying place. There must be no orphans or leftovers.
- **"Rope Connection Max Distance"** on each rig's `sail_visual` script limits the pick: horizontal distance for braces, 3D for sheets. Past it, the game falls back to the nearest knot in XY on either side of the yard, and the ropes cross the ship.
  - We set it to `ROPE_REACH` = 60. The sail corners are 20–40 m up, so smaller values make every sheet fall back.

## Prefab inheritance trap

The game builds an entity's children as its own list plus every child of its base prefab that the own list doesn't override.

- **Deleting** a child from a still-linked entity does nothing in game; the child comes back.
- **Flattening** a child (cutting its link) makes its parent re-add the vanilla original.
- **Do not** cut links up the chain either. Unlinking the three sail rigs (and `sail_holder`) hung the battle loading in `MissionShipFactory.CreateMissionShip` (2026-10-18).
- **Use `hide(parent, child)`** (`build_prefab.py`) instead. It keeps an override linked to the vanilla child, moves it to the parent's origin, shrinks it to scale 0.001 and replaces its tags with `galleass_hidden`, so SailVisual skips it.
  - `eff_kids()` lists the children the game will build, own plus merged.
- `prefab_layout.py` and `rig_check.py` resolve children with the same merge rule. `rig_check.py` ignores shrunk (hidden) entities.

## The pieces

| File | Role |
|---|---|
| `belay_model.py` | Fitting meshes: `galleass_pinrail_3/4` (pin board laid ON a cap rail, pins through it) and `galleass_bitts_3` (+ `bo_` collision). Writes the pin rope points to `ref/galleass_belay_pins.json`. |
| `build_prefab.py` | `CAP_BOARDS` (waist cap rail: y centre, pins), `FC_BOARDS` (forecastle parapet cap: bearings), `POOP_BITTS`. `board_clear()` keeps boards off swivels, shroud feet (`SHROUD_FEET` = standing_rig feet), boarding hooks and the castle ends. `knobs_holder` = one entity per fitting with one `knot_point` per pin. `fasten()` = nearest pin. `ROPE_REACH`. `rerig_ropes()`: tie, halyard foot, stays/shrouds/mizzen sheets hidden with `hide()`, orphan mast hangers removed. Bitts are cut out of the navmesh (`STORE_FOOT`). |
| `rig_check.py` | Replays the game's pick for every yaw in the sail limits (`ModuleData/galleass_mission_ships.xml`), with the lateen roll and yard shift. Errors: any fallback, or any rope through a deck or the bulwark. Warnings: pins no rope uses, rope ends outboard or low. `--strict`; `--dump=<json>` for the preview. |
| `rig_preview.py` | Blender renders. `RUNTIME=<dump json> RUNTIME_YAWS=0,90,170` draws the picked ropes at those yaws. |
| `standing_rig.py` | Static mesh `galleass_standing_rigging`: shrouds with tackles, tie tackle, halyard coil. |
| `mast_model.py` | Masts. The main's fighting top has a lubber's hole (`LUBBER_DEG`) for the flag halyard. The capture flag runs along that halyard, so it can't be rerouted. |
| `install_prefab.sh` | Builds the prefab, runs `rig_check.py --strict`, and installs to `AssetPackages` + `EmAssetPackages` only if both pass. |

## The spritsail (sail 3)

A working square sail under the bowsprit, the 4th `<sail>` in `ModuleData/galleass_mission_ships.xml` (`sail_center_3`).

- **Geometry:** shared by the mesh, the hull's hole and the prefab, all in `mast_dims.py` (`SPRIT_*`, `sprit_point()`, `sprit_tip()`, `sprit_pins()`).
  - The bowsprit passes the forecastle parapet where the centre falconet's embrasure was. That gun is gone (`FC_GUN_DEGS` in `galleass_model.py`), and the hull has a round hole there.
  - It rises at 22°. Steeper puts it into the fore lateen yard's lower end when that yard lies fore and aft (yaw ~85°).
  - Its heel lies on a sloped bed on the forecastle platform.
- **Mesh:** `mast_model.py` builds `galleass_bowsprit` and `bo_galleass_bowsprit` in the ship frame. The parts are:
  - the bed;
  - the lashing to iron rings beside the bed;
  - an iron ring flat on the parapet's face around the hole;
  - the sling and lift blocks;
  - a belaying pin through the spar near its end.

  The collision mesh needs a **physics** material name (`wood`), not the visual one.
- **Rig:** `build_prefab.py` copies vanilla's `sail_square_small_nested` from `galley_ship_nested` and scales it by `SPRIT_SCALE`, so its yard hangs under the sling.
  - **Tags:** the copy needs its **own** tags, because the galley's instance inherits `sail_center_0`.
  - **Vanilla mast:** `sail_mast` is shrunk to a point in the spar with its tags kept, because SailVisual reads `mast_entity`. Don't `hide()` it.
  - **Hidden:** the stays, the flag halyard and the level-3 topsail extras.
- **Ropes:** braces and sheets are re-tied at run time, but a square sail wants knots on its own side of the centre line (same sign of x) as well as the yard side.
  - Forward legs go to the pin through the bowsprit end, two knot points a side.
  - Aft legs go to the forecastle pins.
  - Every rope end the game does not move (the rest ends, shown during furl and set) belays on the fore-waist pin boards beside the forecastle (`FORE_WAIST_BOARDS`), or under the sling.
- **Campaign map:** the map's ship visual drops `torch_holder` and the other mission-only holders (`VisualShipFactory.CreateShipEntityForCache`). The bowsprit, standing rigging, guns and banners therefore live in `mesh_holder`.

## Redo / change the rigging

1. **Change belaying places:** edit `CAP_BOARDS` / `FC_BOARDS` / `POOP_BITTS` in `build_prefab.py`. A board that hits an obstacle fails `board_clear` with an assert.
2. **Trial build without installing:** `GALLEASS_ALLOW_MISSING=1` lets the build run before the Kit has new meshes.
   ```
   GALLEASS_ALLOW_MISSING=1 python3 _art/build_prefab.py ../NavalDLC/AssetPackages/nested_prefabs_packed.xml _art/ref/clone.xml /tmp/trial.xml
   python3 _art/rig_check.py /tmp/trial.xml,../NavalDLC/AssetPackages/nested_prefabs_packed.xml
   ```
   - The trial build rewrites `NavMeshPrefabs/galleass_ship_navmesh.bin`.
   - Iterate until there are 0 errors. Check the per-rope pick lists: braces should land on boards near their own yard ends.
3. **Look at it in Blender:**
   ```
   python3 _art/rig_check.py /tmp/trial.xml,../NavalDLC/AssetPackages/nested_prefabs_packed.xml --dump=/tmp/picks.json
   python3 _art/prefab_layout.py /tmp/trial.xml,../NavalDLC/AssetPackages/nested_prefabs_packed.xml galleass_ship_nested /tmp/layout.json
   cd _art && MASTS_BLEND=ref/galleass_masts.blend RUNTIME=/tmp/picks.json RUNTIME_YAWS=0,90,170 \
       blender -b ref/galleass_model.blend --python rig_preview.py -- /tmp/layout.json ref/rig /tmp/rt
   ```
   Then look at `/tmp/rt/rt_*_persp.png`, `_top`, `_deck`.
4. **New or changed fitting meshes:**
   ```
   cd _art && blender -b --factory-startup --python belay_model.py -- ref/galleass_belay.blend ../AssetSources/export renders/belay
   ```
   - Import into the Modding Kit from the `AssetSources/export` subfolder: meshes on; for `bo_*`, physics shape on and meshes off.
   - For a changed FBX: delete it in the Kit, then import fresh.
5. **Install:** `sh _art/install_prefab.sh`. It refuses when the Kit meshes are missing or the rig check fails.
6. **Navmesh:** check it with `blender -b ref/galleass_model.blend --python navmesh_view.py -- ../NavMeshPrefabs/galleass_ship_navmesh.bin ref/galleass_navmesh_view.blend`.
7. **In game:** restart the game (the prefab loads at startup). Swing all yards round both tacks: no rope in the water or through the hull. Then check the rgl log for crew "stuck" lines.

## Limits of the checker

- Sail bones are taken at their prefab rest frames plus no wind. The game adds a small wind push.
- During fold, unfold or the lateen roll animation the game doesn't re-pick knots, and the yard bones snap to the sail mesh origin. Ropes may look odd for those few seconds.
- The "through the ship" test uses simple deck heights and the waist bulwark (constants at the top of `rig_check.py`), not the real hull mesh.
