import os
import bpy
import math
import queue
import shutil
import logging
from mathutils import Vector, Matrix
from pathlib import Path
from datetime import datetime, timedelta
from .ui import importer, callbacks
from . import utilities
from .dna_io import (
    DNACalibrator, 
    DNAExporter,
    get_dna_reader,
    get_dna_writer
)
from .properties import MetahumanDnaImportProperties, BlendFileMetaHumanCollection
from .components import (
    MetaHumanComponentHead,
    MetaHumanComponentBody,
    get_meta_human_component
)
from . import constants
from .constants import (
    SEND2UE_FACE_SETTINGS,
    ToolInfo,
    NUMBER_OF_HEAD_LODS,
    DEFAULT_UV_TOLERANCE,
    HEAD_TEXTURE_LOGIC_NODE_NAME,
    HEAD_TEXTURE_LOGIC_NODE_LABEL,
    SHAPE_KEY_BASIS_NAME,
    FACE_BOARD_NAME,
    RBF_SOLVER_POSTFIX
)

logger = logging.getLogger(__name__)

class GenericUIListOperator:
    """Mix-in class containing functionality shared by operators
    that deal with managing Blender list entries."""
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    active_index: bpy.props.IntProperty() # type: ignore

class GenericProgressQueueOperator(bpy.types.Operator):
    """
    Mix-in class containing functionality shared by operators that have a progress queue.
    """
    _timer = None
    _commands_queue = queue.Queue()
    _commands_queue_size = 0

    def modal(self, context, event):
        if event.type == 'ESC':
            return self.finish(context)

        if event.type == 'TIMER':
            [a.tag_redraw() for a in context.screen.areas] # type: ignore
            if self._commands_queue.empty():
                return self.finish(context)
            
            index, mesh_index, description, kwargs_callback, callback = self._commands_queue.get() # type: ignore
            new_size = self._commands_queue.qsize()

            # calculate the kwargs
            kwargs = kwargs_callback(index, mesh_index)
            # inject the kwargs into the description
            description = description.format(**kwargs)
            context.window_manager.meta_human_dna.progress = (self._commands_queue_size-new_size)/self._commands_queue_size # type: ignore
            context.window_manager.meta_human_dna.progress_description = description # type: ignore
            callback(**kwargs)
                
        return {'PASS_THROUGH'}

    def execute(self, context):
        if not self.validate(context):
            return {'CANCELLED'}
        
        self._timer = context.window_manager.event_timer_add(0.01, window=context.window) # type: ignore
        context.window_manager.modal_handler_add(self) # type: ignore
        head = utilities.get_active_head()
        if head:
            context.window_manager.meta_human_dna.progress = 0 # type: ignore
            context.window_manager.meta_human_dna.progress_description = '' # type: ignore
            self._commands_queue = queue.Queue()
            self.set_commands_queue(context, head, self._commands_queue)
            self._commands_queue_size = self._commands_queue.qsize()
            return {'RUNNING_MODAL'}
        return {'CANCELLED'}


    def finish(self, context):
        context.window_manager.event_timer_remove(self._timer) # type: ignore
        context.window_manager.meta_human_dna.progress = 1 # type: ignore
        # re-initialize the rig logic instance so the shape key blocks collection is updated for the UI
        instance = callbacks.get_active_rig_logic()
        if instance:
            instance.data.clear()
            instance.initialize()
        return {'FINISHED'}
    

    def validate(self, context) -> bool:
        return True
    
    def set_commands_queue(
            self, 
            context, 
            component: MetaHumanComponentHead | MetaHumanComponentBody,
            commands_queue: queue.Queue
        ):
        pass   


class AppendOrLinkMetaHuman(bpy.types.Operator, importer.LinkAppendMetaHumanImportHelper):
    """Append or link a MetaHuman from a .blend file. The .blend file must contain a collection with all data related to the MetaHuman asset."""
    bl_idname = "meta_human_dna.append_or_link_metahuman"
    bl_label = "Import"
    filename_ext = ".blend"

    filter_glob: bpy.props.StringProperty(
        default="*.blend",
        options={"HIDDEN"},
        subtype="FILE_PATH",
    ) # type: ignore

    relative_path: bpy.props.BoolProperty(default=True) # type: ignore
    previous_file_path: bpy.props.StringProperty(default="") # type: ignore
    operation_type: bpy.props.EnumProperty(
        items=[
            ('APPEND', "Append", "Append the selected MetaHuman"),
            ('LINK', "Link", "Link the selected MetaHuman"),
        ],
        default='APPEND'
    ) # type: ignore
    meta_human_list: bpy.props.CollectionProperty(type=BlendFileMetaHumanCollection) # type: ignore

    def execute(self, context):
        if not self.filepath: # type: ignore
            self.report({'ERROR'}, 'You must select a .blend file')
            return {'CANCELLED'}
        
        if not Path(bpy.path.abspath(self.filepath)).exists(): # type: ignore
            self.report({'ERROR'}, f'File not found: {self.filepath}') # type: ignore
            return {'CANCELLED'}

        if bpy.data.filepath == self.filepath: # type: ignore
            self.report({'ERROR'}, 'You cannot import a MetaHuman from the current .blend file')
            return {'CANCELLED'}


        # track the current control objects
        current_control_objects = []
        for instance in context.scene.meta_human_dna.rig_logic_instance_list: # type: ignore
            if instance.face_board: 
                for pose_bone in instance.face_board.pose.bones:
                    current_control_objects.append(pose_bone.custom_shape)
                
        collection_names = []
        with bpy.data.libraries.load(
            filepath=self.filepath, # type: ignore
            link=self.operation_type=='LINK',
            relative=self.relative_path) as (data_from, data_to): # type: ignore
            
            # we only append/link the collections that the user has selected
            for item in self.meta_human_list:
                if item.include:
                    for collection_name in data_from.collections:
                        if collection_name == item.name:
                            data_to.collections.append(collection_name)
                            collection_names.append(collection_name)

        # extract the rig instance data from the blend file
        data, error = utilities.extract_rig_instance_data_from_blend_file(Path(bpy.path.abspath(self.filepath))) # type: ignore
        if error:
            logger.error(error)
            self.report({'ERROR'}, f'Failed to extract rig instance data from blend file: {error}')
            return {'CANCELLED'}

        # link the collections to the scene
        for collection_name in collection_names:
            collection = bpy.data.collections.get(collection_name)
            if collection:
                bpy.context.scene.collection.children.link(collection) # type: ignore

            # delete the face board and its control object shapes if they exist
            face_board = bpy.data.objects.get(f'{collection_name}_{FACE_BOARD_NAME}')
            if face_board:
                for pose_bone in face_board.pose.bones: # type: ignore
                    if pose_bone.custom_shape and pose_bone.custom_shape not in current_control_objects:
                        control_object = pose_bone.custom_shape
                        pose_bone.custom_shape = None
                        bpy.data.objects.remove(control_object, do_unlink=True)
                # remove the face board object
                bpy.data.objects.remove(face_board, do_unlink=True)

            # Extract the rig instance data from the .blend file and set them on the new rig instance
            instance = utilities.add_rig_instance(name=collection_name)
            instance.head_dna_file_path = data[collection_name]['head_dna_file_path']
            instance.head_mesh = bpy.data.objects.get(data[collection_name]['head_mesh'] or '')
            instance.head_rig = bpy.data.objects.get(data[collection_name]['head_rig'] or '')
            instance.head_material = bpy.data.materials.get(data[collection_name]['head_material'] or '')
            instance.body_mesh = bpy.data.objects.get(data[collection_name]['body_mesh'] or '')
            instance.body_rig = bpy.data.objects.get(data[collection_name]['body_rig'] or '')
            instance.body_material = bpy.data.materials.get(data[collection_name]['body_material'] or '')
            instance.body_dna_file_path = data[collection_name]['body_dna_file_path']
            instance.output_folder_path = data[collection_name]['output_folder_path']

            # duplicate the face board if there is one already in the scene
            if any(i.face_board for i in context.scene.meta_human_dna.rig_logic_instance_list): # type: ignore
                instance.face_board = utilities.duplicate_face_board(name=collection_name)
            # otherwise import it
            else:
                instance.face_board = utilities.import_face_board(name=collection_name)
            
            # position the face board next to the head mesh
            if instance.face_board:
                utilities.position_face_board(
                    head_mesh_object=instance.head_mesh, 
                    head_rig_object=instance.head_rig, 
                    face_board_object=instance.face_board
                )
                if self.operation_type != 'LINK':
                    utilities.move_to_collection(
                        scene_objects=[instance.face_board],
                        collection_name=collection_name,
                        exclusively=True
                    )

                utilities.constrain_face_board_to_head(
                    face_board_object=instance.face_board,
                    head_rig_object=instance.head_rig,
                    body_rig_object=instance.body_rig,
                    bone_name='CTRL_faceGUI'
                )
                utilities.constrain_face_board_to_head(
                    face_board_object=instance.face_board,
                    head_rig_object=instance.head_rig,
                    body_rig_object=instance.body_rig,
                    bone_name='CTRL_C_eyesAim'
                )

        return {'FINISHED'}
    

class ImportAnimationBase(bpy.types.Operator):
    filename_ext = ".fbx"

    filter_glob: bpy.props.StringProperty(
        default="*.fbx",
        options={"HIDDEN"},
        subtype="FILE_PATH",
    ) # type: ignore

    round_sub_frames: bpy.props.BoolProperty(
        name="Round Sub Frames",
        default=True,
        description=(
            "Whether to round sub frames when importing the animation. This "
            "ensure all keyframes are on whole frames with integer values"
        )
    ) # type: ignore

    match_frame_rate: bpy.props.BoolProperty(
        name="Match Frame Rate",
        default=True,
        description=(
            "Whether to match the frame rate when importing the animation. This "
            "will scale the animation curves to match the current scene frame rate"
        )
    ) # type: ignore

    prefix_instance_name: bpy.props.BoolProperty(
        name="Prefix Instance Name",
        default=True,
        description="Prefixes the baked action name with the rig instance name. This helps avoid name collisions with other action names when multiple are in the same scene."
    ) # type: ignore

    prefix_component_name: bpy.props.BoolProperty(
        name="Prefix Component Name",
        default=True,
        description="Prefixes the baked action name with the component name. This helps avoid name collisions with other components that might have the same action names."
    ) # type: ignore

    @property
    def settings_title(self) -> str:
        return "Animation Import Settings:"


class ImportFaceBoardAnimation(ImportAnimationBase, importer.ImportAnimation):
    """Import an animation for the metahuman face board exported from an Unreal Engine Level Sequence"""
    bl_idname = "meta_human_dna.import_face_board_animation"
    bl_label = "Import"

    @property
    def settings_title(self) -> str:
        return "Face Board Animation Import Settings:"

    def execute(self, context):
        logger.info(f'Importing animation {self.filepath}')  # type: ignore
        head = utilities.get_active_head()
        if head:
            head.import_action(
                Path(self.filepath), # type: ignore
                is_face_board=True,
                round_sub_frames=self.round_sub_frames,
                match_frame_rate=self.match_frame_rate,
                prefix_instance_name=self.prefix_instance_name,
                prefix_component_name=self.prefix_component_name
            )
        return {'FINISHED'}
    

