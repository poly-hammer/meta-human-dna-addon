import bpy
from pathlib import Path
from bl_ui.generic_ui_list import draw_ui_list

def valid_rig_logic_instance_exists(context, ignore_face_board: bool = False) -> str:
    properties = context.scene.meta_human_dna # type: ignore
    if len(properties.rig_logic_instance_list) > 0:
        active_index = properties.rig_logic_instance_list_active_index
        instance = properties.rig_logic_instance_list[active_index]
        if not instance.face_board and not ignore_face_board:
            return f'"{instance.name}" Has No Face Board set.'
        elif not instance.dna_file_path:
            return f'"{instance.name}" Has No DNA File set.'
        elif not Path(bpy.path.abspath(instance.dna_file_path)).exists():
            return f'"{instance.name}" DNA File is not found on disk.'
        elif not Path(bpy.path.abspath(instance.dna_file_path)).stem != '.dna':
            return f'"{instance.name}" DNA File must be a binary .dna file.'
        elif instance.dna_file_path and instance.face_board:
            return ''
    else:
        return 'Missing data. Create/Import DNA data.'
    return ''

def draw_rig_logic_instance_error(layout, error: str):
    # Validate installed dependencies.
    from ..utilities import dependencies_are_valid
    if not dependencies_are_valid():
        row = layout.row()
        row.alert = True
        row.label(text='Dependencies are missing.', icon='ERROR')
        row = layout.row()
        row.operator('meta_human_dna.open_build_tool_documentation', icon='URL', text='Show Me How to Fix This?')
        return

    row = layout.row()
    # row.alignment = 'CENTER'
    row.label(text="Rig Logic Instance Error:", icon='ERROR')
    row = layout.row()
    row.alignment = 'CENTER'
    row.alert = True
    row.label(text=error)
    

class META_HUMAN_DNA_UL_output_items(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop_name):
        layout.separator(factor=0.1)
        layout.prop(item, "include", text="")

        icon = 'MESH_DATA'
        prop_name = 'scene_object'
        if item.scene_object and item.scene_object.type == 'ARMATURE':
            icon = 'ARMATURE_DATA'
        elif item.image_object:
            icon = 'IMAGE_DATA'
            prop_name = 'image_object'
            
        if item.editable_name:
            layout.prop(item, "name", text="", emboss=False, icon=icon)
        else:
            layout.label(text=item.name, icon=icon)
        
        row = layout.row()
        row.enabled = False
        row.prop(item, prop_name, text="", emboss=False)

class META_HUMAN_DNA_UL_material_slot_to_instance_mapping(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop_name):        
        split = layout.split(factor=0.25)
        split.alert = not item.valid_path
        split.label(text=item.name.replace(f'{data.name}_', ''), icon='MATERIAL')
        split.prop(item, 'asset_path', text="", emboss=False)

class META_HUMAN_DNA_UL_rig_logic_instances(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_prop_name):
        layout.split(factor=0.2)
        layout.prop(item, "auto_evaluate", text="")
        row = layout.row()
        row.enabled = True
    
        row.enabled = item.auto_evaluate
        row.prop(item, "name", text="", emboss=False, icon='NETWORK_DRIVE')
        row.alignment = 'RIGHT'
        row.prop(item, "evaluate_bones", text="", icon='BONE_DATA', emboss=False)
        row.prop(item, "evaluate_shape_keys", text="", icon='SHAPEKEY_DATA', emboss=False)
        row.prop(item, "evaluate_texture_masks", text="", icon='NODE_TEXTURE', emboss=False)

