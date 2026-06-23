# Groom Exporter (Unreal → Character DNA)

A headless Unreal Engine **commandlet** that reads MetaHuman `UGroomAsset` strand
geometry and writes it in the format the Character DNA add-on imports: one
`.cdgr` binary per groom (the highest-detail **render strands**) plus a
`groom_manifest.json`. Hair **cards** can optionally be exported to FBX.

This is a one-time, offline pre-process. The add-on never calls Unreal; it just
reads the folder this commandlet produces (set it as the **Groom Folder** in the
add-on's Output panel, then click **Import Groom**).

> Why a commandlet? Strand point/curve geometry inside a `UGroomAsset` is C++-only
> — Unreal's Python/Blueprint API exposes only groom *settings*, and there is no
> built-in groom geometry exporter (no Alembic/USD/FBX writer for strands). A
> source build lets us add this small commandlet.

## Requirements

- **Unreal Engine 5.8 source build** (referred to as `$UE` below). A source
  build is required to compile the commandlet. (UE 5.5–5.8 expose the same
  `FHairDescription` / `FHairDescriptionGroups` API used here.)
- The **HairStrands** plugin (ships with the engine; the commandlet's `.uplugin`
  enables it).
- A project containing the MetaHuman groom `.uasset` files.

## One-time setup

The steps below use two shell variables — set them to your own paths:

```bash
UE=/path/to/UnrealEngine            # your UE 5.8 source build
PROJECT=/path/to/GroomExportProject # any C++ or Blueprint project
```

1. **Create (or reuse) a project.** Any project works; a blank C++ or Blueprint
   project is fine (`$PROJECT/GroomExportProject.uproject`).

2. **Add the plugin.** Copy this `groom_exporter/` folder into the project's
   `Plugins/` directory and rename it to the module name:

   ```bash
   cp -r tools/groom_exporter "$PROJECT/Plugins/GroomExporter"
   ```

   (The `.uplugin`, `Source/GroomExporter/*` must end up at
   `$PROJECT/Plugins/GroomExporter/...`.)

3. **Place the groom content** at its `/Game` paths. The exported content folder
   already mirrors the MetaHuman layout, so copy it under `Content`:

   ```bash
   mkdir -p "$PROJECT/Content/MetaHumans"
   cp -r /path/to/NewMetaHumanCharacter "$PROJECT/Content/MetaHumans/"
   ```

   The grooms then resolve under
   `/Game/MetaHumans/NewMetaHumanCharacter/Grooms/...`.

4. **Generate project files & build the editor** (incremental against the
   prebuilt engine):

   ```bash
   "$UE/Engine/Build/BatchFiles/Linux/GenerateProjectFiles.sh" -project="$PROJECT/GroomExportProject.uproject" -game -engine
   "$UE/Engine/Build/BatchFiles/Linux/Build.sh" GroomExportProjectEditor Linux Development -project="$PROJECT/GroomExportProject.uproject"
   ```

   (On a Blueprint-only project, building the `...Editor` target still compiles
   the plugin module. Substitute your project name for `GroomExportProject`.)

## Run (headless)

```bash
"$UE/Engine/Binaries/Linux/UnrealEditor-Cmd" \
    "$PROJECT/GroomExportProject.uproject" \
    -run=GroomExport \
    -OutDir=/abs/path/to/groom_export \
    -ContentPath=/Game/MetaHumans/NewMetaHumanCharacter/Grooms \
    -unattended -nop4 -nosplash
```

Flags:

| Flag | Meaning |
| --- | --- |
| `-OutDir=` | **Required.** Output folder for `.cdgr` files + `groom_manifest.json`. |
| `-ContentPath=` | `/Game` package path to scan (default `/Game`). Scope it to the Grooms folder to skip unrelated assets. |
| `-Cards` | Also export hair-cards (`UStaticMesh`, LOD0) to FBX and list them in the manifest. Off by default — strands are the priority. |
| `-Widths` | Also export per-point strand widths (approximate: each point's normalized radius scaled by the group's render hair width). Off by default; without it the add-on uses a small default radius. |

The commandlet (class `UGroomExportCommandlet`) is invoked as `-run=GroomExport`
(Unreal strips the leading `U` and the `Commandlet` suffix).

## Use in Blender

Point the add-on's **Output → Groom Import → Groom Folder** at `-OutDir`, then
**Import Groom**. The add-on reads the manifest, takes the highest-detail strands
per groom, and builds Blender hair `Curves` attached to the imported head.

## Output format

`groom_manifest.json`:

```json
{
  "format": "character_dna_groom",
  "version": 1,
  "source": "/Game/MetaHumans/NewMetaHumanCharacter/Grooms",
  "space": { "units": "cm", "up_axis": "Z", "handedness": "left" },
  "grooms": [
    { "name": "Eyelashes_S_Sparse", "kind": "strands",
      "geometry": "Eyelashes_S_Sparse.cdgr",
      "group_id": 0, "lod": 0, "curve_count": 321, "point_count": 4173,
      "guide_count": 16, "surface": "head" }
  ]
}
```

`*.cdgr` (little-endian binary) — **must stay in sync with
`src/addons/character_dna/groom_io/io.py`**:

```
magic         char[4]        "CDGR"
version       uint32         1
curve_count   uint32         N
point_count   uint32         P
flags         uint32         bit0 widths, bit1 root_uv, bit2 group_id, bit3 guide
reserved      uint32         0
curve_offsets int32[N + 1]   offset-index topology ([0]=0, [N]=P)
positions     float32[P*3]   x, y, z per point, in Unreal space (cm, Z-up, left-handed)
widths        float32[P]     per-point width (diameter), if bit0
root_uv       float32[N*2]   per-curve scalp UV, if bit1
group_id      int32[N]       per-curve group id, if bit2
guide         int32[N]       per-curve guide flag, if bit3
```

### Coordinate space

Positions are written verbatim in **Unreal space: centimetres, Z-up,
left-handed**. The add-on converts to Blender's space (metres, Z-up,
right-handed) on import as `(x, y, z) -> (x, -y, z) * 0.01`, which is the inverse
of the Y/Z handling the DNA importer bakes into the head mesh — so a groom lands
in the imported head's space. The conversion is driven by the manifest `space`
block (`groom_io/curves_builder.py`), so it can be re-tuned without recompiling
the commandlet if a source uses other conventions.
