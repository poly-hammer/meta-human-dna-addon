# standard library imports
import logging
import re

# third party imports
import bpy

from mathutils import Euler, Matrix, Quaternion, Vector

from ... import utilities

# local imports
from ...constants import BONE_DELTA_THRESHOLD, IS_BLENDER_5, RBF_SOLVER_POSTFIX
from ...typing import *  # noqa: F403


logger = logging.getLogger(__name__)


def find_joint_index(instance: "RigInstance", bone_name: str) -> int | None:
    if not instance.body_initialized:
        instance.body_initialize(update_rbf_solver_list=False)

    # Find joint index
    if instance.body_dna_reader:
        for joint_index in range(instance.body_dna_reader.getJointCount()):
            joint_name = instance.body_dna_reader.getJointName(joint_index)
            if joint_name == bone_name:
                return joint_index
    return None


def set_driven_bone_data(
    instance: "RigInstance",
    pose: "RBFPoseData",
    driven: "RBFDrivenData",
    pose_bone: bpy.types.PoseBone,
    new: bool = False,
) -> str:
    updates = []
    update_message = ""
    if pose_bone:
        if not instance.body_initialized:
            instance.body_initialize(update_rbf_solver_list=False)

        existing_rotation = Vector(driven.euler_rotation[:])
        existing_location = Vector(driven.location[:])
        existing_scale = Vector(driven.scale[:])

        driven.name = pose_bone.name
        driven.pose_index = pose.pose_index
        driven.data_type = "BONE"
        # Find the joint index for this bone
        joint_index = find_joint_index(instance, pose_bone.name)
        if joint_index is not None:
            driven.joint_index = joint_index

        # Get the rest pose for this bone
        rest_location, _rest_rotation, rest_scale, rest_to_parent_matrix = instance.body_rest_pose[pose_bone.name]

        # Extract current transforms from the bone's matrix_basis
        modified_matrix = rest_to_parent_matrix @ pose_bone.matrix_basis
        current_location = modified_matrix.to_translation()
        current_scale = modified_matrix.to_scale()

        # Calculate deltas from rest pose (this is what DNA stores)
        location = Vector(
            [
                current_location.x - rest_location.x,
                current_location.y - rest_location.y,
                current_location.z - rest_location.z,
            ]
        )

        # rotation is directly in the bone local space
        rotation = pose_bone.rotation_euler.copy()

        # Scale delta (DNA stores 0.0 for scale_factor, actual delta otherwise)
        scale = Vector(
            [
                current_scale.x - rest_scale.x
                if round(current_scale.x - rest_scale.x, 5) != 0.0
                else pose.scale_factor,
                current_scale.y - rest_scale.y
                if round(current_scale.y - rest_scale.y, 5) != 0.0
                else pose.scale_factor,
                current_scale.z - rest_scale.z
                if round(current_scale.z - rest_scale.z, 5) != 0.0
                else pose.scale_factor,
            ]
        )

        rotation_delta = Vector(rotation[:]).copy() - existing_rotation
        location_delta = location.copy() - existing_location
        scale_delta = scale.copy() - existing_scale

        # only update if the delta is significant enough to avoid floating point value drift
        if rotation_delta.length > BONE_DELTA_THRESHOLD or new:
            driven.euler_rotation = rotation[:]
            logger.debug(
                f'Updated RBF pose "{pose.name}" driven bone "{driven.name}" rotation to {driven.euler_rotation[:]}',
            )
            updates.append("rotation")
        if location_delta.length > BONE_DELTA_THRESHOLD or new:
            driven.location = location[:]
            logger.debug(
                f'Updated RBF pose "{pose.name}" driven bone "{driven.name}" location to {driven.location[:]}',
            )
            updates.append("location")

        # only update if scale is not zero or equal to the scale factor, because only those are actual deltas
        if all(round(abs(i), 5) != 0.0 and pose.scale_factor != round(abs(i), 5) for i in scale_delta) or new:
            driven.scale = scale[:]
            logger.debug(
                f'Updated RBF pose "{pose.name}" driven bone "{driven.name}" scale to {driven.scale[:]}',
            )
            updates.append("scale")

    if updates:
        _updated = ", ".join(updates)
        update_message = f'Updated pose "{pose.name}" driven bone "{driven.name}" ({_updated})'
    return update_message


def set_driver_bone_data(
    instance: "RigInstance",
    pose: "RBFPoseData",
    driver: "RBFDriverData",
    pose_bone: bpy.types.PoseBone,
    new: bool = False,
) -> str:
    update_message = ""

    if pose_bone:
        if not instance.body_initialized:
            instance.body_initialize(update_rbf_solver_list=False)

        driver.solver_index = pose.solver_index
        driver.pose_index = pose.pose_index
        driver.name = pose_bone.name

        # only update if the delta is significant enough to avoid floating point value drift
        delta = Quaternion(driver.quaternion_rotation[:]) - pose_bone.rotation_quaternion.copy()
        if any(abs(i) > BONE_DELTA_THRESHOLD for i in delta) or new:
            driver.euler_rotation = pose_bone.rotation_quaternion.to_euler("XYZ")[:]
            driver.quaternion_rotation = pose_bone.rotation_quaternion[:]
            logger.debug(
                f'Updated RBF pose "{pose.name}" driver bone "{driver.name}" rotation '
                f"to {driver.quaternion_rotation[:]}",
            )
            update_message = f'Updated pose "{pose.name}" driver bone "{driver.name}" (rotation)'

        # Find the joint index for this bone
        joint_index = find_joint_index(instance, pose_bone.name)
        if joint_index is not None:
            driver.joint_index = joint_index

    return update_message


def set_body_rbf_pose_name(self: "RBFPoseData", value: str):
    instance = utilities.get_active_rig_instance()

    if not instance or not instance.body_rig or not instance.editing_rbf_solver:
        return

    solver = get_active_solver(instance)
    if not solver:
        return

    existing_names = {p.name for p in solver.poses if p != self}
    if value in existing_names:
        logger.warning(f"The pose name '{value}' is already in use and cannot be used.")
        return

    self["name"] = value


def get_body_rbf_pose_name(self: "RBFPoseData") -> str:
    return self.get("name", "")


def update_body_rbf_driven_active_index(self: "RBFPoseData", context: "Context"):  # noqa: ARG001
    instance = utilities.get_active_rig_instance()

    if not instance or not instance.body_rig or not instance.editing_rbf_solver:
        return

    driven = get_active_driven(instance)
    if not driven:
        return

    instance.body_rig.hide_set(False)
    utilities.switch_to_pose_mode(instance.body_rig)
    for pose_bone in instance.body_rig.pose.bones:
        if pose_bone.name == driven.name:
            # Note: In Blender 5.0+, the select property moved from Bone to PoseBone
            if IS_BLENDER_5:
                pose_bone.select = True
            else:
                pose_bone.bone.select = True
            instance.body_rig.data.bones.active = pose_bone.bone
        elif IS_BLENDER_5:
            pose_bone.select = False
        else:
            pose_bone.bone.select = False