class ImportComponentAnimation(ImportAnimationBase, importer.ImportAnimation):
    """Import an animation for the selected metahuman component that has been exported from an Unreal Engine"""
    bl_idname = "meta_human_dna.import_component_animation"
    bl_label = "Import"

    component_type: bpy.props.StringProperty(default="body") # type: ignore

    @property
    def settings_title(self) -> str:
        return f"{self.component_type.capitalize()} Animation Import Settings:"

    def execute(self, context):
        file_path = Path(bpy.path.abspath(self.filepath)) # type: ignore
        logger.info(f'Importing animation {file_path}')  # type: ignore
        if self.component_type == 'head':
            head = utilities.get_active_head()
            if head:
                head.import_action(
                    file_path, 
                    is_face_board=False,
                    round_sub_frames=self.round_sub_frames,
                    match_frame_rate=self.match_frame_rate,
                    prefix_instance_name=self.prefix_instance_name,
                    prefix_component_name=self.prefix_component_name
                )  # type: ignore
            
        elif self.component_type == 'body':
            body = utilities.get_active_body()
            if body:
                body.import_action(
                    file_path, 
                    round_sub_frames=self.round_sub_frames,
                    match_frame_rate=self.match_frame_rate,
                    prefix_instance_name=self.prefix_instance_name,
                    prefix_component_name=self.prefix_component_name
                )  # type: ignore

        self.report({'INFO'}, f'Imported {self.component_type} animation from {file_path}')  # type: ignore

        return {'FINISHED'}


class BakeAnimationBase(bpy.types.Operator):
    action_name: bpy.props.StringProperty(
        name="Action Name",
        default="baked_action",
        description="The name of the action that will be created to store the baked animation data"
    ) # type: ignore

    prefix_instance_name: bpy.props.BoolProperty(
        name="Prefix Instance Name",
        default=True,
        description="Prefixes the baked action name with the rig instance name. This helps avoid name collisions with other action names when multiple are in the same scene."
    ) # type: ignore
    prefix_component_name: bpy.props.BoolProperty(
        name="Prefix Component Name",
        default=True,
        description="Prefixes the baked action name with the component name. This helps avoid name collisions with other components that might have the same action names."
    ) # type: ignore

    replace_action: bpy.props.BoolProperty(
        name="Replace Action",
        default=False,
        description="Replaces the existing action with the baked action"
    ) # type: ignore

    start_frame: bpy.props.IntProperty(
        name="Start Frame",
        default=1,
        min=1,
        get=callbacks.get_bake_start_frame,
        set=callbacks.set_bake_start_frame,
        description="The frame to start baking the animation on"
    ) # type: ignore

    end_frame: bpy.props.IntProperty(
        name="End Frame",
        default=250,
        min=1,
        get=callbacks.get_bake_end_frame,
        set=callbacks.set_bake_end_frame,
        description="The frame to end baking the animation on"
    ) # type: ignore

    step: bpy.props.IntProperty(
        name="Step",
        default=1,
        min=1,
        description="The frame step to bake the animation on. Essentially add a keyframe every nth frame"
    ) # type: ignore

    masks: bpy.props.BoolProperty(
        name="Masks",
        default=True,
        description="Bakes the values of the wrinkle map masks over time"
    ) # type: ignore

    shape_keys: bpy.props.BoolProperty(
        name="Shape Keys",
        default=True,
        description="Bakes the values of the shape keys over time"
    ) # type: ignore

    clean_curves: bpy.props.BoolProperty(
        name="Clean Curves",
        default=False,
        description="Clean Curves, After baking curves, remove redundant keys"
    ) # type: ignore

    bone_location: bpy.props.BoolProperty(
        name="Bone Location",
        default=True,
        description="Bakes the location of the bones"
    ) # type: ignore
    bone_rotation: bpy.props.BoolProperty(
        name="Bone Rotation",
        default=True,
        description="Bakes the rotation of the bones"
    ) # type: ignore
    bone_scale: bpy.props.BoolProperty(
        name="Bone Scale",
        default=True,
        description="Bakes the scale of the bones"
    ) # type: ignore

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog( # type: ignore
            self, 
            title=self.dialog_title,
            width=250
        )

    @property
    def dialog_title(self) -> str:
        return self.bl_label
    
    def draw_extra_settings(self, layout, context):
        pass

    def draw(self, context):
        if not self.layout:
            return
        
        row = self.layout.row()
        row.label(text="Naming:")
        row = self.layout.row()
        row.prop(self, 'action_name', text='')
        row = self.layout.row()
        row.prop(self, 'prefix_instance_name')
        row = self.layout.row()
        row.prop(self, 'prefix_component_name')
        row = self.layout.row()
        row.label(text="Settings:")
        row = self.layout.row()
        row.prop(self, 'start_frame')
        row.prop(self, 'end_frame')
        row = self.layout.row()
        row.prop(self, 'step')
        row = self.layout.row()
        row.prop(self, 'replace_action')
        row = self.layout.row()
        row.prop(self, 'shape_keys')
        row = self.layout.row()
        row.prop(self, 'masks')
        row = self.layout.row()
        self.draw_extra_settings(self.layout, context)
        row = self.layout.row()
        row.label(text="Bone Transforms:")
        row = self.layout.row()
        row.prop(self, 'bone_location', text="Location")
        row = self.layout.row()
        row.prop(self, 'bone_rotation', text="Rotation")
        row = self.layout.row()
        row.prop(self, 'bone_scale', text="Scale")

    
class BakeFaceBoardAnimation(BakeAnimationBase):
    """Bakes the active face board action to the pose bones, shape key values, and texture logic mask values. Useful for rendering, simulations, etc. where rig logic evaluation is not available"""
    bl_idname = "meta_human_dna.bake_face_board_animation"
    bl_label = "Bake Face Board Animation"

    def execute(self, context):
        if self.start_frame > self.end_frame:
            self.report({'ERROR'}, 'The start frame must be less than the end frame')
            return {'CANCELLED'}

        instance = callbacks.get_active_rig_logic()
        if instance and instance.head_rig:
            channel_types = set()
            if self.bone_location:
                channel_types.add('LOCATION')
            if self.bone_rotation:
                channel_types.add('ROTATION')
            if self.bone_scale:
                channel_types.add('SCALE')

            action_name = utilities.get_action_name(
                instance=instance,
                action_name=self.action_name,
                component='head',
                prefix_component_name=self.prefix_component_name,
                prefix_instance_name=self.prefix_instance_name,
            )

            utilities.bake_face_board_to_action(
                instance=instance,
                armature_object=instance.head_rig,
                action_name=action_name,
                replace_action=self.replace_action,
                start_frame=self.start_frame, # type: ignore
                end_frame=self.end_frame, # type: ignore
                step=self.step,
                channel_types=channel_types,
                clean_curves=self.clean_curves,
                masks=self.masks,
                shape_keys=self.shape_keys   
            )
        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        instance = callbacks.get_active_rig_logic()
        if not instance:
            return False
        if not instance.head_rig:
            return False
        if not instance.face_board:
            return False
        if not instance.face_board.animation_data:
            return False
        if not instance.face_board.animation_data.action:
            return False
        return True
    

class BakeComponentAnimation(BakeAnimationBase):
    """Bakes the active component action. This takes into account how the driver pose bones effect the rbf driven bones, shape key values, and texture logic mask values. Useful for rendering, simulations, etc. where rig logic evaluation is not available"""
    bl_idname = "meta_human_dna.bake_component_animation"
    bl_label = "Bake Component Animation"

    component_type: bpy.props.StringProperty(
        default="body",
        options={"HIDDEN"},
        subtype="FILE_PATH",
    ) # type: ignore

    driver_bones: bpy.props.BoolProperty(
        name="Driver Bones",
        default=True,
        description="Bakes the values of the driver bones over time"
    ) # type: ignore
    driven_bones: bpy.props.BoolProperty(
        name="Driven Bones",
        default=True,
        description="Bakes the values of the RBF driven bones over time"
    ) # type: ignore
    twist_bones: bpy.props.BoolProperty(
        name="Twist Bones",
        default=True,
        description="Bakes the values of the twist bones over time"
    ) # type: ignore
    swing_bones: bpy.props.BoolProperty(
        name="Swing Bones",
        default=True,
        description="Bakes the values of the swing bones over time"
    ) # type: ignore
    other_bones: bpy.props.BoolProperty(
        name="Other Bones",
        default=True,
        description="Bakes the values of other bones on the rig that are not explicitly categorized as driver, driven, twist, or swing bones"
    ) # type: ignore

    def execute(self, context):
        if self.start_frame > self.end_frame:
            self.report({'ERROR'}, 'The start frame must be less than the end frame')
            return {'CANCELLED'}

        instance = callbacks.get_active_rig_logic()
        if instance and instance.body_rig and self.component_type == 'body':
            channel_types = set()
            if self.bone_location:
                channel_types.add('LOCATION')
            if self.bone_rotation:
                channel_types.add('ROTATION')
            if self.bone_scale:
                channel_types.add('SCALE')

            action_name = utilities.get_action_name(
                instance=instance,
                action_name=self.action_name,
                component=self.component_type,
                prefix_component_name=self.prefix_component_name,
                prefix_instance_name=self.prefix_instance_name,
            )

            utilities.bake_body_to_action(
                instance=instance,
                armature_object=instance.body_rig,
                action_name=action_name,
                replace_action=self.replace_action,
                start_frame=self.start_frame, # type: ignore
                end_frame=self.end_frame, # type: ignore
                step=self.step,
                channel_types=channel_types,
                clean_curves=self.clean_curves,
                masks=self.masks,
                shape_keys=self.shape_keys, 
                driver_bones=self.driver_bones,
                driven_bones=self.driven_bones,
                twist_bones=self.twist_bones,
                swing_bones=self.swing_bones,
                other_bones=self.other_bones
            )
        return {'FINISHED'}
    
    @property
    def dialog_title(self) -> str:
        return f'Bake {self.component_type.capitalize()} Animation'
    
    def draw_extra_settings(self, layout, context):
        if self.component_type == 'body':
            row = layout.row()
            row.label(text="Bone Types:")
            row = layout.row()
            row.prop(self, 'driver_bones')
            row = layout.row()
            row.prop(self, 'driven_bones')
            row = layout.row()
            row.prop(self, 'twist_bones')
            row = layout.row()
            row.prop(self, 'swing_bones')
            row = layout.row()
            row.prop(self, 'other_bones')
    
    @classmethod
    def poll(cls, context):
        instance = callbacks.get_active_rig_logic()

        if not instance:
            return False
        
        if context.window_manager.meta_human_dna.current_component_type == 'body': # type: ignore
            if not instance.body_rig:
                return False
            if not instance.body_rig.animation_data:
                return False
            if not instance.body_rig.animation_data.action:
                return False
            return True
        
        return False


