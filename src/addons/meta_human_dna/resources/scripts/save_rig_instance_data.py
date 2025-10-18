import os
import bpy
import json
import sys
import argparse
from pathlib import Path

def main():
    # Get arguments after '--'
    if '--' in sys.argv:
        argv = sys.argv[sys.argv.index('--') + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser()
    parser.add_argument('--data-file', type=str, help='Where to save the rig instance data')
    parser.add_argument('--blend-file', type=str, help='The blend file to extract data from')
    args = parser.parse_args(argv)

    data_file = Path(args.data_file)
    bpy.ops.wm.open_mainfile(filepath=args.blend_file)

    # Ensure the addon is enabled
    try:
        bpy.ops.preferences.addon_enable(module='meta_human_dna')
    except Exception:
        pass

    os.makedirs(data_file.parent, exist_ok=True)
    data = {}
    try:
        data = {
            i.name: {
                'face_board': i.face_board.name if i.face_board else None,
                'head_mesh': i.head_mesh.name if i.head_mesh else None,
                'head_rig': i.head_rig.name if i.head_rig else None,
                'head_material': i.head_material.name if i.head_material else None,
                'head_dna_file_path': i.head_dna_file_path,
                'body_mesh': i.body_mesh.name if i.body_mesh else None,
                'body_rig': i.body_rig.name if i.body_rig else None,
                'body_material': i.body_material.name if i.body_material else None,
                'body_dna_file_path': i.body_dna_file_path,
                'output_folder_path': i.output_folder_path,
            }
            for i in bpy.context.scene.meta_human_dna.rig_logic_instance_list # type: ignore
        }
    except Exception as error:
        with open(f'{data_file.parent / data_file.stem}_error.log', 'w') as f:
            f.write(str(error))
            return

    with open(data_file, 'w') as f:
        json.dump(data, f)

if __name__ == "__main__":
    main()