def update_body_rbf_poses_active_index(self: "RBFSolverData", context: "Context"):  # noqa: ARG001, PLR0912
    if not utilities.dependencies_are_valid():
        return

    from ...bindings import meta_human_dna_core  # pyright: ignore[reportAttributeAccessIssue]

    instance = utilities.get_active_rig_instance()

    if not instance or not instance.body_rig:
        return

    pose = get_active_pose(instance)
    if not pose:
        return

    # reset all bone transforms
    if instance.body_reset_rbf_pose_on_change or instance.editing_rbf_solver:
        for pose_bone in instance.body_rig.pose.bones:
            pose_bone.matrix_basis = Matrix.Identity(4)

    if pose.name == "default":
        return

    for driver in pose.drivers:
        pose_bone = instance.body_rig.pose.bones.get(driver.name)
        if pose_bone:
            quaternion_rotation = Quaternion(driver.quaternion_rotation)
            pose_bone.rotation_mode = driver.rotation_mode
            pose_bone.rotation_quaternion = quaternion_rotation
            pose_bone.rotation_euler = Euler(driver.euler_rotation, "XYZ")

            swing_axis = pose_bone.get("swing_axis", "")
            swing_bone_names = pose_bone.get("swing_bone_names", [])
            swing_blend_weights = pose_bone.get("swing_blend_weights", [])

            twist_axis = pose_bone.get("twist_axis", "")
            twist_bone_names = pose_bone.get("twist_bone_names", [])
            twist_blend_weights = pose_bone.get("twist_blend_weights", [])

            # calculate swing and twist outputs
            swing_outputs, twist_outputs = meta_human_dna_core.calculate_swing_twist(
                driver_quaternion_rotation=list(driver.quaternion_rotation[:]),
                swing_bone_names=swing_bone_names,
                swing_blend_weights=list(swing_blend_weights[:]),
                twist_bone_names=twist_bone_names,
                twist_blend_weights=list(twist_blend_weights[:]),
                swing_axis=swing_axis,
                twist_axis=twist_axis,
            )
            # Apply swing and twist outputs
            for bone_name, swing_output in swing_outputs.items():
                swing_bone = instance.body_rig.pose.bones.get(bone_name)
                if swing_bone:
                    swing_bone.rotation_euler = Euler(swing_output, "XYZ")
            for bone_name, twist_output in twist_outputs.items():
                twist_bone = instance.body_rig.pose.bones.get(bone_name)
                if twist_bone:
                    twist_bone.rotation_euler = Euler(twist_output, "XYZ")

    # ensure the body is initialized
    if not instance.body_initialized:
        instance.body_initialize(update_rbf_solver_list=False)

    # evaluate the body rig logic when not editing the rbf solver
    if not instance.editing_rbf_solver:
        instance.evaluate(component="body")
        return

    for driven in pose.driven:
        if driven.data_type == "BONE":
            pose_bone = instance.body_rig.pose.bones.get(driven.name)
            if pose_bone:
                rest_location, rest_rotation, rest_scale, rest_to_parent_matrix = instance.body_rest_pose[
                    pose_bone.name
                ]

                location = Vector(
                    [
                        rest_location.x + driven.location[0],
                        rest_location.y + driven.location[1],
                        rest_location.z + driven.location[2],
                    ]
                )
                rotation = Euler(
                    [
                        rest_rotation.x + driven.euler_rotation[0],
                        rest_rotation.y + driven.euler_rotation[1],
                        rest_rotation.z + driven.euler_rotation[2],
                    ],
                    "XYZ",
                )
                scale = Vector(
                    [
                        rest_scale.x
                        + (driven.scale[0] if round(driven.scale[0], 5) != round(pose.scale_factor, 5) else 0.0),
                        rest_scale.y
                        + (driven.scale[1] if round(driven.scale[1], 5) != round(pose.scale_factor, 5) else 0.0),
                        rest_scale.z
                        + (driven.scale[2] if round(driven.scale[2], 5) != round(pose.scale_factor, 5) else 0.0),
                    ]
                )

                # update the bone matrix
                modified_matrix = Matrix.LocRotScale(location, rotation, scale)
                pose_bone.matrix_basis = rest_to_parent_matrix.inverted() @ modified_matrix

                # rotation is applied separately in pose space
                pose_bone.rotation_euler = Euler(driven.euler_rotation, "XYZ")


def update_evaluate_rbfs_value(self: "RigInstance", context: "Context"):
    addon_window_manager_properties = utilities.get_addon_window_manager_properties(context)
    addon_window_manager_properties.evaluate_dependency_graph = False
    self.reset_body_raw_control_values()
    self.reset_head_raw_control_values()
    addon_window_manager_properties.evaluate_dependency_graph = True


def update_body_rbf_solver_list(self: "RigInstance"):  # noqa: PLR0912
    if not utilities.dependencies_are_valid():
        return

    from ...bindings import meta_human_dna_core  # pyright: ignore[reportAttributeAccessIssue]

    # skip if the body rig is not set
    if not self.body_rig or not self.body_dna_reader:
        return

    last_active_solver_index = -1
    last_active_pose_index = -1
    last_active_driven_index = -1
    last_active_driver_index = -1

    # store the last active indices to try and preserve them after updating the list
    if len(self.rbf_solver_list) > 0:
        last_active_solver_index = self.rbf_solver_list_active_index
        _solver = self.rbf_solver_list[last_active_solver_index]
        if len(_solver.poses) > 0:
            last_active_pose_index = _solver.poses_active_index
            _pose = _solver.poses[last_active_pose_index]
            if len(_pose.driven) > 0:
                last_active_driven_index = _pose.driven_active_index
            if len(_pose.drivers) > 0:
                last_active_driver_index = _pose.drivers_active_index

    self.rbf_solver_list.clear()
    for solver_data in meta_human_dna_core.get_rbf_solver_data(self.body_dna_reader):
        solver = self.rbf_solver_list.add()
        for solver_field_name in solver_data.__annotations__:
            if solver_field_name == "poses":
                solver.poses.clear()
                for pose_data in solver_data.poses:
                    pose = solver.poses.add()
                    for pose_field_name in pose_data.__annotations__:
                        if pose_field_name == "driven":
                            pose.driven.clear()
                            for driven_data in pose_data.driven:
                                driven = pose.driven.add()
                                for driven_field_name in driven_data.__annotations__:
                                    setattr(driven, driven_field_name, getattr(driven_data, driven_field_name))
                        elif pose_field_name == "drivers":
                            pose.drivers.clear()
                            for driver_data in pose_data.drivers:
                                driver = pose.drivers.add()
                                for driver_field_name in driver_data.__annotations__:
                                    setattr(driver, driver_field_name, getattr(driver_data, driver_field_name))
                        else:
                            setattr(pose, pose_field_name, getattr(pose_data, pose_field_name))

                        if pose_field_name == "name":
                            # use internal dictionary to bypass the custom setter which checks for active solver
                            pose["name"] = getattr(pose_data, pose_field_name)
            else:
                setattr(solver, solver_field_name, getattr(solver_data, solver_field_name))

    # restore the last active indices if possible
    if last_active_solver_index >= 0 and last_active_solver_index < len(self.rbf_solver_list):
        self.rbf_solver_list_active_index = last_active_solver_index
        _solver = self.rbf_solver_list[last_active_solver_index]
        if last_active_pose_index >= 0 and last_active_pose_index < len(_solver.poses):
            _solver.poses_active_index = last_active_pose_index
            _pose = _solver.poses[last_active_pose_index]
            if last_active_driven_index >= 0 and last_active_driven_index < len(_pose.driven):
                _pose.driven_active_index = last_active_driven_index
            if last_active_driver_index >= 0 and last_active_driver_index < len(_pose.drivers):
                _pose.drivers_active_index = last_active_driver_index


def get_active_solver(instance: "RigInstance") -> "RBFSolverData | None":
    if not instance or not instance.body_rig:
        return None

    if len(instance.rbf_solver_list) == 0:
        return None

    return instance.rbf_solver_list[instance.rbf_solver_list_active_index]


def get_active_pose(instance: "RigInstance") -> "RBFPoseData | None":
    solver = get_active_solver(instance)
    if not solver:
        return None

    if len(solver.poses) == 0:
        return None

    return solver.poses[solver.poses_active_index]


