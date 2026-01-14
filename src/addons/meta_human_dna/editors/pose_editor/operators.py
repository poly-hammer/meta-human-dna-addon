# standard library imports
import logging
import math

from pathlib import Path

# third-party imports
import bpy

# local imports
from ... import utilities
from ...constants import RBF_SOLVER_POSTFIX
from ...dna_io import get_dna_reader, get_dna_writer

# type checking imports
from ...typing import *  # noqa: F403
from . import core


logger = logging.getLogger(__name__)


def get_new_pose_name(self: "AddRBFPose") -> str:
    value = self.get("new_pose_name")
    if value is None:
        instance = utilities.get_active_rig_instance()
        if instance:
            solver = instance.rbf_solver_list[instance.rbf_solver_list_active_index]
            driver_bone_name = solver.name.replace(RBF_SOLVER_POSTFIX, "")
            driver_bone = instance.body_rig.pose.bones.get(driver_bone_name)
            if driver_bone:
                name = driver_bone.name
                rotation_euler = driver_bone.rotation_quaternion.to_euler("XYZ")
                x = round(math.degrees(rotation_euler.x))
                y = round(math.degrees(rotation_euler.y))
                z = round(math.degrees(rotation_euler.z))

                if x != 0:
                    name += f"_x_{x}"
                if y != 0:
                    name += f"_y_{y}"
                if z != 0:
                    name += f"_z_{z}"
                return name
        return ""
    return value


def set_new_pose_name(self: "AddRBFPose", value: str):
    self["new_pose_name"] = value


class RBFEditorOperatorBase(bpy.types.Operator):
    solver_index: bpy.props.IntProperty(default=0)  # pyright: ignore[reportInvalidTypeForm]
    pose_index: bpy.props.IntProperty(default=0)  # pyright: ignore[reportInvalidTypeForm]
    driver_index: bpy.props.IntProperty(default=0)  # pyright: ignore[reportInvalidTypeForm]
    driven_index: bpy.props.IntProperty(default=0)  # pyright: ignore[reportInvalidTypeForm]

    def validate(self, context: "Context", instance: "RigInstance") -> tuple[bool, str]:
        return True, ""

    def execute(self, context: "Context") -> set[str]:
        instance = utilities.get_active_rig_instance()
        if instance and instance.body_rig:
            result, message = self.validate(context, instance)
            if not result:
                self.report({"ERROR"}, message)
                return {"CANCELLED"}

            self.run(instance)

        return {"FINISHED"}

    def run(self, instance: "RigInstance"):
        pass


class AddRBFSolver(RBFEditorOperatorBase):
    """Add a new RBF Solver"""

    bl_idname = "meta_human_dna.add_rbf_solver"
    bl_label = "Add RBF Solver"

    def run(self, instance: "RigInstance"):
        pass


class RemoveRBFSolver(RBFEditorOperatorBase):
    """Remove the selected RBF Solver"""

    bl_idname = "meta_human_dna.remove_rbf_solver"
    bl_label = "Remove RBF Solver"

    def run(self, instance: "RigInstance"):
        pass


class EvaluateRBFSolvers(RBFEditorOperatorBase):
    """Evaluate the RBF Solvers"""

    bl_idname = "meta_human_dna.evaluate_rbf_solvers"
    bl_label = "Evaluate RBF Solvers"

    def run(self, instance: "RigInstance"):
        instance.evaluate(component="body")


class RevertRBFSolver(RBFEditorOperatorBase):
    """Revert RBF solver back to the original DNA."""

    bl_idname = "meta_human_dna.revert_rbf_solver"
    bl_label = "Revert RBF Solver"

    def run(self, instance: "RigInstance"):
        core.stop_listening_for_pose_edits()
        utilities.reset_pose(instance.body_rig)
        instance.editing_rbf_solver = False
        instance.auto_evaluate_body = True
        bpy.ops.meta_human_dna.force_evaluate()  # type: ignore[attr-defined]


class EditRBFSolver(RBFEditorOperatorBase):
    """Switch to Editing mode for the selected RBF solver. Changes will not take effect until committed to the .dna file."""  # noqa: E501

    bl_idname = "meta_human_dna.edit_rbf_solver"
    bl_label = "Edit RBF Solver"

    @classmethod
    def poll(cls, context: "Context") -> bool:  # noqa: ARG003
        instance = utilities.get_active_rig_instance()
        if not instance or not instance.body_rig:
            return False

        return bool(not instance.editing_rbf_solver)

    def run(self, instance: "RigInstance"):
        instance.editing_rbf_solver = True
        instance.auto_evaluate_body = False
        instance.body_rig.hide_set(False)
        utilities.switch_to_pose_mode(instance.body_rig)
        core.start_listening_for_pose_edits()


