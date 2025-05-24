import os
import bpy
import gpu
import math
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from mathutils import Vector, Matrix, Euler
from gpu_extras.presets import draw_circle_2d
from ..constants import (
    HEAD_MAPS,
    POSES_FOLDER,
    NUMBER_OF_FACE_LODS,
    MATERIAL_SLOT_TO_MATERIAL_INSTANCE_DEFAULTS,
    SEND2UE_FACE_SETTINGS,
    BASE_DNA_FOLDER,
    ToolInfo
)

if TYPE_CHECKING:
    from ..rig_logic import RigLogicInstance


logger = logging.getLogger(__name__)


def get_bake_start_frame(self) -> int:
    try:
        return self.get('bake_start_frame', bpy.context.scene.frame_start) # type: ignore
    except AttributeError:
        return self.get('bake_start_frame', 1)

def get_bake_end_frame(self) -> int:
    try:
        return self.get('bake_end_frame', bpy.context.scene.frame_end) # type: ignore
    except AttributeError:
        return self.get('bake_end_frame', 250)
    
def get_active_rig_logic() -> 'RigLogicInstance | None':
    """
    Gets the active rig logic instance.
    """
    properties = bpy.context.scene.meta_human_dna # type: ignore
    if len(properties.rig_logic_instance_list) > 0:
        index = properties.rig_logic_instance_list_active_index
        return properties.rig_logic_instance_list[index]
    
def get_texture_logic_node(material: bpy.types.Material) -> bpy.types.ShaderNodeGroup | None:
    if not material or not material.node_tree:
        return None
    for node in material.node_tree.nodes:
        if node.type == 'GROUP':
            # Check if this is the right group node by checking one input name
            # We don't check all to avoid performance issues
            if node.inputs.get('head_wm1_jawOpen_msk'):
                return node

def get_active_material_preview(self) -> int:
    return self.get('active_material_preview', 0)

def get_output_instance_items(self, context):
    enum_items = []
    properties = bpy.context.scene.meta_human_dna # type: ignore
    for instance in properties.rig_logic_instance_list:
        enum_items.append((instance.name, instance.name, f'Face rig logic instance {instance.name}'))
    return enum_items

def get_face_pose_previews_items(self, context):
    from ..properties import preview_collections
    enum_items = []

    if context is None:
        return enum_items

    directory = POSES_FOLDER / 'face'

    # Get the preview collection.
    preview_collection = preview_collections["face_poses"]

    # If the enum items have already been cached, return them so we don't have to regenerate them.
    if preview_collection.values():
        return preview_collection.face_pose_previews

    if directory.exists():
        image_paths = []

        for folder_path, _, file_names in os.walk(directory):
            for file_name in file_names:
                if file_name == 'thumbnail-preview.png':
                    thumbnail_file_path = Path(folder_path, file_name)
                    pose_file_path = Path(folder_path, 'pose.json')
                    if pose_file_path.exists() and thumbnail_file_path.exists():
                        image_paths.append(Path(folder_path, file_name))

        for i, file_path in enumerate(image_paths):
            name = file_path.parent.name
            # generates a thumbnail preview for a file.
            icon = preview_collection.get(name)
            if not icon:
                thumb = preview_collection.load(name, str(file_path), 'IMAGE')
            else:
                thumb = preview_collection[name]
            enum_items.append((str(file_path), name, "", thumb.icon_id, i))

    # cache the enum item values for later retrieval
    preview_collection.face_pose_previews = enum_items
    return preview_collection.face_pose_previews

def get_head_mesh_topology_groups(self, context):
    enum_items = []
    instance = get_active_rig_logic()
    if instance and instance.head_mesh:
        for group_name in instance.head_mesh.vertex_groups.keys():
            if group_name.startswith('TOPO_GROUP_'):
                enum_items.append(
                    (
                        group_name, 
                        ' '.join([i.capitalize() for i in group_name.replace('TOPO_GROUP_', '').split('_')]),
                        f'Select vertices assigned to {group_name} on the active head mesh'
                    )
                )

    return enum_items


