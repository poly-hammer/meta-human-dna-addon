# standard library imports
from pathlib import Path

# third party imports
import bpy

from bl_ui.generic_ui_list import draw_ui_list

# local imports
from ..constants import SHAPE_KEY_BASIS_NAME
from ..typing import *  # noqa: F403


def get_active_rig_instance() -> "RigInstance | None":
    # Avoid circular import
    from ..ui.callbacks import get_active_rig_instance as _get_active_rig_instance

    return _get_active_rig_instance()


def dependencies_are_valid() -> bool:
    # Avoid circular import
    from ..utilities import dependencies_are_valid as _dependencies_are_valid

    return _dependencies_are_valid()


def valid_rig_instance_exists(_: "Context", ignore_face_board: bool = False) -> str:  # noqa: PLR0911
    instance = get_active_rig_instance()
    if instance:
        if not instance.face_board and not ignore_face_board:
            return f'"{instance.name}" Has No Face Board set.'

        if instance.head_mesh or instance.head_rig:
            if not instance.head_dna_file_path:
                return f'"{instance.name}" Has no head DNA file set.'
            if not Path(bpy.path.abspath(instance.head_dna_file_path)).exists():
                return f'"{instance.name}" head DNA file is not found on disk.'
            if Path(bpy.path.abspath(instance.head_dna_file_path)).suffix.lower() != ".dna":
                return f'"{instance.name}" head DNA file must be a binary .dna file.'
        elif instance.body_mesh or instance.body_rig:
            if not instance.body_dna_file_path:
                return f'"{instance.name}" Has no body DNA file set.'
            if not Path(bpy.path.abspath(instance.body_dna_file_path)).exists():
                return f'"{instance.name}" body DNA file is not found on disk.'
            if Path(bpy.path.abspath(instance.body_dna_file_path)).suffix.lower() != ".dna":
                return f'"{instance.name}" body DNA file must be a binary .dna file.'

        return ""
    return "Missing data. Create/Import DNA data."


def draw_rig_instance_error(layout: bpy.types.UILayout, error: str):
    # Validate installed dependencies.
    if not dependencies_are_valid():
        row = layout.row()
        row.alert = True
        row.label(text="Dependencies are missing.", icon="ERROR")
        row = layout.row()
        row.operator("meta_human_dna.open_build_tool_documentation", icon="URL", text="Show Me How to Fix This?")
        return

    row = layout.row()
    row.label(text="Rig Instance Error:", icon="ERROR")
    row = layout.row()
    row.alignment = "CENTER"
    row.alert = True
    row.label(text=error)


class RigInstanceDependentPanel(bpy.types.Panel):
    @classmethod
    def poll(cls, context: "Context") -> bool:
        error = valid_rig_instance_exists(context, ignore_face_board=True)
        return bool(not error)


class ArmatureDependentPanel(bpy.types.Panel):
    @classmethod
    def poll(cls, context: "Context") -> bool:
        error = valid_rig_instance_exists(context, ignore_face_board=True)
        if error:
            return False

        instance = get_active_rig_instance()
        if not instance:
            return False

        current_component = context.window_manager.meta_human_dna.current_component_type
        return bool(
            (current_component == "head" and instance.head_rig) or (current_component == "body" and instance.body_rig)
        )


class MeshDependentPanel(bpy.types.Panel):
    @classmethod
    def poll(cls, context: "Context") -> bool:
        error = valid_rig_instance_exists(context, ignore_face_board=True)
        if error:
            return False

        instance = get_active_rig_instance()
        if not instance:
            return False

        current_component = context.window_manager.meta_human_dna.current_component_type
        return bool(
            (current_component == "head" and instance.head_mesh) or (current_component == "body" and instance.body_mesh)
        )


