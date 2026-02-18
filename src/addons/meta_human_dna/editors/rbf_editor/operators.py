# standard library imports
import logging
import math

from pathlib import Path

# third-party imports
import bpy

# local imports
from ... import utilities
from ...constants import RBF_SOLVER_POSTFIX, ToolInfo
from ...dna_io import get_dna_reader, get_dna_writer

# type checking imports
from ...typing import *  # noqa: F403
from ...ui.toast import clear_toasts, toast_info, toast_success, toast_warning
from . import change_tracker, core
from .viewport_overlay import register_draw_handler, unregister_draw_handler


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
    """Add a new RBF Solver based on the selected pose bone."""

    bl_idname = f"{ToolInfo.NAME}.add_rbf_solver"
    bl_label = "Add RBF Solver"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: "Context") -> bool:
        instance = utilities.get_active_rig_instance()
        if not instance or not instance.body_rig:
            return False
        # Must be in edit mode for the solver and have a pose bone selected
        if not instance.editing_rbf_solver:
            return False
        return context.active_pose_bone is not None

    def validate(self, context: "Context", instance: "RigInstance") -> tuple[bool, str]:
        if not context.active_pose_bone:
            return False, "No pose bone selected. Please select a bone to use as the driver for the new solver."

        driver_bone = context.active_pose_bone
        driver_bone_name = driver_bone.name

        # Check that the selected bone belongs to the body rig
        if driver_bone.id_data != instance.body_rig:
            return False, f'Bone "{driver_bone_name}" does not belong to the body rig.'

        # Delegate to core validation
        return core.validate_add_rbf_solver(instance, driver_bone_name)

    def run(self, instance: "RigInstance"):
        driver_bone = bpy.context.active_pose_bone
        if not driver_bone:
            return

        # Get the driver quaternion from the pose bone
        driver_quaternion = tuple(driver_bone.rotation_quaternion[:])

        # Delegate to core function
        success, message, _ = core.add_rbf_solver(
            instance=instance,
            driver_bone_name=driver_bone.name,
            driver_quaternion=driver_quaternion,  # pyright: ignore[reportArgumentType]
        )

        if not success:
            self.report({"ERROR"}, message)
            return

        # Update change tracking and show toast
        change_tracker.update_tracking(instance)
        toast_success(f"Added solver for '{driver_bone.name}'", duration=2.5)


class RemoveRBFSolver(RBFEditorOperatorBase):
    """Remove the selected RBF Solver."""

    bl_idname = f"{ToolInfo.NAME}.remove_rbf_solver"
    bl_label = "Remove RBF Solver"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: "Context") -> bool:  # noqa: ARG003
        instance = utilities.get_active_rig_instance()
        if not instance or not instance.body_rig:
            return False
        # Must be in edit mode and have at least one solver
        if not instance.editing_rbf_solver:
            return False
        return len(instance.rbf_solver_list) > 0

    def run(self, instance: "RigInstance"):
        # Get the solver name before removal for the toast
        solver = core.get_active_solver(instance)
        solver_name = solver.name if solver else "solver"

        # Delegate to core function
        success, message = core.remove_rbf_solver(instance)

        if not success:
            self.report({"ERROR"}, message)
            return

        # Update change tracking and show toast
        change_tracker.update_tracking(instance)
        toast_warning(f"Removed solver '{solver_name}'", duration=2.5)


class EvaluateRBFSolvers(RBFEditorOperatorBase):
    """Evaluate the RBF Solvers"""

    bl_idname = f"{ToolInfo.NAME}.evaluate_rbf_solvers"
    bl_label = "Evaluate RBF Solvers"

    def run(self, instance: "RigInstance"):
        instance.evaluate(component="body")


class RevertRBFSolver(RBFEditorOperatorBase):
    """Revert RBF solver back to the original DNA."""

    bl_idname = f"{ToolInfo.NAME}.revert_rbf_solver"
    bl_label = "Revert RBF Solver"

    def run(self, instance: "RigInstance"):
        utilities.reset_pose(instance.body_rig)
        instance.editing_rbf_solver = False
        instance.auto_evaluate_body = True

        tracker = change_tracker.get_change_tracker(instance)
        change_count = tracker.change_count if tracker else 0

        # Clear change tracking and toasts
        change_tracker.clear_tracking(instance)
        clear_toasts()
        ops = utilities.get_addon_ops_module()
        ops.force_evaluate()

        toast_warning(f"Reverted {change_count} edit(s)", duration=3.0)
        # Unregister the draw handler after the final toast has been shown
        bpy.app.timers.register(unregister_draw_handler, first_interval=3.0)


