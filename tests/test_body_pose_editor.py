import bpy
import pytest
from mathutils import Vector, Euler, Quaternion
from meta_human_dna.ui.callbacks import get_active_rig_logic
from meta_human_dna.utilities import reset_pose
from utilities.pose_editor import (
    set_body_pose
)

TOLERANCE = 1e-5

@pytest.mark.parametrize(
    (
        'solver_name', 
        'pose_name',
        'driver_bone_name',
        'driver_bone_rotation',
        'changed_driven_bone_names',
        'changed_driven_bone_locations',
    ), 
    [
        (
            'calf_l_UERBFSolver', 
            'calf_l_back_90', 
            'calf_l',
            Quaternion((0.707107, 0.0, 0.0, -0.707107)),
            ['calf_twistCor_02_l'], 
            [Vector((0.0, 0.1, 0.0))]
        ),
        (
            'thigh_l_UERBFSolver', 
            'thigh_l_in_45_out_90', 
            'thigh_l',
            Quaternion((0.653282, -0.270598, 0.270598, 0.653282)),
            ['thigh_out_l'], 
            [Vector((0.0, 0.2, 0.0))]
        ),
        (
            'clavicle_r_UERBFSolver', 
            'clavicle_r_up_40', 
            'clavicle_r',
            Quaternion((0.939693, 0.0, -0.34202, 0.0)),
            ['clavicle_out_r'], 
            [Vector((0.0, 0.1, 0.0))]
        ),
    ]
)
def test_body_pose_editing(
    load_body_dna_for_rbf_tests,
    solver_name: str,
    pose_name: str,
    driver_bone_name: str,
    driver_bone_rotation: Quaternion,
    changed_driven_bone_names: list[str],
    changed_driven_bone_locations: list[Vector]
):
    instance = get_active_rig_logic()

    # reset the pose to the default position
    reset_pose(instance.body_rig)
    
    pose, solver_index, pose_index = set_body_pose(
        solver_name=solver_name,
        pose_name=pose_name
    )

    for driven_name, change_location in zip(changed_driven_bone_names, changed_driven_bone_locations):
        for driven_index, driven in enumerate(pose.driven): # type: ignore
            if driven.name == driven_name:
                pose.driven_active_index = driven_index
                pose_bone = instance.body_rig.pose.bones[driven.name]

                # update the location
                pose_bone.location = change_location
                # update the driven bone transform in the pose
                bpy.ops.meta_human_dna.update_rbf_driven(solver_index=solver_index, pose_index=pose_index, driven_index=driven_index)

    # commit these changes to the dna
    bpy.ops.meta_human_dna.commit_rbf_solver_changes()

    # reset the pose to the default position
    reset_pose(instance.body_rig)

    # set the driver bone rotation to the pose to trigger the driven bones
    driver_bone = instance.body_rig.pose.bones[driver_bone_name]
    driver_bone.rotation_quaternion = driver_bone_rotation

    # ensure we evaluate the rig to apply the driven bone transforms
    instance.evaluate(component='body')

    for driven_name, expected_location in zip(changed_driven_bone_names, changed_driven_bone_locations):
        pose_bone = instance.body_rig.pose.bones[driven_name]
        
        assert pose_bone.location.x == pytest.approx(expected_location.x, abs=TOLERANCE), f'Driven bone {driven_name} X location {pose_bone.location.x} not {expected_location.x} as expected'
        assert pose_bone.location.y == pytest.approx(expected_location.y, abs=TOLERANCE), f'Driven bone {driven_name} Y location {pose_bone.location.y} not {expected_location.y} as expected'
        assert pose_bone.location.z == pytest.approx(expected_location.z, abs=TOLERANCE), f'Driven bone {driven_name} Z location {pose_bone.location.z} not {expected_location.z} as expected'