def get_head_rig_bone_groups(self, context):
    enum_items = []   
    from ..bindings import meta_human_dna_core
    for group_name in meta_human_dna_core.BONE_SELECTION_GROUPS.keys():    
        enum_items.append(
            (
                group_name, 
                ' '.join([i.capitalize() for i in group_name.split('_')]),
                f'Select bones in the group {group_name} on the head rig'
            )
        )
    instance = get_active_rig_logic()
    if instance and instance.head_mesh and instance.list_surface_bone_groups:
        for item in get_head_mesh_topology_groups(self, context):
            _item = list(item)
            _item[1] = f'(Surface) {item[1]}'
            enum_items.append(tuple(_item))
    return enum_items

def get_base_dna_files(self, context):
    enum_items = []   
    # get all the dna files in the addon's dna folder
    for file in BASE_DNA_FOLDER.iterdir():    
        if file.is_file() and file.suffix == '.dna':
            enum_items.append(
                (
                    str(file.absolute()), 
                    ' '.join([i.capitalize() for i in file.stem.split('_')]),
                    f'Use the {file.name} file as the base DNA to convert the selected mesh'
                )
            )

    # get all the dna files in the extra dna folders
    extra_dna_folder_list = context.preferences.addons[ToolInfo.NAME].preferences.extra_dna_folder_list
    for item in extra_dna_folder_list:
        for file in Path(item.folder_path).iterdir():    
            if file.is_file() and file.suffix == '.dna':
                enum_items.append(
                    (
                        str(file.absolute()), 
                        ' '.join([i.capitalize() for i in file.stem.split('_')]),
                        f'Use the {file.name} file as the base DNA to convert the selected mesh'
                    )
                )
    return enum_items

def get_send2ue_settings_templates(self, context):
    items = [
        (
            SEND2UE_FACE_SETTINGS.name, 
            'Meta-Human DNA', 
            'The Send to Unreal Settings template that will be used for exporting from blender and importing to unreal', 
            'NONE', 
            0
        )
    ]
        
    send2ue_properties = getattr(bpy.context.scene, 'send2ue', None) # type: ignore
    if send2ue_properties:
        from send2ue.core.settings import populate_settings_template_dropdown # type: ignore
        for item in populate_settings_template_dropdown(self, context):
            if item[0] != SEND2UE_FACE_SETTINGS.name:
                items.append(
                    (item[0], item[1], item[2], item[3], item[4]+1) # type: ignore
                )
    return items

def get_active_lod(self) -> int:
    return self.get('active_lod', 0)

def get_show_bones(self) -> bool:
    if self.head_rig:
        return not self.head_rig.hide_get() # type: ignore
    return False

def get_shape_key_value(self) -> float:
    instance = get_active_rig_logic()
    if instance:
        channel_index = instance.channel_name_to_index_lookup.get(self.name)
        if not channel_index:
            return 0.0      
        
        for shape_key_block in instance.shape_key_blocks.get(channel_index, []):
            try:
                if shape_key_block.name == self.name:
                    return shape_key_block.value
            except UnicodeDecodeError:
                # This happens when the block is already removed from memory
                pass
    return 0.0

def get_active_shape_key_mesh_names(self, context):
    items = []
    if self.mesh_index_lookup:
        for mesh_index, mesh_object in self.mesh_index_lookup.items(): 
            if mesh_object.data.shape_keys and len(mesh_object.data.shape_keys.key_blocks) > 0:       
                items.append(
                    (
                        mesh_object.name, 
                        mesh_object.name.replace(f'{self.name}_', ''),
                        f'Only display the shape key values for "{mesh_object.name}"', 
                        'NONE', 
                        mesh_index
                    )
                )
    elif self.head_mesh:
        items.append(
                (
                    self.head_mesh.name, 
                    self.head_mesh.name.replace(f'{self.name}_', ''), 
                    f'Only display the shape key values for "{self.head_mesh.name}"', 
                    'NONE', 
                    0
                )
            )
    return items

