import bpy
import math
import logging
from pprint import pformat
from pathlib import Path
from mathutils import Matrix, Vector, Euler
from . import utilities
from .ui import callbacks
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .bindings import riglogic


logger = logging.getLogger(__name__)


def rig_logic_listener(scene, dependency_graph):
    # this condition prevents constant evaluation
    if not bpy.context.window_manager.meta_human_dna.evaluate_dependency_graph: # type: ignore
        return

    should_update = False

    # if the screen is the temp screen, then is is rendering and we need to evaluate
    if bpy.context.screen and 'temp' in bpy.context.screen.name.lower(): # type: ignore
        should_update = True

    # only evaluate if in pose mode or if animation is
    if bpy.context.mode == 'POSE' or (bpy.context.screen and bpy.context.screen.is_animation_playing): # type: ignore
        for update in dependency_graph.updates:
            data_type = update.id.bl_rna.name
            if data_type == 'Action':
                should_update = True
                break

            elif data_type == 'Armature':
                if update.is_updated_transform:
                    # Note: we split the name by '.' to get the armature name incase there are duplicates i.e. "face_gui.001"
                    face_board_armature_name = update.id.name.split('.')[0]
                    # get all the face board names from the rig logic instances and check if this armature is one of those face boards
                    if any(i.face_board.name.endswith(face_board_armature_name) for i in scene.meta_human_dna.rig_logic_instance_list if i.face_board):
                        should_update = True
                    break

    if should_update:
        for instance in scene.meta_human_dna.rig_logic_instance_list: # type: ignore
            if instance.auto_evaluate:
                instance.evaluate()

def stop_listening():
    for handler in bpy.app.handlers.depsgraph_update_post:
        if handler.__name__ == rig_logic_listener.__name__:
            bpy.app.handlers.depsgraph_update_post.remove(handler)

    for handler in bpy.app.handlers.frame_change_post:
        if handler.__name__ == rig_logic_listener.__name__:
            bpy.app.handlers.frame_change_post.remove(handler)

def start_listening():
    stop_listening()
    logging.info('Listening for Rig Logic...')
    callbacks.update_output_items(None, bpy.context)
    bpy.app.handlers.depsgraph_update_post.append(rig_logic_listener) # type: ignore
    bpy.app.handlers.frame_change_post.append(rig_logic_listener) # type: ignore