class ImportMetahumanDna(bpy.types.Operator, importer.ImportAsset, MetahumanDnaImportProperties):
    """Import a metahuman head from a DNA file"""
    bl_idname = "meta_human_dna.import_dna"
    bl_label = "Import DNA"
    filename_ext = ".dna"

    filter_glob: bpy.props.StringProperty(
        default="*.dna",
        options={"HIDDEN"},
        subtype="FILE_PATH",
    ) # type: ignore

    def execute(self, context):
        window_manager_properties = bpy.context.window_manager.meta_human_dna  # type: ignore
        # we define the properties initially on the operator so has preset
        # transfer the settings from the operator onto the window properties, so they are globally accessible
        for key in self.__annotations__.keys():
            if hasattr(MetahumanDnaImportProperties, key):
                value = getattr(self.properties, key)
                setattr(bpy.context.window_manager.meta_human_dna, key, value) # type: ignore

        file_path = Path(bpy.path.abspath(self.filepath)) # type: ignore
        if not file_path.exists():
            self.report({'ERROR'}, f'File not found: {file_path}')
            return {'CANCELLED'}
        if not file_path.is_file():
            self.report({'ERROR'}, f'"{file_path}" is a folder. Please select a DNA file.')
            return {'CANCELLED'}
        if file_path.suffix not in ['.dna']:
            self.report({'ERROR'}, f'The file "{file_path}" is not a DNA file')
            return {'CANCELLED'}
        if round(context.scene.unit_settings.scale_length, 2) != 1.0: # type: ignore
            self.report({'ERROR'}, 'The scene unit scale must be set to 1.0')
            return {'CANCELLED'}

        # we don't want to evaluate the dependency graph while importing the DNA
        window_manager_properties.evaluate_dependency_graph = False
        component = get_meta_human_component(
            file_path=file_path,
            properties=self.properties # type: ignore
        )
        # if the component is a head, we import the body first if the user has selected the option
        body_file = file_path.parent / 'body.dna'
        if self.properties.include_body and component.component_type == 'head' and body_file.exists(): # type: ignore
            body_component = get_meta_human_component(
                file_path=body_file,
                properties=self.properties, # type: ignore
                rig_logic_instance=component.rig_logic_instance
            )
            valid, message = body_component.ingest()
            logger.info(f'Finished importing "{body_file}"')
            if not valid:
                self.report({'ERROR'}, message)
                return {'CANCELLED'}
            else:
                self.report({'INFO'}, message)

        # now we can import the chosen .dna file
        valid, message = component.ingest()
        logger.info(f'Finished importing "{self.filepath}"') # type: ignore
        if not valid:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
        else:
            self.report({'INFO'}, message)

        # populate the output items based on what was imported
        callbacks.update_head_output_items(None, bpy.context)
        # now we can evaluate the dependency graph again
        window_manager_properties.evaluate_dependency_graph = True
        bpy.ops.meta_human_dna.force_evaluate() # type: ignore

        bpy.ops.meta_human_dna.metrics_collection_consent('INVOKE_DEFAULT') # type: ignore

        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        return utilities.dependencies_are_valid()
    
class DNA_FH_import_dna(bpy.types.FileHandler):
    bl_idname = "DNA_FH_import_dna"
    bl_label = "File handler for .dna files"
    bl_import_operator = "meta_human_dna.import_dna"
    bl_file_extensions = ".dna"

    @classmethod
    def poll_drop(cls, context):
        if not utilities.dependencies_are_valid():
            return False

        return (
            context.region and context.region.type == 'WINDOW' and # type: ignore
            context.area and context.area.ui_type == 'VIEW_3D' # type: ignore
        )
    

class ConvertSelectedToDna(bpy.types.Operator, MetahumanDnaImportProperties):
    """Converts the selected mesh object to a valid mesh that matches the provided base DNA file"""
    bl_idname = "meta_human_dna.convert_selected_to_dna"
    bl_label = "Convert Selected to DNA"

    new_name: bpy.props.StringProperty(
        name="Name", 
        default="",
        get=callbacks.get_copied_rig_logic_instance_name,
        set=callbacks.set_copied_rig_logic_instance_name
    ) # type: ignore
    constrain_head_to_body: bpy.props.BoolProperty(
        name="Constrain Head to Body",
        default=True,
        description="If enabled, the head will be constrained to the body (if available) during the conversion process."
    ) # type: ignore
    validate_uvs: bpy.props.BoolProperty(
        name="Validate UVs",
        default=True,
        description="Validates the selected mesh's UVs before trying to perform the conversion. This helps prevent issues with the conversion process, but can be disabled if you are sure the mesh is valid and want to skip this step."
    ) # type: ignore
    uv_tolerance: bpy.props.FloatProperty(
        name="UV Tolerance",
        default=DEFAULT_UV_TOLERANCE,
        description="The tolerance distance used when considering if 2 UV points are in the same position. This is used when validating if the selected mesh has the same UV layout as the template DNA mesh.",
        precision= 5,
    ) # type: ignore
    run_calibration: bpy.props.BoolProperty(
        name="Run Calibration",
        default=True,
        description="Runs the calibration process after converting the selected mesh. This export the DNA to disk and re-loads it into the rig logic instance."
    ) # type: ignore

    # this can be used when invoking the operator programmatically to set the rig logic instance name
    new_instance_name: bpy.props.StringProperty(default="") # type: ignore
    new_folder: bpy.props.StringProperty(
        name="Output Folder",
        default="",
        subtype='DIR_PATH',
        options={'PATH_SUPPORTS_BLEND_RELATIVE'}
    ) # type: ignore
    maps_folder: bpy.props.StringProperty(
        default='',
        name='Maps Folder',
        description='Optionally, this can be set to a folder location for the face wrinkle maps. Textures following the same naming convention as the metahuman source files will be found and set on the materials automatically.',
        subtype='DIR_PATH',
        options={'PATH_SUPPORTS_BLEND_RELATIVE'}
    ) # type: ignore

    def execute(self, context):
        window_manager_properties = bpy.context.window_manager.meta_human_dna  # type: ignore

        # If values passed to the operator, we update them.
        # This allows clean programmatic access to the operator properties.
        if self.new_folder:
            window_manager_properties.new_folder = self.new_folder # type: ignore
        if self.maps_folder:
            window_manager_properties.maps_folder = self.maps_folder # type: ignore

        selected_object = context.active_object # type: ignore
        new_folder = Path(bpy.path.abspath(window_manager_properties.new_folder))
        new_name = self.new_name or self.new_instance_name
        if not selected_object or not selected_object.type == 'MESH':
            self.report({'ERROR'}, 'You must select a mesh to convert.')
            return {'CANCELLED'}
        if not new_name:
            self.report({'ERROR'}, 'You must set a new name.')
            return {'CANCELLED'}
        if not window_manager_properties.new_folder:
            self.report({'ERROR'}, 'You must set an output folder.')
            return {'CANCELLED'}
        if not new_folder.exists():
            self.report({'ERROR'}, f'Folder not found: {new_folder}')
            return {'CANCELLED'}
        if round(context.scene.unit_settings.scale_length, 2) != 1.0: # type: ignore
            self.report({'ERROR'}, 'The scene unit scale must be set to 1.0')
            return {'CANCELLED'}
        
        kwargs = {
            'import_face_board': True,
            'import_materials': True,
            'import_vertex_groups': True,
            'import_bones': True,
            'import_mesh': True,
            'import_normals': False,
            'import_shape_keys': False,
            'alternate_maps_folder': window_manager_properties.maps_folder,
        }
        
        for lod_index in range(NUMBER_OF_HEAD_LODS):
            kwargs[f'import_lod{lod_index}'] = lod_index==0

        # set the properties 
        for key, value in kwargs.items():    
            setattr(self.properties, key, value)

        # we don't want to evaluate the dependency graph while importing the DNA
        window_manager_properties.evaluate_dependency_graph = False
        component = None
        
        base_dna_file = Path(window_manager_properties.base_dna) / f'{window_manager_properties.current_component_type}.dna'
        if not base_dna_file.exists():
            self.report({'ERROR'}, f'Base DNA file not found: {base_dna_file}')
            return {'CANCELLED'}

        if window_manager_properties.current_component_type == 'head':
            component = MetaHumanComponentHead(
                name=new_name,
                dna_file_path=base_dna_file,
                component_type='head',
                dna_import_properties=self.properties # type: ignore
            )
        elif window_manager_properties.current_component_type == 'body':
            component = MetaHumanComponentBody(
                name=new_name,
                dna_file_path=base_dna_file,
                component_type='body',
                dna_import_properties=self.properties # type: ignore
            )

        if not component:
            self.report({'ERROR'}, f'Failed to convert component {window_manager_properties.current_component_type}.')
            return {'CANCELLED'}

        # try to separate the selected object by its unreal material first if it has one
        selected_object = component.pre_convert_mesh_cleanup(mesh_object=selected_object)
        if not selected_object:
            window_manager_properties.evaluate_dependency_graph = True
            self.report({'ERROR'}, 'The selected object failed to be separated by its material.')
            return {'CANCELLED'}

        # check if the selected object has the same UVs as the base DNA
        if self.validate_uvs:
            success, message = component.validate_conversion(
                mesh_object=selected_object,
                tolerance=self.uv_tolerance
            )
            if not success: # type: ignore
                component.delete()
                window_manager_properties.evaluate_dependency_graph = True
                self.report({'ERROR'}, message)
                return {'CANCELLED'}

        component.ingest(align=False, constrain=False)
        
        if window_manager_properties.current_component_type == 'head':
            callbacks.update_head_output_items(None, bpy.context)
        elif window_manager_properties.current_component_type == 'body':
            callbacks.update_body_output_items(None, bpy.context)

        component.convert(mesh_object=selected_object, constrain=self.constrain_head_to_body) # type: ignore
        selected_object.hide_set(True)
        # populate the output items based on what was imported
        logger.info(f'Finished converting "{window_manager_properties.base_dna}"') # type: ignore

        # set the output folder path
        component.rig_logic_instance.output_folder_path = window_manager_properties.new_folder

        if self.run_calibration:
            # now we can export the new DNA file
            calibrator = DNACalibrator(
                instance=component.rig_logic_instance,
                linear_modifier=component.linear_modifier,
                component_type=window_manager_properties.current_component_type,
                file_name=f'{window_manager_properties.current_component_type}.dna'
            )
            calibrator.run()
            
            new_dna_file_path = str(new_folder / f'{window_manager_properties.current_component_type}.dna')
            # make the path relative to the blend file if it is saved
            if bpy.data.filepath:
                try:
                    new_dna_file_path = bpy.path.relpath(new_dna_file_path, start=os.path.dirname(bpy.data.filepath))
                except ValueError:
                    pass
            
            # now we can set the new DNA file path on the component
            if window_manager_properties.current_component_type == 'head':
                component.rig_logic_instance.head_dna_file_path = new_dna_file_path
            elif window_manager_properties.current_component_type == 'body':
                component.rig_logic_instance.body_dna_file_path = new_dna_file_path

        # now hide the component rig and switch it back to object mode and change the
        # active object to the face board
        utilities.switch_to_object_mode()

        if window_manager_properties.current_component_type == 'head':
            bpy.context.view_layer.objects.active = component.face_board_object # type: ignore
            utilities.switch_to_pose_mode(component.face_board_object) # type: ignore
            component.head_rig_object.hide_set(True) # type: ignore
        elif window_manager_properties.current_component_type == 'body':
            bpy.context.view_layer.objects.active = component.body_mesh_object # type: ignore
            component.body_rig_object.hide_set(True) # type: ignore

        # now we can evaluate the dependency graph again
        window_manager_properties.evaluate_dependency_graph = True
        bpy.ops.meta_human_dna.force_evaluate() # type: ignore

        # Ask the user for consent to collect metrics
        bpy.ops.meta_human_dna.metrics_collection_consent('INVOKE_DEFAULT') # type: ignore

        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width = 450) # type: ignore
    
    @classmethod
    def poll(cls, context):
        if not utilities.dependencies_are_valid():
            return False
        
        selected_object = context.active_object # type: ignore
        properties = context.scene.meta_human_dna # type: ignore
        if selected_object and selected_object.type == 'MESH' and selected_object.select_get():
            for instance in properties.rig_logic_instance_list:
                for item in instance.output_head_item_list:
                    if item.scene_object == selected_object:
                        return False
                for item in instance.output_body_item_list:
                    if item.scene_object == selected_object:
                        return False
            else:
                return True
        return False
    
    def _get_path_error(self, folder_path: str) -> str:
        if not folder_path:
            return ''

        if not os.path.exists(folder_path):
            return "Folder does not exist"
        if not os.path.isdir(folder_path):
            return "Path is not a folder"
        return ''
    
    def draw(self, context):
        if not self.layout:
            return
        window_manager_properties = context.window_manager.meta_human_dna # type: ignore

        row = self.layout.row()

        column = row.column()
        row_inner = column.row()
        row_inner.label(text='Component Type:')
        row_inner = column.row()
        row_inner.prop(window_manager_properties, 'current_component_type', text='') # type: ignore
        column = row.column()
        row_inner = column.row()
        row_inner.label(text='Base DNA:')
        row_inner = column.row()
        row_inner.prop(window_manager_properties, 'base_dna', text='')

        row = self.layout.row()
        row.prop(self, 'new_name')
        row = self.layout.row()
        row.prop(window_manager_properties, 'new_folder')
        row = self.layout.row()
        path_error = self._get_path_error(window_manager_properties.maps_folder)
        if path_error:
            row.alert = True
        row.prop(window_manager_properties, 'maps_folder')

        if path_error:
            row = self.layout.row()
            row.alert = True
            row.label(text=path_error, icon='ERROR')

        row = self.layout.row()
        column = row.column()
        column.prop(self, 'validate_uvs')
        column = row.column()
        column.enabled = self.validate_uvs
        column.prop(self, 'uv_tolerance')
        row = self.layout.row()
        row.prop(self, 'constrain_head_to_body')
        row = self.layout.row()
        row.prop(self, 'run_calibration')