def get_active_driven(instance: "RigInstance") -> "RBFDrivenData | None":
    pose = get_active_pose(instance)
    if not pose:
        return None

    if len(pose.driven) == 0:
        return None

    return pose.driven[pose.driven_active_index]


def update_driven_bone(instance: "RigInstance", pose_bone: bpy.types.PoseBone):
    pose = get_active_pose(instance)
    if not pose:
        return

    # Default pose driven data is only for UI display, don't update it
    if pose.name == "default":
        return

    for driven in pose.driven:
        if driven.name == pose_bone.name:
            set_driven_bone_data(instance=instance, pose=pose, driven=driven, pose_bone=pose_bone)
            break


def update_pose(instance: "RigInstance", _: "Context"):
    # ensure the body is initialized
    if not instance.body_initialized:
        instance.body_initialize(update_rbf_solver_list=False)

    pose = get_active_pose(instance)
    if not pose:
        return

    # Update all the driver bone data for the pose
    for driver in pose.drivers:
        driver_bone = instance.body_rig.pose.bones.get(driver.name)
        if driver_bone:
            set_driver_bone_data(instance=instance, pose=pose, driver=driver, pose_bone=driver_bone)
        else:
            utilities.report_error(
                (
                    f'Driver bone "{driver.name}" was not found in armature "{instance.body_rig.name}" '
                    f'when updating RBF Pose "{pose.name}". Please ensure the bone exists or delete '
                    f"this pose and recreate it."
                ),
            )

    # Update all the driven bone data for the pose
    # Skip the default pose - its driven data is only for UI display purposes
    if pose.name != "default":
        for driven in pose.driven:
            driven_pose_bone = instance.body_rig.pose.bones.get(driven.name)
            if driven_pose_bone:
                set_driven_bone_data(instance=instance, pose=pose, driven=driven, pose_bone=driven_pose_bone)
            else:
                logger.warning(
                    f'Driven bone "{driven.name}" was not found in armature when '
                    f'updating RBF Pose "{pose.name}". It will be deleted from '
                    "the pose when this data is committed to the dna."
                )


def diff_rbf_pose_data(instance: "RigInstance") -> None:  # noqa: PLR0912
    """
    Compare current RBF pose data against the original DNA data and update edit flags.

    This function performs two tasks:
    1. Updates the location_edited, rotation_edited, scale_edited flags on each driven bone
       for UI display purposes (showing which bones have been modified).
    2. Updates the change tracker to maintain a complete record of all modifications
       since entering edit mode.

    Args:
        instance: The active rig instance.
    """
    from . import change_tracker

    if not instance or not instance.body_rig:
        return

    pose = get_active_pose(instance)
    if not pose:
        return

    driven = sorted(list(d for d in pose.driven), key=lambda x: x.name)  # noqa: C400, C414

    from ...bindings import meta_human_dna_core  # pyright: ignore[reportAttributeAccessIssue]

    if not instance.body_initialized:
        instance.body_initialize(update_rbf_solver_list=False)

    # Update the driven bone edit flags by comparing to original DNA data
    for solver_data in meta_human_dna_core.get_rbf_solver_data(instance.body_dna_reader):
        for solver_field_name in solver_data.__annotations__:
            if solver_field_name == "poses":
                for pose_data in solver_data.poses:
                    if pose_data.name == pose.name:
                        for pose_field_name in pose_data.__annotations__:
                            if pose_field_name == "driven":
                                driven_data = sorted(pose_data.driven.copy(), key=lambda x: x.name)
                                for _driven, _driven_data in zip(driven, driven_data, strict=False):
                                    location_delta = Vector(_driven_data.location) - Vector(_driven.location)
                                    rotation_delta = Vector(_driven_data.euler_rotation) - Vector(
                                        _driven.euler_rotation
                                    )
                                    scale_delta = Vector(_driven_data.scale) - Vector(_driven.scale)

                                    # compare location
                                    if location_delta.length > BONE_DELTA_THRESHOLD:
                                        _driven.location_edited = True
                                    else:
                                        _driven.location_edited = False

                                    # compare rotation
                                    if rotation_delta.length > BONE_DELTA_THRESHOLD:
                                        _driven.rotation_edited = True
                                    else:
                                        _driven.rotation_edited = False

                                    # compare scale
                                    if scale_delta.length > BONE_DELTA_THRESHOLD:
                                        _driven.scale_edited = True
                                    else:
                                        _driven.scale_edited = False

    # Update the global change tracker for the overlay display
    change_tracker.update_tracking(instance)


def validate_no_duplicate_driver_bone_values(instance: "RigInstance") -> tuple[bool, str]:
    solver = get_active_solver(instance)
    if not solver:
        return False, "No active RBF solver found."

    if len(solver.poses) == 0:
        return False, "No poses found in the active RBF solver."

    # Collect all driver quaternions from all poses in the solver
    all_pose_quaternions = []
    for pose_index, pose in enumerate(solver.poses):
        all_pose_quaternions.extend(
            [
                {
                    "quaternion": Quaternion(driver.quaternion_rotation),
                    "pose_name": pose.name,
                    "pose_index": pose_index,
                    "driver_name": driver.name,
                }
                for driver in pose.drivers
            ]
        )

    # Check if quaternion values are unique across all poses within the threshold
    for i, quat_data1 in enumerate(all_pose_quaternions):
        for j, quat_data2 in enumerate(all_pose_quaternions):
            driver1_name = quat_data1["driver_name"]
            driver2_name = quat_data2["driver_name"]
            if i != j and driver1_name == driver2_name:
                quat1 = quat_data1["quaternion"]
                quat2 = quat_data2["quaternion"]

                pose1_name = quat_data1["pose_name"]
                pose2_name = quat_data2["pose_name"]

                # Calculate the rotation difference between quaternions
                rotation_difference = quat1.normalized().rotation_difference(quat2.normalized()).angle

                if rotation_difference < BONE_DELTA_THRESHOLD:
                    return (
                        False,
                        f"Poses '{pose1_name}' and '{pose2_name}' have a driver bone '{driver1_name}' with the "
                        "same rotation values. Driver bone rotations must be unique across all poses in the solver.",
                    )

    return True, ""


def validate_solver_non_default_pose_with_driven_bones(instance: "RigInstance") -> tuple[bool, str]:
    if len(instance.rbf_solver_list) == 0:
        return False, "No RBF solvers, please add one."

    for solver in instance.rbf_solver_list:
        if len(solver.poses) <= 1:
            return False, f"The RBF solver '{solver.name}' must have at least one non-default pose."

        for pose in solver.poses:
            if pose.name != "default" and len(pose.driven) == 0:
                return (
                    False,
                    f'Pose "{pose.name}" in the RBF solver "{solver.name}" has no driven bones. '
                    "Poses must have at least one driven bone.",
                )

    return True, ""


def get_solver_joint_group_bones(instance: "RigInstance") -> set[str]:
    solver = get_active_solver(instance)
    if not solver:
        return set()

    bone_names: set[str] = set()
    for pose in solver.poses:
        for driven in pose.driven:
            if driven.data_type == "BONE":
                bone_names.add(driven.name)

    return bone_names


def get_available_driven_bones(instance: "RigInstance") -> list[tuple[str, int, bool]]:
    if not instance or not instance.body_rig or not instance.body_dna_reader:
        return []

    existing_joint_group_bones = get_solver_joint_group_bones(instance)

    # Build a map of bone names to joint indices
    bone_to_joint_index: dict[str, int] = {}
    for joint_index in range(instance.body_dna_reader.getJointCount()):
        joint_name = instance.body_dna_reader.getJointName(joint_index)
        bone_to_joint_index[joint_name] = joint_index

    available_bones: list[tuple[str, int, bool]] = []

    for pose_bone in instance.body_rig.pose.bones:
        bone_name = pose_bone.name

        # Skip driver bones, swing bones, and twist bones
        if bone_name in instance.body_driver_bone_names:
            continue
        if bone_name in instance.body_swing_bone_names:
            continue
        if bone_name in instance.body_twist_bone_names:
            continue

        joint_index = bone_to_joint_index.get(bone_name, -1)
        is_in_existing = bone_name in existing_joint_group_bones

        available_bones.append((bone_name, joint_index, is_in_existing))

    # Sort: existing joint group bones first, then alphabetically
    available_bones.sort(key=lambda x: (not x[2], x[0]))

    return available_bones


