# import os
# import sys
# import bpy
# import math
# import json
# import pytest
# from mathutils import Vector, Euler
# from pathlib import Path
# from pprint import pformat
# from meta_human_dna.constants import (
#     CUSTOM_BONE_SHAPE_NAME, 
#     CUSTOM_BONE_SHAPE_SCALE
# )
# from utilities.bones import (
#     get_bone_differences,
#     show_differences
# )
# from constants import TEST_FBX_POSES_FOLDER, TEST_JSON_POSES_FOLDER
# from meta_human_dna.ui.callbacks import get_active_rig_logic
# from meta_human_dna.utilities import (
#     switch_to_pose_mode,
#     switch_to_object_mode,
#     copy_mesh,
#     reset_pose,
#     select_only
# )

# def get_all_pose_names() -> list[str]:
#     pose_names = []
#     json_poses_folder = TEST_JSON_POSES_FOLDER / 'ada_body_rig'
#     fbx_poses_folder = TEST_FBX_POSES_FOLDER / 'ada_body_rig'

#     if json_poses_folder.exists():
#         for root, _, files in os.walk(json_poses_folder):
#             for file in files:
#                 if file.lower().endswith('.json') and root.lower().endswith('solver'):
#                     pose_name = str(Path(root, file.split('.')[0]).relative_to(json_poses_folder))
#                     pose_names.append(pose_name)

#     elif fbx_poses_folder.exists():
#         for root, _, files in os.walk(fbx_poses_folder):
#             for file in files:
#                 if file.lower().endswith('.fbx') and root.lower().endswith('solver'):
#                     pose_name = str(Path(root, file.split('.')[0]).relative_to(fbx_poses_folder))
#                     pose_names.append(pose_name)
    
#     return pose_names


# def set_body_pose(pose_name: str, source_rig_name: str):
#     source_rig_object = bpy.data.objects[source_rig_name]
#     reset_pose(source_rig_object)

#     if sys.platform == 'win32':
#         chunks = pose_name.split('\\')[-1].rsplit('_', 2)
#     else:
#         chunks = pose_name.split('/')[-1].rsplit('_', 2)

#     bone_name, direction, rotation = chunks

#     rotation = math.radians(int(rotation))

#     euler_rotation = Euler((0, 0, 0))

#     if direction == 'fwd':
#         euler_rotation.z = rotation
#     elif direction == 'back':
#         euler_rotation.z = -rotation
#     elif direction == 'up':
#         euler_rotation.y = rotation
#     elif direction == 'down':
#         euler_rotation.y = -rotation

#     switch_to_pose_mode(source_rig_object)

#     source_rig_object.pose.bones[bone_name].rotation_euler = euler_rotation # type: ignore
#     source_rig_object.pose.bones[bone_name].rotation_quaternion = euler_rotation.to_quaternion() # type: ignore

#     switch_to_object_mode()

# def import_fbx_pose(file_path: Path, source_rig_name: str) -> bpy.types.Object:
#     armature_name = 'joints_grp'
#     prefix = source_rig_name.split('_')[0]

#     bpy.ops.wm.fbx_import(filepath=str(file_path))
#     file_path = Path(file_path)

#     # Remove the extra empties
#     rig_empty = bpy.data.objects.get('rig')
#     if rig_empty:
#         for child in rig_empty.children_recursive:
#             if child.name in [armature_name, 'head_lod0_mesh']:
#                 continue
#             bpy.data.objects.remove(child)
#         bpy.data.objects.remove(rig_empty)

#     # rename the armature
#     armature_object = bpy.data.objects.get(armature_name)
#     armature_object.name = f'{file_path.stem}_body_rig' # type: ignore
#     armature_object.data.name = f'{file_path.stem}_body_rig' # type: ignore
#     sphere_object = bpy.data.objects[CUSTOM_BONE_SHAPE_NAME] 
#     for bone in armature_object.data.bones: # type: ignore
#         bone.name = bone.name.replace('DHIhead:', '')
#         armature_object.pose.bones[bone.name].rotation_mode = 'XYZ' # type: ignore
#         # set the custom shape for the face bones to make them easier to see
#         armature_object.pose.bones[bone.name].custom_shape = sphere_object # type: ignore
#         armature_object.pose.bones[bone.name].custom_shape_scale_xyz.x = CUSTOM_BONE_SHAPE_SCALE.x/10 # type: ignore
#         armature_object.pose.bones[bone.name].custom_shape_scale_xyz.y = CUSTOM_BONE_SHAPE_SCALE.y/10 # type: ignore
#         armature_object.pose.bones[bone.name].custom_shape_scale_xyz.z = CUSTOM_BONE_SHAPE_SCALE.z/10 # type: ignore