class GenerateMaterial(bpy.types.Operator):
    """Generates a material for the head mesh object that you can then customize"""
    bl_idname = "meta_human_dna.generate_material"
    bl_label = "Generate Material"    

    def execute(self, context):
        head = utilities.get_active_head()
        if head and head.head_mesh_object:
            head.import_materials()
        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        instance = callbacks.get_active_rig_logic()
        if instance and instance.head_mesh and not instance.head_material and bpy.context.mode == 'OBJECT': # type: ignore
            return True
        return False


class ImportShapeKeys(GenericProgressQueueOperator):
    """Imports the shape keys from the DNA file and their deltas"""
    bl_idname = "meta_human_dna.import_shape_keys"
    bl_label = "Import Shape Keys"    

    def validate(self, context) -> bool:
        return True
    
    def set_commands_queue(
            self, 
            context, 
            component: MetaHumanComponentHead,
            commands_queue: queue.Queue
        ):
        component.import_shape_keys(commands_queue)
        bpy.ops.meta_human_dna.force_evaluate() # type: ignore


class ForceEvaluate(bpy.types.Operator):
    """Force the active Rig Logic Instance to evaluate based on the face board controls"""
    bl_idname = "meta_human_dna.force_evaluate"
    bl_label = "Force Evaluate"

    def execute(self, context):
        utilities.teardown_scene()
        utilities.setup_scene()
        instance = callbacks.get_active_rig_logic()
        if instance:
            instance.evaluate()
            # NOTE: Some dependency graph weirdness here. This is necessary to ensure that the rig logic 
            # evaluates the pose bones, otherwise bone transform updates won't be applied when the face 
            # board updates.
            current_context = utilities.get_current_context()
            if instance.head_rig:
                instance.head_rig.hide_set(False) # type: ignore
                instance.head_rig.hide_viewport = False # type: ignore
                utilities.switch_to_pose_mode(instance.head_rig) # type: ignore

            utilities.set_context(current_context)

        context.window_manager.meta_human_dna.evaluate_dependency_graph = True # type: ignore
        return {'FINISHED'}
    

class TestSentry(bpy.types.Operator):
    """Test the Sentry error reporting system"""
    bl_idname = "meta_human_dna.test_sentry"
    bl_label = "Test Sentry"

    def execute(self, context):
        division_by_zero = 1 / 0 # noqa: F841
        return {'FINISHED'}
    
class OpenBuildToolDocumentation(bpy.types.Operator):
    """Opens the Build Tool documentation in the default web browser"""
    bl_idname = "meta_human_dna.open_build_tool_documentation"
    bl_label = "Open Build Tool Documentation"

    def execute(self, context):
        import webbrowser
        webbrowser.open(ToolInfo.BUILD_TOOL_DOCUMENTATION)
        return {'FINISHED'}

class OpenMetricsCollectionAgreement(bpy.types.Operator):
    """Opens the metrics collection agreement in the default web browser"""
    bl_idname = "meta_human_dna.open_metrics_collection_agreement"
    bl_label = "Open Metrics Collection Agreement"

    def execute(self, context):
        import webbrowser
        webbrowser.open(ToolInfo.METRICS_COLLECTION_AGREEMENT)
        return {'FINISHED'}
    
class SendToMetaHumanCreator(bpy.types.Operator):
    """Exports the MetaHuman DNA head and body components, as well as, textures in a format supported by MetaHuman Creator."""
    bl_idname = "meta_human_dna.send_to_meta_human_creator"
    bl_label = "Send to MetaHuman Creator"

    def execute(self, context):
        instance = callbacks.get_active_rig_logic()
        if instance:
            # store the current auto evaluate settings
            auto_evaluate_head = instance.auto_evaluate_head
            auto_evaluate_body = instance.auto_evaluate_body

            # disable auto evaluate while we are exporting
            instance.auto_evaluate_head = False
            instance.auto_evaluate_body = False

            current_context = utilities.get_current_context()

            for attribute_name in ['head_mesh', 'head_rig', 'body_mesh', 'body_rig']:
                if not getattr(instance, attribute_name):
                    self.report({'ERROR'}, f'No {attribute_name} set on the active instance. Please ensure you have a head and body mesh and rig set before sending to MetaHuman Creator.')
                    return {'CANCELLED'}

            if not bpy.path.abspath(instance.output_folder_path) and not bpy.data.filepath:
                self.report({'ERROR'}, 'File must be saved to use a relative path')
                return {'CANCELLED'}

            head = utilities.get_active_head()
            body = utilities.get_active_body()
            if not head or not body:
                self.report({'ERROR'}, 'No active instance found. Please select an instance from the list under the RigLogic panel.')
                return {'CANCELLED'}

            last_component = None
            for component in [head, body]:
                dna_io_instance: DNAExporter = None # type: ignore
                if instance.output_method == 'calibrate':
                    dna_io_instance = DNACalibrator(
                        instance=instance,
                        linear_modifier=component.linear_modifier,
                        file_name=f'{component.component_type}.dna',
                        component_type=component.component_type
                    )              
                elif instance.output_method == 'overwrite':
                    dna_io_instance = DNAExporter(
                        instance=instance,
                        linear_modifier=component.linear_modifier,
                        file_name=f'{component.component_type}.dna',
                        component_type=component.component_type
                    )

                valid, title, message, fix = dna_io_instance.run()
                if not valid:
                    # self.report({'ERROR'}, message)
                    utilities.report_error(
                        title=title,
                        message=message,
                        fix=fix,
                        width=500
                    )
                    return {'CANCELLED'}
                else:
                    self.report({'INFO'}, message)
                
                last_component = component
            
            # write a manifest file to the output folder similar to the MetaHuman Creator DCC export
            if last_component:
                last_component.write_export_manifest()
                bpy.ops.meta_human_dna.force_evaluate() # type: ignore

            utilities.set_context(current_context)

            # restore the auto evaluate settings
            instance.auto_evaluate_head = auto_evaluate_head
            instance.auto_evaluate_body = auto_evaluate_body

        return {'FINISHED'}

class SendToUnreal(bpy.types.Operator):
    """Exports the metahuman DNA, SkeletalMesh, and Textures, then imports them into Unreal Engine. This requires the Send to Unreal addon to be installed"""
    bl_idname = "meta_human_dna.send_to_unreal"
    bl_label = "Send to Unreal"

    def execute(self, context):
        send2ue_properties = getattr(bpy.context.scene, 'send2ue', None) # type: ignore
        send2ue_addon_preferences = bpy.context.preferences.addons.get('send2ue') # type: ignore
        if not send2ue_properties:
            logger.error('The Send to Unreal addon is not installed!')
            return {'CANCELLED'}

        head = utilities.get_active_head()
        if head and head.rig_logic_instance and head.head_mesh_object and head.head_rig_object:
            instance = head.rig_logic_instance
            dna_io_instance: DNAExporter = None # type: ignore

            # sync the spine bones with the body skeleton in the unreal blueprint
            if instance.auto_sync_spine_with_body:
                utilities.sync_spine_with_body_skeleton(instance)

            # export a separate DNA file since we are only going to export bone 
            # transforms, mesh are sent across via FBX
            dna_file = f'export/{head.rig_logic_instance.name}.dna'
            if head.rig_logic_instance.output_method == 'calibrate':
                dna_io_instance = DNACalibrator(
                    instance=head.rig_logic_instance,
                    linear_modifier=head.linear_modifier,
                    meshes=False,
                    vertex_colors=False,
                    bones=True,
                    file_name=dna_file
                )              
            elif head.rig_logic_instance.output_method == 'overwrite':
                dna_io_instance = DNAExporter(
                    instance=head.rig_logic_instance,
                    linear_modifier=head.linear_modifier,
                    meshes=False,
                    vertex_colors=False,
                    bones=True,
                    file_name=dna_file
                )

            valid, title, message, fix = dna_io_instance.run()
            if not valid:
                utilities.report_error(
                    title=title,
                    message=message,
                    fix=fix,
                    width=300
                )
                return {'CANCELLED'}
            else:
                self.report({'INFO'}, message)
            
            # make sure our send2ue extension has its repo folder linked
            utilities.link_send2ue_extension()
            # Ensure the RPC response timeout is at least long enough to 
            # import the metahuman meshes since they can be quite large.
            if send2ue_addon_preferences.preferences.rpc_response_timeout < 180: # type: ignore
                send2ue_addon_preferences.preferences.rpc_response_timeout = 180 # type: ignore
            
            # set the active settings template to the face settings if it is not already set
            if bpy.context.scene.send2ue.active_settings_template != instance.send2ue_settings_template: # type: ignore
                # load the file into the template folder location if it is the default Metahuman DNA settings template
                if instance.send2ue_settings_template == SEND2UE_FACE_SETTINGS.name: # type: ignore
                    bpy.ops.send2ue.load_template(filepath=str(SEND2UE_FACE_SETTINGS)) # type: ignore
                # set the active template which modifies the state of the properties
                bpy.context.scene.send2ue.active_settings_template = SEND2UE_FACE_SETTINGS.name # type: ignore

            # include only the checked scene objects related to the head mesh. Our send2ue extension will override the final
            # selection, but we need to ensure only one asset is detected with its associated lods
            included_objects = []
            head_mesh_prefix = instance.head_mesh.name.split('_lod0_mesh')[0]
            for item in instance.output_head_item_list:
                if item.include and item.scene_object and item.scene_object.name.startswith(head_mesh_prefix):
                    included_objects.append(item.scene_object)
            
            if instance.head_mesh not in included_objects:
                included_objects.append(instance.head_mesh)

            if instance.head_rig not in included_objects:
                included_objects.append(instance.head_rig)

            # override what objects are collected by the send2ue to the head mesh
            bpy.context.window_manager.send2ue.object_collection_override.clear() # type: ignore
            bpy.context.window_manager.send2ue.object_collection_override.extend(included_objects) # type: ignore
            bpy.context.view_layer.objects.active = instance.head_mesh # type: ignore
            # ensure the meta_human_dna extension is enabled so the extension logic is run
            bpy.context.scene.send2ue.extensions.meta_human_dna.enabled = True # type: ignore

            # run send to unreal
            bpy.ops.wm.send2ue('INVOKE_DEFAULT') # type: ignore

            self.report({'INFO'}, "Successfully sent to Unreal Engine")

        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        return bool(getattr(context.scene, 'send2ue', False)) # type: ignore
    