class CommitRBFSolverChanges(RBFEditorOperatorBase):
    """Commit the current changes for the selected RBF solver to the .dna file"""

    bl_idname = "meta_human_dna.commit_rbf_solver_changes"
    bl_label = "Commit RBF Solver Changes"

    @classmethod
    def poll(cls, context: "Context") -> bool:  # noqa: ARG003
        instance = utilities.get_active_rig_instance()
        if instance is None:
            return False

        return bool(instance.editing_rbf_solver)

    def validate(self, context: "Context", instance: "RigInstance") -> tuple[bool, str]:
        if not utilities.dependencies_are_valid():
            return False, "Dependencies are not valid. Ensure the core dependencies are installed."

        if not instance.body_rig:
            return False, "No body rig found. Please assign a body rig."
        if not instance.body_dna_file_path:
            return False, "No body .dna file. Please assign a body .dna file."
        if not Path(bpy.path.abspath(instance.body_dna_file_path)).exists():
            return False, "Body .dna file does not exist. Please check the file path."

        valid, message = core.validate_no_duplicate_driver_bone_values(instance)
        if not valid:
            return False, message

        return True, ""

    def run(self, instance: "RigInstance"):
        # Create a backup before committing edit mode changes
        from ..backup_manager.core import BackupType, create_backup

        create_backup(instance, BackupType.POSE_EDITOR)

        core.stop_listening_for_pose_edits()

        from ...bindings import meta_human_dna_core  # pyright: ignore[reportAttributeAccessIssue]

        reader = get_dna_reader(file_path=instance.body_dna_file_path)
        writer = get_dna_writer(file_path=instance.body_dna_file_path)
        data = utilities.collection_to_list(instance.rbf_solver_list)

        # destroy the reader and writer instances to release file locks and
        # any memory they are using
        instance.destroy()

        meta_human_dna_core.commit_rbf_data_to_dna(reader=reader, writer=writer, data=data)
        logger.info(f'DNA exported successfully to: "{instance.body_dna_file_path}"')

        # turn off editing mode and re-enable auto evaluation
        instance.editing_rbf_solver = False
        instance.auto_evaluate_body = True
        # re-initialize and evaluate the body rig
        instance.evaluate(component="body")


class RBFPoseOperatorBase(RBFEditorOperatorBase):
    def add_pose(
        self,
        instance: "RigInstance",
        pose_name: str,
        driven_bones: list[bpy.types.PoseBone],
        from_pose: "RBFPoseData | None" = None,
    ) -> "RBFPoseData | None":
        solver = instance.rbf_solver_list[self.solver_index]
        local_pose_index = len(solver.poses)
        pose = solver.poses.add()

        # For new poses, we need to assign a pose_index that indicates it's a new pose.
        # This must be >= the total DNA pose count so commit_rbf_data_to_dna knows it's new.
        # Calculate the next available global pose index by finding the max existing index
        # across all solvers and adding 1.
        max_existing_pose_index = -1
        for s in instance.rbf_solver_list:
            for p in s.poses:
                if p != pose:  # Don't include the pose we just added
                    max_existing_pose_index = max(max_existing_pose_index, p.pose_index)

        # Get the DNA pose count - new poses should have index >= this value
        dna_pose_count = instance.body_dna_reader.getRBFPoseCount() if instance.body_dna_reader else 0
        # The new pose index should be at least dna_pose_count, and also greater than any
        # existing pose index (in case other new poses were added in this session)
        new_pose_index = max(dna_pose_count, max_existing_pose_index + 1)

        pose.solver_index = self.solver_index
        pose.pose_index = new_pose_index
        pose.name = pose_name

        # copy the values from an existing pose if provided
        if from_pose:
            pose.joint_group_index = from_pose.joint_group_index
            pose.target_enable = from_pose.target_enable
            pose.scale_factor = from_pose.scale_factor

        driver_bone_name = solver.name.replace(RBF_SOLVER_POSTFIX, "")
        driver_bone = instance.body_rig.pose.bones.get(driver_bone_name)
        if not driver_bone:
            return None

        driver = pose.drivers.add()
        core.set_driver_bone_data(instance=instance, pose=pose, driver=driver, pose_bone=driver_bone, new=True)

        # When duplicating from an existing pose, copy the driven data directly
        # instead of reading from Blender's current bone transforms
        if from_pose:
            # Build a lookup of source pose's driven data by bone name
            source_driven_lookup = {d.name: d for d in from_pose.driven}
            for pose_bone in driven_bones:
                driven = pose.driven.add()
                source_driven = source_driven_lookup.get(pose_bone.name)
                if source_driven:
                    # Copy all driven data from the source pose
                    driven.name = source_driven.name
                    driven.pose_index = pose.pose_index  # Use the new pose's index
                    driven.joint_index = source_driven.joint_index
                    driven.data_type = source_driven.data_type
                    driven.location = source_driven.location[:]
                    driven.euler_rotation = source_driven.euler_rotation[:]
                    driven.quaternion_rotation = source_driven.quaternion_rotation[:]
                    driven.scale = source_driven.scale[:]
                else:
                    # Bone not in source pose, read from current scene
                    core.set_driven_bone_data(
                        instance=instance, pose=pose, driven=driven, pose_bone=pose_bone, new=True
                    )
        else:
            # New pose (not duplicating), read from current bone transforms
            for pose_bone in driven_bones:
                driven = pose.driven.add()
                core.set_driven_bone_data(instance=instance, pose=pose, driven=driven, pose_bone=pose_bone, new=True)

        # set the active pose to the new pose (use local index within solver's poses list)
        solver.poses_active_index = local_pose_index

        return pose


