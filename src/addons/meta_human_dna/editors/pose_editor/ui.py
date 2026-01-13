# standard library imports
from pathlib import Path

# third party imports
import bpy

from bl_ui.generic_ui_list import draw_ui_list

# local imports
from ...typing import *  # noqa: F403
from ...ui.view_3d import RigInstanceDependentPanel, valid_rig_instance_exists


class META_HUMAN_DNA_UL_rbf_solvers(bpy.types.UIList):
    def draw_item(
        self,
        context: "Context",
        layout: bpy.types.UILayout,
        data: "RigInstance",
        item: "RBFSolverData",
        icon: int | None,
        active_data: "RigInstance",
        active_prop_name: str,
    ):
        layout.label(text=item.name)


class META_HUMAN_DNA_UL_rbf_poses(bpy.types.UIList):
    def draw_item(
        self,
        context: "Context",
        layout: bpy.types.UILayout,
        data: "RigInstance",
        item: "RBFPoseData",
        icon: int | None,
        active_data: "RigInstance",
        active_prop_name: str,
    ):
        properties = context.scene.meta_human_dna
        active_index = properties.rig_instance_list_active_index
        instance = properties.rig_instance_list[active_index]
        if instance.editing_rbf_solver:
            layout.prop(item, "name", icon="ARMATURE_DATA", text="", emboss=False)
        else:
            layout.label(text=item.name, icon="ARMATURE_DATA")


class META_HUMAN_DNA_UL_rbf_drivers(bpy.types.UIList):
    def draw_item(
        self,
        context: "Context",
        layout: bpy.types.UILayout,
        data: "RigInstance",
        item: "RBFDriverData",
        icon: int | None,
        active_data: "RigInstance",
        active_prop_name: str,
    ):
        layout.label(text=item.name, icon="BONE_DATA")


class META_HUMAN_DNA_UL_rbf_driven(bpy.types.UIList):
    def draw_item(
        self,
        context: "Context",
        layout: bpy.types.UILayout,
        data: "RigInstance",
        item: "RBFDrivenData",
        icon: int | None,
        active_data: "RigInstance",
        active_prop_name: str,
    ):
        row = layout.row()
        row.label(text=item.name, icon="BONE_DATA")
        if context.active_pose_bone and context.active_pose_bone.name == item.name:
            row.label(text="", icon="RESTRICT_SELECT_OFF")
        # Push the transform indicators to the right
        # sub = row.row(align=True)  # noqa: ERA001
        # sub.alignment = "RIGHT" # noqa: ERA001
        # if item.location_edited:
        #     sub.label(text="L") # noqa: ERA001
        # if item.rotation_edited:
        #     sub.label(text="R") # noqa: ERA001
        # if item.scale_edited:
        #     sub.label(text="S") # noqa: ERA001