class ExportSelectedComponent(bpy.types.Operator):
    """Export only the selected component to a single DNA file. No textures or supporting files will be exported."""
    bl_idname = "meta_human_dna.export_selected_component"
    bl_label = "Export Selected Component"

    def execute(self, context):
        instance = callbacks.get_active_rig_logic()
        if not instance:
            self.report({'ERROR'}, 'No active Rig Logic Instance found. Please select an instance from the list under the RigLogic panel.')
            return {'CANCELLED'}
        
        current_context = utilities.get_current_context()
        component = None
        if instance.output_component == 'head':
            component = utilities.get_active_head()
        elif instance.output_component == 'body':
            component = utilities.get_active_body()

        if component:            
            if not bpy.path.abspath(instance.output_folder_path) and not bpy.data.filepath:
                self.report({'ERROR'}, 'File must be saved to use a relative path')
                return {'CANCELLED'}

            dna_io_instance: DNAExporter = None # type: ignore
            if instance.output_method == 'calibrate':
                dna_io_instance = DNACalibrator(
                    instance=instance,
                    linear_modifier=component.linear_modifier,
                    file_name=f'{component.component_type}.dna',
                    component_type=component.component_type,
                    textures=False
                )              
            elif instance.output_method == 'overwrite':
                dna_io_instance = DNAExporter(
                    instance=instance,
                    linear_modifier=component.linear_modifier,
                    file_name=f'{component.component_type}.dna',
                    component_type=component.component_type,
                    textures=False
                )

            valid, title, message, fix = dna_io_instance.run()
            bpy.ops.meta_human_dna.force_evaluate() # type: ignore

            if not valid:
                utilities.report_error(
                    title=title,
                    message=message,
                    fix=fix,
                    width=300
                )
                return {'CANCELLED'}
            else:
                self.report({'INFO'}, message)

        utilities.set_context(current_context)

        return {'FINISHED'}

class SyncWithBodyBonesInBlueprint(bpy.types.Operator):
    """Syncs the spine bone positions with the body skeleton in the unreal blueprint. This can help ensure that your head matches the body height. You must have the blueprint asset path set in your Send to Unreal Settings so it knows where to look for the bone positions"""
    bl_idname = "meta_human_dna.sync_with_body_in_blueprint"
    bl_label = "Sync with Body in Blueprint"

    def execute(self, context):
        instance = callbacks.get_active_rig_logic()
        if instance:
            utilities.sync_spine_with_body_skeleton(instance)
        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        from .utilities import send2ue_addon_is_valid
        if not send2ue_addon_is_valid():
            return False

        instance = callbacks.get_active_rig_logic()
        if instance:
            if instance.unreal_blueprint_asset_path:
                return True
        return False
    
class MirrorSelectedBones(bpy.types.Operator):
    """Mirrors the selected bone positions to the other side of the head mesh"""
    bl_idname = "meta_human_dna.mirror_selected_bones"
    bl_label = "Mirror Selected Bones"

    def execute(self, context):
        head = utilities.get_active_head()
        if head:
            success, message = head.mirror_selected_bones()        
            if not success:
                self.report({'ERROR'}, message)
                return {'CANCELLED'}
        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        return callbacks.poll_head_rig_bone_selection(cls, context)

class ShrinkWrapVertexGroup(bpy.types.Operator):
    """Shrink wraps the active vertex group on the head mesh using the shrink wrap modifier"""
    bl_idname = "meta_human_dna.shrink_wrap_vertex_group"
    bl_label = "Shrink Wrap Active Group"

    def execute(self, context):
        current_component_type = context.window_manager.meta_human_dna.current_component_type # type: ignore
        head = utilities.get_active_head()
        body = utilities.get_active_body()
        if head and current_component_type == 'head':
            head.shrink_wrap_vertex_group()
        elif body and current_component_type == 'body':
            body.shrink_wrap_vertex_group()
        return {'FINISHED'}
    
class AutoFitSelectedBones(bpy.types.Operator):
    """Auto-fits the selected bones to the head mesh"""
    bl_idname = "meta_human_dna.auto_fit_selected_bones"
    bl_label = "Auto Fit Selected Bones"

    def execute(self, context):
        head = utilities.get_active_head()
        if head and head.head_mesh_object and head.head_rig_object:
            if bpy.context.mode != 'POSE': # type: ignore
                self.report({'ERROR'}, 'You must be in pose mode')
                return {'CANCELLED'}
            
            if not bpy.context.selected_pose_bones: # type: ignore
                self.report({'ERROR'}, 'You must at least have one pose bone selected')
                return {'CANCELLED'}
            
            for pose_bone in bpy.context.selected_pose_bones: # type: ignore
                if pose_bone.id_data != head.head_rig_object:
                    self.report({'ERROR'}, f'The selected bone "{pose_bone.id_data.name}:{pose_bone.name}" is not associated with the rig logic instance "{head.rig_logic_instance.name}"')
                    return {'CANCELLED'}
            
            utilities.auto_fit_bones(
                mesh_object=head.head_mesh_object, 
                armature_object=head.head_rig_object,
                dna_reader=head.dna_reader,
                only_selected=True
            ) # type: ignore

        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        return callbacks.poll_head_rig_bone_selection(cls, context)
    
class RevertBoneTransformsToDna(bpy.types.Operator):
    """Revert the selected bone's transforms to their values in the DNA file"""
    bl_idname = "meta_human_dna.revert_bone_transforms_to_dna"
    bl_label = "Revert Bone Transforms to DNA"

    def execute(self, context):
        head = utilities.get_active_head()
        if head:
            if bpy.context.mode != 'POSE': # type: ignore
                self.report({'ERROR'}, 'Must be in pose mode')
                return {'CANCELLED'}
            
            if not head.rig_logic_instance.head_rig:
                self.report({'ERROR'}, f'"{head.rig_logic_instance.name}" does not have a head rig assigned')
                return {'CANCELLED'}

            head.revert_bone_transforms_to_dna()
        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        return callbacks.poll_head_rig_bone_selection(cls, context)
    
class ShapeKeyOperatorBase(bpy.types.Operator):
    shape_key_name: bpy.props.StringProperty(name="Shape Key Name") # type: ignore

    def get_select_shape_key(self, instance):
        # find the related mesh objects for the head rig
        channel_index = instance.head_channel_name_to_index_lookup[self.shape_key_name]
        for shape_key_block in instance.head_shape_key_blocks.get(channel_index, []):
            for index, key_block in enumerate(shape_key_block.id_data.key_blocks):
                if key_block.name == self.shape_key_name:
                    # set this as the active shape key so we can edit it
                    return index, key_block, channel_index
        return None, None, None
    
    def lock_all_other_shape_keys(self, mesh_object: bpy.types.Object, key_block: bpy.types.ShapeKey):            
        mesh_object.hide_set(False)
        bpy.context.view_layer.objects.active = mesh_object # type: ignore
                
        # make sure the armature modifier is visible on mesh in edit mode
        for modifier in mesh_object.modifiers:
            if modifier.type == 'ARMATURE':
                modifier.show_in_editmode = True
                modifier.show_on_cage = True

        # lock all shape keys except the one we are editing
        for _key_block in mesh_object.data.shape_keys.key_blocks: # type: ignore
            _key_block.lock_shape = _key_block.name != self.shape_key_name
        
        # Unlock and set the active shape key block to the one we are editing
        key_block.lock_shape = False
        mesh_object.active_shape_key_index = mesh_object.data.shape_keys.key_blocks.find(self.shape_key_name) # type: ignore
        mesh_object.use_shape_key_edit_mode = True
    
    def validate(self, context, instance) -> bool | tuple:
        mesh_object = bpy.data.objects.get(instance.active_shape_key_mesh_name)
        if not mesh_object:
            self.report({'ERROR'}, 'The mesh object associated with the active shape key is not found')
            return False
        
        if self.shape_key_name == SHAPE_KEY_BASIS_NAME:
            if not mesh_object.data.shape_keys: # type: ignore
                self.report({'ERROR'}, 'The mesh object does not have shape keys')
                return False
            
            key_block = mesh_object.data.shape_keys.key_blocks.get(SHAPE_KEY_BASIS_NAME) # type: ignore
            return None, key_block, None, mesh_object
        
        if not instance.head_channel_name_to_index_lookup:
            instance.initialize()
            if not instance.head_channel_name_to_index_lookup:
                self.report({'ERROR'}, 'The shape key blocks are not initialized')
                return False

        shape_key_index, key_block, channel_index = self.get_select_shape_key(instance)
        if shape_key_index is not None:
            mesh_object.active_shape_key_index = shape_key_index
        else:
            self.report({'ERROR'}, f'The shape key "{self.shape_key_name}" is not found')
            return False
        
        # Set the active shape key in the shape key list to the one we are editing
        for i,  _shape_key in enumerate(instance.shape_key_list):
            if _shape_key.name == self.shape_key_name:
                instance.shape_key_list_active_index = i
                break
        
        return shape_key_index, key_block, channel_index, mesh_object
    

class RBFEditorOperatorBase(bpy.types.Operator):
    solver_index: bpy.props.IntProperty(default=0) # type: ignore
    pose_index: bpy.props.IntProperty(default=0) # type: ignore
    driver_index: bpy.props.IntProperty(default=0) # type: ignore
    driven_index: bpy.props.IntProperty(default=0) # type: ignore

    def validate(self, context, instance) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, context):
        instance = callbacks.get_active_rig_logic()
        if instance and instance.body_rig:
            result, message = self.validate(context, instance)
            if not result:
                self.report({'ERROR'}, message)
                return {'CANCELLED'}
            
            self.run(instance)

        return {'FINISHED'}
    
    def run(self, instance):
        pass


class MetaHumanDnaReportError(ShapeKeyOperatorBase):
    """Reports and error message to the user with a optional fix"""
    bl_idname = "meta_human_dna.report_error"
    bl_label = "Error"

    title: bpy.props.StringProperty(default="") # type: ignore
    message: bpy.props.StringProperty(default="") # type: ignore
    width: bpy.props.IntProperty(default=300) # type: ignore

    def execute(self, context):
        wm = context.window_manager # type: ignore
        fix = wm.meta_human_dna.errors.get(self.title, {}).get('fix', None) # type: ignore
        if fix:
            fix()
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager # type: ignore
        if not wm:
            return

        fix = wm.meta_human_dna.errors.get(self.title, {}).get('fix', None) # type: ignore
        return wm.invoke_props_dialog(
            self,
            confirm_text="Fix" if fix else "OK",
            cancel_default=False,
            width=self.width
        )

    def draw(self, context):
        if not self.layout:
            return
        
        for line in self.title.split('\n'):
            row = self.layout.row()
            row.scale_y = 1.5
            row.label(text=line)
        for line in self.message.split('\n'):
            row = self.layout.row()
            row.alert = True
            row.label(text=line)


class MetricsCollectionConsent(bpy.types.Operator):
    """Tell the user that we collect metrics and ask for their consent"""
    bl_idname = "meta_human_dna.metrics_collection_consent"
    bl_label = "Meta-Human DNA Addon Metrics"

    def execute(self, context):
        preferences = context.preferences.addons[ToolInfo.NAME].preferences # type: ignore
        preferences.metrics_collection = True # type: ignore
        utilities.init_sentry()
        bpy.ops.meta_human_dna.force_evaluate() # type: ignore
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager # type: ignore
        if not wm:
            return
        
        preferences = context.preferences.addons[ToolInfo.NAME].preferences # type: ignore
        current_timestamp = datetime.now().timestamp()

        if preferences.metrics_collection: # type: ignore
            utilities.init_sentry()
            return {'FINISHED'}

        if bpy.app.online_access and preferences.next_metrics_consent_timestamp < current_timestamp: # type: ignore
            return wm.invoke_props_dialog(
                self,
                confirm_text="Allow",
                cancel_default=False,
                width=500
            )
        elif bpy.app.online_access and preferences.metrics_collection: # type: ignore
            utilities.init_sentry()
        
        return {'FINISHED'}
        
    def cancel(self, context):
        preferences = context.preferences.addons[ToolInfo.NAME].preferences # type: ignore
        # wait 30 days before asking again
        preferences.next_metrics_consent_timestamp = (datetime.now() + timedelta(days=30)).timestamp() # type: ignore
        preferences.metrics_collection = False # type: ignore
        bpy.ops.meta_human_dna.force_evaluate() # type: ignore

    def draw(self, context):
        if not self.layout:
            return
        
        row = self.layout.row()
        row.label(text="We collect anonymous metrics and bug reports to help improve the MetaHuman DNA addon.")
        row = self.layout.row()
        row.label(text="No personal data is collected.")
        row = self.layout.row()
        row.label(text="Will you allow us to collect bug reports?")
        row.operator('meta_human_dna.open_metrics_collection_agreement', text='', icon='URL')

