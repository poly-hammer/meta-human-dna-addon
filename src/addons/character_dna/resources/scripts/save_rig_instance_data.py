import os
import traceback
import bpy # pyright: ignore[reportMissingImports]
import json
import sys
import argparse
import addon_utils # pyright: ignore[reportMissingImports]
from pathlib import Path

ADDON_IDS = [
    "meta_human_dna",
    "meta_human_dna_pro",
    "character_dna",
    "character_dna_pro",
]

DATA_KEYS = [
    "rig_instance_list",
    "rig_logic_instance_list"
]

def is_addon_installed(addon_name: str) -> bool:
    for mod in addon_utils.modules(): # type: ignore
        if mod.__name__ == addon_name:
            return True
    return False

def ensure_addon_enabled(addon_name: str, scripts_folder: Path):
    # check all disabled addons and install if needed
    if not is_addon_installed(addon_name): # type: ignore
        # otherwise, install it
        script_directory = bpy.context.preferences.filepaths.script_directories.get(addon_name) # type: ignore
        if script_directory:
            bpy.context.preferences.filepaths.script_directories.remove(script_directory) # type: ignore

        script_directory = bpy.context.preferences.filepaths.script_directories.new() # type: ignore
        script_directory.name = addon_name
        script_directory.directory = str(scripts_folder)
        sys.path.append(str(scripts_folder))

    # check if the addon is enabled
    if not addon_utils.check(addon_name)[1]:
        # otherwise, enable it
        addon_utils.enable(addon_name, default_set=True)

def main():
    # Get arguments after '--'
    if '--' in sys.argv:
        argv = sys.argv[sys.argv.index('--') + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser()
    parser.add_argument('--data-file', type=str, help='Where to save the rig instance data')
    parser.add_argument('--blend-file', type=str, help='The blend file to extract data from')
    parser.add_argument('--addon-folder', type=str, help='The addon folder to use')
    parser.add_argument('--addon-name', type=str, help='The addon name to use')
    args = parser.parse_args(argv)

    data_file = Path(args.data_file)

    try:
        bpy.ops.wm.open_mainfile(filepath=args.blend_file)

        # Ensure the addon is enabled
        ensure_addon_enabled(args.addon_name, Path(args.addon_folder))

        os.makedirs(data_file.parent, exist_ok=True)
        data = {}

        def field(obj, key):
            # A live RigInstance (registered edition) is read via RNA attribute; a
            # raw IDProperty group (old prototype) is read via `.get`.
            if hasattr(obj, 'bl_rna'):
                return getattr(obj, key, None)
            if hasattr(obj, 'get'):
                return obj.get(key)
            return None

        def name_of(value):
            return value.name if value else None

        for addon_id in ADDON_IDS:
            # Read registered editions (current + read-only sibling) via attribute
            # access so data saved by EITHER edition (character_dna or
            # character_dna_pro) is found regardless of which one is enabled. Saved
            # PointerProperty data is only exposed once a matching property is
            # registered, so subscript access would miss the sibling edition. The
            # old prototype stored plain custom properties, read via subscript.
            group = getattr(bpy.context.scene, addon_id, None)
            if group is None:
                group = bpy.context.scene.get(addon_id)
            if not group:
                continue

            if hasattr(group, 'bl_rna'):
                sources = list(group.rig_instance_list)
            else:
                sources = []
                for key in DATA_KEYS:
                    value = group.get(key)
                    if value:
                        sources = list(value)
                        break

            for i in sources:
                name = field(i, 'name') or field(i, 'instance_name')
                if not name:
                    continue

                # Output folder: the current format nests it under `output`; the
                # old prototype stored it flat as `output_folder_path`.
                output_folder_path = field(i, 'output_folder_path')
                if output_folder_path is None:
                    output = field(i, 'output')
                    if output is not None:
                        output_folder_path = field(output, 'folder_path')

                data[name] = {
                    'face_board': name_of(field(i, 'face_board')),
                    'head_mesh': name_of(field(i, 'head_mesh')),
                    'head_rig': name_of(field(i, 'head_rig')),
                    'head_material': name_of(field(i, 'head_material')),
                    'head_dna_file_path': bpy.path.abspath(field(i, 'head_dna_file_path') or ''),
                    'control_rig': name_of(field(i, 'control_rig')),
                    'body_mesh': name_of(field(i, 'body_mesh')),
                    'body_rig': name_of(field(i, 'body_rig')),
                    'body_material': name_of(field(i, 'body_material')),
                    'body_dna_file_path': bpy.path.abspath(field(i, 'body_dna_file_path') or ''),
                    'output_folder_path': output_folder_path or '',
                }


    except Exception as error:
        with open(f'{data_file.parent / data_file.stem}_error.log', 'w') as f:
            f.write(str(error) + traceback.format_exc())
            return

    with open(data_file, 'w') as f:
        json.dump(data, f)

if __name__ == "__main__":
    main()
