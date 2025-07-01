import os
import sys
import bpy
from pathlib import Path
from mathutils import Vector
from send2ue.core.extension import ExtensionBase # type: ignore
from send2ue.core.utilities import report_error # type: ignore
from send2ue.core.formatting import auto_format_unreal_folder_path, auto_format_unreal_asset_path # type: ignore
from send2ue.dependencies.rpc.factory import make_remote # type: ignore
from send2ue.core.export import export_file # type: ignore


class MetaHumanDna(ExtensionBase):
    name = 'meta_human_dna'
    
    enabled: bpy.props.BoolProperty(default=False) # type: ignore
    mesh_object_name: bpy.props.StringProperty(default='') # type: ignore
    asset_path: bpy.props.StringProperty(default='') # type: ignore

    @staticmethod
    def get_active_rig_logic():
        from meta_human_dna.ui.callbacks import get_active_rig_logic
        return get_active_rig_logic()
    
    @staticmethod
    def deselect_all():
        from meta_human_dna.utilities import deselect_all
        deselect_all()
    
    @staticmethod
    def get_lod_index(name: str) -> int:
        from meta_human_dna.utilities import get_lod_index
        return get_lod_index(name)


    def pre_operation(self, properties):
        # prevent continuous evaluation of the dependency graph by rig logic
        bpy.context.window_manager.meta_human_dna.evaluate_dependency_graph = False # type: ignore

        # clear the face board control and evaluate the rig so it is in a neutral position
        instance = self.get_active_rig_logic()
        if instance:
            for pose_bone in instance.face_board.pose.bones:
                if not pose_bone.bone.children and pose_bone.name.startswith('CTRL_'):
                    pose_bone.location = Vector((0.0, 0.0, 0.0))
            instance.evaluate()


    def pre_validations(self, properties) -> bool:
        if self.enabled:
            instance = self.get_active_rig_logic()
            if instance and instance.head_mesh:
                # validate folder path
                error = auto_format_unreal_folder_path('unreal_content_folder', instance)
                if error:
                    report_error(error)
                    return False

                # validate asset paths
                for prop_name in [
                    'unreal_blueprint_asset_path', 
                    'unreal_face_control_rig_asset_path', 
                    'unreal_face_anim_bp_asset_path'
                ]:
                    error = auto_format_unreal_asset_path(prop_name, instance)
                    if error:
                        report_error(error)
                        return False
                    
                # validate material instance paths
                for item in instance.unreal_material_slot_to_instance_mapping:
                    error = auto_format_unreal_asset_path('asset_path', item)
                    if error:
                        report_error(error)
                        return False
        return True
    
    def pre_mesh_export(self, asset_data, properties):
        if self.enabled:
            instance = self.get_active_rig_logic()
            mesh_object_name = asset_data.get('_mesh_object_name', '')
            mesh_object = bpy.data.objects.get(mesh_object_name)
            # only proceed if the mesh object is the head mesh
            if instance and instance.head_mesh == mesh_object:
                # deselect all objects
                self.deselect_all()

                # override the selected objects with the output item list
                for item in instance.output_head_item_list:
                    if item.scene_object and item.include:
                        # select only lod 0 and non lods -1
                        if self.get_lod_index(item.scene_object.name) in [-1, 0]:
                            # object must be visible to be selected
                            item.scene_object.hide_set(False)
                            item.scene_object.select_set(True)

                # rename the asset to match the instance name
                _, extension = os.path.splitext(asset_data['file_path'])
                
                file_path = Path(bpy.path.abspath(instance.output_folder_path)).absolute() / 'export' / f'{instance.name}{extension}'
                asset_folder = '/' + '/'.join([i for i in instance.unreal_content_folder.split('/') if i]) + '/'

                # update the the file path, asset folder and asset path
                self.update_asset_data({
                    'asset_folder': asset_folder,
                    'file_path': str(file_path),
                    'asset_path': f'{asset_folder}{instance.name}'
                })

    def post_mesh_export(self, asset_data, properties):
        if self.enabled:
            if asset_data.get('lods'):
                # make send2ue skip exporting the lods, we will do it manually in the pre_import
                self.update_asset_data({
                    'skip': True
                })

    def pre_import(self, asset_data, properties):
        if self.enabled:
            instance = self.get_active_rig_logic()
            mesh_object_name = asset_data.get('_mesh_object_name', '')
            mesh_object = bpy.data.objects.get(mesh_object_name)
            # only proceed if the mesh object is the head mesh
            if instance and instance.head_mesh == mesh_object:
                lods = {}
                # determine how many lods are available and their file paths
                lod_indexes = []
                for item in instance.output_head_item_list:
                    if item.scene_object and item.include:
                        lod_index = self.get_lod_index(item.scene_object.name)
                        if lod_index not in [0, -1] and lod_index not in lod_indexes:
                            main_file_path = Path(asset_data['file_path'])
                            file_path = main_file_path.parent / f'{main_file_path.stem}_lod{lod_index}_mesh.fbx'
                            lod_indexes.append(lod_index)
                            lods[str(lod_index)] = str(file_path)
                
                # update the lod data
                self.update_asset_data({
                    'lods': lods,
                    'skip': False
                })

                # now loop through each lod and export it
                for lod_index in lod_indexes:
                    if lod_index == 0:
                        continue
                    
                    # deselect all objects
                    self.deselect_all()

                    # select the objects for the current lod
                    for item in instance.output_head_item_list:
                        if item.scene_object and item.include:
                            if self.get_lod_index(item.scene_object.name) == lod_index:
                                # object must be visible to be selected
                                item.scene_object.hide_set(False)
                                item.scene_object.select_set(True)
                    
                    # also select the head rig
                    instance.head_rig.hide_set(False)
                    instance.head_rig.select_set(True)
                    # export the file
                    export_file(
                        properties=properties,
                        lod=lod_index
                    )

    def post_import(self, asset_data, properties):
        if self.enabled:
            self.mesh_object_name = asset_data.get('_mesh_object_name', '')
            self.asset_path = asset_data.get('asset_path', '')
        
    def post_operation(self, properties):
        # defer this till the lods are imported
        if self.enabled:
            # make sure that the unreal utilities are available
            import meta_human_dna_utilities
            folder = Path(meta_human_dna_utilities.__file__).parent.parent
            if Path(folder) not in [Path(path) for path in sys.path]:
                sys.path.append(str(folder))
            from meta_human_dna_utilities import update_meta_human_face

            # remotely update the dna
            instance = self.get_active_rig_logic()
            mesh_object = bpy.data.objects.get(self.mesh_object_name)
            material_name =  ''
            if instance.head_material: # type: ignore
                material_name = instance.head_material.name # type: ignore

            # only proceed if the mesh object is the head mesh
            if instance and instance.head_mesh == mesh_object:
                remote_update_meta_human_face = make_remote(update_meta_human_face)
                remote_update_meta_human_face(
                    self.asset_path,
                    str(Path(bpy.path.abspath(instance.output_folder_path)).absolute() / f'export/{instance.name}.dna'),
                    material_name,
                    instance.unreal_face_control_rig_asset_path,
                    instance.unreal_face_anim_bp_asset_path,
                    instance.unreal_blueprint_asset_path,
                    instance.unreal_level_sequence_asset_path,
                    instance.unreal_copy_assets,
                    {item.name: item.asset_path for item in instance.unreal_material_slot_to_instance_mapping}
                )

        # Always disable the extension afterwards since we don't want this to be enabled
        # unless the explicitly enabled via code.
        self.enabled = False
        bpy.context.window_manager.meta_human_dna.evaluate_dependency_graph = True # type: ignore