class META_HUMAN_DNA_UL_shape_keys(bpy.types.UIList):
    
    filter_by_name: bpy.props.StringProperty(
        default='',
        name='Filter by Name',
        description='Filter shape keys by name',
        options={'TEXTEDIT_UPDATE'}
    ) # type: ignore

    show_zero_values: bpy.props.BoolProperty(
        default=False,
        name='Show Zeros',
        description='Hide shape keys with a value of 0.0',
    ) # type: ignore

    order_by_value: bpy.props.BoolProperty(
        default=True,
        name='Order by Value',
        description='Order shape keys by value in descending order',
    ) # type: ignore
    

    def draw_item(self, context, layout, data, item, icon, active_data, active_prop_name):       
        row = layout.row(align=True)
        label = item.name.split("__", 1)[-1]
        row.label(text=label, icon='SHAPEKEY_DATA')
        sub = row.row(align=True)
        sub.alignment = 'RIGHT'
        sub.prop(item, "value", text="", emboss=False)
        sub.operator('meta_human_dna.sculpt_this_shape_key', text='', icon='SCULPTMODE_HLT').shape_key_name = item.name
        sub.operator('meta_human_dna.edit_this_shape_key', text='', icon='EDITMODE_HLT').shape_key_name = item.name
        sub.operator("meta_human_dna.reimport_this_shape_key", text='', icon='IMPORT').shape_key_name = item.name
    
    def draw_filter(self, context, layout): 
        """UI code for the filtering/sorting/search area.""" 
        # col = layout.column(align=True)
        row = layout.row(align=True)
        row.prop(self, 'filter_by_name', text='')
        row.separator()
        row.separator()
        row.separator()
        row.separator()
        row.prop(self, 'show_zero_values', text='', icon='HIDE_OFF' if self.show_zero_values else 'HIDE_ON') 
        row.prop(self, 'order_by_value', text='', icon='LINENUMBERS_ON')

    def filter_items(self, context, data, prop_name):
        items = getattr(data, prop_name)
        filtered = [self.bitflag_filter_item] * len(items)
        ordered = []
        _sort = []
        mesh_name_prefix = data.active_shape_key_mesh_name.replace(f"{data.name}_", '')

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
            _sort = [(idx, it.value) for idx, it in enumerate(items)]
            ordered = bpy.types.UI_UL_list.sort_items_helper(_sort, lambda e: e[1], reverse=True)

        # filter items by name if a name is provided
        if self.filter_by_name:
            for index, item in enumerate(items):
                if self.filter_by_name.lower() not in item.name.lower():
                    filtered[index] &= ~self.bitflag_filter_item

        return filtered, ordered

class META_HUMAN_DNA_PT_face_board(bpy.types.Panel):
    bl_label = "Face Board"
    bl_category = 'Meta-Human DNA'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        error = valid_rig_logic_instance_exists(context)
        if not error:
            window_manager_properties = context.window_manager.meta_human_dna # type: ignore
            row = self.layout.row()
            row.label(text='Poses:')
            row = self.layout.row()
            row.template_icon_view(
                window_manager_properties, 
                "face_pose_previews", 
                show_labels=True,
                scale_popup=5.0
            )
            row = self.layout.row()
            row.prop(window_manager_properties, "face_pose_previews", text='')
            row = self.layout.row()
            row.label(text='Animation:')
            split = self.layout.split(factor=0.5)
            split.operator('meta_human_dna.import_animation', icon='IMPORT', text='Import')
            split.operator('meta_human_dna.bake_animation', icon='ACTION', text='Bake')
        else:
            draw_rig_logic_instance_error(self.layout, error)



class META_HUMAN_DNA_PT_utilities(bpy.types.Panel):
    bl_label = "Utilities"
    bl_category = 'Meta-Human DNA'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        pass


class META_HUMAN_DNA_PT_mesh_utilities_sub_panel(bpy.types.Panel):
    bl_parent_id = "META_HUMAN_DNA_PT_utilities"
    bl_label = "Mesh"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Meta-Human DNA'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        properties = context.scene.meta_human_dna # type: ignore
        error = valid_rig_logic_instance_exists(context)
        if not error:
            active_index = properties.rig_logic_instance_list_active_index
            instance = properties.rig_logic_instance_list[active_index]
            box = self.layout.box()
            row = box.row()
            row.label(text='Topology Vertex Groups:')
            row = box.row()
            grid = row.grid_flow(
                row_major=True, 
                columns=2, 
                even_columns=True, 
                even_rows=True, 
                align=True
            )
            col = grid.column()
            col.enabled = bool(instance.head_mesh)
            col.label(text='Selection Mode:')
            row = col.row()
            row.prop(instance, 'head_mesh_topology_selection_mode', text='')

            col = grid.column()
            col.enabled = bool(instance.head_mesh)
            col.label(text='Set Selection:')
            row = col.row()
            row.prop(instance, 'head_mesh_topology_groups', text='')

            row = box.row()
            row.label(text='Shrink Wrap Target:')
            row = box.row()
            row.prop(instance, 'shrink_wrap_target', text='')
            row = box.row()
            row.enabled = bool(instance.shrink_wrap_target)
            row.operator('meta_human_dna.shrink_wrap_vertex_group')
        else:
            draw_rig_logic_instance_error(self.layout, error)


