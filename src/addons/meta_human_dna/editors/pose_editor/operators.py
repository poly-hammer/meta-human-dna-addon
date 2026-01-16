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
                    location = source_driven.location[:]
                    euler_rotation = source_driven.euler_rotation[:]
                    quaternion_rotation = source_driven.quaternion_rotation[:]
                    scale = source_driven.scale[:]
                    if from_pose.name == "default":
                        location = [0.0, 0.0, 0.0]
                        euler_rotation = [0.0, 0.0, 0.0]
                        quaternion_rotation = [1.0, 0.0, 0.0, 0.0]
                        scale = [1.0, 1.0, 1.0]

                    # Copy all driven data from the source pose
                    driven.name = source_driven.name
                    driven.pose_index = pose.pose_index  # Use the new pose's index
                    driven.joint_index = source_driven.joint_index
                    driven.data_type = source_driven.data_type
                    driven.location = location
                    driven.euler_rotation = euler_rotation
                    driven.quaternion_rotation = quaternion_rotation
                    driven.scale = scale
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
    """Add a new RBF Pose to the selected solver."""

    bl_idname = "meta_human_dna.add_rbf_pose"
    bl_label = "Add RBF Pose"
    bl_options = {"REGISTER", "UNDO"}

    new_pose_name: bpy.props.StringProperty(
        default="default", description="The name of the new RBF Pose", get=get_new_pose_name, set=set_new_pose_name
    )  # pyright: ignore[reportInvalidTypeForm]

    def _populate_bone_selections(self, context: "Context") -> None:
        """Populate the bone selection collections based on the current solver's joint group."""
        instance = utilities.get_active_rig_instance()
        if not instance or not instance.body_rig:
            return

        if not instance.body_initialized:
            instance.body_initialize()

        # Use window manager to store the collection (persists across draw calls)
        wm = context.window_manager
        if not hasattr(wm.meta_human_dna, "add_pose_driven_bones"):
            return

        # Clear existing selections
        wm.meta_human_dna.add_pose_driven_bones.clear()

        # Get available driven bones
        available_bones = core.get_available_driven_bones(instance)

        for bone_name, joint_index, is_in_existing in available_bones:
            item = wm.meta_human_dna.add_pose_driven_bones.add()
            item.name = bone_name
            # Pre-select bones that are already in the joint group
            item.selected = is_in_existing
            item.joint_index = joint_index
            item.is_in_existing_joint_group = is_in_existing

    def _get_selected_driven_bones(self, context: "Context") -> list[bpy.types.PoseBone]:
        """Get the list of selected driven bones from the selection collections."""
        instance = utilities.get_active_rig_instance()
        if not instance or not instance.body_rig:
            return []

        wm = context.window_manager
        if not hasattr(wm.meta_human_dna, "add_pose_driven_bones"):
            return []

        driven_bones = []
        for item in wm.meta_human_dna.add_pose_driven_bones:
            if item.selected:
                pose_bone = instance.body_rig.pose.bones.get(item.name)
                if pose_bone:
                    driven_bones.append(pose_bone)

        return driven_bones

    def validate(self, context: "Context", instance: "RigInstance") -> tuple[bool, str]:
        # Get selected driven bones from our selection lists
        driven_bones = self._get_selected_driven_bones(context)

        if not driven_bones:
            return False, "No driven bones selected. Please select at least one driven bone."

        if not instance.body_initialized:
            instance.body_initialize()

        for pose_bone in driven_bones:
            if pose_bone.name in instance.body_driver_bone_names:
                return (
                    False,
                    f'The selected bone "{pose_bone.name}" is assigned as a driver bone. Please deselect it.',
                )
            if pose_bone.name in instance.body_swing_bone_names:
                return (
                    False,
                    f'The selected bone "{pose_bone.name}" is assigned as a swing bone. Please deselect it.',
                )
            if pose_bone.name in instance.body_twist_bone_names:
                return (
                    False,
                    f'The selected bone "{pose_bone.name}" is assigned as a twist bone. Please deselect it.',
                )

        solver = instance.rbf_solver_list[instance.rbf_solver_list_active_index]
        for pose in solver.poses:
            if pose.name == self.new_pose_name:
                return False, f'A pose with the name "{self.new_pose_name}" already exists. Use a different name.'

        driver_bone_name = solver.name.replace(RBF_SOLVER_POSTFIX, "")
        if not instance.body_rig.pose.bones.get(driver_bone_name):
            return (
                False,
                (
                    f'The driver bone "{driver_bone_name}" for the solver "{solver.name}" is not found in the '
                    "armature. Please ensure the bone exists."
                ),
            )

        # Validate and update joint group consistency
        driven_bone_names = [pb.name for pb in driven_bones]
        valid, message = core.validate_and_update_solver_joint_group(instance, driven_bone_names)
        if not valid:
            return False, message

        return True, ""

    def run(self, instance: "RigInstance"):
        solver = instance.rbf_solver_list[instance.rbf_solver_list_active_index]
        new_pose_index = len(solver.poses)

        # Get driven bones from our selection
        driven_bones = self._get_selected_driven_bones(bpy.context)  # pyright: ignore[reportArgumentType]

        self.add_pose(
            instance=instance,
            pose_name=self.new_pose_name if self.new_pose_name else f"Pose{new_pose_index}",
            driven_bones=driven_bones,
        )

    def invoke(self, context: "Context", event: bpy.types.Event) -> set[str]:
        # Populate bone selections when the dialog is opened
        self._populate_bone_selections(context)
        return context.window_manager.invoke_props_dialog(self, width=400)  # type: ignore[return-type]

    def draw(self, context: "Context"):
        if not self.layout:
            return

        layout = self.layout
        wm = context.window_manager

        # Pose name input
        row = layout.row()
        row.label(text="Pose Name:")
        row = layout.row()
        row.prop(self, "new_pose_name", text="")

        layout.separator()

        # Driven bones selection header
        row = layout.row()
        row.label(text="Driven Bones:", icon="BONE_DATA")

        # Info about joint group consistency
        instance = utilities.get_active_rig_instance()
        if instance:
            existing_bones = core.get_solver_joint_group_bones(instance)
            if existing_bones:
                box = layout.box()
                col = box.column(align=True)
                col.label(text=f"Existing joint group has {len(existing_bones)} bones", icon="INFO")
                col.label(text="Pre-selected bones are linked to existing group.")
                col.label(text="Adding new bones will update all poses.")

        # Draw driven bone selections as UIList
        if hasattr(wm.meta_human_dna, "add_pose_driven_bones"):
            # Count selected bones for display
            selected_count = sum(1 for item in wm.meta_human_dna.add_pose_driven_bones if item.selected)
            row = layout.row()
            row.label(text=f"Selected: {selected_count} bones")

            # UIList for bone selection with search/filter capability
            layout.template_list(
                "META_HUMAN_DNA_UL_bone_selection",
                "",
                wm.meta_human_dna,
                "add_pose_driven_bones",
                wm.meta_human_dna,
                "add_pose_driven_bones_active_index",
                rows=8,
            )

    @classmethod
    def poll(cls, context: "Context") -> bool:  # noqa: ARG003
        instance = utilities.get_active_rig_instance()
        if not instance or not instance.body_rig:
            return False

        # Must be in edit mode for the solver
        return instance.editing_rbf_solver


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
    bl_idname = "meta_human_dna.remove_rbf_pose"
    bl_label = "Remove RBF Pose"
    bl_description = "Remove the active RBF Pose from the selected solver. Note: the default pose cannot be removed."

    @classmethod
    def poll(cls, _: "Context") -> bool:
        instance = utilities.get_active_rig_instance()
        if not instance or not instance.body_rig or not instance.editing_rbf_solver:
            return False

        pose = core.get_active_pose(instance)
        if pose:
            return pose.name != "default"
        return False

    def run(self, instance: "RigInstance"):
        solver = instance.rbf_solver_list[instance.rbf_solver_list_active_index]
        solver.poses.remove(solver.poses_active_index)
        to_index = min(solver.poses_active_index, len(solver.poses) - 1)
        solver.poses_active_index = to_index