def validate_and_update_solver_joint_group(
    instance: "RigInstance",
    new_driven_bone_names: list[str],
) -> tuple[bool, str]:
    if not instance or not instance.body_rig:
        return False, "No active rig instance or body rig found."

    solver = get_active_solver(instance)
    if not solver:
        return False, "No active RBF solver found."

    # Get existing bones in the joint group
    existing_bones = get_solver_joint_group_bones(instance)
    new_bones = set(new_driven_bone_names) - existing_bones

    if not new_bones:
        # All bones are already in the joint group, no update needed
        return True, ""

    # New bones need to be added to all existing poses
    # We'll add them with their rest pose transforms (zero deltas)
    logger.info(
        f"Adding {len(new_bones)} new bones to solver joint group: {new_bones}. "
        "Existing poses will be updated with rest pose values for these bones."
    )

    # Ensure the body is initialized to get rest pose data
    if not instance.body_initialized:
        instance.body_initialize(update_rbf_solver_list=False)

    # Add the new bones to all existing poses with rest pose transforms
    for pose in solver.poses:
        # Skip the default pose - its driven data is auto-populated for UI display only
        if pose.name == "default":
            continue

        for bone_name in new_bones:
            # Check if this bone is already in the pose
            if any(d.name == bone_name for d in pose.driven):
                continue

            # Add new driven entry with rest pose transforms (zero deltas)
            driven = pose.driven.add()
            driven.name = bone_name
            driven.pose_index = pose.pose_index
            driven.data_type = "BONE"
            driven.location = [0.0, 0.0, 0.0]
            driven.euler_rotation = [0.0, 0.0, 0.0]
            driven.quaternion_rotation = [1.0, 0.0, 0.0, 0.0]
            driven.scale = [pose.scale_factor, pose.scale_factor, pose.scale_factor]

            # Find the joint index for this bone
            for joint_index in range(instance.body_dna_reader.getJointCount()):
                joint_name = instance.body_dna_reader.getJointName(joint_index)
                if joint_name == bone_name:
                    driven.joint_index = joint_index
                    break

            logger.debug(f"Added bone '{bone_name}' to pose '{pose.name}' with rest pose transforms.")

    return True, f"Added {len(new_bones)} new bones to the solver's joint group."


def remove_driven_bone_from_solver(
    instance: "RigInstance",
    bone_names_to_remove: set[str],
) -> tuple[bool, str]:
    if not instance or not instance.body_rig:
        return False, "No active rig instance or body rig found."

    solver = get_active_solver(instance)
    if not solver:
        return False, "No active RBF solver found."

    # Get existing bones in the joint group
    existing_bones = get_solver_joint_group_bones(instance)

    # Filter to only bones that actually exist in the joint group
    bones_to_remove = bone_names_to_remove & existing_bones

    if not bones_to_remove:
        return False, "None of the selected bones are in the solver's joint group."

    # Check that we're not removing ALL bones - at least one must remain
    remaining_bones = existing_bones - bones_to_remove
    if not remaining_bones:
        return False, "Cannot remove all driven bones. At least one driven bone must remain in the solver."

    removed_count = 0

    # Remove the bones from all poses
    for pose in solver.poses:
        # Skip the default pose - its driven data is auto-populated for UI display only
        if pose.name == "default":
            # Remove any driven entries for the default pose. This is strictly for UI display purposes
            for i, driven in enumerate(pose.driven):
                if driven.name in bones_to_remove:
                    pose.driven.remove(i)
            # Then skip further processing, as the default pose is not stored in DNA
            continue

        # Find and remove matching driven entries (iterate in reverse to safely remove)
        indices_to_remove = []
        for i, driven in enumerate(pose.driven):
            if driven.name in bones_to_remove:
                indices_to_remove.append(i)

        # Remove in reverse order to maintain valid indices
        for i in reversed(indices_to_remove):
            pose.driven.remove(i)
            removed_count += 1

        # Update the active index if needed
        if pose.driven_active_index >= len(pose.driven):
            pose.driven_active_index = max(0, len(pose.driven) - 1)

    logger.info(
        f"Removed {len(bones_to_remove)} bones from solver joint group: {bones_to_remove}. "
        f"Total driven entries removed across all poses: {removed_count}."
    )

    return True, f"Removed {len(bones_to_remove)} bones from the solver's joint group."


def add_driven_bones_to_solver(
    instance: "RigInstance",
    bone_names_to_add: list[str],
    update_active_pose_transforms: bool = False,
) -> tuple[bool, str]:
    if not instance or not instance.body_rig:
        return False, "No active rig instance or body rig found."

    if not bone_names_to_add:
        return False, "No bones specified to add."

    # Get existing bones in the joint group
    existing_bones = get_solver_joint_group_bones(instance)

    # Combine existing and new bones (preserving order, no duplicates)
    all_driven_bones = list(existing_bones) + [name for name in bone_names_to_add if name not in existing_bones]

    # Use the validation function to add bones to all poses
    valid, message = validate_and_update_solver_joint_group(instance, all_driven_bones)
    if not valid:
        return False, message

    # Determine which bones were actually new
    new_bones = [name for name in bone_names_to_add if name not in existing_bones]

    if not new_bones:
        return True, "All specified bones are already in the solver's joint group."

    # Optionally update the active pose with actual bone transforms
    if update_active_pose_transforms:
        pose = get_active_pose(instance)
        if pose:
            for bone_name in new_bones:
                pose_bone = instance.body_rig.pose.bones.get(bone_name)
                if not pose_bone:
                    continue

                # Find the driven entry for this bone
                driven = None
                for d in pose.driven:
                    if d.name == bone_name:
                        driven = d
                        break

                if driven:
                    # Update with current bone transforms
                    set_driven_bone_data(instance=instance, pose=pose, driven=driven, pose_bone=pose_bone, new=True)

            # Set the active driven to the last added bone
            if new_bones:
                for i, driven in enumerate(pose.driven):
                    if driven.name == new_bones[-1]:
                        pose.driven_active_index = i
                        break

    logger.info(f"Added {len(new_bones)} bones to solver joint group: {new_bones}.")
    return True, f"Added {len(new_bones)} bones to the solver's joint group."


# =============================================================================
# RBF Solver Management Functions
# =============================================================================


def validate_add_rbf_solver(
    instance: "RigInstance",
    driver_bone_name: str,
) -> tuple[bool, str]:
    """
    Validate whether a new RBF solver can be created for the given driver bone.

    Args:
        instance: The active rig instance.
        driver_bone_name: The name of the bone to use as the driver for the new solver.

    Returns:
        A tuple of (is_valid, error_message). If is_valid is True, error_message will be empty.
    """
    if not instance:
        return False, "No active rig instance found."

    if not instance.body_rig:
        return False, "No body rig found on instance."

    # Ensure the body is initialized
    if not instance.body_initialized:
        instance.body_initialize(update_rbf_solver_list=False)

    # Check that the bone exists in the rig
    if driver_bone_name not in instance.body_rig.pose.bones:
        return False, f'Bone "{driver_bone_name}" not found in the body rig.'

    # Check that the bone is not a swing bone
    if driver_bone_name in instance.body_swing_bone_names:
        return False, f'Bone "{driver_bone_name}" is a swing bone and cannot be used as a driver bone.'

    # Check that the bone is not a twist bone
    if driver_bone_name in instance.body_twist_bone_names:
        return False, f'Bone "{driver_bone_name}" is a twist bone and cannot be used as a driver bone.'

    # Check that a solver with this driver bone doesn't already exist
    expected_solver_name = f"{driver_bone_name}{RBF_SOLVER_POSTFIX}"
    for solver in instance.rbf_solver_list:
        if solver.name == expected_solver_name:
            return False, f'A solver for bone "{driver_bone_name}" already exists: "{expected_solver_name}".'

    return True, ""