class META_HUMAN_DNA_PT_armature_utilities_sub_panel(bpy.types.Panel):
    bl_parent_id = "META_HUMAN_DNA_PT_utilities"
    bl_label = "Armature"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Meta-Human DNA'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        properties = context.scene.meta_human_dna # type: ignore
        error = valid_rig_logic_instance_exists(context)
        if not error:
            active_index = properties.rig_logic_instance_list_active_index
            instance = properties.rig_logic_instance_list[active_index]
            box = self.layout.box()
            row = box.row()
            row.label(text='Bone Selection Groups:')
            row = box.row()
            row.prop(instance, 'list_surface_bone_groups')
            row = box.row()
            grid = row.grid_flow(
                row_major=True, 
                columns=2, 
                even_columns=True, 
                even_rows=True, 
                align=True
            )
            col = grid.column()
            col.enabled = bool(instance.head_mesh)
            col.label(text='Selection Mode:')
            row = col.row()
            row.prop(instance, 'head_rig_bone_group_selection_mode', text='')

            col = grid.column()
            col.enabled = bool(instance.head_mesh)
            col.label(text='Set Selection:')
            row = col.row()
            row.prop(instance, 'head_rig_bone_groups', text='')
            row = self.layout.row()
            # row.label(text='Push Bones:')
            # row = self.layout.row()
            # row.prop(properties, 'push_along_normal_distance', text='Normal Distance')
            # split = row.split(factor=0.5, align=True)
            # split.operator('meta_human_dna.push_bones_backward_along_normals', text='', icon='REMOVE')
            # split.operator('meta_human_dna.push_bones_forward_along_normals', text='', icon='ADD')
            row = self.layout.row()
            row.label(text='Transform and Apply Selected Bones:')
            row = self.layout.row()
            row.operator('meta_human_dna.sync_with_body_in_blueprint', text='Sync with Body in Blueprint')
            row = self.layout.row()
            row.operator('meta_human_dna.mirror_selected_bones', text='Mirror Selected Bones')
            row = self.layout.row()
            split = row.split(factor=0.5)
            split.scale_y = 1.5
            split.operator('meta_human_dna.auto_fit_selected_bones', text='Auto Fit')
            split.operator('meta_human_dna.revert_bone_transforms_to_dna', text='Revert')
        else:
            draw_rig_logic_instance_error(self.layout, error)


class META_HUMAN_DNA_PT_materials_utilities_sub_panel(bpy.types.Panel):
    bl_parent_id = "META_HUMAN_DNA_PT_utilities"
    bl_label = "Material"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Meta-Human DNA'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        error = valid_rig_logic_instance_exists(context)
        if not error:
            row = self.layout.row()
            row.operator('meta_human_dna.generate_material', icon='MATERIAL')
        else:
            draw_rig_logic_instance_error(self.layout, error)



class META_HUMAN_DNA_PT_utilities_sub_panel(bpy.types.Panel):
    bl_parent_id = "META_HUMAN_DNA_PT_utilities"
    bl_label = "(Not Shown)"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Meta-Human DNA'
    bl_options = {'HIDE_HEADER'}

    def draw(self, context):
        row = self.layout.row()
        row.scale_y = 1.5
        row.operator('meta_human_dna.convert_selected_to_dna', icon='RNA_ADD')