class META_HUMAN_DNA_UL_output_items(bpy.types.UIList):
    def draw_item(
        self,
        context: "Context",
        layout: bpy.types.UILayout,
        data: "RigInstance",
        item: "OutputData",
        icon: int | None,
        active_data: "RigInstance",
        active_prop_name: str,
    ):
        layout.separator(factor=0.1)
        layout.prop(item, "include", text="")

        item_icon = "MESH_DATA"
        prop_name = "scene_object"
        if item.scene_object and item.scene_object.type == "ARMATURE":
            item_icon = "ARMATURE_DATA"
        elif item.image_object:
            item_icon = "IMAGE_DATA"
            prop_name = "image_object"

        if item.editable_name:
            layout.prop(item, "name", text="", emboss=False, icon=item_icon)
        else:
            layout.label(text=item.name, icon=item_icon)

        row = layout.row()
        row.enabled = False
        row.prop(item, prop_name, text="", emboss=False)


class META_HUMAN_DNA_UL_rig_instances(bpy.types.UIList):
    def draw_item(
        self,
        context: "Context",
        layout: bpy.types.UILayout,
        data: "MetahumanSceneProperties",
        item: "RigInstance",
        icon: int | None,
        active_data: "MetahumanSceneProperties",
        active_prop_name: str,
    ):
        layout.prop(item, "auto_evaluate", text="")

        row = layout.row()
        row.enabled = True

        row.prop(item, "name", text="", emboss=False, icon="NETWORK_DRIVE")
        row.alignment = "RIGHT"

        col = row.column(align=True)
        col.enabled = item.auto_evaluate and (item.auto_evaluate_head or item.auto_evaluate_body)
        col.alert = not item.evaluate_bones
        col.prop(item, "evaluate_bones", text="", icon="BONE_DATA", emboss=False)

        col = row.column(align=True)
        col.enabled = item.auto_evaluate and (item.auto_evaluate_head or item.auto_evaluate_body)
        col.alert = not item.evaluate_shape_keys
        col.prop(item, "evaluate_shape_keys", text="", icon="SHAPEKEY_DATA", emboss=False)

        col = row.column(align=True)
        col.enabled = item.auto_evaluate and (item.auto_evaluate_head or item.auto_evaluate_body)
        col.alert = not item.evaluate_texture_masks
        col.prop(item, "evaluate_texture_masks", text="", icon="NODE_TEXTURE", emboss=False)

        col = row.column(align=True)
        col.enabled = item.auto_evaluate and (item.auto_evaluate_head or item.auto_evaluate_body)
        col.alert = not item.evaluate_rbfs
        col.prop(item, "evaluate_rbfs", text="", icon="DRIVER_ROTATIONAL_DIFFERENCE", emboss=False)