class MaterialSlotToInstance(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(
        default='',
        description='The name of the shape key',
    ) # type: ignore
    asset_path: bpy.props.StringProperty(
        default='',
        description='The unreal asset path to the material instance',
    ) # type: ignore
    valid_path: bpy.props.BoolProperty(default=True) # type: ignore


class OutputData(bpy.types.PropertyGroup):
    include: bpy.props.BoolProperty(
        default=True,
        description='Whether to include this data in the output',
    ) # type: ignore
    name: bpy.props.StringProperty(
        default='',
        description='The name of the shape key',
    ) # type: ignore
    scene_object: bpy.props.PointerProperty(
        type=bpy.types.Object, # type: ignore
        description=(
            'A object that is associated with the dna data. This automatically '
            'gets set based on what is linked in the Rig Logic Instance data'
        )
    ) # type: ignore
    image_object: bpy.props.PointerProperty(
        type=bpy.types.Image, # type: ignore
        description=(
            'A object that is associated with the dna data. This automatically '
            'gets set based on what is linked in the Rig Logic Instance data'
        )
    ) # type: ignore
    relative_file_path: bpy.props.StringProperty(
        default='',
        description='The relative file path from the output folder',
    ) # type: ignore
    editable_name: bpy.props.BoolProperty(
        default=True,
        description='Whether to include this data in the output',
    ) # type: ignore


class ShapeKeyData(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(
        default='',
        description='The name of the shape key',
    ) # type: ignore
    value: bpy.props.FloatProperty(
        default=0.0,
        description='The value of the shape key',
        get=callbacks.get_shape_key_value, # this makes the value read-only
    ) # type: ignore


class RigLogicInstance(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(
        default='my_metahuman',
        description='The name associated with this Rig Logic instance. This is also the unique identifier for all data associated with the metahuman head',
        set=callbacks.set_instance_name,
        get=callbacks.get_instance_name
    ) # type: ignore
    auto_evaluate: bpy.props.BoolProperty(
        default=True,
        name='Auto Evaluate',
        description='Whether to automatically evaluate this rig logic instance when the scene is updated',
    ) # type: ignore
    evaluate_bones: bpy.props.BoolProperty(
        default=True,
        name='Evaluate Bones',
        description='Whether to evaluate bone positions based on the face board controls'
    ) # type: ignore
    evaluate_shape_keys: bpy.props.BoolProperty(
        default=True,
        name='Evaluate Shape Keys',
        description='Whether to evaluate shape keys based on the face board controls'
    ) # type: ignore
    evaluate_texture_masks: bpy.props.BoolProperty(
        default=True,
        name='Evaluate Texture Masks',
        description='Whether to evaluate texture masks based on the face board controls'
    ) # type: ignore
    dna_file_path: bpy.props.StringProperty(
        name="DNA File",
        description="The path to the DNA file that rig logic reads from when evaluating the face board controls",
        subtype='FILE_PATH'
    ) # type: ignore
    face_board: bpy.props.PointerProperty(
        type=bpy.types.Object, # type: ignore
        name='Face Board',
        description='The face board that rig logic reads control positions from',
        poll=callbacks.poll_face_boards
    ) # type: ignore
    head_mesh: bpy.props.PointerProperty(
        type=bpy.types.Object, # type: ignore
        name='Head Mesh',
        description='The head mesh with the shape keys that rig logic will evaluate',
        poll=callbacks.poll_head_mesh,
        update=callbacks.update_output_items
    ) # type: ignore
    head_rig: bpy.props.PointerProperty(
        type=bpy.types.Object, # type: ignore
        name='Head Rig',
        description='The armature object that rig logic will evaluate',
        poll=callbacks.poll_head_rig,
        update=callbacks.update_output_items
    ) # type: ignore
    material: bpy.props.PointerProperty(
        type=bpy.types.Material, # type: ignore
        name='Material',
        description='The head material that has a node with wrinkle map sliders that rig logic will evaluate',
        poll=callbacks.poll_head_materials,
        update=callbacks.update_output_items
    ) # type: ignore

    # ----- View Options Properties -----
    active_lod: bpy.props.EnumProperty(
        name="Active LOD",
        items=callbacks.get_head_mesh_lod_items,
        description="Choose what Level of Detail should be displayed from the face",
        options={'ANIMATABLE'},
        set=callbacks.set_active_lod,
        get=callbacks.get_active_lod
    ) # type: ignore
    active_material_preview: bpy.props.EnumProperty(
        name="Material Color",
        items=[
            ('combined', 'Combined', 'Displays all combined textures maps'),
            ('masks', 'Masks', 'Displays only the color of the mask texture maps'),
            ('normals', 'Normals', 'Displays only the color of the normal texture maps'),
            ('topology', 'Topology', 'Displays only the mesh topology colors')
        ],
        description="Choose what color should be shown by the material",
        default='combined',
        set=callbacks.set_active_material_preview,
        get=callbacks.get_active_material_preview
    ) # type: ignore
    show_bones: bpy.props.BoolProperty(
        name="Show Bones",
        default=False,
        description="Whether to show or hide the bones that belong to this RigLogic instance in the 3D view",
        set=callbacks.set_show_bones,
        get=callbacks.get_show_bones
    ) # type: ignore

    # --------------------- Mesh Utilities Properties ------------------
    head_mesh_topology_groups: bpy.props.EnumProperty(
        name="Topology Groups",
        items=callbacks.get_head_mesh_topology_groups,
        description="Select the bone group to display in the 3D view",
        options={'ANIMATABLE'},
        update=callbacks.update_head_topology_selection
    ) # type: ignore
    head_mesh_topology_selection_mode: bpy.props.EnumProperty(
        name="Selection Mode",
        default='isolate',
        items=[
            ('add', 'Add', 'Adds the chosen topology group to the current selection'),
            ('isolate', 'Isolate', 'Isolates the chosen topology group by de-selecting everything else'),
        ],
        description="Choose what selection mode to use when selecting the head topology groups"
    ) # type: ignore
    shrink_wrap_target: bpy.props.PointerProperty(
        type=bpy.types.Object, # type: ignore
        name='Material',
        description='The head mesh that the shrink wrap modifier will target. This is the mesh that you will wrap the head topology to',
        poll=callbacks.poll_shrink_wrap_target
    ) # type: ignore

    # --------------------- Armature Utilities Properties ------------------
    head_rig_bone_group_selection_mode: bpy.props.EnumProperty(
        name="Selection Mode",
        default='isolate',
        items=[
            ('add', 'Add', 'Adds the chosen bone group to the current selection'),
            ('isolate', 'Isolate', 'Isolates the chosen bone group by de-selecting everything else'),
        ],
        description="Choose what selection mode to use when selecting the head topology groups"
    ) # type: ignore
    head_rig_bone_groups: bpy.props.EnumProperty(
        name="Bone Groups",
        items=callbacks.get_head_rig_bone_groups,
        description="Select the bone group to display in the 3D view",
        options={'ANIMATABLE'},
        update=callbacks.update_head_rig_bone_group_selection
    ) # type: ignore
    list_surface_bone_groups: bpy.props.BoolProperty(
        name="List Surface Bones",
        default=False,
        description="Whether to also show the surface bone groups in the bone group selection dropdown",
    ) # type: ignore

    # ----- Shape Keys Properties -----
    active_shape_key_mesh_name: bpy.props.EnumProperty(
        name='Active Shape Key Mesh',
        description="This determines which mesh object's shape keys value are being displayed in the shape key list",
        options={'ANIMATABLE'},
        items=callbacks.get_active_shape_key_mesh_names
    ) # type: ignore
    solo_shape_key: bpy.props.BoolProperty(
        name="Solo Shape Key",
        description="If this is enabled, every time you sculpt/edit a shape key, it will set all other shape keys to 0 and the selected shape key to 1",
        default=False
    ) # type: ignore
    generate_neutral_shapes: bpy.props.BoolProperty(
        name="Generate Neutral Shapes",
        description="Use this to generate neutral shape keys that match the names in the DNA file. This is useful when you can't import the deltas because vert ids are not the same, or you just want to use neutral shapes as a starting point",
        default=False
    ) # type: ignore

    # ----- Output Properties -----
    output_folder_path: bpy.props.StringProperty(
        name="Output Folder",
        description="The root folder where the output files will be saved",
        subtype='DIR_PATH'
    ) # type: ignore
    output_method: bpy.props.EnumProperty(
        name='DNA Output Method',
        description='The output method to use when creating the dna file',
        default='calibrate',
        items=[
            ('calibrate', 'Calibrate', 'Uses the original dna file and calibrates the included bones and mesh changes into a new dna file. Use this method if your vert indices and bone names are the same as the original DNA. This is the recommended method', 'NONE', 0),
            ('overwrite', 'Overwrite', '(Experimental, and not fully functional yet) Uses the original dna file and overwrites the dna data based on the current mesh and armature data in the scene. Use this method if your vert indices and bone names are different from the original DNA. Only use this method when calibration method is not possible', 'ERROR', 1),
        ]
    ) # type: ignore
    output_format: bpy.props.EnumProperty(
        name='File Format',
        description='The file format to use when output the dna file. Either binary or json',
        default='binary',
        items=[
            ('json', 'JSON', 'Writes the dna file in a human readable json format. Use this method if you want to manually edit the dna file'),
            ('binary', 'Binary', 'Writes the dna file in a binary format. Use this method if you want to use the dna file with the rig logic system'),
        ]
    ) # type: ignore
    send2ue_settings_template: bpy.props.EnumProperty(
        name='Send to Unreal Settings Template',
        description='The output method to use when creating the dna file',
        options={'ANIMATABLE'},
        items=callbacks.get_send2ue_settings_templates
    ) # type: ignore
    unreal_copy_assets: bpy.props.BoolProperty(
        default=True,
        name='Copy Supporting Unreal Assets',
        description=(
            'Whether to copy the referenced unreal assets (Control Rig, Anim BP, Materials Instances, etc.) to the same folder as '
            'the face skeletal mesh asset if they dont already exist. This should be preferred, it is not a good idea to import on top '
            'of the original metahuman common assets, however if you have a custom setup with different asset references, you can disable this option'
        )
    ) # type: ignore
    unreal_content_folder: bpy.props.StringProperty(
        name='Content Folder',
        description='The content folder in your unreal project where the assets will be imported',
        set=callbacks.set_unreal_content_folder,
        get=callbacks.get_unreal_content_folder
    ) # type: ignore
    
    unreal_blueprint_asset_path: bpy.props.StringProperty(
        default='',
        name='Blueprint Asset',
        description=(
            'The asset path to the Metahuman Blueprint asset that the '
            'SkeletalMesh data will be bound to. If left empty, the blueprint will '
            'be created in the same folder as the SkeletalMesh asset'
        )
    ) # type: ignore
    auto_sync_spine_with_body: bpy.props.BoolProperty(
        default=True,
        name='Auto-Sync Head with Body',
        description=(
            'Whether to automatically sync the head spine bone positions with '
            'the body spine bone positions. This uses the blueprint asset path to '
            'find the body skeleton. This will modify the objects in your blender scene'
        )
    ) # type: ignore
    unreal_level_sequence_asset_path: bpy.props.StringProperty(
        default='',
        name='Level Sequence Asset',
        description=(
            'The asset path to the Level Sequence that the blueprint actor '
            'will be added too. If the level sequence does not exist, it will be'
            ' created. If left empty the blueprint will not be spawned into a level sequence'
        )
    ) # type: ignore
    unreal_face_control_rig_asset_path: bpy.props.StringProperty(
        default='/Game/MetaHumans/Common/Face/Face_ControlBoard_CtrlRig',
        name='Face Control Rig',
        description=(
            'The asset path to the Metahuman Face Board Control Rig asset that will '
            'drive the SkeletalMesh data'
        )
    ) # type: ignore
    unreal_face_anim_bp_asset_path: bpy.props.StringProperty(
        default='/Game/MetaHumans/Common/Face/Face_PostProcess_AnimBP',
        name='Face Post Process Animation Blueprint',
        description=(
            'The asset path to the Face Post Process Animation Blueprint asset that will '
            'drive the SkeletalMesh data'
        )
    ) # type: ignore


    unreal_material_slot_to_instance_mapping: bpy.props.CollectionProperty(type=MaterialSlotToInstance) # type: ignore
    unreal_material_slot_to_instance_mapping_active_index: bpy.props.IntProperty() # type: ignore

    # ----- Internal Properties -----
    shape_key_list: bpy.props.CollectionProperty(type=ShapeKeyData) # type: ignore
    shape_key_list_active_index: bpy.props.IntProperty() # type: ignore

    output_item_list: bpy.props.CollectionProperty(type=OutputData) # type: ignore
    output_item_active_index: bpy.props.IntProperty() # type: ignore
    calibrate_bones: bpy.props.BoolProperty(default=True) # type: ignore
    calibrate_meshes: bpy.props.BoolProperty(default=True) # type: ignore
    calibrate_shape_keys: bpy.props.BoolProperty(default=True) # type: ignore

    # this holds the rig logic references
    data = {}

    warning_messages = []
    
    def get_shape_key(self, mesh_index: int) -> bpy.types.Key | None:
        shape_key = self.data.get('shape_key', {}).get(mesh_index)
        try:
            if shape_key:
                shape_key.name
                return shape_key
        except ReferenceError:
            return None
    
    def get_shape_key_block(self, mesh_index: int, name: str) -> bpy.types.ShapeKey | None:
        cached_shape_key = self.get_shape_key(mesh_index)
        if cached_shape_key and cached_shape_key.key_blocks:
            return cached_shape_key.key_blocks.get(name)
        
        mesh_object = self.mesh_index_lookup.get(mesh_index)
        if mesh_object:
            self.data['shape_key'] = self.data.get('shape_key', {})
            for shape_key in bpy.data.shape_keys:
                if shape_key.user == mesh_object.data:
                    key_block = shape_key.key_blocks.get(name)
                    if key_block:
                        # store the shape key in the shape key property so we don't have to search for it again
                        self.data['shape_key'][mesh_index] = shape_key
                        return key_block

    @property
    def valid(self) -> bool: 
        dna_file_path = Path(bpy.path.abspath(self.dna_file_path))
        if not dna_file_path.exists():
            logger.warning(f'The DNA file path "{dna_file_path}" does not exist. The Rig Logic Instance {self.name} will not be initialized.')
            return False
        if not self.face_board:
            logger.warning(f'The Face board is not set. The Rig Logic Instance {self.name} will not be initialized.')
            return False
        return True
        
    @property
    def texture_masks_node(self) -> bpy.types.ShaderNodeGroup | None:
        # first check if the texture masks node is set
        texture_masks_node = self.data.get('texture_masks_node')
        if texture_masks_node is False:
            return None
        elif texture_masks_node is not None:
            return texture_masks_node
        else:
            node = callbacks.get_texture_logic_node(self.material)
            if node:
                self.data['texture_masks_node'] = node
                return self.data['texture_masks_node']
        
        self.data['texture_masks_node'] = False

    @property
    def initialized(self) -> bool:
        return bool(self.data.get('initialized'))
    
    @property
    def mesh_index_lookup(self) -> dict[int, bpy.types.Object]:
        if not self.dna_reader:
            return {}
        
        mesh_index_lookup = self.data.get('mesh_index_lookup', {})
        if mesh_index_lookup:
            return mesh_index_lookup
        
        for mesh_index in range(self.dna_reader.getMeshCount()):
            dna_mesh_name = self.dna_reader.getMeshName(mesh_index)
            mesh_object = bpy.data.objects.get(f'{self.name}_{dna_mesh_name}')
            if mesh_object:
                mesh_index_lookup[mesh_index] = mesh_object
        
        self.data['mesh_index_lookup'] = mesh_index_lookup
        return self.data['mesh_index_lookup'] # type: ignore
    
    @property
    def channel_name_to_index_lookup(self) -> dict[str, int]:
        if not self.dna_reader:
            return {}
        
        channel_name_to_index_lookup = self.data.get('channel_name_to_index_lookup', {})
        if channel_name_to_index_lookup:
            return channel_name_to_index_lookup
        
        for mesh_index in self.dna_reader.getMeshIndicesForLOD(0):
            mesh_name = self.dna_reader.getMeshName(mesh_index)
            for index in range(self.dna_reader.getBlendShapeTargetCount(mesh_index)):
                channel_index = self.dna_reader.getBlendShapeChannelIndex(mesh_index, index)
                shape_key_name = self.dna_reader.getBlendShapeChannelName(channel_index)
                channel_name_to_index_lookup[f'{mesh_name}__{shape_key_name}'] = channel_index
        
        self.data['channel_name_to_index_lookup'] = channel_name_to_index_lookup
        return self.data['channel_name_to_index_lookup'] # type: ignore

    @property
    def channel_index_to_mesh_index_lookup(self) -> dict[int, int]:
        if not self.dna_reader:
            return {}

        mesh_shape_key_index_lookup = self.data.get('mesh_shape_key_index_lookup', {})
        if mesh_shape_key_index_lookup:
            return mesh_shape_key_index_lookup
        
        # build a lookup dictionary of shape key index to mesh index
        for mesh_index in self.dna_reader.getMeshIndicesForLOD(0):
            for index in range(self.dna_reader.getBlendShapeTargetCount(mesh_index)):
                channel_index = self.dna_reader.getBlendShapeChannelIndex(mesh_index, index)
                mesh_shape_key_index_lookup[channel_index] = mesh_index
        self.data['mesh_shape_key_index_lookup'] = mesh_shape_key_index_lookup
        return mesh_shape_key_index_lookup
    
    @property
    def manager(self) -> 'riglogic.RigLogic':
        return self.data.get('manager')
    
    @property
    def instance(self) -> 'riglogic.RigInstance':
        return self.data.get('instance')
    
    @property
    def dna_reader(self) -> 'riglogic.BinaryStreamReader':
        return self.data.get('dna_reader') # type: ignore
    
    @property
    def shape_key_blocks(self) -> dict[int, list[bpy.types.ShapeKey]]:
        shape_key_blocks = self.data.get('shape_key_blocks')
        if shape_key_blocks is None:
            self.shape_key_list.clear()
            mesh_index = 0 # this is the head lod 0 mesh index
            shape_key_blocks = {}

            # Note: That lod 0 is the only lod that has shape keys
            failed_to_cache_count = 0
            for mesh_index in self.dna_reader.getMeshIndicesForLOD(0):
                mesh_object = self.mesh_index_lookup.get(mesh_index)
                if not mesh_object:
                    logger.warning(f'The mesh object for mesh index "{mesh_index}" was not found')
                    continue

                for target_index in range(self.dna_reader.getBlendShapeTargetCount(mesh_index)):
                    channel_index = self.dna_reader.getBlendShapeChannelIndex(mesh_index, target_index)
                    name = self.dna_reader.getBlendShapeChannelName(channel_index)
                    dna_mesh_name = mesh_object.name.replace(f'{self.name}_', '')
                    shape_key_block_name = f'{dna_mesh_name}__{name}'
                    shape_key_block = self.get_shape_key_block(mesh_index=mesh_index, name=shape_key_block_name)
                    if shape_key_block:    
                        # store the shape key block names in the shape key list as well
                        shape_key_item = self.shape_key_list.add()
                        shape_key_item.name = shape_key_block_name
                        
                        # store the shape key block in a list on the dictionary
                        key_block_list = shape_key_blocks.get(channel_index, [])
                        key_block_list.append(shape_key_block)
                        shape_key_blocks[channel_index] = key_block_list

                    elif len(shape_key_block_name) <= 63:
                        failed_to_cache_count += 1
                
            if failed_to_cache_count > 0:
                logger.warning(
                    f'Rig Logic Instance {self.name} did not cache {failed_to_cache_count} shape key blocks, '
                    'because they are not in the scene. However they are in the DNA file. Import all shape keys to cache them.'
                )
            
            self.data['shape_key_blocks'] = shape_key_blocks

        return self.data['shape_key_blocks']
    
    @property
    def rest_pose(self) -> dict[str, tuple[Vector, Euler, Vector, Matrix]]:
        rest_pose = self.data.get('rest_pose', {})
        if rest_pose:
            return rest_pose
        
        # make sure the rig bone are using the correct rotation mode
        if self.head_rig and self.head_rig.pose:
            for pose_bone in self.head_rig.pose.bones:
                pose_bone.rotation_mode = "XYZ"
                # save the rest pose and their parent space matrix so we don't have to calculate it again
                try:
                    rest_pose[pose_bone.name] = utilities.get_bone_rest_transformations(pose_bone.bone)
                except ValueError:
                    return {}
        
        # save the rest pose so we don't have to calculate it again
        self.data['rest_pose'] = rest_pose
        # return a copy so the original rest position is not modified
        return self.data['rest_pose']

    def initialize(self):
        if not self.valid:
            return
        
        from .bindings import riglogic
        from .dna_io import get_dna_reader
        # set the dna reader
        self.data['dna_reader'] = get_dna_reader(Path(bpy.path.abspath(self.dna_file_path)).absolute())

        # make sure the rig bones are using the correct rotation mode
        if self.head_rig and self.head_rig.pose:
            for pose_bone in self.head_rig.pose.bones:
                if not pose_bone.name.startswith('FACIAL_'):
                    pose_bone.rotation_mode = "XYZ"

        # set the rig logic manager and instance
        self.data['manager'] = riglogic.RigLogic.create(
            reader=self.data['dna_reader'],
            config=riglogic.Configuration()
        )
        self.data['instance'] = riglogic.RigInstance.create(
            rigLogic=self.data['manager'], 
            memRes=None
        )

        # calling theses properties will cache their values
        self.texture_masks_node
        self.mesh_index_lookup
        self.channel_name_to_index_lookup
        self.channel_index_to_mesh_index_lookup
        self.shape_key_blocks
        self.rest_pose
        self.data['initialized'] = True

    def destroy(self):
        # clears these data items from the dictionary, this frees them up to be garbage collected
        self.data.clear()        
        self.data['initialized'] = False


    def update_gui_control_values(self, override_values: dict[str, dict[str, float]] | None = None):
        # skip if the face board is not set
        if not self.face_board or not self.dna_reader:
            return
        
        missing_gui_controls = []
        
        for index in range(self.dna_reader.getGUIControlCount()):
            full_name = self.dna_reader.getGUIControlName(index)
            control_name, axis = full_name.split('.')
            axis = axis.rsplit('t',-1)[-1].lower()
            if self.face_board:
                # override the values can be provided to update values based on them vs current face board bone locations 
                # This can be used for baking the values to an action
                if override_values:
                    value = override_values.get(control_name, {}).get(axis)
                    if value is not None:
                        self.instance.setGUIControl(index, value)
                else:
                    pose_bone = self.face_board.pose.bones.get(control_name)
                    if pose_bone:
                        value = getattr(pose_bone.location, axis)
                        self.instance.setGUIControl(index, value)
                    else:
                        missing_gui_controls.append(control_name)

        if missing_gui_controls and not self.data.get('logged_missing_gui_controls'):
            logger.warning(f'The following GUI controls are missing on "{self.face_board.name}":\n{pformat(missing_gui_controls)}.')
            logger.warning(f'You are not listening to {len(missing_gui_controls)} GUI controls')
            logger.warning('This is most likely due to the DNA file being an older version then what the face board currently supports.')
            logger.warning('Using a new .dna file created from the latest version of MetaHuman Creator will probably resolve this.')
            self.data['logged_missing_gui_controls'] = True

        # calculate the changes
        self.manager.mapGUIToRawControls(self.instance)
        self.manager.calculate(self.instance)

    def solo_shape_key_value(self, shape_key: bpy.types.ShapeKey):
        # skip if the head mesh is not set
        if not self.head_mesh or not self.dna_reader:
            return
        
        # skip if there are no shape keys
        if len(bpy.data.shape_keys) == 0:
            return
        
        # make all other shape keys 0.0
        for index, _ in enumerate(self.instance.getBlendShapeOutputs()):
            for _shape_key in self.shape_key_blocks.get(index, []):
                if _shape_key and _shape_key != shape_key:
                    _shape_key.value = 0.0

        # set the provided shape key value to 1.0
        shape_key.value = 1.0

    def update_shape_keys(self) -> list[tuple[bpy.types.ShapeKey, float]]:
        # skip if the head mesh is not set
        if not self.head_mesh or not self.dna_reader:
            return []
        
        # skip if there are no shape keys
        if len(bpy.data.shape_keys) == 0:
            return []
        
        missing_shape_keys = []
        shape_key_values = []
    
        # update blend shapes
        for index, value in enumerate(self.instance.getBlendShapeOutputs()):  
            for shape_key in self.shape_key_blocks.get(index, []):
                if shape_key:
                    shape_key.value = value
                    shape_key_values.append((shape_key, value))
                else:
                    missing_shape_keys.append(index)

        if missing_shape_keys and not self.data.get('logged_missing_shape_keys'):
            name_lookup = {v:k for k,v in self.channel_name_to_index_lookup.items()}
            missing_data = {}
            # group the missing shape keys by mesh object
            for index in missing_shape_keys:
                missing_name = name_lookup[index]
                mesh_index = self.channel_index_to_mesh_index_lookup[index]
                mesh_object = self.mesh_index_lookup[mesh_index]
                if len(missing_name) > 63:
                    # skip warning the user about any missing shape keys names being too long.

                    # Currently, Blender has a limit of 63 characters for shape key names.
                    # This is something that the user could might be able to overcome by changing blender 
                    # source and recompiling. However, this is not something that we can fix in the addon.

                    # Because this limitation there are 42 missing shape keys from the MetaHuman creator DNA files 
                    # that can't be imported because their names are too long. However these are extreme 
                    # combinations and for most people this will not be an issue.
                    continue

                missing_data[mesh_object.name] = missing_data.get(mesh_object.name, [])
                missing_data[mesh_object.name].append(missing_name)
            
            for mesh_name, missing_names in missing_data.items():
                logger.warning(f'The following shape key blocks are missing on "{mesh_name}":\n{pformat(missing_names)}.')

            if len(missing_data.keys()) > 0:
                logger.warning(f'A total of {len(missing_data.keys())} shape key blocks are not being updated by Rig Logic.')
            
            self.data['logged_missing_shape_keys'] = True

        return shape_key_values

    def update_texture_masks(self) -> list[tuple[str, float]]:
        # skip if the material is not set
        if not self.material or not self.dna_reader:
            return []

        # if the texture masks node is not set, we can't update the texture masks
        if not self.texture_masks_node:
            logger.warning(f'The texture masks node was not found on the material "{self.material.name}"')
            return []
        
        texture_mask_values = []

        # update texture masks values
        for index, value in enumerate(self.instance.getAnimatedMapOutputs()):
            name = self.dna_reader.getAnimatedMapName(index) 
            slider_name = f"{name.split('.')[-1]}_msk"
            mask_slider = self.texture_masks_node.inputs.get(slider_name)
            if mask_slider:
                mask_slider.default_value = value # type: ignore
                texture_mask_values.append((slider_name, value))
            else:
                logger.warning(f'The texture mask slider "{slider_name}" was not found on the material "{self.material.name}"')

        return texture_mask_values

    def update_bone_transforms(self):
        # skip if the head rig is not set
        if not self.head_rig or not self.dna_reader:
            return
        
        # skip if the rest pose is not initialized
        # https://github.com/poly-hammer/meta-human-dna-addon/issues/58
        if not self.rest_pose:
            return
        
        joint_output = self.instance.getJointOutputs()
        raw_joint_output = self.instance.getRawJointOutputs()
        # update joint transforms
        for index in range(joint_output.size):
            if not self.dna_reader:
                return

            # get the bone 
            name = self.dna_reader.getJointName(index)

            # only update facial bones
            if not name.startswith('FACIAL_'):
                continue

            pose_bone = self.head_rig.pose.bones.get(name)
            if pose_bone:
                # get the rest pose values that we saved during initialization
                rest_location, rest_rotation, rest_scale, rest_to_parent_matrix = self.rest_pose[pose_bone.name]

                # get the values
                matrix_index = (index + 1) * 9
                values = raw_joint_output[(index * 9):matrix_index]

                # extract the delta values
                location_delta = Vector([value * 0.01 for value in values[:3]])
                rotation_delta = Euler([math.radians(value) for value in values[3:6]])
                scale_delta = Vector(values[6:9])

                # update the transformations using the rest pose and the delta values
                # we need to copy the vectors so we don't modify the original rest pose
                location = rest_location.copy() + location_delta
                rotation = rest_rotation.copy()
                rotation.x += rotation_delta.x
                rotation.y += rotation_delta.y
                rotation.z += rotation_delta.z
                scale = rest_scale.copy()
                scale.x += scale_delta.x
                scale.y += scale_delta.y
                scale.z += scale_delta.z

                # update the bone matrix
                modified_matrix = Matrix.LocRotScale(location, rotation, scale)
                pose_bone.matrix_basis = rest_to_parent_matrix.inverted() @ modified_matrix

                # if the bone is not a leaf bone, we need to update the rotation again
                if pose_bone.children:
                    pose_bone.rotation_euler = rotation_delta
            else:
                logger.warning(f'The bone "{name}" was not found on "{self.head_rig.name}". Rig Logic will not update the bone.')

    def evaluate(self):
        # this condition prevents constant evaluation
        if bpy.context.window_manager.meta_human_dna.evaluate_dependency_graph: # type: ignore
            if not self.initialized:
                self.initialize()

            if not self.initialized:
                logger.error(f'The Rig Logic Instance {self.name} could not be initialized.')
                return
            
            # turn off the dependency graph evaluation so we can update the controls without triggering an update
            bpy.context.window_manager.meta_human_dna.evaluate_dependency_graph = False # type: ignore
            
            self.update_gui_control_values()

            # apply the changes
            if self.evaluate_bones: 
                self.update_bone_transforms()
            if self.evaluate_shape_keys:
                self.update_shape_keys()
            if self.evaluate_texture_masks:
                self.update_texture_masks()

            # turn on the dependency graph evaluation back on
            bpy.context.window_manager.meta_human_dna.evaluate_dependency_graph = True # type: ignore
