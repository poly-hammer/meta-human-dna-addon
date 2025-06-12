import os
import bpy
import queue
import shutil
import logging
from pathlib import Path
from datetime import datetime, timedelta
from .face import MetahumanFace
from .ui import importer, callbacks
from . import utilities
from .dna_io import DNACalibrator, DNAExporter, create_shape_key
from .properties import MetahumanDnaImportProperties
from .constants import (
    SEND2UE_FACE_SETTINGS,
    TEXTURE_LOGIC_NODE_NAME,
    TEXTURE_LOGIC_NODE_LABEL,
    ToolInfo,
    NUMBER_OF_FACE_LODS,
    SHAPE_KEY_GROUP_PREFIX,
    DEFAULT_UV_TOLERANCE
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
        face = utilities.get_active_face()
        if face:
            context.window_manager.meta_human_dna.progress = 0 # type: ignore
            context.window_manager.meta_human_dna.progress_description = '' # type: ignore
            self._commands_queue = queue.Queue()
            self.set_commands_queue(context, face, self._commands_queue)
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
            face: MetahumanFace,
            commands_queue: queue.Queue
        ):
        pass   


class ImportAnimation(bpy.types.Operator, importer.ImportAsset):
    """Import an animation for the metahuman face board exported from an Unreal Engine Level Sequence"""
    bl_idname = "meta_human_dna.import_animation"
    bl_label = "Import Animation"
    filename_ext = ".fbx"

    filter_glob: bpy.props.StringProperty(
        default="*.fbx",
        options={"HIDDEN"},
        subtype="FILE_PATH",
    ) # type: ignore

    def execute(self, context):
        logger.info(f'Importing animation {self.filepath}')  # type: ignore
        face = utilities.get_active_face()
        if face:
            face.import_action(Path(self.filepath))  # type: ignore
        return {'FINISHED'}
    