def add_rbf_solver(
    instance: "RigInstance",
    driver_bone_name: str,
    driver_quaternion: tuple[float, float, float, float] | None = None,
) -> tuple[bool, str, int]:
    """
    Add a new RBF solver for the given driver bone.

    This function creates a new RBF solver with a default pose and sets up the driver bone.
    The solver will be added to the instance's rbf_solver_list and made active.

    Args:
        instance: The active rig instance.
        driver_bone_name: The name of the bone to use as the driver for the new solver.
        driver_quaternion: Optional quaternion rotation for the driver bone in the default pose.
                          If None, uses the identity quaternion (1, 0, 0, 0).

    Returns:
        A tuple of (success, message, new_solver_index).
        If success is False, message contains the error description and new_solver_index is -1.
    """
    from ...constants import RBF_SOLVER_POSTFIX

    # Validate first
    is_valid, error_message = validate_add_rbf_solver(instance, driver_bone_name)
    if not is_valid:
        return False, error_message, -1

    solver_name = f"{driver_bone_name}{RBF_SOLVER_POSTFIX}"

    # Calculate the next solver index
    dna_solver_count = instance.body_dna_reader.getRBFSolverCount() if instance.body_dna_reader else 0
    max_existing_solver_index = -1
    for s in instance.rbf_solver_list:
        max_existing_solver_index = max(max_existing_solver_index, s.solver_index)
    new_solver_index = max(dna_solver_count, max_existing_solver_index + 1)

    # Create the new solver
    solver = instance.rbf_solver_list.add()
    solver.solver_index = new_solver_index
    solver.name = solver_name

    # Calculate the next pose index for the default pose
    dna_pose_count = instance.body_dna_reader.getRBFPoseCount() if instance.body_dna_reader else 0
    max_existing_pose_index = -1
    for s in instance.rbf_solver_list:
        for p in s.poses:
            max_existing_pose_index = max(max_existing_pose_index, p.pose_index)
    new_pose_index = max(dna_pose_count, max_existing_pose_index + 1)

    # Create the default pose
    default_pose = solver.poses.add()
    default_pose.solver_index = new_solver_index
    default_pose.pose_index = new_pose_index
    # Use internal dictionary to bypass the custom setter which checks for active solver
    default_pose["name"] = "default"

    # Add the driver bone to the default pose
    driver = default_pose.drivers.add()
    driver.name = driver_bone_name
    driver.pose_index = default_pose.pose_index

    # Find and set the joint index for the driver bone
    if instance.body_dna_reader:
        for joint_index in range(instance.body_dna_reader.getJointCount()):
            joint_name = instance.body_dna_reader.getJointName(joint_index)
            if joint_name == driver_bone_name:
                driver.joint_index = joint_index
                break

    # Set the driver quaternion (identity by default)
    if driver_quaternion is None:
        driver_quaternion = (1.0, 0.0, 0.0, 0.0)
    driver.quaternion_rotation = driver_quaternion

    # Set the active solver to the new solver
    new_solver_list_index = len(instance.rbf_solver_list) - 1
    instance.rbf_solver_list_active_index = new_solver_list_index
    solver.poses_active_index = 0

    logger.info(f'Created new RBF solver "{solver_name}" with driver bone "{driver_bone_name}".')
    return True, f'Created new RBF solver "{solver_name}".', new_solver_list_index


def remove_rbf_solver(
    instance: "RigInstance",
    solver_index: int | None = None,
) -> tuple[bool, str]:
    """
    Remove an RBF solver from the instance.

    Args:
        instance: The active rig instance.
        solver_index: The index of the solver in rbf_solver_list to remove.
                     If None, removes the currently active solver.

    Returns:
        A tuple of (success, message).
    """
    if not instance:
        return False, "No active rig instance found."

    if len(instance.rbf_solver_list) == 0:
        return False, "No RBF solvers to remove."

    # Use active index if not specified
    if solver_index is None:
        solver_index = instance.rbf_solver_list_active_index

    if solver_index < 0 or solver_index >= len(instance.rbf_solver_list):
        return False, f"Invalid solver index: {solver_index}"

    solver = instance.rbf_solver_list[solver_index]
    solver_name = solver.name

    # Remove the solver
    instance.rbf_solver_list.remove(solver_index)

    # Update the active index to stay within bounds
    if len(instance.rbf_solver_list) > 0:
        instance.rbf_solver_list_active_index = min(solver_index, len(instance.rbf_solver_list) - 1)
    else:
        instance.rbf_solver_list_active_index = 0

    logger.info(f'Removed RBF solver "{solver_name}".')
    return True, f'Removed RBF solver "{solver_name}".'