class META_HUMAN_DNA_UL_shape_keys(bpy.types.UIList):
    filter_by_name: bpy.props.StringProperty(
        default="", name="Filter by Name", description="Filter shape keys by name", options={"TEXTEDIT_UPDATE"}
    )  # pyright: ignore[reportInvalidTypeForm]

    show_zero_values: bpy.props.BoolProperty(
        default=False,
        name="Show Zeros",
        description="Hide shape keys with a value of 0.0",
    )  # pyright: ignore[reportInvalidTypeForm]

    order_by_value: bpy.props.BoolProperty(
        default=True,
        name="Order by Value",
        description="Order shape keys by value in descending order",
    )  # pyright: ignore[reportInvalidTypeForm]

    def draw_item(
        self,
        context: "Context",
        layout: bpy.types.UILayout,
        data: "RigInstance",
        item: "ShapeKeyData",
        icon: int | None,
        active_data: "RigInstance",
        active_prop_name: str,
    ):
        row = layout.row(align=True)
        label = item.name.split("__", 1)[-1]
        row.label(text=label, icon="SHAPEKEY_DATA")
        sub = row.row(align=True)
        sub.alignment = "RIGHT"
        sub.prop(item, "value", text="", emboss=False)
        sub.operator("meta_human_dna.sculpt_this_shape_key", text="", icon="SCULPTMODE_HLT").shape_key_name = item.name
        sub.operator("meta_human_dna.edit_this_shape_key", text="", icon="EDITMODE_HLT").shape_key_name = item.name
        sub.operator("meta_human_dna.reimport_this_shape_key", text="", icon="IMPORT").shape_key_name = item.name

    def draw_filter(self, context: "Context", layout: bpy.types.UILayout):
        """UI code for the filtering/sorting/search area."""
        row = layout.row(align=True)
        row.prop(self, "filter_by_name", text="")
        row.separator()
        row.separator()
        row.separator()
        row.separator()
        row.prop(self, "show_zero_values", text="", icon="HIDE_OFF" if self.show_zero_values else "HIDE_ON")
        row.prop(self, "order_by_value", text="", icon="LINENUMBERS_ON")

    def filter_items(self, context: "Context", data: "RigInstance", prop_name: str) -> tuple[list[int], list[int]]:
        items = getattr(data, prop_name)
        filtered = [self.bitflag_filter_item] * len(items)
        ordered: list[int] = []
        _sort = []
        mesh_name_prefix = data.active_shape_key_mesh_name.replace(f"{data.name}_", "")

        # hide items that don't belong to the active mesh filter
        for index, item in enumerate(items):
            if not item.name.startswith(mesh_name_prefix):
                filtered[index] &= ~self.bitflag_filter_item

        # hide items that have a zero value
        if not self.show_zero_values:
            for index, item in enumerate(items):
                if round(item.value, 3) == 0.0:
                    filtered[index] &= ~self.bitflag_filter_item

        # sort items by descending shape key value
        if self.order_by_value:
            _sort = [(i, it.value) for i, it in enumerate(items)]
            bpy.types.UI_UL_list.sort_items_helper(_sort, lambda e: e[1], reverse=True)

        # filter items by name if a name is provided
        if self.filter_by_name:
            for index, item in enumerate(items):
                if self.filter_by_name.lower() not in item.name.lower():
                    filtered[index] &= ~self.bitflag_filter_item

        return filtered, ordered


class META_HUMAN_DNA_PT_face_board(RigInstanceDependentPanel):
    bl_label = "Face Board"
    bl_category = "MetaHuman DNA"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: "Context"):
        if not self.layout:
            return

        error = valid_rig_instance_exists(context)
        if not error:
            window_manager_properties = context.window_manager.meta_human_dna
            row = self.layout.row()
            row.label(text="Poses:")
            row = self.layout.row()
            row.template_icon_view(window_manager_properties, "face_pose_previews", show_labels=True, scale_popup=5.0)
            row = self.layout.row()
            row.prop(window_manager_properties, "face_pose_previews", text="")
            row = self.layout.row()
            row.label(text="Animation:")
            split = self.layout.split(factor=0.5)
            split.scale_y = 1.5
            split.operator("meta_human_dna.import_face_board_animation", icon="IMPORT", text="Import")
            split.operator("meta_human_dna.bake_face_board_animation", icon="ACTION", text="Bake")
        else:
            draw_rig_instance_error(self.layout, error)


class META_HUMAN_DNA_PT_utilities(bpy.types.Panel):
    bl_label = "Utilities"
    bl_category = "MetaHuman DNA"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: "Context"):
        if not self.layout:
            return

        row = self.layout.row()
        row.label(text="Current Component:")
        row = self.layout.row()
        row.scale_y = 1.25
        row.prop(context.window_manager.meta_human_dna, "current_component_type", text="")