def set_highlight_matching_active_bone(self, value):
    gpu_draw_handler = self.context.pop('gpu_draw_highlight_matching_active_bone_handler', None)
    if gpu_draw_handler:
        bpy.types.SpaceView3D.draw_handler_remove(gpu_draw_handler, 'WINDOW')

    if value:        
        def draw():
            if bpy.context.mode == 'POSE': # type: ignore
                pose_bone = bpy.context.active_pose_bone # type: ignore
                if pose_bone:
                    for instance in bpy.context.scene.meta_human_dna.rig_logic_instance_list: # type: ignore
                        if instance and instance.head_rig and pose_bone.id_data != instance.head_rig:
                            source_pose_bone = instance.head_rig.pose.bones.get(pose_bone.name)
                            if source_pose_bone:
                                world_location = instance.head_rig.matrix_world @ source_pose_bone.matrix.to_translation()
                                draw_sphere(
                                    position=world_location,
                                    color=(1,0,1,1), 
                                    radius=0.001
                                )

        gpu_draw_handler = bpy.types.SpaceView3D.draw_handler_add(draw, (), 'WINDOW', 'POST_VIEW') # type: ignore
        self.context['gpu_draw_highlight_matching_active_bone_handler'] = gpu_draw_handler

    self['highlight_matching_active_bone'] = value


def get_highlight_matching_active_bone(self):
    return self.get('highlight_matching_active_bone', False)


def set_bake_start_frame(self, value):
    self['bake_start_frame'] = value

def set_bake_end_frame(self, value):
    self['bake_end_frame'] = value

def set_active_lod(self, value):
    self['active_lod'] = value
    for scene_object in bpy.context.scene.objects: # type: ignore
        if scene_object.name.startswith(self.name) and scene_object.type == 'MESH':
            ignored_names = [
                f'{self.name}_eyeshell_lod{value}_mesh',
                f'{self.name}_eyeEdge_lod{value}_mesh',
                f'{self.name}_cartilage_lod{value}_mesh',
                f'{self.name}_saliva_lod{value}_mesh'
            ]
            scene_object.hide_set(True)
            if scene_object.name.endswith(f'_lod{value}_mesh') and scene_object.name not in ignored_names:
                scene_object.hide_set(False)

def set_show_bones(self, value):
    if self.head_rig:
        self.head_rig.hide_set(not value)

def set_copied_rig_logic_instance_name(self, value):
    self['copied_rig_logic_instance_name'] = value

def get_copied_rig_logic_instance_name(self):
    value = self.get('copied_rig_logic_instance_name')
    if value is None:
        instance = get_active_rig_logic()
        if instance:
            return f'{instance.name}_copy'
        else:
            return ''
    return value

def set_unreal_content_folder(self, value):
    self['unreal_content_folder'] = value

def get_unreal_content_folder(self):
    value = self.get('unreal_content_folder')
    if value is None:
        instance = get_active_rig_logic()
        if instance:
            return f'/Game/MetaHumans/{instance.name}/Face'
    return value


def set_active_material_preview(self, value):
    self['active_material_preview'] = value
    input_name = 'Factor'

    node_group = get_texture_logic_node(self.material)
    if not node_group or not node_group.node_tree:
        return

    # combined
    if value == 0:
        node_group.node_tree.nodes['show_color_or_other'].inputs[input_name].default_value = 0 # type: ignore
        node_group.node_tree.nodes['show_mask_or_normal'].inputs[input_name].default_value = 0 # type: ignore
        node_group.node_tree.nodes['show_color_or_topology'].inputs[input_name].default_value = 0 # type: ignore
    # masks
    elif value == 1:
        node_group.node_tree.nodes['show_color_or_other'].inputs[input_name].default_value = 1 # type: ignore
        node_group.node_tree.nodes['show_mask_or_normal'].inputs[input_name].default_value = 1 # type: ignore
        node_group.node_tree.nodes['show_color_or_topology'].inputs[input_name].default_value = 0 # type: ignore
    # normals
    elif value == 2:
        node_group.node_tree.nodes['show_color_or_other'].inputs[input_name].default_value = 1 # type: ignore
        node_group.node_tree.nodes['show_mask_or_normal'].inputs[input_name].default_value = 0 # type: ignore
        node_group.node_tree.nodes['show_color_or_topology'].inputs[input_name].default_value = 0 # type: ignore
    
    # topology
    elif value == 3:
        node_group.node_tree.nodes['show_color_or_other'].inputs[input_name].default_value = 0 # type: ignore
        node_group.node_tree.nodes['show_mask_or_normal'].inputs[input_name].default_value = 0 # type: ignore
        node_group.node_tree.nodes['show_color_or_topology'].inputs[input_name].default_value = 1 # type: ignore