class SculptThisShapeKey(ShapeKeyOperatorBase):
    """Sculpt this shape key"""
    bl_idname = "meta_human_dna.sculpt_this_shape_key"
    bl_label = "Edit this Shape Key"

    def execute(self, context):
        instance = callbacks.get_active_rig_logic()
        if instance and instance.head_rig:
            result = self.validate(context, instance)
            if not result:
                return {'CANCELLED'}
            
            _, key_block, _, mesh_object = result # type: ignore

            # solo the shape key before sculpting if the solo option is enabled
            if instance.solo_shape_key:
                instance.solo_head_shape_key_value(shape_key=key_block)

            self.lock_all_other_shape_keys(mesh_object, key_block)
            utilities.switch_to_sculpt_mode(mesh_object)
            mesh_object.show_only_shape_key = False

        return {'FINISHED'}

class EditThisShapeKey(ShapeKeyOperatorBase):
    """Edit this shape key"""
    bl_idname = "meta_human_dna.edit_this_shape_key"
    bl_label = "Edit this Shape Key"

    def execute(self, context):
        instance = callbacks.get_active_rig_logic()
        if instance and instance.head_rig:
            result = self.validate(context, instance)
            if not result:
                return {'CANCELLED'}
            
            _, key_block, _, mesh_object = result # type: ignore

            # solo the shape key before editing if the solo option is enabled
            if instance.solo_shape_key:
                instance.solo_head_shape_key_value(shape_key=key_block)

            self.lock_all_other_shape_keys(mesh_object, key_block)
            utilities.switch_to_edit_mode(mesh_object)
            mesh_object.show_only_shape_key = False

        return {'FINISHED'}
    
    
class ReImportThisShapeKey(ShapeKeyOperatorBase):
    """Re-Import this shape key from the DNA file"""
    bl_idname = "meta_human_dna.reimport_this_shape_key"
    bl_label = "Re-Import this Shape Key"

    shape_key_name: bpy.props.StringProperty(name="Shape Key Name") # type: ignore

    def execute(self, context):
        head = utilities.get_active_head()
        if head and head.rig_logic_instance:
            instance = head.rig_logic_instance
            result = self.validate(context, instance)
            if not result:
                return {'CANCELLED'}
            
            _, shape_key_block, _, mesh_object = result # type: ignore
            mesh_index = {v.name: k for k, v in instance.head_mesh_index_lookup.items()}.get(mesh_object.name)
            if mesh_index is None:
                self.report({'ERROR'}, f'The mesh index for "{mesh_object.name}" is not found')
                return {'CANCELLED'}

            current_context = utilities.get_current_context()
            utilities.switch_to_object_mode()
            short_name = self.shape_key_name.split("__", 1)[-1]

            if not instance.generate_neutral_shapes:
                reader = get_dna_reader(file_path=instance.head_dna_file_path)

                # determine the shape key index in the DNA file
                shape_key_index = None
                for index in range(reader.getBlendShapeTargetCount(mesh_index)):
                    channel_index = reader.getBlendShapeChannelIndex(mesh_index, index)
                    channel_name = reader.getBlendShapeChannelName(channel_index)
                    if channel_name == short_name:
                        shape_key_index = index
                        break

                if shape_key_index is None:
                    self.report({'ERROR'}, f'The shape key "{short_name}" is not found in the DNA file')
                    return {'CANCELLED'}

                # DNA is Y-up, Blender is Z-up, so we need to rotate the deltas
                rotation_matrix = Matrix.Rotation(math.radians(90), 4, 'X')

                delta_x_values = reader.getBlendShapeTargetDeltaXs(mesh_index, shape_key_index)
                delta_y_values = reader.getBlendShapeTargetDeltaYs(mesh_index, shape_key_index)
                delta_z_values = reader.getBlendShapeTargetDeltaZs(mesh_index, shape_key_index)
                vertex_indices = reader.getBlendShapeTargetVertexIndices(mesh_index, shape_key_index)

                # the new vertex layout is the original vertex layout with the deltas from the dna applied
                for vertex_index, delta_x, delta_y, delta_z in zip(vertex_indices, delta_x_values, delta_y_values, delta_z_values):
                    try:
                        delta = Vector((delta_x, delta_y, delta_z)) * head.linear_modifier
                        rotated_delta = rotation_matrix @ delta
                        
                        # set the positions of the shape key vertices
                        shape_key_block.data[vertex_index].co = mesh_object.data.vertices[vertex_index].co.copy() + rotated_delta # type: ignore
                    except IndexError:
                        logger.warning(f'Vertex index {vertex_index} is missing for shape key "{short_name}". Was this deleted on the base mesh "{mesh_object.name}"?')
            else:
                # reset the shape key to the basis shape key
                shape_key_block.data.foreach_set("co", [v.co for v in mesh_object.data.vertices])

            utilities.set_context(current_context)
        return {'FINISHED'}
    

class AddRBFSolver(RBFEditorOperatorBase):
    """Add a new RBF Solver"""
    bl_idname = "meta_human_dna.add_rbf_solver"
    bl_label = "Add RBF Solver"

    def run(self, instance):
        pass
    

class RemoveRBFSolver(RBFEditorOperatorBase):
    """Remove the selected RBF Solver"""
    bl_idname = "meta_human_dna.remove_rbf_solver"
    bl_label = "Remove RBF Solver"

    def run(self, instance):
        pass
    

class EvaluateRBFSolvers(RBFEditorOperatorBase):
    """Evaluate the RBF Solvers"""
    bl_idname = "meta_human_dna.evaluate_rbf_solvers"
    bl_label = "Evaluate RBF Solvers"

    def run(self, instance):
        instance.evaluate(component='body')


class RevertRBFSolver(RBFEditorOperatorBase):
    """Revert RBF solver back to the original DNA."""
    bl_idname = "meta_human_dna.revert_rbf_solver"
    bl_label = "Revert RBF Solver"

    def run(self, instance):
        utilities.reset_pose(instance.body_rig)

        instance.editing_rbf_solver = False
        instance.auto_evaluate_body = True
        bpy.ops.meta_human_dna.force_evaluate() # type: ignore

class EditRBFSolver(RBFEditorOperatorBase):
    """Switch to Editing mode for the selected RBF solver. Changes will not take effect until committed to the .dna file."""
    bl_idname = "meta_human_dna.edit_rbf_solver"
    bl_label = "Edit RBF Solver"

    @classmethod
    def poll(cls, context):
        instance = callbacks.get_active_rig_logic()
        if not instance or not instance.body_rig:
            return False
        
        if not instance.editing_rbf_solver:
            return True
        
        return False

    def run(self, instance):
        instance.editing_rbf_solver = True
        instance.auto_evaluate_body = False
        instance.body_rig.hide_set(False)
        utilities.switch_to_pose_mode(instance.body_rig) # type: ignore
            

class CommitRBFSolverChanges(RBFEditorOperatorBase):
    """Commit the current changes for the selected RBF solver to the .dna file"""
    bl_idname = "meta_human_dna.commit_rbf_solver_changes"
    bl_label = "Commit RBF Solver Changes"

    @classmethod
    def poll(cls, context):
        instance = callbacks.get_active_rig_logic()
        if instance is None:
            return False
        
        if instance.editing_rbf_solver:
            return True
        
        return False
    
    def validate(self, context, instance) -> tuple[bool, str]:
        if not utilities.dependencies_are_valid():
            return False, "Dependencies are not valid. Ensure the core dependencies are installed."

        if not instance.body_rig:
            return False, "No body rig found. Please assign a body rig."
        if not instance.body_dna_file_path:
            return False, "No body .dna file. Please assign a body .dna file."
        if not Path(bpy.path.abspath(instance.body_dna_file_path)).exists():
            return False, "Body .dna file does not exist. Please check the file path."

        return True, ""

    def run(self, instance):
        import meta_human_dna_core

        reader = get_dna_reader(file_path=instance.body_dna_file_path)
        writer = get_dna_writer(file_path=instance.body_dna_file_path)
        data = utilities.collection_to_list(instance.rbf_solver_list)

        # destroy the reader and writer instances to release file locks and
        # any memory they are using
        instance.destroy()

        meta_human_dna_core.commit_rbf_data_to_dna(
            reader=reader,
            writer=writer,
            data=data
        )
        logger.info(f'DNA exported successfully to: "{instance.body_dna_file_path}"')
        
        # turn off editing mode and re-enable auto evaluation
        instance.editing_rbf_solver = False
        instance.auto_evaluate_body = True
        # re-initialize and evaluate the body rig
        instance.evaluate(component='body')


class RBFPoseOperatorBase(RBFEditorOperatorBase):    
    def add_pose(
            self, 
            instance, 
            pose_name: str,
            driven_bones: list[bpy.types.PoseBone],
            from_pose = None
        ):
        solver = instance.rbf_solver_list[self.solver_index]
        new_pose_index = len(solver.poses)
        pose = solver.poses.add()
        
        pose.solver_index = self.solver_index
        pose.pose_index = new_pose_index
        pose.name = pose_name
        
        # copy the values from an existing pose if provided
        if from_pose:
            pose.joint_group_index = from_pose.joint_group_index
            pose.target_enable = from_pose.target_enable
            pose.scale_factor = from_pose.scale_factor

        driver_bone_name = solver.name.replace(RBF_SOLVER_POSTFIX, '')
        driver_bone = instance.body_rig.pose.bones.get(driver_bone_name)
        if not driver_bone:
            return
        
        driver = pose.drivers.add()
        utilities.set_driver_bone_data(
            instance=instance,
            pose=pose,
            driver=driver,
            pose_bone=driver_bone,
            new=True
        )

        for pose_bone in driven_bones:
            driven = pose.driven.add()            
            utilities.set_driven_bone_data(
                instance=instance,
                pose=pose,
                driven=driven,
                pose_bone=pose_bone,
                new=True
            )

        # set the active pose to the new pose
        solver.poses_active_index = new_pose_index # type: ignore

        return pose