def add_rbf_pose(  # noqa: PLR0912, PLR0915
    instance: "RigInstance",
    pose_name: str,
    solver_index: int | None = None,
    driven_bones: list[bpy.types.PoseBone] | None = None,
    driven_bone_transforms: dict[str, dict] | None = None,
    driver_quaternion: tuple[float, float, float, float] | None = None,
    from_pose: "RBFPoseData | None" = None,
) -> tuple[bool, str, int]:
    """
    Add a new pose to an RBF solver.

    This is a core function that supports multiple use cases:
    1. Interactive UI: Pass `driven_bones` (list of PoseBone) to read transforms from the scene
    2. Programmatic/tests: Pass `driven_bone_transforms` (dict) with explicit transform data
    3. Duplication: Pass `from_pose` to copy data from an existing pose

    Args:
        instance: The active rig instance.
        pose_name: The name for the new pose.
        solver_index: Index of solver in rbf_solver_list. If None, uses active solver.
        driven_bones: List of Blender PoseBone objects. Transforms are read from the scene.
        driven_bone_transforms: Dict mapping bone names to transform data.
            Each entry should have: {"location": [x,y,z], "rotation": [x,y,z], "scale": [x,y,z]}
        driver_quaternion: Optional driver bone quaternion rotation (w, x, y, z).
            If None, reads from the driver bone in the scene.
        from_pose: Optional existing pose to duplicate from.

    Returns:
        A tuple of (success, message, new_pose_index).
    """
    if not instance:
        return False, "No active rig instance found.", -1

    if not instance.body_rig:
        return False, "No body rig found on instance.", -1

    if len(instance.rbf_solver_list) == 0:
        return False, "No RBF solvers available.", -1

    # Must provide either driven_bones or driven_bone_transforms
    if driven_bones is None and driven_bone_transforms is None and from_pose is None:
        return False, "Must provide either driven_bones, driven_bone_transforms, or from_pose.", -1

    # Use active index if not specified
    if solver_index is None:
        solver_index = instance.rbf_solver_list_active_index

    if solver_index < 0 or solver_index >= len(instance.rbf_solver_list):
        return False, f"Invalid solver index: {solver_index}", -1

    solver = instance.rbf_solver_list[solver_index]

    # Check for duplicate pose names
    existing_names = {p.name for p in solver.poses}
    if pose_name in existing_names:
        return False, f"A pose named '{pose_name}' already exists in this solver.", -1

    # Calculate the next pose index
    local_pose_index = len(solver.poses)
    max_existing_pose_index = -1
    for s in instance.rbf_solver_list:
        for p in s.poses:
            max_existing_pose_index = max(max_existing_pose_index, p.pose_index)

    dna_pose_count = instance.body_dna_reader.getRBFPoseCount() if instance.body_dna_reader else 0
    new_pose_index = max(dna_pose_count, max_existing_pose_index + 1)

    # Create the new pose
    pose = solver.poses.add()
    pose.solver_index = solver_index
    pose.pose_index = new_pose_index
    pose["name"] = pose_name  # Use internal dict to bypass setter

    # Copy values from an existing pose if provided
    if from_pose:
        pose.joint_group_index = from_pose.joint_group_index
        pose.target_enable = from_pose.target_enable
        pose.scale_factor = from_pose.scale_factor

    # Get the driver bone
    driver_bone_name = solver.name.replace(RBF_SOLVER_POSTFIX, "")
    driver_bone = instance.body_rig.pose.bones.get(driver_bone_name)
    if not driver_bone:
        # Remove the pose we just added since we can't set up the driver
        solver.poses.remove(local_pose_index)
        return False, f"Driver bone '{driver_bone_name}' not found in armature.", -1

    # Add the driver
    driver = pose.drivers.add()
    if driver_quaternion is not None:
        # Use explicit quaternion (for tests/programmatic use)
        driver.name = driver_bone_name
        driver.pose_index = pose.pose_index
        driver.quaternion_rotation = driver_quaternion
        driver.euler_rotation = Quaternion(driver_quaternion).to_euler("XYZ")[:]
        # Find the joint index for the driver bone
        if instance.body_dna_reader:
            for joint_index in range(instance.body_dna_reader.getJointCount()):
                joint_name = instance.body_dna_reader.getJointName(joint_index)
                if joint_name == driver_bone_name:
                    driver.joint_index = joint_index
                    break
    else:
        # Read from the scene (for UI use)
        set_driver_bone_data(instance=instance, pose=pose, driver=driver, pose_bone=driver_bone, new=True)

    # Handle driven bones based on which parameter was provided
    driven_list = []

    if from_pose is not None:
        # Duplicating from an existing pose
        source_driven_lookup = {d.name: d for d in from_pose.driven}

        # Get driven bones from source pose or from driven_bones parameter
        bones_to_process = driven_bones or [
            instance.body_rig.pose.bones.get(d.name)
            for d in from_pose.driven
            if instance.body_rig.pose.bones.get(d.name)
        ]

        for pose_bone in bones_to_process:
            driven = pose.driven.add()
            source_driven = source_driven_lookup.get(pose_bone.name)

            if source_driven:
                # Copy transforms from source, but reset if source is "default"
                if from_pose.name == "default":
                    location = [0.0, 0.0, 0.0]
                    euler_rotation = [0.0, 0.0, 0.0]
                    quaternion_rotation = [1.0, 0.0, 0.0, 0.0]
                    scale = [1.0, 1.0, 1.0]
                else:
                    location = source_driven.location[:]
                    euler_rotation = source_driven.euler_rotation[:]
                    quaternion_rotation = source_driven.quaternion_rotation[:]
                    scale = source_driven.scale[:]

                driven.name = source_driven.name
                driven.pose_index = pose.pose_index
                driven.joint_index = source_driven.joint_index
                driven.data_type = source_driven.data_type
                driven.location = location
                driven.euler_rotation = euler_rotation
                driven.quaternion_rotation = quaternion_rotation
                driven.scale = scale
            else:
                # Bone not in source pose, read from current scene
                set_driven_bone_data(instance=instance, pose=pose, driven=driven, pose_bone=pose_bone, new=True)
            driven_list.append(driven)

    elif driven_bones is not None:
        # Reading from scene (UI mode)
        for pose_bone in driven_bones:
            driven = pose.driven.add()
            set_driven_bone_data(instance=instance, pose=pose, driven=driven, pose_bone=pose_bone, new=True)
            driven_list.append(driven)

    elif driven_bone_transforms is not None:
        # Using explicit transforms (test/programmatic mode)
        for bone_name, transforms in driven_bone_transforms.items():
            driven = pose.driven.add()
            driven.name = bone_name
            driven.pose_index = pose.pose_index
            driven.data_type = "BONE"
            driven.location = transforms.get("location", [0.0, 0.0, 0.0])
            driven.euler_rotation = transforms.get("rotation", [0.0, 0.0, 0.0])
            driven.quaternion_rotation = Quaternion(Euler(transforms.get("rotation", [0.0, 0.0, 0.0]), "XYZ"))[:]  # pyright: ignore[reportArgumentType]
            driven.scale = transforms.get("scale", [1.0, 1.0, 1.0])

            # Find the joint index for this bone
            if instance.body_dna_reader:
                for joint_index in range(instance.body_dna_reader.getJointCount()):
                    joint_name = instance.body_dna_reader.getJointName(joint_index)
                    if joint_name == bone_name:
                        driven.joint_index = joint_index
                        break
            driven_list.append(driven)

    # Update the default pose to have entries for all driven bones (for UI purposes)
    # Only do this if we're not duplicating (from_pose is None)
    if from_pose is None and driven_list:
        for _pose in solver.poses:
            if _pose.name == "default":
                _pose.driven.clear()
                for _driven in driven_list:
                    driven = _pose.driven.add()
                    driven.name = _driven.name
                    driven.pose_index = _pose.pose_index
                    driven.joint_index = _driven.joint_index
                    driven.data_type = _driven.data_type
                    driven.location = [0.0, 0.0, 0.0]
                    driven.euler_rotation = [0.0, 0.0, 0.0]
                    driven.quaternion_rotation = [1.0, 0.0, 0.0, 0.0]
                    driven.scale = [1.0, 1.0, 1.0]
                break

    # Set the new pose as active
    solver.poses_active_index = local_pose_index

    logger.info(f'Created new RBF pose "{pose_name}" with {len(driven_list)} driven bones.')
    return True, f'Created new RBF pose "{pose_name}".', new_pose_index


# =============================================================================
# Mirroring Utility Functions
# =============================================================================


def get_mirror_side_replacement(source_side: str) -> str:
    """
    Get the replacement string for the opposite side.

    Args:
        source_side: The matched side string (e.g., "_l_", "_r_", "_l", "_r")

    Returns:
        The opposite side string with matching format.
    """
    if "_l_" in source_side:
        return source_side.replace("_l_", "_r_")
    if "_r_" in source_side:
        return source_side.replace("_r_", "_l_")
    if source_side.endswith("_l"):
        return source_side[:-2] + "_r"
    if source_side.endswith("_r"):
        return source_side[:-2] + "_l"
    return source_side


def get_mirrored_name(name: str, regex_pattern: str) -> str | None:
    try:
        match = re.match(regex_pattern, name)
        if not match:
            return None

        groups = match.groupdict()
        if "side" not in groups or groups["side"] is None:
            return None

        source_side = groups["side"]
        target_side = get_mirror_side_replacement(source_side)

        if source_side == target_side:
            return None  # No valid mirror side found

        # Reconstruct the name with the mirrored side
        return name.replace(source_side, target_side)
    except re.error:
        logger.warning(f"Invalid regex pattern: {regex_pattern}")
        return None


def can_mirror_name(name: str, regex_pattern: str) -> bool:
    return get_mirrored_name(name, regex_pattern) is not None


def mirror_driven_bone_transform(
    location: Vector,
    euler_rotation: Euler,
    scale: Vector,
    mirror_axis: str = "x",  # noqa: ARG001
) -> tuple[Vector, Euler, Vector]:
    return (location * -1, euler_rotation, scale)