class META_HUMAN_DNA_PT_mesh_utilities_sub_panel(MeshDependentPanel):
    bl_parent_id = "META_HUMAN_DNA_PT_utilities"
    bl_label = "Mesh"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: "Context"):
        properties = context.scene.meta_human_dna
        error = valid_rig_instance_exists(context, ignore_face_board=True)
        if not self.layout:
            return

        if not error:
            active_index = properties.rig_instance_list_active_index
            instance = properties.rig_instance_list[active_index]
            current_component_type = context.window_manager.meta_human_dna.current_component_type

            # whether to enable the topology vertex group dropdowns
            enabled = bool(
                (current_component_type == "head" and instance.head_mesh)
                or (current_component_type == "body" and instance.body_mesh)
            )

            box = self.layout.box()
            row = box.row()
            row.label(text="Topology Vertex Groups:")
            row = box.row()
            grid = row.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
            col = grid.column()
            col.enabled = enabled
            col.label(text="Selection Mode:")
            row = col.row()
            row.prop(instance, "mesh_topology_selection_mode", text="")

            col = grid.column()
            col.enabled = enabled
            col.label(text="Set Selection:")
            row = col.row()
            if current_component_type == "head":
                row.prop(instance, "head_mesh_topology_groups", text="")
            elif current_component_type == "body":
                row.prop(instance, "body_mesh_topology_groups", text="")
                row = box.row()
                row.prop(instance, "body_show_only_high_level_topology_groups", text="Filter High Level Groups")

            row = box.row()
            row.label(text="Shrink Wrap Target:")
            row = box.row()
            if current_component_type == "head":
                row.prop(instance, "head_shrink_wrap_target", text="")
            elif current_component_type == "body":
                row.prop(instance, "body_shrink_wrap_target", text="")
            row = box.row()
            row.enabled = bool(instance.head_shrink_wrap_target)
            row.operator("meta_human_dna.shrink_wrap_vertex_group")
        else:
            draw_rig_instance_error(self.layout, error)


class META_HUMAN_DNA_PT_armature_utilities_sub_panel(ArmatureDependentPanel):
    bl_parent_id = "META_HUMAN_DNA_PT_utilities"
    bl_label = "Armature"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: "Context"):
        properties = context.scene.meta_human_dna
        error = valid_rig_instance_exists(context, ignore_face_board=True)

        if not self.layout:
            return

        if not error:
            active_index = properties.rig_instance_list_active_index
            instance = properties.rig_instance_list[active_index]
            current_component_type = context.window_manager.meta_human_dna.current_component_type
            box = self.layout.box()
            row = box.row()
            row.label(text="Bone Selection Groups:")
            row = box.row()
            row.prop(instance, "list_surface_bone_groups")
            row = box.row()
            grid = row.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
            col = grid.column()
            col.enabled = bool(instance.head_mesh)
            col.label(text="Selection Mode:")
            row = col.row()
            row.prop(instance, "rig_bone_group_selection_mode", text="")

            col = grid.column()
            col.enabled = bool(instance.head_mesh)
            col.label(text="Set Selection:")
            row = col.row()
            if current_component_type == "head":
                row.prop(instance, "head_rig_bone_groups", text="")
            elif current_component_type == "body":
                row.prop(instance, "body_rig_bone_groups", text="")
            row = self.layout.row()
            # row.label(text='Push Bones:')  # noqa: ERA001
            # row = self.layout.row() # noqa: ERA001
            # row.prop(properties, 'push_along_normal_distance', text='Normal Distance') # noqa: ERA001
            # split = row.split(factor=0.5, align=True) # noqa: ERA001
            # split.operator('meta_human_dna.push_bones_backward_along_normals', text='', icon='REMOVE') # noqa: ERA001
            # split.operator('meta_human_dna.push_bones_forward_along_normals', text='', icon='ADD') # noqa: ERA001
            row = self.layout.row()
            row.label(text="Head to Body Constraint:")
            row = self.layout.row()
            row.prop(instance, "head_to_body_constraint_influence", text="")
            row = self.layout.row()
            row.label(text="Transform and Apply Selected Bones:")
            # row = self.layout.row() # noqa: ERA001
            # row.operator('meta_human_dna.sync_with_body_in_blueprint', text='Sync with Body in Blueprint')  # noqa: E501, ERA001
            row = self.layout.row()
            row.operator("meta_human_dna.mirror_selected_bones", text="Mirror Selected Bones")
            row = self.layout.row()
            # split = row.split(factor=0.5) # noqa: ERA001
            # split.scale_y = 1.5 # noqa: ERA001
            # split.operator('meta_human_dna.auto_fit_selected_bones', text='Auto Fit') # noqa: ERA001
            # split.operator('meta_human_dna.revert_bone_transforms_to_dna', text='Revert') # noqa: ERA001
            row.operator("meta_human_dna.revert_bone_transforms_to_dna", text="Revert")
        else:
            draw_rig_instance_error(self.layout, error)