class META_HUMAN_DNA_PT_view_options(bpy.types.Panel):
    bl_label = "View Options"
    bl_category = 'Meta-Human DNA'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        properties = context.scene.meta_human_dna # type: ignore
        error = valid_rig_logic_instance_exists(context)
        if not error:
            active_index = properties.rig_logic_instance_list_active_index
            instance = properties.rig_logic_instance_list[active_index]
            grid = self.layout.grid_flow(
                row_major=True, 
                columns=2, 
                even_columns=True, 
                even_rows=True, 
                align=True
            )
            col = grid.column()
            col.enabled = bool(instance.material)
            col.label(text='Head Material Color:')
            row = col.row()
            row.prop(instance, 'active_material_preview', text='')

            col = grid.column()
            col.enabled = bool(instance.head_mesh)
            col.label(text='Active LOD:')
            row = col.row()
            row.prop(instance, 'active_lod', text='')
            row = self.layout.row()
            row.prop(instance, 'show_bones')
            row = self.layout.row()
            row.prop(properties, 'highlight_matching_active_bone')
        else:
            draw_rig_logic_instance_error(self.layout, error)


class META_HUMAN_DNA_PT_rig_logic(bpy.types.Panel):
    bl_label = "Rig Logic"
    bl_category = 'Meta-Human DNA'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        properties = context.scene.meta_human_dna # type: ignore
        row = self.layout.row()
        row = self.layout.row()
        col = draw_ui_list(
            row,
            context,
            class_name="META_HUMAN_DNA_UL_rig_logic_instances",
            list_path="scene.meta_human_dna.rig_logic_instance_list",
            active_index_path="scene.meta_human_dna.rig_logic_instance_list_active_index",
            unique_id="rig_logic_instance_list_id",
            insertion_operators=False,
            move_operators=False # type: ignore
        )

        enabled = len(properties.rig_logic_instance_list) > 0

        # plus and minus buttons
        row = col.row()
        props = row.operator("meta_human_dna.rig_logic_instance_entry_add", text="", icon='ADD')
        props.active_index = properties.rig_logic_instance_list_active_index # type: ignore

        row = col.row()
        row.enabled = enabled
        props = row.operator("meta_human_dna.rig_logic_instance_entry_remove", text="", icon='REMOVE')
        props.active_index = properties.rig_logic_instance_list_active_index # type: ignore

        if enabled:
            row = col.row()
            row.operator('meta_human_dna.duplicate_rig_logic_instance', icon='DUPLICATE', text='')

            row = col.row()
            props = row.operator("meta_human_dna.rig_logic_instance_entry_move", text="", icon='TRIA_UP')
            props.direction = 'UP' # type: ignore
            props.active_index = properties.rig_logic_instance_list_active_index # type: ignore

            row = col.row()
            props = row.operator("meta_human_dna.rig_logic_instance_entry_move", text="", icon='TRIA_DOWN')
            props.direction = 'DOWN' # type: ignore
            props.active_index = properties.rig_logic_instance_list_active_index # type: ignore

        active_index = properties.rig_logic_instance_list_active_index
        if len(properties.rig_logic_instance_list) > 0:
            instance = properties.rig_logic_instance_list[active_index]
            row = self.layout.row()
            box = row.box()
            row = box.row()
            row.label(text='Rig Logic Instance:')
            row = box.row()
            row.alert = False
            bad_path = instance.dna_file_path and not Path(bpy.path.abspath(instance.dna_file_path)).exists()
            if not instance.dna_file_path or bad_path:
                row.alert = True
            row.prop(instance, 'dna_file_path', icon='RNA')
            if bad_path:
                row = box.row()
                row.alert = True
                row.label(text='DNA File not found on disk.', icon='ERROR')
            row = box.row()
            row.alert = False
            if not instance.face_board:
                row.alert = True
            row.prop(instance, 'face_board', icon='PIVOT_BOUNDBOX')
            row = box.row()
            row.prop(instance, 'head_mesh', icon='OUTLINER_OB_MESH')
            row = box.row()
            row.prop(instance, 'head_rig', icon='OUTLINER_OB_ARMATURE')
            row = box.row()
            row.prop(instance, 'material', icon='MATERIAL')
            row = box.row()
            row.operator('meta_human_dna.force_evaluate', icon='FILE_REFRESH')