class EditRBFSolver(RBFEditorOperatorBase):
    """Switch to Editing mode for the selected RBF solver. Changes will not take effect until committed to the .dna file."""  # noqa: E501

    bl_idname = f"{ToolInfo.NAME}.edit_rbf_solver"
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
        register_draw_handler()

        # Initialize change tracking when entering edit mode
        change_tracker.initialize_tracking(instance)
        toast_info("Entered RBF Editor edit mode", duration=2.0)


class CommitRBFSolverChanges(RBFEditorOperatorBase):
    """Commit the current changes for the selected RBF solver to the .dna file"""

    bl_idname = f"{ToolInfo.NAME}.commit_rbf_solver_changes"
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

        valid, message = core.validate_solver_non_default_pose_with_driven_bones(instance)
        if not valid:
            return False, message

        return True, ""

    def run(self, instance: "RigInstance"):
        # Create a backup before committing edit mode changes
        from ..backup_manager.core import BackupType, create_backup

        create_backup(instance, BackupType.PRE_RBF_EDITOR_COMMIT)

        from ...bindings import meta_human_dna_core  # pyright: ignore[reportAttributeAccessIssue]

        reader = get_dna_reader(file_path=instance.body_dna_file_path)
        writer = get_dna_writer(file_path=instance.body_dna_file_path)
        data = utilities.collection_to_list(instance.rbf_solver_list)

        # Get the change count before clearing for the toast message
        tracker = change_tracker.get_change_tracker(instance)
        change_count = tracker.change_count if tracker else 0

        # destroy the reader and writer instances to release file locks and
        # any memory they are using
        instance.destroy()

        try:
            meta_human_dna_core.commit_rbf_data_to_dna(reader=reader, writer=writer, data=data)
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return

        # turn off editing mode and re-enable auto evaluation
        instance.editing_rbf_solver = False
        instance.auto_evaluate_body = True

        # Clear change tracking and toasts
        change_tracker.clear_tracking(instance)
        clear_toasts()

        # re-initialize and evaluate the body rig
        instance.evaluate(component="body")
        logger.info(f'DNA exported successfully to: "{instance.body_dna_file_path}"')

        # Show success toast
        toast_success(f"Committed {change_count} change(s) to DNA", duration=3.0)

        # Unregister the draw handler after the final toast has been shown
        bpy.app.timers.register(unregister_draw_handler, first_interval=3.0)

        # Create a backup with can toggle back too
        create_backup(instance, BackupType.POST_RBF_EDITOR_COMMIT)


class RBFPoseOperatorBase(RBFEditorOperatorBase):
    def add_pose(
        self,
        instance: "RigInstance",
        pose_name: str,
        driven_bones: list[bpy.types.PoseBone],
        from_pose: "RBFPoseData | None" = None,
    ) -> "RBFPoseData | None":
        """
        Add a new pose to an RBF solver.

        This method delegates to the core.add_rbf_pose function, which handles
        all the logic for creating poses with proper indexing, driver/driven setup,
        and default pose updating.

        Args:
            instance: The active rig instance.
            pose_name: The name for the new pose.
            driven_bones: List of Blender PoseBone objects to be driven.
            from_pose: Optional existing pose to duplicate from.

        Returns:
            The newly created RBFPoseData, or None if creation failed.
        """
        success, message, _ = core.add_rbf_pose(
            instance=instance,
            pose_name=pose_name,
            solver_index=instance.rbf_solver_list_active_index,
            driven_bones=driven_bones,
            from_pose=from_pose,
        )

        if not success:
            logger.error(message)
            return None

        # Return the newly added pose
        solver = instance.rbf_solver_list[instance.rbf_solver_list_active_index]
        return solver.poses[solver.poses_active_index]