class META_HUMAN_DNA_PT_animation_utilities_sub_panel(ArmatureDependentPanel):
    bl_parent_id = "META_HUMAN_DNA_PT_utilities"
    bl_label = "Animation"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: "Context"):
        error = valid_rig_instance_exists(context, ignore_face_board=True)

        if not self.layout:
            return

        if not error:
            current_component_type = context.window_manager.meta_human_dna.current_component_type
            row = self.layout.row()
            row.scale_y = 1.5
            split = row.split(factor=0.5)
            split.operator(
                "meta_human_dna.import_component_animation",
                icon="IMPORT",
                text=f"Import on {current_component_type.capitalize()}",
            ).component_type = current_component_type
            split.operator(
                "meta_human_dna.bake_component_animation",
                icon="ACTION",
                text=f"Bake on {current_component_type.capitalize()}",
            ).component_type = current_component_type


class META_HUMAN_DNA_PT_materials_utilities_sub_panel(RigInstanceDependentPanel):
    bl_parent_id = "META_HUMAN_DNA_PT_utilities"
    bl_label = "Material"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: "Context"):
        if not self.layout:
            return

        error = valid_rig_instance_exists(context)
        if not error:
            row = self.layout.row()
            row.operator("meta_human_dna.generate_material", icon="MATERIAL")
        else:
            draw_rig_instance_error(self.layout, error)


class META_HUMAN_DNA_PT_utilities_sub_panel(bpy.types.Panel):
    bl_parent_id = "META_HUMAN_DNA_PT_utilities"
    bl_label = "(Not Shown)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"
    bl_options = {"HIDE_HEADER"}

    def draw(self, context: "Context"):
        if not self.layout:
            return
        row = self.layout.row()
        row.scale_y = 1.5
        row.operator("meta_human_dna.convert_selected_to_dna", icon="RNA")


class META_HUMAN_DNA_PT_view_options(RigInstanceDependentPanel):
    bl_label = "View Options"
    bl_category = "MetaHuman DNA"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: "Context"):
        if not self.layout:
            return

        properties = context.scene.meta_human_dna
        error = valid_rig_instance_exists(context, ignore_face_board=True)
        if not error:
            active_index = properties.rig_instance_list_active_index
            instance = properties.rig_instance_list[active_index]
            grid = self.layout.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
            col = grid.column()
            col.enabled = bool(instance.head_material)
            col.label(text="Head Material Color:")
            row = col.row()
            row.prop(instance, "active_material_preview", text="")
            row = col.row()
            row.label(text="Bone Visibility:")
            row = col.row()
            row.enabled = bool(instance.head_rig)
            row.prop(
                instance,
                "show_head_bones",
                text="Head Bones",
                icon="HIDE_OFF" if instance.show_head_bones else "HIDE_ON",
            )
            row = col.row()
            row.enabled = bool(instance.body_rig)
            row.prop(
                instance,
                "show_body_bones",
                text="Body Bones",
                icon="HIDE_OFF" if instance.show_body_bones else "HIDE_ON",
            )

            col = grid.column()
            col.enabled = bool(instance.head_mesh)
            col.label(text="Active LOD:")
            row = col.row()
            row.prop(instance, "active_lod", text="")
            row = col.row()
            row.label(text="Control Visibility:")
            row = col.row()
            row.enabled = bool(instance.face_board)
            row.prop(
                instance,
                "show_face_board",
                text="Face Board",
                icon="HIDE_OFF" if instance.show_face_board else "HIDE_ON",
            )
            row = col.row()
            row.enabled = bool(instance.control_rig)
            row.prop(
                instance,
                "show_control_rig",
                text="Control Rig",
                icon="HIDE_OFF" if instance.show_control_rig else "HIDE_ON",
            )

            row = self.layout.row()
            row.prop(properties, "highlight_matching_active_bone")
        else:
            draw_rig_instance_error(self.layout, error)


