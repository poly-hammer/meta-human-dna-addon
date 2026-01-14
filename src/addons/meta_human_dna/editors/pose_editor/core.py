# standard library imports
import logging

# third party imports
import bpy

from mathutils import Euler, Matrix, Quaternion, Vector

from ... import utilities

# local imports
from ...constants import BONE_DELTA_THRESHOLD, IS_BLENDER_5
from ...rig_instance import start_listening, stop_listening
from ...typing import *  # noqa: F403


logger = logging.getLogger(__name__)


def pose_editor_listener(scene: "Scene", dependency_graph: bpy.types.Depsgraph):
    context: "Context" = bpy.context  # pyright: ignore[reportAssignmentType]  # noqa: UP037

    # only evaluate if in pose mode
    if context.mode == "POSE":
        for update in dependency_graph.updates:
            if not update.id:
                continue

            data_type = update.id.bl_rna.name  # type: ignore[attr-defined]
            if data_type == "Armature" and update.is_updated_transform:
                for instance in scene.meta_human_dna.rig_instance_list:
                    armature_name = update.id.name
                    active_pose_bone = context.active_pose_bone
                    if active_pose_bone:
                        update_driven_bone(instance=instance, pose_bone=active_pose_bone)

                    # Check if the armature is the body rig
                    if instance.body_rig.data.name == armature_name:
                        return


def start_listening_for_pose_edits():
    # stop listening to other rig instance changes
    stop_listening()

    # stop_listening_for_pose_edits()  # noqa: ERA001
    # logger.debug("Listening for Pose Edits...") # noqa: ERA001
    # bpy.app.handlers.depsgraph_update_post.append(pose_editor_listener)  # type: ignore[call-arg] # noqa: ERA001


def stop_listening_for_pose_edits():
    for handler in bpy.app.handlers.depsgraph_update_post:
        if handler.__name__ == pose_editor_listener.__name__:
            bpy.app.handlers.depsgraph_update_post.remove(handler)

    logger.debug("Stopped listening for Pose Edits.")
    # start listening again to other rig instance changes
    start_listening()


def set_driven_bone_data(
    instance: "RigInstance",
    pose: "RBFPoseData",
    driven: "RBFDrivenData",
    pose_bone: bpy.types.PoseBone,
    new: bool = False,
) -> None:
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
        for joint_index in range(instance.body_dna_reader.getJointCount()):
            joint_name = instance.body_dna_reader.getJointName(joint_index)
            if joint_name == pose_bone.name:
                driven.joint_index = joint_index
                break

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
            logger.info(
                f'Updated RBF pose "{pose.name}" driven bone "{driven.name}" rotation to {driven.euler_rotation[:]}',
            )
        if location_delta.length > BONE_DELTA_THRESHOLD or new:
            driven.location = location[:]
            logger.info(
                f'Updated RBF pose "{pose.name}" driven bone "{driven.name}" location to {driven.location[:]}',
            )

        # only update if scale is not zero or equal to the scale factor, because only those are actual deltas
        if all(round(abs(i), 5) != 0.0 and pose.scale_factor != round(abs(i), 5) for i in scale_delta) or new:
            driven.scale = scale[:]
            logger.info(
                f'Updated RBF pose "{pose.name}" driven bone "{driven.name}" scale to {driven.scale[:]}',
            )


def set_driver_bone_data(
    instance: "RigInstance",
    pose: "RBFPoseData",
    driver: "RBFDriverData",
    pose_bone: bpy.types.PoseBone,
    new: bool = False,
) -> None:
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
            logger.info(
                f'Updated RBF pose "{pose.name}" driver bone "{driver.name}" rotation '
                f"to {driver.quaternion_rotation[:]}",
            )

        # Find the joint index for this bone
        for joint_index in range(instance.body_dna_reader.getJointCount()):
            joint_name = instance.body_dna_reader.getJointName(joint_index)
            if joint_name == pose_bone.name:
                driver.joint_index = joint_index
                break


def update_body_rbf_driven_active_index(self: "RBFPoseData", context: "Context"):  # noqa: ARG001
    instance = utilities.get_active_rig_instance()

    if not instance or not instance.body_rig or not instance.editing_rbf_solver:
        return

    driven = self.driven[self.driven_active_index]
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


def update_body_rbf_poses_active_index(self: "RBFSolverData", context: "Context"):  # noqa: ARG001
    if not utilities.dependencies_are_valid():
        return

    from ...bindings import meta_human_dna_core  # pyright: ignore[reportAttributeAccessIssue]

    instance = utilities.get_active_rig_instance()

    if not instance or not instance.body_rig:
        return

    pose = self.poses[self.poses_active_index]

    # reset all bone transforms
    if instance.body_reset_rbf_pose_on_change or instance.editing_rbf_solver:
        for pose_bone in instance.body_rig.pose.bones:
            pose_bone.matrix_basis = Matrix.Identity(4)

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
    context.window_manager.meta_human_dna.evaluate_dependency_graph = False
    self.reset_body_raw_control_values()
    self.reset_head_raw_control_values()
    context.window_manager.meta_human_dna.evaluate_dependency_graph = True


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


def diff_rbf_pose_data(instance: "RigInstance"):  # noqa: PLR0912
    if not instance or not instance.body_rig:
        return

    pose = get_active_pose(instance)
    if not pose:
        return

    driven = sorted(list(d for d in pose.driven), key=lambda x: x.name)  # noqa: C400, C414

    from ...bindings import meta_human_dna_core  # pyright: ignore[reportAttributeAccessIssue]

    if not instance.body_initialized:
        instance.body_initialize(update_rbf_solver_list=False)

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