class META_HUMAN_DNA_PT_pose_editor(bpy.types.Panel):
    bl_label = "Pose Editor"
    bl_category = "MetaHuman DNA"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context: "Context") -> bool:
        properties = context.scene.meta_human_dna
        if not len(properties.rig_instance_list) > 0:
            return False

        active_index = properties.rig_instance_list_active_index
        instance = properties.rig_instance_list[active_index]
        return not (
            not instance.body_rig or not instance.body_dna_file_path or not Path(instance.body_dna_file_path).exists()
        )

    def draw(self, context: "Context"):
        if not self.layout:
            return

        properties = context.scene.meta_human_dna

        active_index = properties.rig_instance_list_active_index
        instance = properties.rig_instance_list[active_index]

        active_rbf_solver_index = instance.rbf_solver_list_active_index

        row = self.layout.row()
        row.label(text="Solvers:")
        row = self.layout.row()
        draw_ui_list(
            row,
            context,  # type: ignore[arg-type]
            class_name="META_HUMAN_DNA_UL_rbf_solvers",
            list_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].rbf_solver_list",
            active_index_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].rbf_solver_list_active_index",
            unique_id="active_rbf_solver_list_id",
            insertion_operators=False,
            move_operators=False,  # type: ignore[arg-type]
        )
        active_rbf_solver = (
            instance.rbf_solver_list[active_rbf_solver_index] if len(instance.rbf_solver_list) > 0 else None
        )

        if not active_rbf_solver:
            return

        if not instance.editing_rbf_solver:
            row = self.layout.row()
            row.label(text="Poses:")
            row = self.layout.row()
            draw_ui_list(
                row,
                context,  # type: ignore[arg-type]
                class_name="META_HUMAN_DNA_UL_rbf_poses",
                list_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].rbf_solver_list[{active_rbf_solver_index}].poses",
                active_index_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].rbf_solver_list[{active_rbf_solver_index}].poses_active_index",
                unique_id="active_rbf_poses_list_id",
                insertion_operators=False,
                move_operators=False,  # type: ignore[arg-type]
            )
            row = self.layout.row()
            row.prop(instance, "body_reset_rbf_pose_on_change", text="Reset Pose")

        if instance.editing_rbf_solver:
            solver_row = self.layout.row(align=True)
            solver_row.operator(
                "meta_human_dna.add_rbf_solver", icon="ADD", text=""
            ).solver_index = active_rbf_solver_index
            solver_row.operator(
                "meta_human_dna.remove_rbf_solver", icon="REMOVE", text=""
            ).solver_index = active_rbf_solver_index
            solver_row.operator("meta_human_dna.evaluate_rbf_solvers", icon="FILE_REFRESH", text="")


class META_HUMAN_DNA_PT_pose_editor_footer_sub_panel(RigInstanceDependentPanel):
    bl_parent_id = "META_HUMAN_DNA_PT_pose_editor"
    bl_label = "(Not Shown)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"
    bl_options = {"HIDE_HEADER"}

    def draw(self, context: "Context"):
        if not self.layout:
            return

        properties = context.scene.meta_human_dna

        active_index = properties.rig_instance_list_active_index
        instance = properties.rig_instance_list[active_index]

        solver_row = self.layout.row(align=True)
        solver_row.scale_y = 1.5

        if instance.editing_rbf_solver:
            solver_row.operator("meta_human_dna.revert_rbf_solver", icon="LOOP_BACK", text="Revert")
        else:
            solver_row.operator("meta_human_dna.edit_rbf_solver", icon="OUTLINER_DATA_ARMATURE", text="Edit")

        solver_row.operator("meta_human_dna.commit_rbf_solver_changes", icon="RNA", text="Commit")


class RbfEditorSubPanelBase(bpy.types.Panel):
    @classmethod
    def poll(cls, context: "Context") -> bool:
        error = valid_rig_instance_exists(context, ignore_face_board=True)
        if not error:
            properties = context.scene.meta_human_dna
            if not len(properties.rig_instance_list) > 0:
                return False

            properties = context.scene.meta_human_dna
            active_index = properties.rig_instance_list_active_index
            instance = properties.rig_instance_list[active_index]

            active_rbf_solver_index = instance.rbf_solver_list_active_index
            active_rbf_solver = (
                instance.rbf_solver_list[active_rbf_solver_index] if len(instance.rbf_solver_list) > 0 else None
            )

            if not active_rbf_solver:
                return False

            return instance.editing_rbf_solver
        return False