class META_HUMAN_DNA_PT_shape_keys(bpy.types.Panel):
    bl_label = "Shape Keys"
    bl_category = 'Meta-Human DNA'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        instance = None
        properties = context.scene.meta_human_dna # type: ignore
        active_index = properties.rig_logic_instance_list_active_index
        if len(properties.rig_logic_instance_list) > 0:
            instance = properties.rig_logic_instance_list[active_index]
            if not instance.shape_key_list and instance.head_mesh:
                if context.window_manager.meta_human_dna.progress == 1: # type: ignore
                    row = self.layout.row()
                    row.label(text=f'No shape keys on {instance.name}', icon='ERROR')
                    row = self.layout.row()
                    row.prop(instance, 'generate_neutral_shapes')
                    row = self.layout.row()
                    row.operator('meta_human_dna.import_shape_keys', icon='IMPORT')
                    return
                
        if context.window_manager.meta_human_dna.progress < 1: # type: ignore
            row = self.layout.row()
            row.label(text=f'Importing onto "{context.window_manager.meta_human_dna.progress_mesh_name}"...', icon='SORTTIME') # type: ignore
            row = self.layout.row()
            row.progress(
                factor=context.window_manager.meta_human_dna.progress, # type: ignore
                type="BAR",
                text=context.window_manager.meta_human_dna.progress_description # type: ignore
            )
            row.scale_x = 2
            return

        error = valid_rig_logic_instance_exists(context)
        if not error:
            row = self.layout.row()
            if instance:
                row.label(text='Filter by Mesh')
                split = self.layout.split(factor=0.97)
                split.prop(instance, 'active_shape_key_mesh_name', text='')
                row = self.layout.row()
            active_index = properties.rig_logic_instance_list_active_index
            draw_ui_list(
                row,
                context,
                class_name="META_HUMAN_DNA_UL_shape_keys",
                list_path=f"scene.meta_human_dna.rig_logic_instance_list[{active_index}].shape_key_list",
                active_index_path=f"scene.meta_human_dna.rig_logic_instance_list[{active_index}].shape_key_list_active_index",
                unique_id="active_shape_key_list_id",
                insertion_operators=False,
                move_operators=False # type: ignore
            )
            row = self.layout.row()
            row.prop(instance, 'solo_shape_key', text='Solo selected shape key')
            row = self.layout.row()
            row.prop(instance, 'generate_neutral_shapes')
            row = self.layout.row()
            row.operator('meta_human_dna.import_shape_keys', icon='IMPORT', text='Reimport All Shape Keys')
        else:
            draw_rig_logic_instance_error(self.layout, error)


class META_HUMAN_DNA_PT_output_panel(bpy.types.Panel):
    """
    This class defines the user interface for the panel in the tab in the 3d view
    """
    bl_label = 'Output'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Meta-Human DNA'

    def draw(self, context):
        properties = bpy.context.scene.meta_human_dna # type: ignore
        error = valid_rig_logic_instance_exists(context, ignore_face_board=True)
        if not error:
            active_index = properties.rig_logic_instance_list_active_index
            instance = properties.rig_logic_instance_list[active_index]
            grid = self.layout.grid_flow(
                row_major=True, 
                columns=1, 
                even_columns=True, 
                even_rows=True, 
                align=True
            )
            col = grid.column()
            col.label(text='Method:')
            row = col.row()
            row.prop(instance, 'output_method', text='')

            row = self.layout.row()           
            draw_ui_list(
                row,
                context,
                class_name="META_HUMAN_DNA_UL_output_items",
                list_path=f"scene.meta_human_dna.rig_logic_instance_list[{active_index}].output_item_list",
                active_index_path=f"scene.meta_human_dna.rig_logic_instance_list[{active_index}].output_item_active_index",
                unique_id="output_item_list_id",
                move_operators=False, # type: ignore
                insertion_operators=False   
            )
            row = self.layout.row()
            row.label(text='Output Folder:')
            row = self.layout.row()
            if not instance.output_folder_path:
                row.alert = True
            row.prop(instance, 'output_folder_path', text='', icon='RNA')
            if not instance.output_folder_path:
                row = self.layout.row()
                row.alert = True
                row.label(text='Must set an output folder.', icon='ERROR')
        else:
            draw_rig_logic_instance_error(self.layout, error)