class META_HUMAN_DNA_PT_rig_instance(bpy.types.Panel):
    bl_label = "Rig Instances"
    bl_category = "MetaHuman DNA"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: "Context"):
        if not self.layout:
            return

        properties = context.scene.meta_human_dna
        row = self.layout.row()
        row = self.layout.row()
        col = draw_ui_list(
            row,
            context,  # type: ignore[arg-type]
            class_name="META_HUMAN_DNA_UL_rig_instances",
            list_path="scene.meta_human_dna.rig_instance_list",
            active_index_path="scene.meta_human_dna.rig_instance_list_active_index",
            unique_id="rig_instance_list_id",
            insertion_operators=False,
            move_operators=False,  # type: ignore[arg-type]
        )

        enabled = len(properties.rig_instance_list) > 0

        # plus and minus buttons
        row = col.row()
        props = row.operator("meta_human_dna.rig_instance_entry_add", text="", icon="ADD")
        props.active_index = properties.rig_instance_list_active_index

        row = col.row()
        row.enabled = enabled
        props = row.operator("meta_human_dna.rig_instance_entry_remove", text="", icon="REMOVE")
        props.active_index = properties.rig_instance_list_active_index

        if enabled:
            row = col.row()
            row.operator("meta_human_dna.duplicate_rig_instance", icon="DUPLICATE", text="")

            row = col.row()
            props = row.operator("meta_human_dna.rig_instance_entry_move", text="", icon="TRIA_UP")
            props.direction = "UP"
            props.active_index = properties.rig_instance_list_active_index

            row = col.row()
            props = row.operator("meta_human_dna.rig_instance_entry_move", text="", icon="TRIA_DOWN")
            props.direction = "DOWN"
            props.active_index = properties.rig_instance_list_active_index

            row = self.layout.row()
            row.label(text="Rig Logic Linked Data:")


class META_HUMAN_DNA_PT_rig_instance_head_sub_panel(bpy.types.Panel):
    bl_parent_id = "META_HUMAN_DNA_PT_rig_instance"
    bl_label = ""
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context: "Context") -> bool:
        return len(context.scene.meta_human_dna.rig_instance_list) > 0

    def draw_header(self, context: "Context"):
        if not self.layout:
            return

        properties = context.scene.meta_human_dna
        active_index = properties.rig_instance_list_active_index
        if len(properties.rig_instance_list) > 0:
            instance = properties.rig_instance_list[active_index]
            row = self.layout.row()
            row.enabled = instance.auto_evaluate
            row.prop(instance, "auto_evaluate_head", text="Head")

    def draw(self, context: "Context"):
        if not self.layout:
            return

        properties = context.scene.meta_human_dna
        active_index = properties.rig_instance_list_active_index
        if len(properties.rig_instance_list) > 0:
            instance = properties.rig_instance_list[active_index]

            box = self.layout.box()
            row = box.row()
            row.alert = False
            bad_path = instance.head_dna_file_path and not Path(bpy.path.abspath(instance.head_dna_file_path)).exists()
            if not instance.head_dna_file_path or bad_path:
                row.alert = True
            row.prop(instance, "head_dna_file_path", icon="RNA")
            if bad_path:
                row = box.row()
                row.alert = True
                row.label(text="DNA File not found on disk.", icon="ERROR")
            row = box.row()
            row.alert = False
            if not instance.face_board:
                row.alert = True
            row.prop(instance, "face_board", icon="PIVOT_BOUNDBOX")
            row = box.row()
            row.prop(instance, "head_mesh", icon="OUTLINER_OB_MESH")
            row = box.row()
            row.prop(instance, "head_rig", icon="OUTLINER_OB_ARMATURE")
            row = box.row()
            row.prop(instance, "head_material", icon="MATERIAL")


