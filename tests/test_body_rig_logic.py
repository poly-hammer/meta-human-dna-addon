import os
import bpy
import json
import pytest
from pathlib import Path
from pprint import pformat
from meta_human_dna.constants import (
    CUSTOM_BONE_SHAPE_NAME, 
    CUSTOM_BONE_SHAPE_SCALE
)
from utilities.bones import (
    get_bone_differences,
    show_differences
)
from constants import TEST_FBX_POSES_FOLDER, TEST_JSON_POSES_FOLDER
from meta_human_dna.ui.callbacks import get_active_rig_logic
from meta_human_dna.utilities import (
    copy_mesh,
    select_only
)

FINGER_NAMES = [
    'index',
    'middle',
    'ring',
    'pinky',
    'thumb'
]

EXCLUDE_FINGER_POSES = int(os.environ.get('META_HUMAN_DNA_ADDON_TESTS_BODY_EXCLUDE_FINGER_POSES', '0')) == 1


def get_all_pose_names(exclude_fingers: bool = False) -> list[str]:
    pose_names = []
    json_poses_folder = TEST_JSON_POSES_FOLDER / 'ada_body_rig'
    fbx_poses_folder = TEST_FBX_POSES_FOLDER / 'ada_body_rig'

    if json_poses_folder.exists():
        for root, _, files in os.walk(json_poses_folder):
            for file in files:
                if file.lower().endswith('.json') and root.lower().endswith('solver'):
                    pose_name = str(Path(root, file.split('.')[0]).relative_to(json_poses_folder))
                    prefix = pose_name.split(os.sep)[-1].split('_')[0]
                    if prefix in FINGER_NAMES and exclude_fingers:
                        continue
                    pose_names.append(pose_name)

    elif fbx_poses_folder.exists():
        for root, _, files in os.walk(fbx_poses_folder):
            for file in files:
                if file.lower().endswith('.fbx') and root.lower().endswith('solver'):
                    pose_name = str(Path(root, file.split('.')[0]).relative_to(fbx_poses_folder))
                    prefix = pose_name.split(os.sep)[-1].split('_')[0]
                    if prefix in FINGER_NAMES and exclude_fingers:
                        continue
                    pose_names.append(pose_name)
    
    return pose_names


def set_body_pose(
        solver_name: str, 
        pose_name: str
    ):
    instance = get_active_rig_logic()
    if instance:
        instance.editing_rbf_solver = True
        instance.auto_evaluate_body = False
        for solver_index, solver in enumerate(instance.rbf_solver_list): # type: ignore
            if solver.name == solver_name:
                instance.rbf_solver_list_active_index = solver_index # type: ignore
                for pose_index, pose in enumerate(solver.poses): # type: ignore
                    if pose.name == pose_name:
                        solver.poses_active_index = pose_index # type: ignore
                        break
                break

def import_fbx_pose(file_path: Path, source_rig_name: str) -> bpy.types.Object:
    armature_name = 'body_grp'
    prefix = source_rig_name.split('_')[0]

    bpy.ops.wm.fbx_import(filepath=str(file_path))
    file_path = Path(file_path)

    # Remove the extra empties
    rig_empty = bpy.data.objects.get('body_geometry_grp')
    if rig_empty:
        for child in rig_empty.children_recursive:
            bpy.data.objects.remove(child)
        bpy.data.objects.remove(rig_empty)

    # rename the armature
    armature_object = bpy.data.objects.get(armature_name)
    armature_object.name = f'{file_path.stem}_body_rig' # type: ignore
    armature_object.data.name = f'{file_path.stem}_body_rig' # type: ignore
    # set the custom shape for the face bones to make them easier to see
    sphere_object = bpy.data.objects[CUSTOM_BONE_SHAPE_NAME] 
    for bone in armature_object.data.bones: # type: ignore
        armature_object.pose.bones[bone.name].custom_shape = sphere_object # type: ignore
        armature_object.pose.bones[bone.name].custom_shape_scale_xyz.x = CUSTOM_BONE_SHAPE_SCALE.x/10 # type: ignore
        armature_object.pose.bones[bone.name].custom_shape_scale_xyz.y = CUSTOM_BONE_SHAPE_SCALE.y/10 # type: ignore
        armature_object.pose.bones[bone.name].custom_shape_scale_xyz.z = CUSTOM_BONE_SHAPE_SCALE.z/10 # type: ignore

    # Remove the body geometry
    body_geometry = bpy.data.objects.get('body_lod0_mesh')
    if body_geometry:
        bpy.data.objects.remove(body_geometry)

    # copy the body mesh and skin it to the imported armature
    body_mesh = copy_mesh(
        mesh_object=bpy.data.objects[f'{prefix}_body_lod0_mesh'],
        new_mesh_name=f'{file_path.stem}_mesh',
        modifiers=True
    )

    # parent the body mesh to the armature using the existing vertex groups
    body_mesh.modifiers['Armature'].object = armature_object # type: ignore
    armature_object.hide_set(True) # type: ignore

    # apply the transformations
    select_only(armature_object)
    bpy.ops.object.transforms_to_deltas(mode='ALL')

    return armature_object # type: ignore