class META_HUMAN_DNA_PT_send2ue_settings_sub_panel(bpy.types.Panel):
    bl_parent_id = "META_HUMAN_DNA_PT_output_panel"
    bl_label = "Send to Unreal Settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Meta-Human DNA'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        from ..utilities import send2ue_addon_is_valid
        error = valid_rig_logic_instance_exists(context, ignore_face_board=True)
        if not error and send2ue_addon_is_valid():
            return True
        return False

    def draw(self, context):
        from ..utilities import send2ue_addon_is_valid
        if not getattr(context.scene, 'send2ue', None): # type: ignore
            row = self.layout.row()
            row.alert = True
            row.label(
                text='Send to Unreal Addon must be installed and enabled', 
                icon='ERROR'
            )
            return        
        
        if not send2ue_addon_is_valid(): # type: ignore
            row = self.layout.row()
            row.alert = True
            row.label(
                text='Send to Unreal Addon version 2.6.0 or greater is required.', 
                icon='ERROR'
            )
            return

        properties = context.scene.meta_human_dna # type: ignore
        error = valid_rig_logic_instance_exists(context, ignore_face_board=True)
        if not error:
            active_index = properties.rig_logic_instance_list_active_index
            instance = properties.rig_logic_instance_list[active_index]
            row = self.layout.row()
            row.label(text='Settings Template:')
            row = self.layout.row()
            row.prop(instance, 'send2ue_settings_template', text='')
            row = self.layout.row()
            row.label(text='Content Folder (Unreal):')
            row = self.layout.row()
            row.prop(instance, 'unreal_content_folder', text='')
            row = self.layout.row()
            row.label(text='Blueprint Asset (Unreal):')
            row = self.layout.row()
            row.prop(instance, 'unreal_blueprint_asset_path', text='')
            row = self.layout.row()
            row.label(text='Level Sequence Asset (Unreal):')
            row = self.layout.row()
            row.prop(instance, 'unreal_level_sequence_asset_path', text='')
            row = self.layout.row()
            row.prop(instance, 'auto_sync_spine_with_body')
            row = self.layout.row()
            row.prop(instance, 'unreal_copy_assets')
            row = self.layout.row()
            row.label(text='Face Control Rig Asset (Unreal):')
            row = self.layout.row()
            row.prop(instance, 'unreal_face_control_rig_asset_path', text='')
            row = self.layout.row()
            row.label(text='Face Anim BP Asset (Unreal):')
            row = self.layout.row()
            row.prop(instance, 'unreal_face_anim_bp_asset_path', text='')
            row = self.layout.row()
            row.label(text='Material Slot to Unreal Material Instance:')
            row = self.layout.row()
            col = draw_ui_list(
                row,
                context,
                class_name="META_HUMAN_DNA_UL_material_slot_to_instance_mapping",
                list_path=f"scene.meta_human_dna.rig_logic_instance_list[{active_index}].unreal_material_slot_to_instance_mapping",
                active_index_path=f"scene.meta_human_dna.rig_logic_instance_list[{active_index}].unreal_material_slot_to_instance_mapping_active_index",
                unique_id="unreal_material_slot_to_instance_mapping_id",
                move_operators=False, # type: ignore
                insertion_operators=False
            )
            col.operator('meta_human_dna.refresh_material_slot_names', icon='FILE_REFRESH', text='')
            col.operator('meta_human_dna.revert_material_slot_values', icon='LOOP_BACK', text='')

        else:
            draw_rig_logic_instance_error(self.layout, error)

class META_HUMAN_DNA_PT_buttons_sub_panel(bpy.types.Panel):
    bl_parent_id = "META_HUMAN_DNA_PT_output_panel"
    bl_label = "(Not Shown)"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Meta-Human DNA'
    bl_options = {'HIDE_HEADER'}

    def draw(self, context):
        properties = context.scene.meta_human_dna # type: ignore
        error = valid_rig_logic_instance_exists(context, ignore_face_board=True)
        row = self.layout.row()
        if not error:
            active_index = properties.rig_logic_instance_list_active_index
            instance = properties.rig_logic_instance_list[active_index]
            if not instance.output_folder_path:
                row.enabled = False
            row.scale_y = 2.0
            row.operator('meta_human_dna.export_to_disk', icon='EXPORT')
            row.operator('meta_human_dna.send_to_unreal', icon='UV_SYNC_SELECT')