class AddRBFPose(RBFPoseOperatorBase):
    """Add a new RBF Pose to the selected solver."""

    bl_idname = f"{ToolInfo.NAME}.add_rbf_pose"
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
            instance.body_initialize(update_rbf_solver_list=False)

        # Use window manager to store the collection (persists across draw calls)
        addon_window_manager_properties = utilities.get_addon_window_manager_properties(context)
        if not hasattr(addon_window_manager_properties, "add_pose_driven_bones"):
            return

        # Clear existing selections
        addon_window_manager_properties.add_pose_driven_bones.clear()  # type: ignore[reportAttributeAccessIssue]

        # Get available driven bones
        available_bones = core.get_available_driven_bones(instance)

        for bone_name, joint_index, is_in_existing in available_bones:
            item = addon_window_manager_properties.add_pose_driven_bones.add()  # type: ignore[reportAttributeAccessIssue]
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

        addon_window_manager_properties = utilities.get_addon_window_manager_properties(context)
        if not hasattr(addon_window_manager_properties, "add_pose_driven_bones"):
            return []

        driven_bones = []
        for item in addon_window_manager_properties.add_pose_driven_bones:
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
            instance.body_initialize(update_rbf_solver_list=False)

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

        pose_name = self.new_pose_name if self.new_pose_name else f"Pose{new_pose_index}"
        pose = self.add_pose(
            instance=instance,
            pose_name=pose_name,
            driven_bones=driven_bones,
        )

        if pose:
            # Update change tracking and show toast
            change_tracker.update_tracking(instance)
            toast_success(f"Added pose '{pose_name}'", duration=2.5)

    def invoke(self, context: "Context", event: bpy.types.Event) -> set[str]:
        # Populate bone selections when the dialog is opened
        self._populate_bone_selections(context)
        return context.window_manager.invoke_props_dialog(self, width=400)  # type: ignore[return-type]

    def draw(self, context: "Context"):
        if not self.layout:
            return

        layout = self.layout
        addon_window_manager_properties = utilities.get_addon_window_manager_properties(context)

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
        if hasattr(addon_window_manager_properties, "add_pose_driven_bones"):
            # Count selected bones for display
            selected_count = sum(1 for item in addon_window_manager_properties.add_pose_driven_bones if item.selected)
            row = layout.row()
            row.label(text=f"Selected: {selected_count} bones")

            # UIList for bone selection with search/filter capability
            layout.template_list(
                "META_HUMAN_DNA_UL_bone_selection",
                "",
                addon_window_manager_properties,
                "add_pose_driven_bones",
                addon_window_manager_properties,
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

    bl_idname = f"{ToolInfo.NAME}.duplicate_rbf_pose"
    bl_label = "Duplicate RBF Pose"

    @classmethod
    def poll(cls, context: "Context") -> bool:  # noqa: ARG003
        instance = utilities.get_active_rig_instance()
        if not instance or not instance.body_rig:
            return False

        pose = core.get_active_pose(instance)
        if not pose or pose.name == "default":
            return False

        # Must be in edit mode for the solver
        return instance.editing_rbf_solver

    def run(self, instance: "RigInstance"):
        solver = core.get_active_solver(instance)
        if not solver:
            return
        pose = core.get_active_pose(instance)
        if not pose:
            return

        # Generate a unique name for the duplicated pose
        count_same_name = 1
        for existing_pose in solver.poses:
            if existing_pose.name.startswith(pose.name):
                count_same_name += 1

        chunks = pose.name.split("_")
        if len(chunks) > 2 and (chunks[-2].isdigit() and chunks[-1].isdigit()):
            new_pose_name = "_".join(chunks[:-1]) + f"_{int(chunks[-1]) + 1}"
        else:
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

        # Update change tracking and show toast
        change_tracker.update_tracking(instance)
        toast_success(f"Duplicated pose '{pose.name}' to '{new_pose_name}'", duration=2.5)


class ApplyRBFPoseEdits(RBFEditorOperatorBase):
    bl_idname = f"{ToolInfo.NAME}.apply_rbf_pose_edits"
    bl_label = "Apply RBF Pose Edits"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = (
        "Apply the driven and driver bone transformations to the selected RBF Pose. "
        "Note: changes are not committed to the .dna file until the solver changes are committed "
        "using the 'Commit' operator."
    )

    @classmethod
    def poll(cls, context: "Context") -> bool:  # noqa: ARG003
        instance = utilities.get_active_rig_instance()
        if not instance or not instance.body_rig:
            return False
        # Must be in edit mode for the solver
        if not instance.editing_rbf_solver:
            return False
        # Must have at least one solver with poses
        if len(instance.rbf_solver_list) == 0:
            return False
        solver = instance.rbf_solver_list[instance.rbf_solver_list_active_index]
        return len(solver.poses) > 0

    def run(self, instance: "RigInstance"):
        # ensure the body is initialized
        if not instance.body_initialized:
            instance.body_initialize(update_rbf_solver_list=False)

        solver = core.get_active_solver(instance)
        if not solver:
            return
        pose = core.get_active_pose(instance)
        if not pose:
            return

        # Update the change tracker
        tracker = change_tracker.get_change_tracker(instance)
        change_count = tracker.change_count if tracker else 0

        # Update all the driver bone data for the pose
        for driver in pose.drivers:
            driver_bone = instance.body_rig.pose.bones.get(driver.name)
            if driver_bone:
                update_message = core.set_driver_bone_data(
                    instance=instance, pose=pose, driver=driver, pose_bone=driver_bone
                )
                if update_message:
                    toast_info(update_message, duration=2.5)
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
                update_message = core.set_driven_bone_data(
                    instance=instance, pose=pose, driven=driven, pose_bone=driven_pose_bone
                )
                if update_message:
                    toast_info(update_message, duration=2.5)
            else:
                logger.warning(
                    f'Driven bone "{driven.name}" was not found in armature when '
                    f'updating RBF Pose "{pose.name}". It will be deleted from '
                    "the pose when this data is committed to the dna."
                )

        # Update the change tracker
        current_tracker = change_tracker.update_tracking(instance)
        current_change_count = current_tracker.change_count - change_count
        if current_change_count > 0:
            # Show toast notification
            toast_success(f"Applied {current_change_count} edits to pose '{pose.name}'", duration=2.5)


class RemoveRBFPose(RBFEditorOperatorBase):
    bl_idname = f"{ToolInfo.NAME}.remove_rbf_pose"
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

        # Get pose name before removal for toast
        pose = solver.poses[solver.poses_active_index]
        pose_name = pose.name

        solver.poses.remove(solver.poses_active_index)
        to_index = min(solver.poses_active_index, len(solver.poses) - 1)
        solver.poses_active_index = to_index

        # Update change tracking and show toast
        change_tracker.update_tracking(instance)
        toast_warning(f"Removed pose '{pose_name}'", duration=2.5)


class AddRBFDriven(RBFEditorOperatorBase):
    bl_idname = f"{ToolInfo.NAME}.add_rbf_driven"
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

        pose = core.get_active_pose(instance)
        if not pose:
            return False, "No active pose found in the solver."

        for pose_bone in context.selected_pose_bones:
            if pose_bone.name in instance.body_driver_bone_names:
                return False, f'Bone "{pose_bone.name}" is a driver bone and cannot be added as a driven bone.'
            if pose_bone.name in instance.body_swing_bone_names:
                return False, f'Bone "{pose_bone.name}" is a swing bone and cannot be added as a driven bone.'
            if pose_bone.name in instance.body_twist_bone_names:
                return False, f'Bone "{pose_bone.name}" is a twist bone and cannot be added as a driven bone.'
            if pose_bone.id_data != instance.body_rig:
                return False, f'Bone "{pose_bone.name}" does not belong to the body rig and cannot be added.'
            if pose_bone.name in [d.name for d in pose.driven]:
                return False, f'Bone "{pose_bone.name}" is already a driven bone in the "{pose.name}" pose.'

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

        # Update change tracking and show toast
        change_tracker.update_tracking(instance)
        toast_success(message=message, duration=2.5)


class RemoveRBFDriven(RBFEditorOperatorBase):
    bl_idname = f"{ToolInfo.NAME}.remove_rbf_driven"
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

            # Update change tracking and show toast
            change_tracker.update_tracking(instance)
            toast_warning(message=f"Removed driven bone '{active_driven.name}'", duration=2.5)


class MirrorRBFSolver(RBFEditorOperatorBase):
    """Mirror the active RBF solver to the opposite side, creating a new solver with mirrored poses."""

    bl_idname = f"{ToolInfo.NAME}.mirror_rbf_solver"
    bl_label = "Mirror RBF Solver"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = (
        "Mirror the active RBF solver to the opposite side. This creates a new solver with mirrored "
        "driver/driven bone names and mirrored transform values for all poses."
    )

    @classmethod
    def poll(cls, context: "Context") -> bool:  # noqa: ARG003
        instance = utilities.get_active_rig_instance()
        if not instance or not instance.body_rig:
            return False
        # Must be in edit mode for the solver
        if not instance.editing_rbf_solver:
            return False
        # Must have at least one solver
        return len(instance.rbf_solver_list) > 0

    def validate(self, context: "Context", instance: "RigInstance") -> tuple[bool, str]:
        # Get the regex patterns from addon preferences
        addon_preferences = utilities.get_addon_preferences()
        if not addon_preferences:
            return False, "Addon preferences not found."

        solver_regex = addon_preferences.rbf_editor_solver_mirror_regex_pattern
        bone_regex = addon_preferences.rbf_editor_bone_mirror_regex_pattern

        return core.validate_mirror_solver(instance, solver_regex, bone_regex)

    def run(self, instance: "RigInstance"):
        # Get the regex patterns from addon preferences
        addon_preferences = utilities.get_addon_preferences()
        if not addon_preferences:
            self.report({"ERROR"}, "Addon preferences not found.")
            return

        solver_regex = addon_preferences.rbf_editor_solver_mirror_regex_pattern
        bone_regex = addon_preferences.rbf_editor_bone_mirror_regex_pattern
        pose_regex = addon_preferences.rbf_editor_pose_mirror_regex_pattern

        success, message, _ = core.mirror_solver(
            instance=instance,
            solver_regex=solver_regex,
            bone_regex=bone_regex,
            pose_regex=pose_regex,
            mirror_axis="x",
        )

        if not success:
            self.report({"ERROR"}, message)
            return

        # Update change tracking and show toast
        change_tracker.update_tracking(instance)
        toast_success(message=message, duration=2.5)


class MirrorRBFPose(RBFEditorOperatorBase):
    """Mirror the active RBF pose to the mirrored solver on the opposite side."""

    bl_idname = f"{ToolInfo.NAME}.mirror_rbf_pose"
    bl_label = "Mirror RBF Pose"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = (
        "Mirror the active RBF pose to the mirrored solver. This creates a new pose in the target solver "
        "with mirrored driver/driven bone names and mirrored transform values."
    )

    @classmethod
    def poll(cls, context: "Context") -> bool:  # noqa: ARG003
        instance = utilities.get_active_rig_instance()
        if not instance or not instance.body_rig:
            return False
        # Must be in edit mode for the solver
        if not instance.editing_rbf_solver:
            return False
        # Must have a non-default pose selected
        pose = core.get_active_pose(instance)
        return pose is not None and pose.name.lower() != "default"

    def validate(self, context: "Context", instance: "RigInstance") -> tuple[bool, str]:
        # Get the regex patterns from addon preferences
        addon_preferences = utilities.get_addon_preferences()
        if not addon_preferences:
            return False, "Addon preferences not found."

        solver_regex = addon_preferences.rbf_editor_solver_mirror_regex_pattern
        pose_regex = addon_preferences.rbf_editor_pose_mirror_regex_pattern

        return core.validate_mirror_pose(instance=instance, solver_regex=solver_regex, pose_regex=pose_regex)

    def run(self, instance: "RigInstance"):
        # Get the regex patterns from addon preferences
        addon_preferences = utilities.get_addon_preferences()
        if not addon_preferences:
            self.report({"ERROR"}, "Addon preferences not found.")
            return

        solver_regex = addon_preferences.rbf_editor_solver_mirror_regex_pattern
        bone_regex = addon_preferences.rbf_editor_bone_mirror_regex_pattern
        pose_regex = addon_preferences.rbf_editor_pose_mirror_regex_pattern

        success, message, _ = core.mirror_pose(
            instance=instance,
            solver_regex=solver_regex,
            bone_regex=bone_regex,
            pose_regex=pose_regex,
            mirror_axis="x",
        )

        if not success:
            self.report({"ERROR"}, message)
            return

        # Update change tracking and show toast
        change_tracker.update_tracking(instance)
        toast_success(message=message, duration=2.5)