class AddRBFPose(RBFPoseOperatorBase):
    """Add a new RBF Pose"""

    bl_idname = "meta_human_dna.add_rbf_pose"
    bl_label = "Add RBF Pose"

    new_pose_name: bpy.props.StringProperty(
        default="default", description="The name of the new RBF Pose", get=get_new_pose_name, set=set_new_pose_name
    )  # pyright: ignore[reportInvalidTypeForm]

    def validate(self, context: "Context", instance: "RigInstance") -> tuple[bool, str]:
        if not context.selected_pose_bones:
            return False, "No pose bones selected. Please select at least one driver bone in pose mode."

        if not instance.body_initialized:
            instance.body_initialize()

        for pose_bone in context.selected_pose_bones:
            if pose_bone.name in instance.body_driver_bone_names:
                return (
                    False,
                    f'The selected bone "{pose_bone.name}" is assigned as a driver bone. Please select other bones.',
                )
            if pose_bone.name in instance.body_swing_bone_names:
                return (
                    False,
                    f'The selected bone "{pose_bone.name}" is assigned as a swing bone. Please select other bones.',
                )
            if pose_bone.name in instance.body_twist_bone_names:
                return (
                    False,
                    f'The selected bone "{pose_bone.name}" is assigned as a twist bone. Please select other bones.',
                )

        solver = instance.rbf_solver_list[instance.rbf_solver_list_active_index]
        for pose in solver.poses:
            if pose.name == self.new_pose_name:
                return False, f'A pose with the name "{self.new_pose_name}" already exists. Use a different name.'

        driver_name_name = solver.name.replace(RBF_SOLVER_POSTFIX, "")
        if not instance.body_rig.pose.bones.get(driver_name_name):
            return (
                False,
                (
                    f'The driver bone "{driver_name_name}" for the solver "{solver.name}" is not found in the '
                    "armature. Please ensure the bone exists."
                ),
            )

        return True, ""

    def run(self, instance: "RigInstance"):
        solver = instance.rbf_solver_list[instance.rbf_solver_list_active_index]
        new_pose_index = len(solver.poses)
        self.add_pose(
            instance=instance,
            pose_name=self.new_pose_name if self.new_pose_name else f"Pose{new_pose_index}",
            driven_bones=bpy.context.selected_pose_bones.copy(),
        )

    def invoke(self, context: "Context", event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self, width=200)  # type: ignore[return-type]

    def draw(self, context: "Context"):
        if not self.layout:
            return

        row = self.layout.row()
        row.label(text="Pose Name:")
        row = self.layout.row()
        row.prop(self, "new_pose_name", text="")
        row = self.layout.row()
        row.label(text="Adding bones:")
        box = self.layout.box()
        for pose_bone in context.selected_pose_bones:
            row = box.row()
            row.label(text=pose_bone.name, icon="BONE_DATA")

    @classmethod
    def poll(cls, context: "Context") -> bool:
        return bool(context.selected_pose_bones)


class DuplicateRBFPose(RBFPoseOperatorBase):
    """Duplicate the selected RBF Pose"""

    bl_idname = "meta_human_dna.duplicate_rbf_pose"
    bl_label = "Duplicate RBF Pose"

    def run(self, instance: "RigInstance"):
        solver = instance.rbf_solver_list[self.solver_index]
        pose = solver.poses[self.pose_index]

        # Generate a unique name for the duplicated pose
        count_same_name = 1
        for existing_pose in solver.poses:
            if existing_pose.name.startswith(pose.name):
                count_same_name += 1
        new_pose_name = f"{pose.name}_{count_same_name}"

        # Copy the driven bone names from the original pose
        driven_bones = []
        for driven in pose.driven:
            pose_bone = instance.body_rig.pose.bones.get(driven.name)
            if pose_bone:
                driven_bones.append(pose_bone)

        self.add_pose(
            instance=instance,
            pose_name=new_pose_name,
            driven_bones=driven_bones,
            from_pose=pose,
        )