def poll_head_rig_bone_selection(cls, context):
    instance = get_active_rig_logic()
    return (
        context.mode == 'POSE' and # type: ignore
        context.selected_pose_bones and # type: ignore
        instance.head_rig == context.active_object # type: ignore
    )

def poll_head_materials(self, material: bpy.types.Material) -> bool:
    node = get_texture_logic_node(material)
    if node:
        return True
    return False

def poll_face_boards(self, scene_object: bpy.types.Object) -> bool:
    if scene_object.type == 'ARMATURE':
        # Check if this is the right armature by checking one bone name
        # We don't check all bone names to avoid performance issues
        if scene_object.pose.bones.get('CTRL_rigLogic'):
            return True
    return False

def poll_head_rig(self, scene_object: bpy.types.Object) -> bool:
    if scene_object.type == 'ARMATURE':
        # This check will filter out the face boards
        if not scene_object.pose.bones.get('CTRL_rigLogic'):
            return True
    return False

def poll_head_mesh(self, scene_object: bpy.types.Object) -> bool:
    if scene_object.type == 'MESH':
        if scene_object.name in bpy.context.scene.objects: # type: ignore
            return True
    return False

def poll_shrink_wrap_target(self, scene_object: bpy.types.Object) -> bool:
    if scene_object.type == 'MESH':
        if scene_object.name in bpy.context.scene.objects: # type: ignore
            # don't allow any existing head mesh that is already linked to a rig logic instance
            if any(i.head_mesh == scene_object for i in bpy.context.scene.meta_human_dna.rig_logic_instance_list): # type: ignore
                return False
            return True
    return False

def update_head_topology_selection(self, context):
    from ..utilities import get_active_face
    face = get_active_face()
    if face:
        face.select_vertex_group()

def update_head_rig_bone_group_selection(self, context):
    from ..utilities import get_active_face
    face = get_active_face()
    if face:
        face.select_bone_group()

def update_face_pose(self, context):
    from ..utilities import get_active_face
    face = get_active_face()
    if face:
        face.set_face_pose()

def get_mesh_output_items(instance: 'RigLogicInstance') -> list[bpy.types.Object]:
    mesh_objects =[]

    # get all mesh objects that are skinned to the head rig
    for scene_object in bpy.data.objects:
        if scene_object.type == 'MESH':
            for modifier in scene_object.modifiers:
                if modifier.type == 'ARMATURE' and modifier.object == instance.head_rig: # type: ignore
                    mesh_objects.append(scene_object)
                    break
    
    return mesh_objects

def get_image_output_items(instance: 'RigLogicInstance') -> list[tuple[bpy.types.Image, str]]:
    image_nodes = []
    if instance.material:
        # Todo: Change this to be all the textures in all the materials
        texture_logic_node = get_texture_logic_node(instance.material)
        if texture_logic_node:
            for input_name, file_name in HEAD_MAPS.items():
                node_input = texture_logic_node.inputs.get(input_name)
                if node_input and node_input.links:
                    image_node = node_input.links[0].from_node
                    if image_node.type == 'TEX_IMAGE':
                        image_nodes.append((image_node.image, file_name))
    return image_nodes

def get_instance_name(self):
    return self.get('instance_name', '')

def set_instance_name(self, value):
    old_name = self.get('instance_name')
    if old_name != value and value:
        if old_name:
            from ..utilities import rename_rig_logic_instance
            rename_rig_logic_instance(
                instance=self,
                old_name=old_name,
                new_name=value
            )
        self['instance_name'] = value