def run_body_pose_test(
    pose_name: str, 
    source_rig_name: str, 
    changed_head_bone_name: str,
    evaluate: bool,
    show: bool = False,
    skip_fbx_import: bool = False
):
    # pytest.skip('TODO: Implement body RBF calculations correctly in RigLogic')
    use_fbx_files = os.environ.get('META_HUMAN_DNA_ADDON_TESTS_UPDATE_BODY_JSON_POSES')
    
    tolerance = 0.001

    instance = get_active_rig_logic()
    if not instance:
        pytest.fail('No active rig logic instance found.')
        return
    
    if use_fbx_files:
        fbx_file_path = TEST_FBX_POSES_FOLDER / source_rig_name / f"{pose_name}.fbx"
        # import the fbx file
        if not skip_fbx_import:
            armature_object = import_fbx_pose(
                file_path=fbx_file_path,
                source_rig_name=source_rig_name
            )
        else:
            armature_object = bpy.data.objects[f'{fbx_file_path.stem}_body_rig']

        # set the current pose
        set_body_pose(
            solver_name=fbx_file_path.parent.name,
            pose_name=pose_name.split(os.sep)[-1]
        )
        # either evaluate through riglogic or stay in edit mode when comparing the poses
        if evaluate:
            instance.evaluate(component='body')

        # check that the poses match
        differences, target_locations = get_bone_differences(
            source_rig_name=source_rig_name, 
            target_rig_name=armature_object.name, 
            tolerance=tolerance,
            # isolated_bones=instance.body_raw_control_bone_names # type: ignore
        )

        # cache bone locations to json for faster testing than importing fbx files
        json_pose_file_path = TEST_JSON_POSES_FOLDER / source_rig_name / f'{pose_name}.json'
        os.makedirs(json_pose_file_path.parent, exist_ok=True)
        with open(json_pose_file_path, 'w') as file:
            json.dump(target_locations, file, indent=2)

        if differences and show:
            show_differences(source_rig_name, armature_object.name, differences)
    else:
        # load bone locations from json
        json_pose_file_path = TEST_JSON_POSES_FOLDER / source_rig_name / f'{pose_name}.json'
        with open(json_pose_file_path, 'r') as file:
            target_locations = json.load(file)

        set_body_pose(
            solver_name=json_pose_file_path.parent.name,
            pose_name=pose_name.split(os.sep)[-1]
        )
        # either evaluate through riglogic or stay in edit mode when comparing the poses
        if evaluate:
            instance.evaluate(component='body')

        # check that the poses match
        differences, target_locations = get_bone_differences(
            source_rig_name=source_rig_name,
            target_bone_locations=target_locations,
            tolerance=tolerance,
            # isolated_bones=instance.body_raw_control_bone_names # type: ignore
        )

    # ignore differences caused by testing bone changes
    differences = [(bone_name, value) for (bone_name, value) in differences if bone_name != changed_head_bone_name]

    assert not differences, \
    (
        f'In the pose "{pose_name}" the following bone location differences '
        f'exceeds the tolerance {tolerance}:\n{pformat(differences)}'
    )
    
    instance.editing_rbf_solver = False
    instance.auto_evaluate_body = True


@pytest.mark.parametrize(
    ('pose_name', 'source_rig_name'), 
    [
        (pose_name, 'ada_body_rig') for pose_name in get_all_pose_names(
            exclude_fingers=EXCLUDE_FINGER_POSES
        )
    ]
)
def test_body_pose(
    load_dna, 
    pose_name: str, 
    source_rig_name: str, 
    changed_head_bone_name: str,
    show: bool = False,
    skip_fbx_import: bool = False
):
    run_body_pose_test(
        pose_name=pose_name,
        source_rig_name=source_rig_name,
        changed_head_bone_name=changed_head_bone_name,
        evaluate=True,
        show=show,
        skip_fbx_import=skip_fbx_import,
    )


@pytest.mark.parametrize(
    ('pose_name', 'source_rig_name'), 
    [
        (pose_name, 'ada_body_rig') for pose_name in get_all_pose_names(
            exclude_fingers=EXCLUDE_FINGER_POSES
        )
    ]
)
def test_body_pose_edit_mode(
    load_dna, 
    pose_name: str, 
    source_rig_name: str, 
    changed_head_bone_name: str,
    show: bool = False,
    skip_fbx_import: bool = False
):
    run_body_pose_test(
        pose_name=pose_name,
        source_rig_name=source_rig_name,
        changed_head_bone_name=changed_head_bone_name,
        evaluate=False,
        show=show,
        skip_fbx_import=skip_fbx_import,
    )