class META_HUMAN_DNA_PT_pose_editor_solver_settings_sub_panel(RbfEditorSubPanelBase):
    bl_parent_id = "META_HUMAN_DNA_PT_pose_editor"
    bl_label = "Settings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: "Context"):
        if not self.layout:
            return

        properties = context.scene.meta_human_dna
        active_index = properties.rig_instance_list_active_index
        instance = properties.rig_instance_list[active_index]

        active_rbf_solver_index = instance.rbf_solver_list_active_index
        active_rbf_solver = (
            instance.rbf_solver_list[active_rbf_solver_index] if len(instance.rbf_solver_list) > 0 else None
        )

        if not active_rbf_solver:
            return

        split = self.layout.split(factor=0.45)
        split.label(text="Mode:")
        split.prop(active_rbf_solver, "mode", text="")
        split = self.layout.split(factor=0.45)
        split.label(text="Distance Method:")
        split.prop(active_rbf_solver, "distance_method", text="")
        split = self.layout.split(factor=0.45)
        split.label(text="Normalize Method:")
        split.prop(active_rbf_solver, "normalize_method", text="")
        split = self.layout.split(factor=0.45)
        split.label(text="Function Type:")
        split.prop(active_rbf_solver, "function_type", text="")
        split = self.layout.split(factor=0.45)
        split.label(text="Twist Axis:")
        split.prop(active_rbf_solver, "twist_axis", text="")
        row = self.layout.row()
        row.prop(active_rbf_solver, "radius", text="Radius")
        row = self.layout.row()
        row.prop(active_rbf_solver, "weight_threshold", text="Weight Threshold")
        row = self.layout.row()
        row.prop(active_rbf_solver, "automatic_radius", text="Automatic Radius")


class META_HUMAN_DNA_PT_pose_editor_poses_sub_panel(RbfEditorSubPanelBase):
    bl_parent_id = "META_HUMAN_DNA_PT_pose_editor"
    bl_label = "Poses"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"

    def draw(self, context: "Context"):
        if not self.layout:
            return

        properties = context.scene.meta_human_dna
        active_index = properties.rig_instance_list_active_index
        instance = properties.rig_instance_list[active_index]

        active_rbf_solver_index = instance.rbf_solver_list_active_index
        active_rbf_solver = (
            instance.rbf_solver_list[active_rbf_solver_index] if len(instance.rbf_solver_list) > 0 else None
        )

        if not active_rbf_solver:
            return

        row = self.layout.row()
        draw_ui_list(
            row,
            context,  # type: ignore[arg-type]
            class_name="META_HUMAN_DNA_UL_rbf_poses",
            list_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].rbf_solver_list[{active_rbf_solver_index}].poses",
            active_index_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].rbf_solver_list[{active_rbf_solver_index}].poses_active_index",
            unique_id="active_rbf_poses_list_id",
            insertion_operators=False,
            move_operators=False,  # type: ignore[arg-type]
        )
        if instance.editing_rbf_solver:
            poses_row = self.layout.row(align=True)
            op = poses_row.operator("meta_human_dna.add_rbf_pose", icon="ADD", text="")
            op.solver_index = active_rbf_solver_index
            op.pose_index = active_rbf_solver.poses_active_index

            op = poses_row.operator("meta_human_dna.remove_rbf_pose", icon="REMOVE", text="")
            op.solver_index = active_rbf_solver_index
            op.pose_index = active_rbf_solver.poses_active_index
            active_rbf_pose_index = active_rbf_solver.poses_active_index
            active_rbf_pose = (
                active_rbf_solver.poses[active_rbf_pose_index] if len(active_rbf_solver.poses) > 0 else None
            )
            if not active_rbf_pose:
                return

            if active_rbf_pose.driven_active_index >= 0 and len(active_rbf_pose.driven) > 0:
                op = poses_row.operator("meta_human_dna.update_rbf_pose", icon="CHECKMARK", text="")
                op.solver_index = active_rbf_solver_index
                op.pose_index = active_rbf_pose_index
                op.driven_index = active_rbf_pose.driven_active_index

            # Push the select all button to the right
            sub = poses_row.row(align=True)
            sub.alignment = "RIGHT"
            op = sub.operator("meta_human_dna.duplicate_rbf_pose", icon="DUPLICATE", text="")
            op.solver_index = active_rbf_solver_index
            op.pose_index = active_rbf_pose_index

            sub.separator(factor=1.5)

            # TODO: Maybe Re-enable when functionality is needed?
            # split = self.layout.split()  # noqa: ERA001
            # split.prop(active_rbf_pose, 'scale_factor', text='Scale Factor') # noqa: ERA001
            # split.prop(active_rbf_pose, 'target_enable', text='Target Enabled') # noqa: ERA001