class AddRBFDriven(RBFEditorOperatorBase):
    bl_idname = "meta_human_dna.add_rbf_driven"
    bl_label = "Add RBF Driven Bone"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = (
        "Add selected bones as driven bones to the solver's joint group. This will add the bones to ALL poses "
        "in this solver."
    )

    @classmethod
    def poll(cls, _: "Context") -> bool:
        instance = utilities.get_active_rig_instance()
        if not instance or not instance.body_rig:
            return False
        # Must be in edit mode for the solver
        return instance.editing_rbf_solver

    def validate(self, context: "Context", instance: "RigInstance") -> tuple[bool, str]:
        if not context.selected_pose_bones:
            return False, "No pose bones selected. Please select at least one bone to add in pose mode."

        # Check that selected bones are not driver, swing, or twist bones
        if not instance.body_initialized:
            instance.body_initialize(update_rbf_solver_list=False)

        for pose_bone in context.selected_pose_bones:
            if pose_bone.name in instance.body_driver_bone_names:
                return False, f'Bone "{pose_bone.name}" is a driver bone and cannot be added as a driven bone.'
            if pose_bone.name in instance.body_swing_bone_names:
                return False, f'Bone "{pose_bone.name}" is a swing bone and cannot be added as a driven bone.'
            if pose_bone.name in instance.body_twist_bone_names:
                return False, f'Bone "{pose_bone.name}" is a twist bone and cannot be added as a driven bone.'
            if pose_bone.id_data != instance.body_rig:
                return False, f'Bone "{pose_bone.name}" does not belong to the body rig and cannot be added.'

        return True, ""

    def run(self, instance: "RigInstance"):
        selected_bone_names = [pb.name for pb in bpy.context.selected_pose_bones]

        valid, message = core.add_driven_bones_to_solver(
            instance=instance,
            bone_names_to_add=selected_bone_names,
            update_active_pose_transforms=True,
        )

        if not valid:
            self.report({"ERROR"}, message)
            return

        self.report({"INFO"}, message)