class META_HUMAN_DNA_PT_rig_instance_body_sub_panel(bpy.types.Panel):
    bl_parent_id = "META_HUMAN_DNA_PT_rig_instance"
    bl_label = ""
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context: "Context") -> bool:
        return len(context.scene.meta_human_dna.rig_instance_list) > 0

    def draw_header(self, context: "Context"):
        if not self.layout:
            return

        properties = context.scene.meta_human_dna
        active_index = properties.rig_instance_list_active_index
        if len(properties.rig_instance_list) > 0:
            instance = properties.rig_instance_list[active_index]
            row = self.layout.row()
            row.enabled = instance.auto_evaluate
            row.prop(instance, "auto_evaluate_body", text="Body")

    def draw(self, context: "Context"):
        if not self.layout:
            return

        properties = context.scene.meta_human_dna
        active_index = properties.rig_instance_list_active_index
        if len(properties.rig_instance_list) > 0:
            instance = properties.rig_instance_list[active_index]

            box = self.layout.box()
            row = box.row()
            row.alert = False
            bad_path = instance.body_dna_file_path and not Path(bpy.path.abspath(instance.body_dna_file_path)).exists()
            if not instance.body_dna_file_path or bad_path:
                row.alert = True
            row.prop(instance, "body_dna_file_path", icon="RNA")
            if bad_path:
                row = box.row()
                row.alert = True
                row.label(text="DNA File not found on disk.", icon="ERROR")
            row = box.row()
            row.prop(instance, "control_rig", icon="CON_ARMATURE")
            row = box.row()
            row.prop(instance, "body_mesh", icon="OUTLINER_OB_MESH")
            row = box.row()
            row.prop(instance, "body_rig", icon="OUTLINER_OB_ARMATURE")
            row = box.row()
            row.prop(instance, "body_material", icon="MATERIAL")


class META_HUMAN_DNA_PT_rig_instance_footer_sub_panel(RigInstanceDependentPanel):
    bl_parent_id = "META_HUMAN_DNA_PT_rig_instance"
    bl_label = "(Not Shown)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"
    bl_options = {"HIDE_HEADER"}

    def draw(self, context: "Context"):
        if not self.layout:
            return

        row = self.layout.row()
        row.scale_y = 1.5
        row.operator("meta_human_dna.force_evaluate", icon="FILE_REFRESH")


class META_HUMAN_DNA_PT_shape_keys(RigInstanceDependentPanel):
    bl_label = "Shape Keys"
    bl_category = "MetaHuman DNA"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: "Context"):
        if not self.layout:
            return

        instance = None
        properties = context.scene.meta_human_dna
        active_index = properties.rig_instance_list_active_index
        if len(properties.rig_instance_list) > 0:
            instance = properties.rig_instance_list[active_index]
            if (
                not instance.shape_key_list
                and instance.head_mesh
                and context.window_manager.meta_human_dna.progress == 1
            ):
                row = self.layout.row()
                row.label(text=f"No shape keys on {instance.name}", icon="ERROR")
                row = self.layout.row()
                row.prop(instance, "generate_neutral_shapes")
                row = self.layout.row()
                row.operator("meta_human_dna.import_shape_keys", icon="IMPORT")
                return

        if context.window_manager.meta_human_dna.progress < 1:
            row = self.layout.row()
            row.label(
                text=f'Importing onto "{context.window_manager.meta_human_dna.progress_mesh_name}"...', icon="SORTTIME"
            )
            row = self.layout.row()
            row.progress(
                factor=context.window_manager.meta_human_dna.progress,
                type="BAR",
                text=context.window_manager.meta_human_dna.progress_description,
            )
            row.scale_x = 2
            return

        error = valid_rig_instance_exists(context)
        if not error:
            row = self.layout.row()
            if instance:
                row.label(text="Filter by Mesh")
                split = self.layout.split(factor=0.97)
                split.prop(instance, "active_shape_key_mesh_name", text="")
                row = self.layout.row()
            active_index = properties.rig_instance_list_active_index
            draw_ui_list(
                row,
                context,  # type: ignore[arg-type]
                class_name="META_HUMAN_DNA_UL_shape_keys",
                list_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].shape_key_list",
                active_index_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].shape_key_list_active_index",
                unique_id="active_shape_key_list_id",
                insertion_operators=False,
                move_operators=False,  # type: ignore[arg-type]
            )
            split = self.layout.split(factor=0.75, align=True)
            split.label(text="Basis Shape Key:")
            split.operator(
                "meta_human_dna.sculpt_this_shape_key", text="", icon="SCULPTMODE_HLT", emboss=True
            ).shape_key_name = SHAPE_KEY_BASIS_NAME
            split.operator(
                "meta_human_dna.edit_this_shape_key", text="", icon="EDITMODE_HLT", emboss=True
            ).shape_key_name = SHAPE_KEY_BASIS_NAME

            row = self.layout.row()
            row.prop(instance, "solo_shape_key", text="Solo selected shape key")
            row = self.layout.row()
            row.prop(instance, "generate_neutral_shapes")
            row = self.layout.row()
            row.operator("meta_human_dna.import_shape_keys", icon="IMPORT", text="Reimport All Shape Keys")
        else:
            draw_rig_instance_error(self.layout, error)


