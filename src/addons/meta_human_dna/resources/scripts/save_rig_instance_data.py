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
    if addon_name not in bpy.context.preferences.addons.keys(): # type: ignore
        # otherwise, enable it
        bpy.ops.preferences.addon_enable(module=addon_name)


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

    bpy.ops.wm.open_mainfile(filepath=args.blend_file)

    # Ensure the addon is enabled
    ensure_addon_enabled(args.addon_name, Path(args.addon_folder))

    os.makedirs(data_file.parent, exist_ok=True)
    data = {}

    try:
        for addon_id in ADDON_IDS:
            scene_properties = getattr(bpy.context.scene, addon_id, None)
            if not scene_properties:
                continue

            rig_instance_list = []
            for key in DATA_KEYS:
                rig_instance_list = scene_properties.get(key, [])
                if rig_instance_list:
                    break

            data.update({
                i.get('name', i.get('instance_name')): {
                    'face_board': i.get('face_board').name if i.get('face_board') else None,
                    'head_mesh': i.get('head_mesh').name if i.get('head_mesh') else None,
                    'head_rig': i.get('head_rig').name if i.get('head_rig') else None,
                    'head_material': i.get('head_material').name if i.get('head_material') else None,
                    'head_dna_file_path': i.get('head_dna_file_path', ''),
                    'body_mesh': i.get('body_mesh').name if i.get('body_mesh') else None,
                    'body_rig': i.get('body_rig').name if i.get('body_rig') else None,
                    'body_material': i.get('body_material').name if i.get('body_material') else None,
                    'body_dna_file_path': i.get('body_dna_file_path', ''),
                    'output_folder_path': i.get('output_folder_path', ''),
                }
                for i in rig_instance_list
            })
    except Exception as error:
        with open(f'{data_file.parent / data_file.stem}_error.log', 'w') as f:
            f.write(str(error) + traceback.format_exc())
            return

    with open(data_file, 'w') as f:
        json.dump(data, f)

if __name__ == "__main__":
    main()