# =============================================================================
# Solver Mirroring Functions
# =============================================================================


def validate_mirror_solver(
    instance: "RigInstance",
    solver_regex: str,
    bone_regex: str,
) -> tuple[bool, str]:
    """
    Validate that the active solver can be mirrored.

    Args:
        instance: The active rig instance.
        solver_regex: Regex pattern for matching solver names.
        bone_regex: Regex pattern for matching bone names.

    Returns:
        A tuple of (is_valid, error_message).
    """
    if not instance:
        return False, "No active rig instance found."

    if not instance.body_rig:
        return False, "No body rig found on instance."

    solver = get_active_solver(instance)
    if not solver:
        return False, "No active RBF solver found."

    # Check if the solver name can be mirrored
    mirrored_solver_name = get_mirrored_name(solver.name, solver_regex)
    if not mirrored_solver_name:
        return False, f'Solver "{solver.name}" does not match the mirror pattern and cannot be mirrored.'

    # Check that the target solver doesn't already exist
    for existing_solver in instance.rbf_solver_list:
        if existing_solver.name == mirrored_solver_name:
            return (
                False,
                f'Target solver "{mirrored_solver_name}" already exists. '
                "Delete it first or mirror individual poses instead.",
            )

    # Validate that the driver bone can be mirrored
    driver_bone_name = solver.name.replace(RBF_SOLVER_POSTFIX, "")
    mirrored_driver_name = get_mirrored_name(driver_bone_name, bone_regex)
    if not mirrored_driver_name:
        return False, f'Driver bone "{driver_bone_name}" does not match the bone mirror pattern.'

    # Check that the mirrored driver bone exists
    if mirrored_driver_name not in instance.body_rig.pose.bones:
        return False, f'Mirrored driver bone "{mirrored_driver_name}" does not exist in the body rig.'

    return True, ""


def mirror_solver(  # noqa: PLR0912, PLR0915
    instance: "RigInstance",
    solver_regex: str,
    bone_regex: str,
    pose_regex: str,
    mirror_axis: str = "x",
) -> tuple[bool, str, int]:
    """
    Mirror the active RBF solver to the opposite side.

    This creates a new solver with mirrored driver/driven bone names and
    mirrored transform values for all poses.

    Args:
        instance: The active rig instance.
        solver_regex: Regex pattern for matching solver names.
        bone_regex: Regex pattern for matching bone names.
        pose_regex: Regex pattern for matching pose names.
        mirror_axis: The axis to mirror transforms across.

    Returns:
        A tuple of (success, message, new_solver_index).
    """
    # Validate first
    is_valid, error_message = validate_mirror_solver(instance, solver_regex, bone_regex)
    if not is_valid:
        return False, error_message, -1

    source_solver = get_active_solver(instance)
    if not source_solver:
        return False, "No active solver found.", -1

    # Get mirrored names
    mirrored_solver_name = get_mirrored_name(source_solver.name, solver_regex)
    if not mirrored_solver_name:
        return False, "Could not generate mirrored solver name.", -1

    driver_bone_name = source_solver.name.replace(RBF_SOLVER_POSTFIX, "")
    mirrored_driver_name = get_mirrored_name(driver_bone_name, bone_regex)
    if not mirrored_driver_name:
        return False, "Could not generate mirrored driver bone name.", -1

    # Calculate the next solver index
    max_existing_solver_index = -1
    for s in instance.rbf_solver_list:
        max_existing_solver_index = max(max_existing_solver_index, s.solver_index)
    new_solver_index = max_existing_solver_index + 1

    # Create the new solver
    new_solver = instance.rbf_solver_list.add()
    new_solver.solver_index = new_solver_index
    new_solver.name = mirrored_solver_name
    new_solver.mode = source_solver.mode
    new_solver.radius = source_solver.radius
    new_solver.weight_threshold = source_solver.weight_threshold
    new_solver.distance_method = source_solver.distance_method
    new_solver.normalize_method = source_solver.normalize_method
    new_solver.function_type = source_solver.function_type
    new_solver.twist_axis = source_solver.twist_axis
    new_solver.automatic_radius = source_solver.automatic_radius

    # Track pose indices
    max_existing_pose_index = -1
    for s in instance.rbf_solver_list:
        for p in s.poses:
            max_existing_pose_index = max(max_existing_pose_index, p.pose_index)
    next_pose_index = max_existing_pose_index + 1

    # Mirror each pose
    for source_pose in source_solver.poses:
        # Get mirrored pose name
        if source_pose.name.lower() == "default":
            mirrored_pose_name = "default"
        else:
            mirrored_pose_name = get_mirrored_name(source_pose.name, pose_regex)
            if not mirrored_pose_name:
                # If pose name doesn't match pattern, keep original name
                mirrored_pose_name = source_pose.name

        # Create new pose
        new_pose = new_solver.poses.add()
        new_pose.solver_index = new_solver_index
        new_pose.pose_index = next_pose_index
        new_pose["name"] = mirrored_pose_name
        # Set joint_group_index to -1 so commit will find/create an appropriate joint group
        # for the mirrored bones (which are different from the source bones)
        new_pose.joint_group_index = -1
        new_pose.target_enable = source_pose.target_enable
        new_pose.scale_factor = source_pose.scale_factor
        next_pose_index += 1

        # Mirror drivers
        for source_driver in source_pose.drivers:
            mirrored_driver_bone = get_mirrored_name(source_driver.name, bone_regex)
            if not mirrored_driver_bone:
                mirrored_driver_bone = source_driver.name

            new_driver = new_pose.drivers.add()
            new_driver.solver_index = new_solver_index
            new_driver.pose_index = new_pose.pose_index
            new_driver.name = mirrored_driver_bone
            new_driver.rotation_mode = source_driver.rotation_mode

            # Find the joint index for this bone
            joint_index = find_joint_index(instance, mirrored_driver_bone)
            if joint_index is not None:
                new_driver.joint_index = joint_index

            # Mirror quaternion using world space transforms
            new_driver.quaternion_rotation = source_driver.quaternion_rotation
            new_driver.euler_rotation = Quaternion(source_driver.quaternion_rotation).to_euler("XYZ")[:]

        # Mirror driven bones
        for source_driven in source_pose.driven:
            mirrored_driven_bone = get_mirrored_name(source_driven.name, bone_regex)
            if not mirrored_driven_bone:
                mirrored_driven_bone = source_driven.name

            new_driven = new_pose.driven.add()
            new_driven.pose_index = new_pose.pose_index
            # Set joint_group_index to -1 since mirrored bones need a different joint group
            new_driven.joint_group_index = -1
            new_driven.name = mirrored_driven_bone
            new_driven.data_type = source_driven.data_type
            new_driven.rotation_mode = source_driven.rotation_mode

            # Find joint index for mirrored driven
            if instance.body_dna_reader:
                for joint_index in range(instance.body_dna_reader.getJointCount()):
                    joint_name = instance.body_dna_reader.getJointName(joint_index)
                    if joint_name == mirrored_driven_bone:
                        new_driven.joint_index = joint_index
                        break

            # Mirror the transforms using the correct driven bone transform function
            mirrored_location, mirrored_euler_rotation, mirrored_scale = mirror_driven_bone_transform(
                location=Vector(source_driven.location[:]),
                euler_rotation=Euler(source_driven.euler_rotation[:], "XYZ"),
                scale=Vector(source_driven.scale[:]),
                mirror_axis=mirror_axis,
            )
            new_driven.location = mirrored_location
            new_driven.scale = mirrored_scale

            # For driven bones, quaternion_rotation is derived from euler_rotation
            new_driven.euler_rotation = mirrored_euler_rotation[:]
            new_driven.quaternion_rotation = mirrored_euler_rotation.to_quaternion()[:]

    # Set the new solver as active
    new_solver_list_index = len(instance.rbf_solver_list) - 1
    instance.rbf_solver_list_active_index = new_solver_list_index
    new_solver.poses_active_index = 0

    logger.info(f'Mirrored solver "{source_solver.name}" to "{mirrored_solver_name}".')
    return True, f'Mirrored solver to "{mirrored_solver_name}".', new_solver_list_index