class AddRBFPose(RBFPoseOperatorBase):
    """Add a new RBF Pose"""
    bl_idname = "meta_human_dna.add_rbf_pose"
    bl_label = "Add RBF Pose"

    new_pose_name: bpy.props.StringProperty(
        default="default",
        description="The name of the new RBF Pose",
        get=callbacks.get_new_pose_name,
        set=callbacks.set_new_pose_name
    ) # type: ignore

    def validate(self, context, instance) -> tuple[bool, str]:
        if not context.selected_pose_bones:
            return False, "No pose bones selected. Please select at least one driver bone in pose mode."
        
        if not instance.body_initialized:
            instance.body_initialize()

        for pose_bone in context.selected_pose_bones:
            if pose_bone.name in instance.body_driver_bone_names:
                return False, f'The selected bone "{pose_bone.name}" is assigned as a driver bone. Please select other bones.'
            elif pose_bone.name in instance.body_swing_bone_names:
                return False, f'The selected bone "{pose_bone.name}" is assigned as a swing bone. Please select other bones.'
            elif pose_bone.name in instance.body_twist_bone_names:
                return False, f'The selected bone "{pose_bone.name}" is assigned as a twist bone. Please select other bones.'
        
        solver = instance.rbf_solver_list[instance.rbf_solver_list_active_index]
        for pose in solver.poses:
            if pose.name == self.new_pose_name:
                return False, f'A pose with the name "{self.new_pose_name}" already exists. Use a different name.'
            
        driver_name_name = solver.name.replace(RBF_SOLVER_POSTFIX, '')
        if not instance.body_rig.pose.bones.get(driver_name_name):
            return False, f'The driver bone "{driver_name_name}" for the solver "{solver.name}" is not found in the armature. Please ensure the bone exists.'
        
        return True, ""

    def run(self, instance):
        solver = instance.rbf_solver_list[instance.rbf_solver_list_active_index]
        new_pose_index = len(solver.poses)
        self.add_pose(
            instance=instance,
            pose_name=self.new_pose_name if self.new_pose_name else f"Pose{new_pose_index}",
            driven_bones=bpy.context.selected_pose_bones.copy()  # type: ignore
        )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width = 200) # type: ignore
    
    def draw(self, context):
        if not self.layout:
            return
        
        row = self.layout.row()
        row.label(text='Pose Name:')
        row = self.layout.row()
        row.prop(self, "new_pose_name", text="")
        row = self.layout.row()
        row.label(text="Adding bones:")
        box = self.layout.box()
        for pose_bone in context.selected_pose_bones:
            row = box.row()
            row.label(text=pose_bone.name, icon='BONE_DATA')
    
    @classmethod
    def poll(cls, context):
        return bool(context.selected_pose_bones)
    

class DuplicateRBFPose(RBFPoseOperatorBase):
    """Duplicate the selected RBF Pose"""
    bl_idname = "meta_human_dna.duplicate_rbf_pose"
    bl_label = "Duplicate RBF Pose"

    def run(self, instance):
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

    def run(self, instance):      
        # ensure the body is initialized
        if not instance.body_initialized:
            instance.body_initialize(update_rbf_solver_list=False)

        solver = instance.rbf_solver_list[self.solver_index]
        pose = solver.poses[self.pose_index]

        # Update all the driver bone data for the pose
        for driver in pose.drivers:
            driver_bone = instance.body_rig.pose.bones.get(driver.name)
            if driver_bone:
                utilities.set_driver_bone_data(
                    instance=instance,
                    pose=pose,
                    driver=driver,
                    pose_bone=driver_bone
                )
            else:
                self.report({'ERROR'}, (
                    f'Driver bone "{driver.name}" was not found in armature "{instance.body_rig.name}" '
                    f'when updating RBF Pose "{pose.name}". Please ensure the bone exists or delete '
                    f'this pose and recreate it.'
                ))
        
        # Update all the driven bone data for the pose
        for driven in pose.driven:
            driven_pose_bone = instance.body_rig.pose.bones.get(driven.name)
            if driven_pose_bone:
                utilities.set_driven_bone_data(
                    instance=instance,
                    pose=pose,
                    driven=driven,
                    pose_bone=driven_pose_bone
                )
            else:
                logger.warning((
                    f'Driven bone "{driven.name}" was not found in armature when '
                    f'updating RBF Pose "{pose.name}". It will be deleted from '
                    'the pose when this data is committed to the dna.'
                ))
    

class RemoveRBFPose(RBFEditorOperatorBase):
    """Remove the selected RBF Pose"""
    bl_idname = "meta_human_dna.remove_rbf_pose"
    bl_label = "Remove RBF Pose"

    def run(self, instance):
        solver = instance.rbf_solver_list[instance.rbf_solver_list_active_index]
        solver.poses.remove(solver.poses_active_index)
        to_index = min(solver.poses_active_index, len(solver.poses) - 1)
        solver.poses_active_index = to_index # type: ignore


class AddRBFDriver(RBFEditorOperatorBase):
    """Add a new RBF Driver bone"""
    bl_idname = "meta_human_dna.add_rbf_driver"
    bl_label = "Add RBF Driver"

    def run(self, instance):
        pass


class RemoveRBFDriver(RBFEditorOperatorBase):
    """Remove the selected RBF Driver bone"""
    bl_idname = "meta_human_dna.remove_rbf_driver"
    bl_label = "Remove RBF Driver"

    def run(self, instance):
        pass

class AddRBFDriven(RBFEditorOperatorBase):
    """Add a new RBF Driven bone"""
    bl_idname = "meta_human_dna.add_rbf_driven"
    bl_label = "Add RBF Driven Bone"

    @classmethod
    def poll(cls, context):
        instance = callbacks.get_active_rig_logic()        
        if instance and instance.body_rig and context.selected_pose_bones:
            return True
        
        return False

    def validate(self, context, instance) -> tuple[bool, str]:
        if not context.selected_pose_bones:
            return False, "No pose bones selected. Please select at least one driven bone in pose mode."

        return True, ""

    def run(self, instance):
        solver = instance.rbf_solver_list[self.solver_index]
        pose = solver.poses[self.pose_index]

        selected_pose_bones = bpy.context.selected_pose_bones.copy()  # type: ignore

        for pose_bone in selected_pose_bones:
            if pose_bone.name not in [d.name for d in pose.driven]:
                driven = pose.driven.add()
                utilities.set_driven_bone_data(
                    instance=instance,
                    pose=pose,
                    driven=driven,
                    pose_bone=pose_bone,
                    new=True
                )

        # set the active driven to the last one added
        pose.driven_active_index = len(pose.driven) - 1

class RemoveRBFDriven(RBFEditorOperatorBase):
    """Remove the selected RBF Driven bone"""
    bl_idname = "meta_human_dna.remove_rbf_driven"
    bl_label = "Remove RBF Driven Bone"

    def run(self, instance):
        pass

class SelectAllRBFDriven(RBFEditorOperatorBase):
    """Select all RBF Driven bones for the current pose"""
    bl_idname = "meta_human_dna.select_all_rbf_driven_for_pose"
    bl_label = "Select All RBF Driven Bones for Pose"

    def run(self, instance):
        solver = instance.rbf_solver_list[self.solver_index]
        pose = solver.poses[self.pose_index]

        # switch to pose mode
        instance.body_rig.hide_set(False)
        utilities.switch_to_pose_mode(instance.body_rig) # type: ignore

        # select all driven bones for the pose
        driven_bone_names = [driven.name for driven in pose.driven]
        for pose_bone in instance.body_rig.pose.bones:
            if pose_bone.name in driven_bone_names:
                pose_bone.bone.select = True
            else:
                pose_bone.bone.select = False
    
class RefreshMaterialSlotNames(bpy.types.Operator):
    """Refresh the material slot names by re-reading them from the meshes in the output list"""
    bl_idname = "meta_human_dna.refresh_material_slot_names"
    bl_label = "Refresh Material Slot Names"

    def execute(self, context):
        callbacks.update_material_slot_to_instance_mapping(self, context)
        return {'FINISHED'}
    
class RevertMaterialSlotValues(bpy.types.Operator):
    """Revert the material slot to unreal material instance values to their default values"""
    bl_idname = "meta_human_dna.revert_material_slot_values"
    bl_label = "Revert Material Slot Values"

    def execute(self, context):
        instance = callbacks.get_active_rig_logic()
        if instance:
            instance.unreal_material_slot_to_instance_mapping.clear()
        callbacks.update_material_slot_to_instance_mapping(self, context)
        return {'FINISHED'}
    