class META_HUMAN_DNA_PT_pose_editor_drivers_sub_panel(RbfEditorSubPanelBase):
    bl_parent_id = "META_HUMAN_DNA_PT_pose_editor"
    bl_label = "Drivers"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: "Context"):
        if not self.layout:
            return

        properties = context.scene.meta_human_dna
        active_index = properties.rig_instance_list_active_index
        instance = properties.rig_instance_list[active_index]

        active_rbf_solver_index = instance.rbf_solver_list_active_index
        active_rbf_solver = (
            instance.rbf_solver_list[active_rbf_solver_index] if len(instance.rbf_solver_list) > 0 else None
        )

        if not active_rbf_solver:
            return

        active_rbf_pose_index = active_rbf_solver.poses_active_index

        row = self.layout.row()
        draw_ui_list(
            row,
            context,  # type: ignore[arg-type]
            class_name="META_HUMAN_DNA_UL_rbf_drivers",
            list_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].rbf_solver_list[{active_rbf_solver_index}].poses[{active_rbf_pose_index}].drivers",
            active_index_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].rbf_solver_list[{active_rbf_solver_index}].poses[{active_rbf_pose_index}].drivers_active_index",
            unique_id="active_rbf_driver_list_id",
            insertion_operators=False,
            move_operators=False,  # type: ignore[arg-type]
        )


class META_HUMAN_DNA_PT_pose_editor_driven_sub_panel(RbfEditorSubPanelBase):
    bl_parent_id = "META_HUMAN_DNA_PT_pose_editor"
    bl_label = "Driven"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"

    def draw(self, context: "Context"):
        if not self.layout:
            return

        properties = context.scene.meta_human_dna
        active_index = properties.rig_instance_list_active_index
        instance: "RigInstance" = properties.rig_instance_list[active_index]  # noqa: UP037

        active_rbf_solver_index = instance.rbf_solver_list_active_index
        active_rbf_solver = (
            instance.rbf_solver_list[active_rbf_solver_index] if len(instance.rbf_solver_list) > 0 else None
        )

        if not active_rbf_solver:
            return

        active_rbf_pose_index = active_rbf_solver.poses_active_index
        active_rbf_pose = active_rbf_solver.poses[active_rbf_pose_index] if len(active_rbf_solver.poses) > 0 else None
        if not active_rbf_pose:
            return

        row = self.layout.row()
        draw_ui_list(
            row,
            context,  # type: ignore[arg-type]
            class_name="META_HUMAN_DNA_UL_rbf_driven",
            list_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].rbf_solver_list[{active_rbf_solver_index}].poses[{active_rbf_pose_index}].driven",
            active_index_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].rbf_solver_list[{active_rbf_solver_index}].poses[{active_rbf_pose_index}].driven_active_index",
            unique_id="active_rbf_driven_list_id",
            insertion_operators=False,
            move_operators=False,  # type: ignore[arg-type]
        )
        column = self.layout.column()
        driven_row = column.row(align=True)

        op = driven_row.operator("meta_human_dna.add_rbf_driven", icon="ADD", text="")
        op.solver_index = active_rbf_solver_index
        op.pose_index = active_rbf_pose_index
        op.driven_index = active_rbf_pose.driven_active_index

        op = driven_row.operator("meta_human_dna.remove_rbf_driven", icon="REMOVE", text="")
        op.solver_index = active_rbf_solver_index
        op.pose_index = active_rbf_pose_index
        op.driven_index = active_rbf_pose.driven_active_index