#     # copy the body mesh and skin it to the imported armature
#     body_mesh = copy_mesh(
#         mesh_object=bpy.data.objects[f'{prefix}_body_lod0_mesh'],
#         new_mesh_name=f'{file_path.stem}_mesh',
#         modifiers=True
#     )

#     # fix the head mesh rotation and scale
#     armature_object.scale = Vector((0.01, 0.01, 0.01)) # type: ignore
#     armature_object.rotation_mode = 'XYZ' # type: ignore
#     armature_object.rotation_euler.x += math.radians(90) # type: ignore
#     body_mesh.modifiers['Armature'].object = armature_object # type: ignore
#     armature_object.hide_set(True) # type: ignore

#     # apply the transformations
#     select_only(armature_object)
#     bpy.ops.object.transforms_to_deltas(mode='ALL')

#     return armature_object # type: ignore

# @pytest.mark.parametrize(
#     ('pose_name', 'source_rig_name'), 
#     [
#         (pose_name, 'ada_body_rig') for pose_name in get_all_pose_names()
#     ]
# )
# def test_body_pose(
#     load_dna, 
#     pose_name: str, 
#     source_rig_name: str, 
#     changed_head_bone_name: str,
#     show: bool = False,
#     skip_fbx_import: bool = False
# ):
#     # pytest.skip('TODO: Implement body RBF calculations correctly in RigLogic')
#     use_fbx_files = os.environ.get('META_HUMAN_DNA_ADDON_TESTS_UPDATE_BODY_JSON_POSES')
    
#     tolerance = 0.001
    
#     if use_fbx_files:
#         fbx_file_path = TEST_FBX_POSES_FOLDER / source_rig_name / f"{pose_name}.fbx"
#         # import the fbx file
#         if not skip_fbx_import:
#             armature_object = import_fbx_pose(
#                 file_path=fbx_file_path,
#                 source_rig_name=source_rig_name
#             )
#         else:
#             armature_object = bpy.data.objects[f'{fbx_file_path.stem}_body_rig']

#         # set the current pose
#         set_body_pose(
#             pose_name=pose_name, 
#             source_rig_name=source_rig_name
#         )

#         instance = get_active_rig_logic()

#         # check that the poses match
#         differences, target_locations = get_bone_differences(
#             source_rig_name=source_rig_name, 
#             target_rig_name=armature_object.name, 
#             tolerance=tolerance,
#             # isolated_bones=instance.body_raw_control_bone_names # type: ignore
#         )

#         # cache bone locations to json for faster testing than importing fbx files
#         json_pose_file_path = TEST_JSON_POSES_FOLDER / source_rig_name / f'{pose_name}.json'
#         os.makedirs(json_pose_file_path.parent, exist_ok=True)
#         with open(json_pose_file_path, 'w') as file:
#             json.dump(target_locations, file, indent=2)

#         if differences and show:
#             show_differences(source_rig_name, armature_object.name, differences)
#     else:
#         # load bone locations from json
#         json_pose_file_path = TEST_JSON_POSES_FOLDER / source_rig_name / f'{pose_name}.json'
#         with open(json_pose_file_path, 'r') as file:
#             target_locations = json.load(file)

#         set_body_pose(
#             pose_name=pose_name, 
#             source_rig_name=source_rig_name
#         )

#         instance = get_active_rig_logic()

#         # check that the poses match
#         differences, target_locations = get_bone_differences(
#             source_rig_name=source_rig_name,
#             target_bone_locations=target_locations,
#             tolerance=tolerance,
#             # isolated_bones=instance.body_raw_control_bone_names # type: ignore
#         )

#     # ignore differences caused by testing bone changes
#     differences = [(bone_name, value) for (bone_name, value) in differences if bone_name != changed_head_bone_name]

#     assert not differences, \
#     (
#         f'In the pose "{pose_name}" the following bone location differences '
#         f'exceeds the tolerance {tolerance}:\n{pformat(differences)}'
#     )