def update_output_items(self, context):
    for instance in bpy.context.scene.meta_human_dna.rig_logic_instance_list: # type: ignore
        if instance and instance.head_mesh and instance.head_rig:
            # update the output items for the scene objects
            for scene_object in get_mesh_output_items(instance) + [instance.head_rig]:
                for i in instance.output_item_list:
                    if not i.image_object and i.scene_object == scene_object:
                        break
                else:
                    new_item = instance.output_item_list.add()
                    new_item.scene_object = scene_object
                    if scene_object == instance.head_mesh:
                        new_item.name = 'head_lod0_mesh'
                        new_item.editable_name = False
                    elif scene_object == instance.head_rig:
                        new_item.name = 'rig'
                        new_item.editable_name = False
                    else:
                        new_item.name = scene_object.name.replace(f'{instance.name}_', '')
                        new_item.editable_name = True

            # update the output items for the image textures
            for image_object, file_name in get_image_output_items(instance):
                for i in instance.output_item_list:
                    if not i.scene_object and i.image_object == image_object:
                        break
                else:
                    new_item = instance.output_item_list.add()
                    new_item.image_object = image_object
                    new_item.name = file_name
                    new_item.editable_name = False

            # remove any output items that do not have a scene object or image object
            for item in instance.output_item_list:
                if not item.scene_object and not item.image_object: # type: ignore
                    index = instance.output_item_list.find(item.name)
                    instance.output_item_list.remove(index)

    # update the material slots to instance mappings
    update_material_slot_to_instance_mapping(self, context)

def update_material_slot_to_instance_mapping(self, context):
    instance = get_active_rig_logic()
    if instance and instance.head_rig:
        material_slot_names = []
        for item in instance.output_item_list:
            if item.scene_object and item.scene_object.type == 'MESH':
                material_slot_names.extend(list(item.scene_object.material_slots.keys()))
        
        # remove duplicates
        material_slot_names = list(set(material_slot_names))
        # remove any material slot names that are linked to a mesh
        for index, item in enumerate(instance.unreal_material_slot_to_instance_mapping):
            if item.name not in material_slot_names:
                instance.unreal_material_slot_to_instance_mapping.remove(index)

        for material_slot_name in material_slot_names:
            slot_name = material_slot_name.replace(f'{instance.name}_', '')
            if instance.unreal_material_slot_to_instance_mapping.find(material_slot_name) == -1:
                slot = instance.unreal_material_slot_to_instance_mapping.add()
                slot.name = material_slot_name
                slot.asset_path = MATERIAL_SLOT_TO_MATERIAL_INSTANCE_DEFAULTS.get(slot_name, '')
    
def get_head_mesh_lod_items(self, context):
    items = []
    
    try:
        # get the lods for the active face
        instance = get_active_rig_logic()
        if instance:
            for i in range(NUMBER_OF_FACE_LODS):
                head_mesh = bpy.data.objects.get(f'{instance.name}_head_lod{i}_mesh')
                if head_mesh:
                    items.append((f'lod{i}', f'LOD {i}', f'Displays only LOD {i}'))
    except AttributeError:
        pass

    # if no lods are found, add a default item
    if not items:
        items = [
            ('lod0', 'LOD 0', 'Displays only LOD 0')
        ]

    return items

def draw_sphere(position, color, radius=0.001):
    segments = 16
    draw_circle_2d(
        position=position,
        color=color, 
        radius=radius, 
        segments=segments
    )
    rotation_matrix = Matrix.Rotation(math.radians(90), 4, 'X')
    rotation_matrix.translation = position
    x_rotation_matrix = rotation_matrix.to_4x4()
    gpu.matrix.multiply_matrix(x_rotation_matrix)
    draw_circle_2d(
        position=Vector((0, 0, 0)),
        color=color, 
        radius=radius, 
        segments=segments
    )
    rotation_matrix = rotation_matrix.to_3x3()
    rotation_matrix.rotate(Euler((0,0, math.radians(90))))
    z_rotation_matrix = rotation_matrix.to_4x4()
    gpu.matrix.multiply_matrix(z_rotation_matrix)
    draw_circle_2d(
        position=Vector((0, 0, 0)),
        color=color, 
        radius=radius, 
        segments=segments
    )

    # undo the rotations
    gpu.matrix.multiply_matrix(z_rotation_matrix.inverted())
    gpu.matrix.multiply_matrix(x_rotation_matrix.inverted())