class BakeAnimation(bpy.types.Operator):
    """Bakes the active face board action to the pose bones, shape key values, and texture logic mask values. Useful for rendering, simulations, etc. where rig logic evaluation is not available"""
    bl_idname = "meta_human_dna.bake_animation"
    bl_label = "Bake Animation"

    action_name: bpy.props.StringProperty(
        name="Action Name",
        default="baked_action",
        description="The name of the action that will be created to store the baked animation data"
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
        return context.window_manager.invoke_props_dialog(self, width = 250) # type: ignore

    def draw(self, context):
        row = self.layout.row()
        row.prop(self, 'action_name', text="Name")
        row = self.layout.row()
        row.prop(self, 'start_frame')
        row.prop(self, 'end_frame')
        row = self.layout.row()
        row.prop(self, 'step')
        row = self.layout.row()
        row.prop(self, 'shape_keys')
        row = self.layout.row()
        row.prop(self, 'masks')
        row = self.layout.row()
        row.label(text="Bones:")
        row = self.layout.row()
        row.prop(self, 'bone_location', text="Location")
        row = self.layout.row()
        row.prop(self, 'bone_rotation', text="Rotation")
        row = self.layout.row()
        row.prop(self, 'bone_scale', text="Scale")

    def execute(self, context):
        if self.start_frame > self.end_frame:
            self.report({'ERROR'}, 'The start frame must be less than the end frame')
            return {'CANCELLED'}

        face = utilities.get_active_face()
        if face and face.head_rig_object:
            channel_types = set()
            if self.bone_location:
                channel_types.add('LOCATION')
            if self.bone_rotation:
                channel_types.add('ROTATION')
            if self.bone_scale:
                channel_types.add('SCALE')

            utilities.bake_to_action(
                armature_object=face.head_rig_object,
                action_name=self.action_name,
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
        face = MetahumanFace(
            dna_file_path=file_path,
            dna_import_properties=self.properties # type: ignore
        )
        valid, message = face.ingest()
        # populate the output items based on what was imported
        callbacks.update_output_items(None, bpy.context)
        logger.info(f'Finished importing "{self.filepath}"') # type: ignore
        # now we can evaluate the dependency graph again
        window_manager_properties.evaluate_dependency_graph = True

        if not valid:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
        else:
            self.report({'INFO'}, message)

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

    base_dna: bpy.props.EnumProperty(
        name="Base DNA",
        items=callbacks.get_base_dna_files,
        description="Choose the base DNA file that will be used when converting the selected.",
        options={'ANIMATABLE'}
    ) # type: ignore
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
    ) # type: ignore
    maps_folder: bpy.props.StringProperty(
        default='',
        name='Maps Folder',
        description='Optionally, this can be set to a folder location for the face wrinkle maps. Textures following the same naming convention as the metahuman source files will be found and set on the materials automatically.',
        subtype='DIR_PATH'
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

    def execute(self, context):
        selected_object = context.active_object # type: ignore
        new_folder = Path(bpy.path.abspath(self.new_folder))
        new_name = self.new_name or self.new_instance_name
        if not selected_object or not selected_object.type == 'MESH':
            self.report({'ERROR'}, 'You must select a mesh to convert.')
            return {'CANCELLED'}
        if not new_name:
            self.report({'ERROR'}, 'You must set a new name.')
            return {'CANCELLED'}
        if not self.new_folder:
            self.report({'ERROR'}, 'You must set an output folder.')
            return {'CANCELLED'}
        if not new_folder.exists():
            self.report({'ERROR'}, f'Folder not found: {new_folder}')
            return {'CANCELLED'}
        if round(context.scene.unit_settings.scale_length, 2) != 1.0: # type: ignore
            self.report({'ERROR'}, 'The scene unit scale must be set to 1.0')
            return {'CANCELLED'}
        
        window_manager_properties = bpy.context.window_manager.meta_human_dna  # type: ignore
        kwargs = {
            'import_face_board': True,
            'import_materials': True,
            'import_vertex_groups': True,
            'import_bones': True,
            'import_mesh': True,
            'import_normals': False,
            'import_shape_keys': False,
            'alternate_maps_folder': self.maps_folder,
        }
        
        for lod_index in range(NUMBER_OF_FACE_LODS):
            kwargs[f'import_lod{lod_index}'] = lod_index==0

        # set the properties 
        for key, value in kwargs.items():    
            setattr(self.properties, key, value)

        # we don't want to evaluate the dependency graph while importing the DNA
        window_manager_properties.evaluate_dependency_graph = False
        face = MetahumanFace(
            name=new_name,
            dna_file_path=Path(self.base_dna),
            dna_import_properties=self.properties # type: ignore
        )
        # try to separate the selected object by its unreal head material first if it has one
        selected_object = face.pre_convert_mesh_cleanup(mesh_object=selected_object)
        if not selected_object:
            window_manager_properties.evaluate_dependency_graph = True
            self.report({'ERROR'}, 'The selected object failed to be separated by its head material.')
            return {'CANCELLED'}

        # check if the selected object has the same number of vertices as the base DNA
        if self.validate_uvs:
            success, message = face.validate_conversion(
                mesh_object=selected_object,
                tolerance=self.uv_tolerance
            )
            if not success: # type: ignore
                face.delete()
                window_manager_properties.evaluate_dependency_graph = True
                self.report({'ERROR'}, message)
                return {'CANCELLED'}
        
        face.ingest()
        callbacks.update_output_items(None, bpy.context)
        face.convert(mesh_object=selected_object)
        selected_object.hide_set(True)
        # populate the output items based on what was imported
        logger.info(f'Finished converting "{self.base_dna}"') # type: ignore

        # set the output folder path
        face.rig_logic_instance.output_folder_path = self.new_folder

        if self.run_calibration:
            # now we can export the new DNA file
            calibrator = DNACalibrator(
                instance=face.rig_logic_instance,
                linear_modifier=face.linear_modifier
            )        
            calibrator.run()
            
            new_dna_file_path = str(new_folder / f'{new_name}.dna')
            # make the path relative to the blend file if it is saved
            if bpy.data.filepath:
                try:
                    new_dna_file_path = bpy.path.relpath(new_dna_file_path, start=os.path.dirname(bpy.data.filepath))
                except ValueError:
                    pass

        # now we can evaluate the dependency graph again
        window_manager_properties.evaluate_dependency_graph = True
        
        bpy.ops.meta_human_dna.force_evaluate() # type: ignore

        # now hide the head rig and switch it back to object mode and change the 
        # active object to the face board
        utilities.switch_to_object_mode()
        bpy.context.view_layer.objects.active = face.face_board_object # type: ignore
        utilities.switch_to_pose_mode(face.face_board_object) # type: ignore
        face.head_rig_object.hide_set(True) # type: ignore

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
                for item in instance.output_item_list:
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
        
        row = self.layout.row()
        row.prop(self, 'base_dna')
        row = self.layout.row()
        row.prop(self, 'new_name')
        row = self.layout.row()
        row.prop(self, 'new_folder')
        row = self.layout.row()
        path_error = self._get_path_error(self.maps_folder)
        if path_error:
            row.alert = True
        row.prop(self, 'maps_folder')

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
        row.prop(self, 'run_calibration')

class GenerateMaterial(bpy.types.Operator):
    """Generates a material for the head mesh object that you can then customize"""
    bl_idname = "meta_human_dna.generate_material"
    bl_label = "Generate Material"    

    def execute(self, context):
        face = utilities.get_active_face()
        if face and face.head_mesh_object:
            face.import_materials()
        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        instance = callbacks.get_active_rig_logic()
        if instance and instance.head_mesh and not instance.material and bpy.context.mode == 'OBJECT': # type: ignore
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
            face: MetahumanFace,
            commands_queue: queue.Queue
        ):
        face.import_shape_keys(commands_queue)
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
            instance.head_rig.hide_set(False) # type: ignore
            instance.head_rig.hide_viewport = False # type: ignore
            utilities.switch_to_pose_mode(instance.head_rig) # type: ignore
            utilities.set_context(current_context)
        else:
            self.report({'ERROR'}, 'No active Rig Logic Instance found!')

        context.window_manager.meta_human_dna.evaluate_dependency_graph = True # type: ignore
        return {'FINISHED'}
    

class TestSentry(bpy.types.Operator):
    """Test the Sentry error reporting system"""
    bl_idname = "meta_human_dna.test_sentry"
    bl_label = "Test Sentry"

    def execute(self, context):
        division_by_zero = 1 / 0
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

        face = utilities.get_active_face()
        if face and face.rig_logic_instance and face.head_mesh_object and face.head_rig_object:
            instance = face.rig_logic_instance
            dna_io_instance: DNAExporter = None # type: ignore

            # sync the spine bones with the body skeleton in the unreal blueprint
            if instance.auto_sync_spine_with_body:
                utilities.sync_spine_with_body_skeleton(instance)

            # export a separate DNA file since we are only going to export bone 
            # transforms, mesh are sent across via FBX
            dna_file = f'export/{face.rig_logic_instance.name}.dna'
            if face.rig_logic_instance.output_method == 'calibrate':
                dna_io_instance = DNACalibrator(
                    instance=face.rig_logic_instance,
                    linear_modifier=face.linear_modifier,
                    meshes=False,
                    vertex_colors=False,
                    bones=True,
                    file_name=dna_file
                )              
            elif face.rig_logic_instance.output_method == 'overwrite':
                dna_io_instance = DNAExporter(
                    instance=face.rig_logic_instance,
                    linear_modifier=face.linear_modifier,
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
            for item in instance.output_item_list:
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
    
class ExportToDisk(bpy.types.Operator):
    """Exports the metahuman DNA file to a folder on disk"""
    bl_idname = "meta_human_dna.export_to_disk"
    bl_label = "Export to Disk"

    def execute(self, context):
        face = utilities.get_active_face()
        if face and face.rig_logic_instance:
            instance = face.rig_logic_instance
            
            if not bpy.path.abspath(instance.output_folder_path) and not bpy.data.filepath:
                self.report({'ERROR'}, 'File must be saved to use a relative path')
                return {'CANCELLED'}

            dna_io_instance: DNAExporter = None # type: ignore
            if instance.output_method == 'calibrate':
                dna_io_instance = DNACalibrator(
                    instance=instance,
                    linear_modifier=face.linear_modifier
                )              
            elif instance.output_method == 'overwrite':
                dna_io_instance = DNAExporter(
                    instance=instance,
                    linear_modifier=face.linear_modifier
                )

            valid, title, message, fix = dna_io_instance.run()
            if not valid:
                # self.report({'ERROR'}, message)
                utilities.report_error(
                    title=title,
                    message=message,
                    fix=fix,
                    width=300
                )
                return {'CANCELLED'}
            else:
                self.report({'INFO'}, message)
            
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
        face = utilities.get_active_face()
        if face:
            success, message = face.mirror_selected_bones()        
            if not success:
                self.report({'ERROR'}, message)
                return {'CANCELLED'}
        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        return callbacks.poll_head_rig_bone_selection(cls, context)
    
class PushBonesForwardAlongNormals(bpy.types.Operator):
    """Pushes the selected bone positions forward along the mesh normals"""
    bl_idname = "meta_human_dna.push_bones_forward_along_normals"
    bl_label = "Push Bones Forward Along Normals"

    def execute(self, context):
        face = utilities.get_active_face()
        if face:
            face.push_selected_bones_along_mesh_normals(direction='forward')
        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        return callbacks.poll_head_rig_bone_selection(cls, context)

class PushBonesBackwardAlongNormals(bpy.types.Operator):
    """Pushes the selected bone positions backward along the mesh normals"""
    bl_idname = "meta_human_dna.push_bones_backward_along_normals"
    bl_label = "Push Bones Backward Along Normals"

    def execute(self, context):
        face = utilities.get_active_face()
        if face:
            face.push_selected_bones_along_mesh_normals(direction='backward')
        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        return callbacks.poll_head_rig_bone_selection(cls, context)


class ShrinkWrapVertexGroup(bpy.types.Operator):
    """Shrink wraps the active vertex group on the head mesh using the shrink wrap modifier"""
    bl_idname = "meta_human_dna.shrink_wrap_vertex_group"
    bl_label = "Shrink Wrap Active Group"

    def execute(self, context):
        face = utilities.get_active_face()
        if face:
            face.shrink_wrap_vertex_group()
        return {'FINISHED'}
    
class AutoFitSelectedBones(bpy.types.Operator):
    """Auto-fits the selected bones to the head mesh"""
    bl_idname = "meta_human_dna.auto_fit_selected_bones"
    bl_label = "Auto Fit Selected Bones"

    def execute(self, context):
        face = utilities.get_active_face()
        if face and face.head_mesh_object and face.head_rig_object:
            if bpy.context.mode != 'POSE': # type: ignore
                self.report({'ERROR'}, 'You must be in pose mode')
                return {'CANCELLED'}
            
            if not bpy.context.selected_pose_bones: # type: ignore
                self.report({'ERROR'}, 'You must at least have one pose bone selected')
                return {'CANCELLED'}
            
            for pose_bone in bpy.context.selected_pose_bones: # type: ignore
                if pose_bone.id_data != face.head_rig_object:
                    self.report({'ERROR'}, f'The selected bone "{pose_bone.id_data.name}:{pose_bone.name}" is not associated with the rig logic instance "{face.rig_logic_instance.name}"')
                    return {'CANCELLED'}
            
            utilities.auto_fit_bones(
                mesh_object=face.head_mesh_object, 
                armature_object=face.head_rig_object,
                dna_reader=face.dna_reader,
                only_selected=True
            )

        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        return callbacks.poll_head_rig_bone_selection(cls, context)
    
class RevertBoneTransformsToDna(bpy.types.Operator):
    """Revert the selected bone's transforms to their values in the DNA file"""
    bl_idname = "meta_human_dna.revert_bone_transforms_to_dna"
    bl_label = "Revert Bone Transforms to DNA"

    def execute(self, context):
        face = utilities.get_active_face()
        if face:
            if bpy.context.mode != 'POSE': # type: ignore
                self.report({'ERROR'}, 'Must be in pose mode')
                return {'CANCELLED'}
            
            if not face.rig_logic_instance.head_rig:
                self.report({'ERROR'}, f'"{face.rig_logic_instance.name}" does not have a head rig assigned')
                return {'CANCELLED'}

            face.revert_bone_transforms_to_dna()
        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        return callbacks.poll_head_rig_bone_selection(cls, context)
    
class ShapeKeyOperatorBase(bpy.types.Operator):
    shape_key_name: bpy.props.StringProperty(name="Shape Key Name") # type: ignore

    def get_select_shape_key(self, instance):
        # find the related mesh objects for the head rig
        channel_index = instance.channel_name_to_index_lookup[self.shape_key_name]
        for shape_key_block in instance.shape_key_blocks.get(channel_index, []):
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
        for key_block in mesh_object.data.shape_keys.key_blocks: # type: ignore
            key_block.lock_shape = key_block.name != self.shape_key_name
        
        key_block.lock_shape = False
        mesh_object.use_shape_key_edit_mode = True
    
    def validate(self, context, instance) -> bool | tuple:
        mesh_object = bpy.data.objects.get(instance.active_shape_key_mesh_name)
        if not mesh_object:
            self.report({'ERROR'}, 'The mesh object associated with the active shape key is not found')
            return False
        if not instance.channel_name_to_index_lookup:
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
        fix = wm.meta_human_dna.errors.get(self.title, {}).get('fix', None) # type: ignore
        return wm.invoke_props_dialog(
            self,
            confirm_text="Fix" if fix else "OK",
            cancel_default=False,
            width=self.width
        )

    def draw(self, context):
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
        return {'CANCELLED'}

    def draw(self, context):
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
                instance.solo_shape_key_value(shape_key=key_block)

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
                instance.solo_shape_key_value(shape_key=key_block)

            self.lock_all_other_shape_keys(mesh_object, key_block)
            short_name = self.shape_key_name.split("__", 1)[-1]
            utilities.switch_to_edit_mode(mesh_object)
            utilities.select_vertex_group(
                mesh_object=mesh_object, 
                vertex_group_name=f'{SHAPE_KEY_GROUP_PREFIX}{short_name}',
                add=False
            )
            mesh_object.show_only_shape_key = False

        return {'FINISHED'}
    
    
class ReImportThisShapeKey(ShapeKeyOperatorBase):
    """Re-Import this shape key from the DNA file"""
    bl_idname = "meta_human_dna.reimport_this_shape_key"
    bl_label = "Re-Import this Shape Key"

    shape_key_name: bpy.props.StringProperty(name="Shape Key Name") # type: ignore

    def execute(self, context):
        face = utilities.get_active_face()
        if face and face.rig_logic_instance:
            instance = face.rig_logic_instance
            result = self.validate(context, instance)
            if not result:
                return {'CANCELLED'}
            
            _, shape_key_block, channel_index, mesh_object = result # type: ignore
            mesh_index = {v.name: k for k, v in instance.mesh_index_lookup.items()}.get(mesh_object.name)
            mesh_dna_name = mesh_object.name.replace(f'{instance.name}_', '')
            if mesh_index is None:
                self.report({'ERROR'}, f'The mesh index for "{mesh_object.name}" is not found')
                return {'CANCELLED'}

            current_context = utilities.get_current_context()
            short_name = self.shape_key_name.split("__", 1)[-1]
            # filter out the shape key block we are re-importing
            shape_key_blocks = instance.data['shape_key_blocks'].pop(channel_index, [])
            new_shape_key_blocks = [block for block in shape_key_blocks if block.name != f'{mesh_dna_name}__{short_name}']
            new_shape_key_block = create_shape_key(
                index=channel_index,
                mesh_index=mesh_index,
                mesh_object=mesh_object,
                reader=instance.dna_reader,
                name=short_name,
                prefix=f'{mesh_dna_name}__',
                is_neutral=instance.generate_neutral_shapes,
                linear_modifier=face.linear_modifier,
                delta_threshold=0.0001
            )
            mesh_object.show_only_shape_key = False
            utilities.set_context(current_context)
            new_shape_key_blocks.append(new_shape_key_block)
            # swap the cached shape key blocks index in the instance
            instance.data['shape_key_blocks'][channel_index] = new_shape_key_blocks
            instance.evaluate()
        return {'FINISHED'}
    
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
    
class DuplicateRigLogicInstance(bpy.types.Operator):
    """Duplicate the active Rig Logic Instance. This copies all it's associated data and offsets it to the right"""
    bl_idname = "meta_human_dna.duplicate_rig_logic_instance"
    bl_label = "Duplicate Rig Logic Instance"

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
    ) # type: ignore

    def execute(self, context):
        new_folder = Path(bpy.path.abspath(self.new_folder))
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
            if instance.head_mesh and instance.head_rig:
                new_head_mesh_object = utilities.copy_mesh(
                    mesh_object=instance.head_mesh,
                    new_mesh_name=instance.head_mesh.name.replace(instance.name, self.new_name),
                    modifiers=False,
                    materials=True
                )
                new_rig_object = utilities.copy_armature(
                    armature_object=instance.head_rig,
                    new_armature_name=instance.head_rig.name.replace(instance.name, self.new_name)
                )

                # duplicate the head mesh materials
                new_head_mesh_material = utilities.copy_materials(
                    mesh_object=new_head_mesh_object,
                    old_prefix=instance.name,
                    new_prefix=self.new_name,
                    new_folder=new_folder
                )
                # duplicate the texture logic node
                if new_head_mesh_material:
                    texture_logic_node = callbacks.get_texture_logic_node(new_head_mesh_material)
                    if texture_logic_node and texture_logic_node.node_tree:
                        new_name = f'{self.new_name}_{TEXTURE_LOGIC_NODE_NAME}'
                        texture_logic_node.label = new_name
                        texture_logic_node_tree_copy = texture_logic_node.node_tree.copy() # type: ignore
                        texture_logic_node_tree_copy.name = new_name
                        texture_logic_node.node_tree = texture_logic_node_tree_copy

                # match the hide state of the original
                new_head_mesh_object.hide_set(instance.head_mesh.hide_get())
                new_rig_object.hide_set(instance.head_rig.hide_get())

                # assign the rig to the duplicated mesh
                modifier = new_head_mesh_object.modifiers.new(name='Armature', type='ARMATURE')
                modifier.object = new_rig_object # type: ignore
                new_head_mesh_object.parent = new_rig_object

                # now we need to duplicate the output items
                for item in instance.output_item_list:
                    if item.scene_object and item.scene_object.type == 'MESH':
                        if item.scene_object == instance.head_mesh:
                            continue

                        new_extra_mesh_object = utilities.copy_mesh(
                            mesh_object=item.scene_object,
                            new_mesh_name=item.scene_object.name.replace(instance.name, self.new_name),
                            modifiers=False,
                            materials=True
                        )
                        
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
                            new_folder=new_folder
                        )                        

                # move the duplicated rig to the right of the last head mesh
                last_instance = context.scene.meta_human_dna.rig_logic_instance_list[-1] # type: ignore
                if last_instance.head_mesh:
                    new_rig_object.location.x = utilities.get_bounding_box_right_x(last_instance.head_mesh) - 0.5
                # otherwise move it to the right of the current instance's head mesh
                else:
                    new_rig_object.location.x = utilities.get_bounding_box_right_x(instance.head_mesh) - 0.5

                # then parent the duplicated rig to the same face board
                new_rig_object.parent = instance.face_board

                new_dna_file_path = new_folder / f'{self.new_name}.dna'
                shutil.copy(instance.dna_file_path, new_dna_file_path)


                # add the duplicated instance to the list and set the initial values
                new_instance = context.scene.meta_human_dna.rig_logic_instance_list.add() # type: ignore
                new_instance.name = self.new_name
                new_instance.dna_file_path = str(new_dna_file_path)
                new_instance.active_lod = instance.active_lod
                new_instance.active_material_preview = instance.active_material_preview
                new_instance.face_board = instance.face_board
                new_instance.head_mesh = new_head_mesh_object
                new_instance.head_rig = new_rig_object
                new_instance.material = new_head_mesh_material
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
        layout = self.layout
        layout.prop(self, 'new_name')
        layout.prop(self, 'new_folder')


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

            if not callbacks.get_texture_logic_node(active_material):
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
        
        texture_logic_node = utilities.import_texture_logic_node()
        if not texture_logic_node:
            self.report({'ERROR'}, "Could not import the Texture Logic Node")
            return {'CANCELLED'}
        
        node = node_tree.nodes.new(type='ShaderNodeGroup')
        node.name = f'{active_material.name}_{TEXTURE_LOGIC_NODE_NAME}'
        node.label = f'{active_material.name} {TEXTURE_LOGIC_NODE_LABEL}'
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
        for item in instance.output_item_list:
            if item.scene_object:
                bpy.data.objects.remove(item.scene_object, do_unlink=True)
            if item.image_object:
                bpy.data.images.remove(item.image_object, do_unlink=True)

        my_list.remove(self.active_index)
        to_index = min(self.active_index, len(my_list) - 1)
        context.scene.meta_human_dna.rig_logic_instance_list_active_index = to_index # type: ignore
        return {'FINISHED'}


class UILIST_RIG_LOGIC_OT_entry_add(GenericUIListOperator, bpy.types.Operator):
    """Add an entry to the list after the current active item"""

    bl_idname = "meta_human_dna.rig_logic_instance_entry_add"
    bl_label = "Add Entry"

    def execute(self, context):
        my_list = context.scene.meta_human_dna.rig_logic_instance_list # type: ignore
        to_index = min(len(my_list), self.active_index + 1)
        my_list.add()
        my_list.move(len(my_list) - 1, to_index)
        context.scene.meta_human_dna.rig_logic_instance_list_active_index = to_index # type: ignore
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

        if from_instance.head_rig and to_instance.head_rig:
            to_x = to_instance.head_rig.location.x
            from_x = from_instance.head_rig.location.x

            # swap the x locations of the rigs
            to_instance.head_rig.location.x = from_x
            from_instance.head_rig.location.x = to_x
        

        my_list.move(self.active_index, to_index)
        context.scene.meta_human_dna.rig_logic_instance_list_active_index = to_index # type: ignore
        return {'FINISHED'}