class UpdateRBFPose(RBFEditorOperatorBase):
    """Update the selected RBF Pose. This includes both the driver and driven bone transforms for the current pose"""

    bl_idname = "meta_human_dna.update_rbf_pose"
    bl_label = "Update RBF Pose"

    def run(self, instance: "RigInstance"):
        # ensure the body is initialized
        if not instance.body_initialized:
            instance.body_initialize(update_rbf_solver_list=False)

        solver = instance.rbf_solver_list[self.solver_index]
        pose = solver.poses[self.pose_index]

        # Update all the driver bone data for the pose
        for driver in pose.drivers:
            driver_bone = instance.body_rig.pose.bones.get(driver.name)
            if driver_bone:
                core.set_driver_bone_data(instance=instance, pose=pose, driver=driver, pose_bone=driver_bone)
            else:
                self.report(
                    {"ERROR"},
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
                core.set_driven_bone_data(instance=instance, pose=pose, driven=driven, pose_bone=driven_pose_bone)
            else:
                logger.warning(
                    f'Driven bone "{driven.name}" was not found in armature when '
                    f'updating RBF Pose "{pose.name}". It will be deleted from '
                    "the pose when this data is committed to the dna."
                )


class RemoveRBFPose(RBFEditorOperatorBase):
    """Remove the selected RBF Pose"""

    bl_idname = "meta_human_dna.remove_rbf_pose"
    bl_label = "Remove RBF Pose"

    def run(self, instance: "RigInstance"):
        solver = instance.rbf_solver_list[instance.rbf_solver_list_active_index]
        solver.poses.remove(solver.poses_active_index)
        to_index = min(solver.poses_active_index, len(solver.poses) - 1)
        solver.poses_active_index = to_index


class AddRBFDriver(RBFEditorOperatorBase):
    """Add a new RBF Driver bone"""

    bl_idname = "meta_human_dna.add_rbf_driver"
    bl_label = "Add RBF Driver"

    def run(self, instance: "RigInstance"):
        pass


class RemoveRBFDriver(RBFEditorOperatorBase):
    """Remove the selected RBF Driver bone"""

    bl_idname = "meta_human_dna.remove_rbf_driver"
    bl_label = "Remove RBF Driver"

    def run(self, instance: "RigInstance"):
        pass


class AddRBFDriven(RBFEditorOperatorBase):
    """
    Add a new RBF Driven bone to the current pose. You must select the 'default' pose to add driven bones.
    Any selected bones will be added to all poses in this solver, since poses are deltas from the default
    pose.
    """

    bl_idname = "meta_human_dna.add_rbf_driven"
    bl_label = "Add RBF Driven Bone"

    @classmethod
    def poll(cls, _: "Context") -> bool:
        instance = utilities.get_active_rig_instance()
        if not instance or not instance.body_rig:
            return False

        pose = core.get_active_pose(instance)
        return bool(pose and pose.name == "default")

    def validate(self, context: "Context", instance: "RigInstance") -> tuple[bool, str]:
        if not context.selected_pose_bones:
            return False, "No pose bones selected. Please select at least one driven bone in pose mode."

        return True, ""

    def run(self, instance: "RigInstance"):
        solver = instance.rbf_solver_list[self.solver_index]
        pose = solver.poses[self.pose_index]

        selected_pose_bones = bpy.context.selected_pose_bones.copy()

        for pose_bone in selected_pose_bones:
            if pose_bone.name not in [d.name for d in pose.driven]:
                driven = pose.driven.add()
                core.set_driven_bone_data(instance=instance, pose=pose, driven=driven, pose_bone=pose_bone, new=True)

        # set the active driven to the last one added
        pose.driven_active_index = len(pose.driven) - 1


class RemoveRBFDriven(RBFEditorOperatorBase):
    """
    Remove the selected RBF Driven bone from the current pose. You must select the 'default' pose to remove driven
    bones. Any selected bones will be removed from all poses in this solver, since poses are deltas from the default
    pose.
    """

    bl_idname = "meta_human_dna.remove_rbf_driven"
    bl_label = "Remove RBF Driven Bone"

    @classmethod
    def poll(cls, _: "Context") -> bool:
        instance = utilities.get_active_rig_instance()
        if not instance or not instance.body_rig:
            return False

        pose = core.get_active_pose(instance)
        return bool(pose and pose.name == "default")

    def run(self, instance: "RigInstance"):
        pass