# =============================================================================
# Pose Mirroring Functions
# =============================================================================


def validate_mirror_pose(  # noqa: PLR0911
    instance: "RigInstance",
    solver_regex: str,
    pose_regex: str,
) -> tuple[bool, str]:
    """
    Validate that the active pose can be mirrored.

    Args:
        instance: The active rig instance.
        solver_regex: Regex pattern for matching solver names.
        bone_regex: Regex pattern for matching bone names.
        pose_regex: Regex pattern for matching pose names.

    Returns:
        A tuple of (is_valid, error_message).
    """
    if not instance:
        return False, "No active rig instance found."

    if not instance.body_rig:
        return False, "No body rig found on instance."

    source_solver = get_active_solver(instance)
    if not source_solver:
        return False, "No active RBF solver found."

    pose = get_active_pose(instance)
    if not pose:
        return False, "No active pose found."

    if pose.name.lower() == "default":
        return False, "Cannot mirror the default pose."

    # Check if the solver name can be mirrored to find target solver
    mirrored_solver_name = get_mirrored_name(source_solver.name, solver_regex)
    if not mirrored_solver_name:
        return False, f'Solver "{source_solver.name}" does not match the mirror pattern.'

    # Check that the target solver exists
    target_solver = None
    for existing_solver in instance.rbf_solver_list:
        if existing_solver.name == mirrored_solver_name:
            target_solver = existing_solver
            break

    if not target_solver:
        return (
            False,
            f'Target solver "{mirrored_solver_name}" does not exist. Mirror the solver first or create it manually.',
        )

    # Get the mirrored pose name
    mirrored_pose_name = get_mirrored_name(pose.name, pose_regex)
    if not mirrored_pose_name:
        # If pose name doesn't match the pattern, use the same name
        mirrored_pose_name = pose.name

    # Check if the mirrored pose already exists in the target solver
    for existing_pose in target_solver.poses:
        if existing_pose.name == mirrored_pose_name:
            return (
                False,
                f'Pose "{mirrored_pose_name}" already exists in solver "{mirrored_solver_name}". '
                "Delete it first or update it manually.",
            )

    return True, ""


def mirror_pose(  # noqa: PLR0915
    instance: "RigInstance",
    solver_regex: str,
    bone_regex: str,
    pose_regex: str,
    mirror_axis: str = "x",
) -> tuple[bool, str, int]:
    """
    Mirror the active pose to the mirrored solver.

    This creates a new pose in the mirrored solver with mirrored driver/driven
    bone names and mirrored transform values.

    Args:
        instance: The active rig instance.
        solver_regex: Regex pattern for matching solver names.
        bone_regex: Regex pattern for matching bone names.
        pose_regex: Regex pattern for matching pose names.
        mirror_axis: The axis to mirror transforms across.

    Returns:
        A tuple of (success, message, new_pose_index).
    """
    # Validate first
    is_valid, error_message = validate_mirror_pose(instance, solver_regex, pose_regex)
    if not is_valid:
        return False, error_message, -1

    source_solver = get_active_solver(instance)
    source_pose = get_active_pose(instance)
    if not source_solver or not source_pose:
        return False, "No active solver or pose.", -1

    # Get mirrored solver
    mirrored_solver_name = get_mirrored_name(source_solver.name, solver_regex)
    if not mirrored_solver_name:
        return False, "Could not generate mirrored solver name.", -1

    target_solver = None
    target_solver_index = -1
    for index, existing_solver in enumerate(instance.rbf_solver_list):
        if existing_solver.name == mirrored_solver_name:
            target_solver = existing_solver
            target_solver_index = index
            break

    if not target_solver:
        return False, f'Target solver "{mirrored_solver_name}" not found.', -1

    # Get mirrored pose name
    mirrored_pose_name = get_mirrored_name(source_pose.name, pose_regex)
    if not mirrored_pose_name:
        mirrored_pose_name = source_pose.name

    # Calculate next pose index
    max_existing_pose_index = -1
    for s in instance.rbf_solver_list:
        for p in s.poses:
            max_existing_pose_index = max(max_existing_pose_index, p.pose_index)
    new_pose_index = max_existing_pose_index + 1

    # Create new pose in target solver
    new_pose = target_solver.poses.add()
    new_pose.solver_index = target_solver.solver_index
    new_pose.pose_index = new_pose_index
    new_pose["name"] = mirrored_pose_name
    # Set joint_group_index to -1 since mirrored bones need a different joint group
    new_pose.joint_group_index = -1
    new_pose.target_enable = source_pose.target_enable
    new_pose.scale_factor = source_pose.scale_factor

    # Mirror drivers
    for source_driver in source_pose.drivers:
        mirrored_driver_bone = get_mirrored_name(source_driver.name, bone_regex)
        if not mirrored_driver_bone:
            mirrored_driver_bone = source_driver.name

        new_driver = new_pose.drivers.add()
        new_driver.solver_index = target_solver.solver_index
        new_driver.pose_index = new_pose.pose_index
        new_driver.name = mirrored_driver_bone
        new_driver.rotation_mode = source_driver.rotation_mode
        joint_index = find_joint_index(instance, mirrored_driver_bone)
        if joint_index is not None:
            new_driver.joint_index = joint_index

        # Mirror quaternion using world space transforms
        new_driver.quaternion_rotation = source_driver.quaternion_rotation
        new_driver.euler_rotation = Quaternion(source_driver.quaternion_rotation).to_euler("XYZ")[:]

    # Mirror driven bones
    for source_driven in source_pose.driven:
        mirrored_driven_bone = get_mirrored_name(source_driven.name, bone_regex)
        if not mirrored_driven_bone:
            mirrored_driven_bone = source_driven.name

        new_driven = new_pose.driven.add()
        new_driven.pose_index = new_pose.pose_index
        # Set joint_group_index to -1 since mirrored bones need a different joint group
        new_driven.joint_group_index = -1
        new_driven.name = mirrored_driven_bone
        new_driven.data_type = source_driven.data_type
        new_driven.rotation_mode = source_driven.rotation_mode
        joint_index = find_joint_index(instance, mirrored_driven_bone)
        if joint_index is not None:
            new_driven.joint_index = joint_index

        # Mirror the transforms using the correct driven bone transform function
        mirrored_location, mirrored_euler_rotation, mirrored_scale = mirror_driven_bone_transform(
            location=Vector(source_driven.location[:]),
            euler_rotation=Euler(source_driven.euler_rotation[:], "XYZ"),
            scale=Vector(source_driven.scale[:]),
            mirror_axis=mirror_axis,
        )
        new_driven.location = mirrored_location[:]
        new_driven.scale = mirrored_scale[:]
        # For driven bones, quaternion_rotation is derived from euler_rotation
        new_driven.euler_rotation = mirrored_euler_rotation[:]
        new_driven.quaternion_rotation = mirrored_euler_rotation.to_quaternion()[:]

    # Set the new pose as active in the target solver
    target_solver.poses_active_index = len(target_solver.poses) - 1

    # Switch to the target solver
    instance.rbf_solver_list_active_index = target_solver_index

    logger.info(f'Mirrored pose "{source_pose.name}" to "{mirrored_pose_name}" in solver "{mirrored_solver_name}".')
    return True, f'Mirrored pose to "{mirrored_pose_name}" in solver "{mirrored_solver_name}".', new_pose_index