class DuplicateRigInstance(bpy.types.Operator):
    """Duplicate the active Rig Instance. This copies all it's associated data and offsets it to the right"""
    bl_idname = "meta_human_dna.duplicate_rig_instance"
    bl_label = "Duplicate Rig Instance"

    new_name: bpy.props.StringProperty(
        name="New Name", 
        default="",
        get=callbacks.get_copied_rig_logic_instance_name,
        set=callbacks.set_copied_rig_logic_instance_name
    ) # type: ignore
    new_folder: bpy.props.StringProperty(
        name="New Output Folder", 
        default="",
        subtype='DIR_PATH',
        options={'PATH_SUPPORTS_BLEND_RELATIVE'}
    ) # type: ignore

    def execute(self, context):
        new_folder = Path(bpy.path.abspath(self.new_folder))
        if not bpy.path.abspath(self.new_folder) and not bpy.data.filepath:
            self.report({'ERROR'}, 'File must be saved to use a relative path')
            return {'CANCELLED'}
        if not self.new_name:
            self.report({'ERROR'}, 'You must set a new name.')
            return {'CANCELLED'}
        if not self.new_folder:
            self.report({'ERROR'}, 'You must set an output folder.')
            return {'CANCELLED'}
        if not new_folder.exists():
            self.report({'ERROR'}, f'Folder not found: {new_folder}')
            return {'CANCELLED'}

        instance = callbacks.get_active_rig_logic()
        if instance:
            for component_type, mesh_object, rig_object in [
                ('body', instance.body_mesh, instance.body_rig),
                ('head', instance.head_mesh, instance.head_rig)
            ]:
                if mesh_object and rig_object:
                    new_mesh_object = utilities.copy_mesh(
                        mesh_object=mesh_object,
                        new_mesh_name=mesh_object.name.replace(instance.name, self.new_name),
                        modifiers=False,
                        materials=True
                    )
                    new_rig_object = utilities.copy_armature(
                        armature_object=rig_object,
                        new_armature_name=rig_object.name.replace(instance.name, self.new_name)
                    )
                    # move the new rig to the right collection
                    utilities.move_to_collection(
                        scene_objects=[new_mesh_object],
                        collection_name=f'{self.new_name}_lod0',
                        exclusively=True
                    )
                    # move the new rig to the right collection
                    utilities.move_to_collection(
                        scene_objects=[new_rig_object],
                        collection_name=self.new_name,
                        exclusively=True
                    )
                    # move the face board also to the this collection
                    utilities.move_to_collection(
                        scene_objects=[instance.face_board],
                        collection_name=self.new_name,
                        exclusively=False
                    )
                    
                    # duplicate the mesh materials
                    new_mesh_material = utilities.copy_materials(
                        mesh_object=new_mesh_object,
                        old_prefix=instance.name,
                        new_prefix=self.new_name,
                        new_folder=new_folder / self.new_name
                    )
                    # duplicate the texture logic node
                    if new_mesh_material:
                        texture_logic_node = getattr(callbacks, f'get_{component_type}_texture_logic_node')(new_mesh_material)
                        if texture_logic_node and texture_logic_node.node_tree:
                            new_name = f'{self.new_name}_{getattr(constants, f"{component_type.upper()}_TEXTURE_LOGIC_NODE_NAME")}'
                            texture_logic_node.label = new_name
                            texture_logic_node_tree_copy = texture_logic_node.node_tree.copy() # type: ignore
                            texture_logic_node_tree_copy.name = new_name
                            texture_logic_node.node_tree = texture_logic_node_tree_copy

                    # match the hide state of the original
                    new_mesh_object.hide_set(mesh_object.hide_get())
                    new_rig_object.hide_set(rig_object.hide_get())

                    # assign the rig to the duplicated mesh
                    modifier = new_mesh_object.modifiers.new(name='Armature', type='ARMATURE')
                    modifier.object = new_rig_object # type: ignore
                    new_mesh_object.parent = new_rig_object

                    # now we need to duplicate the output items
                    for item in getattr(instance, f'output_{component_type}_item_list'):
                        if item.scene_object and item.scene_object.type == 'MESH':
                            if item.scene_object == mesh_object:
                                continue

                            new_extra_mesh_object = utilities.copy_mesh(
                                mesh_object=item.scene_object,
                                new_mesh_name=item.scene_object.name.replace(instance.name, self.new_name),
                                modifiers=False,
                                materials=True
                            )

                            lod_index = utilities.get_lod_index(new_extra_mesh_object.name)
                            if lod_index == -1:
                                lod_index = 0
                                
                            # move the new mesh to the right collection
                            utilities.move_to_collection(
                                scene_objects=[new_extra_mesh_object],
                                collection_name=f'{self.new_name}_lod{lod_index}',
                                exclusively=True
                            )
                            main_collection = bpy.data.collections.get(self.new_name)
                            lod_collection = bpy.data.collections.get(f'{self.new_name}_lod{lod_index}')
                            if main_collection and lod_collection:
                                # unlink the lod collection from the scene collection if it exists
                                if lod_collection in bpy.context.scene.collection.children.values(): # type: ignore
                                    bpy.context.scene.collection.children.unlink(lod_collection) # type: ignore
                                # link the lod collection to the main collection if it is not already linked
                                if lod_collection not in main_collection.children.values():
                                    main_collection.children.link(lod_collection)
                            
                            # assign the rig to the duplicated extra mesh
                            modifier = new_extra_mesh_object.modifiers.new(name='Armature', type='ARMATURE')
                            modifier.object = new_rig_object # type: ignore
                            new_extra_mesh_object.parent = new_rig_object

                            # match the hide state of the original
                            new_extra_mesh_object.hide_set(item.scene_object.hide_get())
                            new_extra_mesh_object.hide_viewport = item.scene_object.hide_viewport

                            # duplicate the extra mesh's materials
                            utilities.copy_materials(
                                mesh_object=new_extra_mesh_object,
                                old_prefix=instance.name,
                                new_prefix=self.new_name,
                                new_folder=new_folder / self.new_name
                            )                        

                    # move the duplicated rig to the right of the last mesh
                    last_instance = context.scene.meta_human_dna.rig_logic_instance_list[-1] # type: ignore
                    
                    if component_type == 'body':
                        new_rig_object.location.x = utilities.get_bounding_box_left_x(last_instance.body_mesh) - (utilities.get_bounding_box_width(last_instance.body_mesh) / 2)
                    
                    if component_type == 'head' and last_instance.body_rig:
                        # Align the head rig with the body rig if it exists
                        body_object_head_bone = last_instance.body_rig.pose.bones.get('head') # type: ignore
                        head_object_head_bone = new_rig_object.pose.bones.get('head') # type: ignore
                        if body_object_head_bone and head_object_head_bone:
                            # get the location of the body head bone and the head head bone in world space
                            body_head_location = (body_object_head_bone.id_data.matrix_world @ body_object_head_bone.matrix).to_translation()
                            head_head_location = (head_object_head_bone.id_data.matrix_world @ head_object_head_bone.matrix).to_translation()
                            delta = body_head_location - head_head_location
                            # move the head rig object to align with the body rig head bone
                            new_rig_object.location += delta
                    # otherwise move it to the right of the last instance's head mesh
                    elif component_type == 'head':
                        new_rig_object.location.x = utilities.get_bounding_box_left_x(last_instance.head_mesh) - (utilities.get_bounding_box_width(last_instance.head_mesh) / 2)

                    new_dna_file_path = new_folder / self.new_name / f'{component_type}.dna'
                    new_dna_file_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(instance.head_dna_file_path, new_dna_file_path)

                    # add the duplicated instance to the list if it doesn't already exist
                    for _rig_logic_instance in context.scene.meta_human_dna.rig_logic_instance_list: # type: ignore
                        if _rig_logic_instance.name == self.new_name:
                            new_instance = _rig_logic_instance
                            break
                    else:
                        new_instance = context.scene.meta_human_dna.rig_logic_instance_list.add() # type: ignore

                    # now set the values on the instance
                    new_instance.name = self.new_name
                    setattr(new_instance, f'{component_type}_dna_file_path', str(new_dna_file_path))
                    new_instance.active_lod = instance.active_lod
                    new_instance.active_material_preview = instance.active_material_preview
                    new_instance.face_board = instance.face_board
                    setattr(new_instance, f'{component_type}_mesh', new_mesh_object)
                    setattr(new_instance, f'{component_type}_rig', new_rig_object)
                    setattr(new_instance, f'{component_type}_material', new_mesh_material)
                    new_instance.output_folder_path = self.new_folder

                    # set the new instance as the active one
                    context.scene.meta_human_dna.rig_logic_instance_list_active_index = len(context.scene.meta_human_dna.rig_logic_instance_list) - 1 # type: ignore


        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width = 450) # type: ignore
    
    @classmethod
    def poll(cls, context):
        return callbacks.get_active_rig_logic() is not None
    
    def draw(self, context):
        if not self.layout:
            return

        self.layout.prop(self, 'new_name')
        self.layout.prop(self, 'new_folder')


class AddRigLogicTextureNode(bpy.types.Operator):
    """Add a new Rig Logic Texture Node to the active material. This is used to control the wrinkle map blending on Metahuman faces"""
    bl_idname = 'meta_human_dna.add_rig_logic_texture_node'
    bl_label = "Add Rig Logic Texture Node"

    @classmethod
    def get_active_material(cls, context) -> bpy.types.Material | None:
        space = context.space_data # type: ignore
        node_tree = space.node_tree # type: ignore                
        for material in bpy.data.materials:
            if material.node_tree == node_tree:
                return material

    @classmethod
    def poll(cls, context):
        space = context.space_data # type: ignore
        node_tree = getattr(space, 'node_tree', None) # type: ignore
        if node_tree and node_tree.type == 'SHADER':
            active_material = cls.get_active_material(context)
            if not active_material:
                return False

            if not callbacks.get_head_texture_logic_node(active_material):
                return True
            return False
        
    def execute(self, context):
        space = context.space_data # type: ignore
        node_tree = space.node_tree # type: ignore
        cursor_location = cursor_location = space.cursor_location # type: ignore

        active_material = self.get_active_material(context)
        if not active_material:
            self.report({'ERROR'}, "Could not find the active material")
            return {'CANCELLED'}
        
        texture_logic_node = utilities.import_head_texture_logic_node()
        if not texture_logic_node:
            self.report({'ERROR'}, "Could not import the Texture Logic Node")
            return {'CANCELLED'}
        
        node = node_tree.nodes.new(type='ShaderNodeGroup')
        node.name = f'{active_material.name}_{HEAD_TEXTURE_LOGIC_NODE_NAME}'
        node.label = f'{active_material.name} {HEAD_TEXTURE_LOGIC_NODE_LABEL}'
        node.node_tree = texture_logic_node
        node.location = cursor_location
        return {'FINISHED'}


class UILIST_ADDON_PREFERENCES_OT_extra_dna_entry_remove(GenericUIListOperator, bpy.types.Operator):
    """Remove the selected entry from the list"""

    bl_idname = "meta_human_dna.addon_preferences_extra_dna_entry_remove"
    bl_label = "Remove Selected Entry"

    def execute(self, context):
        addon_preferences = context.preferences.addons[ToolInfo.NAME].preferences # type: ignore
        my_list = addon_preferences.extra_dna_folder_list # type: ignore
        active_index = addon_preferences.extra_dna_folder_list_active_index # type: ignore
        my_list.remove(active_index)
        to_index = min(active_index, len(my_list) - 1)
        addon_preferences.extra_dna_folder_list_active_index = to_index # type: ignore
        return {'FINISHED'}


class UILIST_ADDON_PREFERENCES_OT_extra_dna_entry_add(GenericUIListOperator, bpy.types.Operator):
    """Add an entry to the list after the current active item"""

    bl_idname = "meta_human_dna.addon_preferences_extra_dna_entry_add"
    bl_label = "Add Entry"

    def execute(self, context):
        addon_preferences = context.preferences.addons[ToolInfo.NAME].preferences # type: ignore
        my_list = addon_preferences.extra_dna_folder_list # type: ignore
        active_index = addon_preferences.extra_dna_folder_list_active_index # type: ignore
        to_index = min(len(my_list), active_index + 1)
        my_list.add()
        my_list.move(len(my_list) - 1, to_index)
        addon_preferences.extra_dna_folder_list_active_index = to_index # type: ignore
        return {'FINISHED'}


class UILIST_RIG_LOGIC_OT_entry_remove(GenericUIListOperator, bpy.types.Operator):
    """Remove the selected entry from the list"""

    bl_idname = "meta_human_dna.rig_logic_instance_entry_remove"
    bl_label = "Remove Selected Entry"

    def execute(self, context):
        my_list = context.scene.meta_human_dna.rig_logic_instance_list # type: ignore

        instance = context.scene.meta_human_dna.rig_logic_instance_list[self.active_index] # type: ignore
        for component_type in ['body', 'head']:
            for item in getattr(instance, f'output_{component_type}_item_list'):
                if item.scene_object:
                    bpy.data.objects.remove(item.scene_object, do_unlink=True)
                if item.image_object:
                    bpy.data.images.remove(item.image_object, do_unlink=True)

            # remove the collections for the component type
            for collection_name in [instance.name] + [f'{instance.name}_{component_type}_lod{i}' for i in range(NUMBER_OF_HEAD_LODS)]:
                collection = bpy.data.collections.get(collection_name)
                if collection:
                    bpy.data.collections.remove(collection, do_unlink=True)

        my_list.remove(self.active_index)
        to_index = min(self.active_index, len(my_list) - 1)
        context.scene.meta_human_dna.rig_logic_instance_list_active_index = to_index # type: ignore
        return {'FINISHED'}


class UILIST_RIG_LOGIC_OT_entry_add(GenericUIListOperator, bpy.types.Operator):
    """Add an entry to the list after the current active item"""

    bl_idname = "meta_human_dna.rig_logic_instance_entry_add"
    bl_label = "Add Entry"

    def execute(self, context):
        utilities.add_rig_instance()
        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        return utilities.dependencies_are_valid()


class UILIST_RIG_LOGIC_OT_entry_move(GenericUIListOperator, bpy.types.Operator):
    """Move an entry in the list up or down"""

    bl_idname = "meta_human_dna.rig_logic_instance_entry_move"
    bl_label = "Move Entry"

    direction: bpy.props.EnumProperty(
        name="Direction",
        items=(
            ('UP', 'UP', 'UP'),
            ('DOWN', 'DOWN', 'DOWN'),
        ),
        default='UP',
    ) # type: ignore

    def execute(self, context):
        my_list = context.scene.meta_human_dna.rig_logic_instance_list # type: ignore
        delta = {
            'DOWN': 1,
            'UP': -1,
        }[self.direction]

        to_index = (self.active_index + delta) % len(my_list)

        from_instance = context.scene.meta_human_dna.rig_logic_instance_list[self.active_index] # type: ignore
        to_instance = context.scene.meta_human_dna.rig_logic_instance_list[to_index] # type: ignore

        if from_instance.body_rig and to_instance.body_rig:
            to_x = to_instance.body_rig.location.x
            from_x = from_instance.body_rig.location.x

            # swap the x locations of the body rigs
            to_instance.body_rig.location.x = from_x
            from_instance.body_rig.location.x = to_x
            # swap the x locations of the head rigs
            to_instance.head_rig.location.x = from_x
            from_instance.head_rig.location.x = to_x
            # swap the x locations of the face boards
            to_instance.face_board.location.x += (from_x - to_x)
            from_instance.face_board.location.x += (to_x - from_x)

        elif from_instance.head_rig and to_instance.head_rig:
            to_x = to_instance.head_rig.location.x
            from_x = from_instance.head_rig.location.x

            # swap the x locations of the head rigs
            to_instance.head_rig.location.x = from_x
            from_instance.head_rig.location.x = to_x
            # swap the x locations of the face boards
            to_instance.face_board.location.x += (from_x - to_x)
            from_instance.face_board.location.x += (to_x - from_x)

        my_list.move(self.active_index, to_index)
        context.scene.meta_human_dna.rig_logic_instance_list_active_index = to_index # type: ignore
        return {'FINISHED'}