class RemoveRBFDriven(RBFEditorOperatorBase):
    bl_idname = "meta_human_dna.remove_rbf_driven"
    bl_label = "Remove RBF Driven Bone"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = (
        "Remove the active driven bone from the solver's joint group. This will remove the bones from ALL poses "
        "in this solver."
    )

    @classmethod
    def poll(cls, _: "Context") -> bool:
        instance = utilities.get_active_rig_instance()
        if not instance or not instance.body_rig:
            return False
        # Must be in edit mode for the solver
        if not instance.editing_rbf_solver:
            return False
        # Must have at least one pose with driven bones
        pose = core.get_active_pose(instance)
        return pose is not None and len(pose.driven) > 0

    def validate(self, context: "Context", instance: "RigInstance") -> tuple[bool, str]:
        active_driven = core.get_active_driven(instance)
        if not active_driven:
            return False, "The active pose has no driven bones to remove."

        # Check that at least one selected bone is in the joint group
        existing_bones = core.get_solver_joint_group_bones(instance)
        selected_bone_names = {active_driven.name}

        bones_to_remove = selected_bone_names & existing_bones
        if not bones_to_remove:
            return False, "None of the selected bones are in the solver's joint group."

        # Check that we're not removing ALL bones
        remaining_bones = existing_bones - bones_to_remove
        if not remaining_bones:
            return False, "Cannot remove all driven bones. At least one driven bone must remain in the solver."

        return True, ""

    def run(self, instance: "RigInstance"):
        active_driven = core.get_active_driven(instance)
        if active_driven:
            # Remove the bone from all poses
            valid, message = core.remove_driven_bone_from_solver(instance, {active_driven.name})
            if not valid:
                self.report({"ERROR"}, message)
                return

        self.report({"INFO"}, message)