class META_HUMAN_DNA_PT_output_panel(RigInstanceDependentPanel):
    """
    This class defines the user interface for the panel in the tab in the 3d view
    """

    bl_label = "Output"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"

    def draw(self, context: "Context"):
        if not self.layout:
            return

        properties = context.scene.meta_human_dna
        error = valid_rig_instance_exists(context, ignore_face_board=True)
        if not error:
            active_index = properties.rig_instance_list_active_index
            instance = properties.rig_instance_list[active_index]
            grid = self.layout.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
            col = grid.column()
            col.label(text="Component:")
            row = col.row()
            row.prop(instance, "output_component", text="")
            col = grid.column()
            col.label(text="Method:")
            row = col.row()
            row.prop(instance, "output_method", text="")

            row = self.layout.row()
            if instance.output_component == "head":
                draw_ui_list(
                    row,
                    context,  # type: ignore[arg-type]
                    class_name="META_HUMAN_DNA_UL_output_items",
                    list_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].output_head_item_list",
                    active_index_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].output_head_item_active_index",
                    unique_id="output_head_item_list_id",
                    move_operators=False,  # type: ignore[arg-type]
                    insertion_operators=False,
                )
            elif instance.output_component == "body":
                draw_ui_list(
                    row,
                    context,  # type: ignore[arg-type]
                    class_name="META_HUMAN_DNA_UL_output_items",
                    list_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].output_body_item_list",
                    active_index_path=f"scene.meta_human_dna.rig_instance_list[{active_index}].output_body_item_active_index",
                    unique_id="output_body_item_list_id",
                    move_operators=False,  # type: ignore[arg-type]
                    insertion_operators=False,
                )
            row = self.layout.row()
            row.label(text="Output Folder:")
            row = self.layout.row()
            if not instance.output_folder_path:
                row.alert = True
            row.prop(instance, "output_folder_path", text="", icon="RNA")
            if not instance.output_folder_path:
                row = self.layout.row()
                row.alert = True
                row.label(text="Must set an output folder.", icon="ERROR")
        else:
            draw_rig_instance_error(self.layout, error)


class META_HUMAN_DNA_PT_output_buttons_sub_panel(bpy.types.Panel):
    bl_parent_id = "META_HUMAN_DNA_PT_output_panel"
    bl_label = "(Not Shown)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"
    bl_options = {"HIDE_HEADER"}

    def draw(self, context: "Context"):
        if not self.layout:
            return

        properties = context.scene.meta_human_dna
        error = valid_rig_instance_exists(context, ignore_face_board=True)
        row = self.layout.row()
        if not error:
            row.label(text="Export:")
            row = self.layout.row()
            active_index = properties.rig_instance_list_active_index
            instance = properties.rig_instance_list[active_index]
            row.prop(instance, "output_run_validations")
            row = self.layout.row()

            if instance.output_method == "calibrate":
                row.prop(instance, "output_align_head_and_body")
                row = self.layout.row()

            if not instance.output_folder_path:
                row.enabled = False
            row.scale_y = 2.0
            row.operator("meta_human_dna.export_selected_component", icon="EXPORT", text="Only Component")
            row.operator("meta_human_dna.send_to_meta_human_creator", icon="UV_SYNC_SELECT", text="MetaHuman Creator")
