import bpy
import json
import math
import queue
import logging
from pathlib import Path
from mathutils import Vector, Matrix
from .base import MetaHumanComponentBase
from .. import utilities
from ..utilities import preserve_context
from ..dna_io import (
    create_shape_key,
    DNAExporter
)
from ..constants import (
    HEAD_TOPOLOGY_VERTEX_GROUPS_FILE_PATH,
    TOPO_GROUP_PREFIX,
    EXTRA_BONES,
    DEFAULT_HEAD_MESH_VERTEX_POSITION_COUNT
)

logger = logging.getLogger(__name__)


class MetaHumanComponentHead(MetaHumanComponentBase):
    def import_action(self, file_path: Path):
        file_path = Path(file_path)
        if not self.face_board_object:
            return
        
        if file_path.suffix.lower() == '.json':
            utilities.import_action_from_json(file_path, self.face_board_object)    
        elif file_path.suffix.lower() == '.fbx':
            utilities.import_action_from_fbx(file_path, self.face_board_object)

    def ingest(
            self, 
            align: bool = True, 
            constrain: bool = True
        ) -> tuple[bool, str]:
        valid, message = self.dna_importer.run()
        self.rig_logic_instance.head_rig = self.dna_importer.rig_object

        self._organize_viewport()
        self.import_materials()
        # import the face board if one does not already exist in the scene
        if not any(i.face_board for i in self.scene_properties.rig_logic_instance_list):
            face_board_object = self._import_face_board()
        elif not self.rig_logic_instance.face_board and not self.dna_import_properties.reuse_face_board:
            face_board_object = self._duplicate_face_board()
        else:
            face_board_object = next(i.face_board for i in self.scene_properties.rig_logic_instance_list if i.face_board)

        # Note that the topology vertex groups are only valid for the default metahuman head mesh with 24408 vertices
        if len(self.dna_reader.getVertexLayoutPositionIndices(0)) == DEFAULT_HEAD_MESH_VERTEX_POSITION_COUNT:
            self.create_topology_vertex_groups()

        # set the references on the rig logic instance
        self.rig_logic_instance.head_mesh = self.head_mesh_object
        self.rig_logic_instance.head_rig = self.head_rig_object
        self.rig_logic_instance.face_board = face_board_object

        if self.head_rig_object and self.head_mesh_object:
            utilities.set_head_bone_collections(
                mesh_object=self.head_mesh_object,
                rig_object=self.head_rig_object,
            )
            
            if self.body_rig_object and align:
                # Align the head rig with the body rig if it exists
                body_object_head_bone = self.body_rig_object.pose.bones.get('head') # type: ignore
                head_object_head_bone = self.head_rig_object.pose.bones.get('head') # type: ignore
                if body_object_head_bone and head_object_head_bone:
                    # get the location offset between the body head bone and the head head bone
                    body_head_location = body_object_head_bone.matrix @ Vector((0, 0, 0))
                    head_head_location = head_object_head_bone.matrix @ Vector((0, 0, 0))
                    delta = body_head_location - head_head_location
                    # move the head rig object to align with the body rig head bone
                    self.head_rig_object.location += delta
            else:
                # if this isn't the first rig, move it to the right of the last head mesh
                if len(self.scene_properties.rig_logic_instance_list) > 1:
                    last_instance = self.scene_properties.rig_logic_instance_list[-2] # type: ignore
                    if last_instance.head_mesh:
                        self.head_rig_object.location.x = utilities.get_bounding_box_left_x(last_instance.head_mesh) - (utilities.get_bounding_box_width(last_instance.head_mesh) / 2)

        # constrain the head rig to the body rig if it exists
        if constrain:
            self.constrain_head_to_body()

        # focus the view on head object
        if self.rig_logic_instance.head_mesh:
            utilities.select_only(self.rig_logic_instance.head_mesh)
            utilities.focus_on_selected()

        # collapse the outliner
        utilities.toggle_expand_in_outliner()

        # switch to pose mode on the face gui object
        if face_board_object:
            bpy.context.view_layer.objects.active = face_board_object # type: ignore
            self._position_face_board(face_board_object)
            utilities.move_to_collection(
                scene_objects=[face_board_object],
                collection_name=self.name,
                exclusively=True
            )
            utilities.switch_to_pose_mode(face_board_object) # type: ignore
        
        return valid, message

    @preserve_context
    def convert(self, mesh_object: bpy.types.Object, constrain: bool = True):
        from ..bindings import meta_human_dna_core
        if self.head_mesh_object and self.face_board_object and self.head_rig_object:
            target_center = utilities.get_bounding_box_center(mesh_object)
            head_center = utilities.get_bounding_box_center(self.head_mesh_object)
            delta = target_center - head_center

            # translate the head rig and the face board
            self.head_rig_object.location += delta
            self.face_board_object.location += delta

            # must be unhidden to switch to edit bone mode
            self.head_rig_object.hide_set(False) # type: ignore
            utilities.switch_to_bone_edit_mode(self.head_rig_object)
            # adjust the root bone so the root bone is still at zero
            root_bone = self.head_rig_object.data.edit_bones.get('root') # type: ignore
            if root_bone:
                root_bone.head.z -= delta.z
                root_bone.tail.z -= delta.z

            # adjust the head rig origin to zero
            utilities.switch_to_object_mode() # type: ignore
            # select all the objects and set their origins to the 3d cursor
            utilities.deselect_all()
            for item in self.rig_logic_instance.output_head_item_list:
                if item.scene_object:
                    item.scene_object.hide_set(False)
                    item.scene_object.select_set(True)
                    bpy.context.view_layer.objects.active = item.scene_object # type: ignore
            self.face_board_object.select_set(True)
            self.head_rig_object.select_set(True)

            bpy.context.scene.cursor.location = Vector((0, 0, 0)) # type: ignore
            bpy.ops.object.origin_set(type='ORIGIN_CURSOR')

            from_bmesh_object = DNAExporter.get_bmesh(mesh_object=mesh_object, rotation=0)
            from_data = {
                'name': mesh_object.name,
                'uv_data': DNAExporter.get_mesh_vertex_uvs(from_bmesh_object),
                'vertex_data': DNAExporter.get_mesh_vertex_positions(from_bmesh_object)
            }
            to_bmesh_object = DNAExporter.get_bmesh(mesh_object=mesh_object, rotation=0)
            to_data = {
                'name': self.head_mesh_object.name,
                'uv_data': DNAExporter.get_mesh_vertex_uvs(to_bmesh_object),
                'vertex_data': DNAExporter.get_mesh_vertex_positions(to_bmesh_object),
                'dna_reader': self.dna_reader
            }

            from_bmesh_object.free()
            to_bmesh_object.free()

            vertex_positions = meta_human_dna_core.calculate_dna_mesh_vertex_positions(from_data, to_data)
            self.head_mesh_object.data.vertices.foreach_set("co", vertex_positions.ravel()) # type: ignore
            self.head_mesh_object.data.update() # type: ignore

            utilities.auto_fit_bones(
                armature_object=self.head_rig_object,
                mesh_object=self.head_mesh_object,
                dna_reader=self.dna_reader,
                only_selected=False,
                component_type='head'
            )

            if constrain:
                self.snap_head_bones_to_body_bones()
                self.constrain_head_to_body()

    def export(self):
        pass

    def delete(self):
        for item in self.rig_logic_instance.output_head_item_list:
            if item.scene_object:
                bpy.data.objects.remove(item.scene_object, do_unlink=True)
            if item.image_object:
                bpy.data.images.remove(item.image_object, do_unlink=True)

        self._delete_rig_logic_instance()

    def create_topology_vertex_groups(self):
        if not self.dna_import_properties.import_mesh:
            return

        if self.head_mesh_object:
            with open(HEAD_TOPOLOGY_VERTEX_GROUPS_FILE_PATH, 'r') as file:
                data = json.load(file)
                logger.info("Creating topology vertex groups...")
                for vertex_group_name, vertex_indexes in data.items():
                    # get the existing vertex_group or create a new one
                    vertex_group = self.head_mesh_object.vertex_groups.get(vertex_group_name)
                    if not vertex_group:
                        vertex_group = self.head_mesh_object.vertex_groups.new(name=vertex_group_name)

                    vertex_group.add(
                        index=vertex_indexes,
                        weight=1.0,
                        type='REPLACE'
                    )

    def select_vertex_group(self):
        if self.rig_logic_instance and self.rig_logic_instance.head_mesh:
            # TODO: Fix once there are topology vertex groups for all LODS
            self.rig_logic_instance.active_lod = 'lod0'
            utilities.select_vertex_group(
                mesh_object=self.rig_logic_instance.head_mesh,
                vertex_group_name=self.rig_logic_instance.head_mesh_topology_groups,
                add=self.rig_logic_instance.mesh_topology_selection_mode == 'add'
            )

    def select_bone_group(self):
        if self.rig_logic_instance and self.rig_logic_instance.head_rig:
            if self.rig_logic_instance.rig_bone_group_selection_mode != 'add':
                # deselect all bones first
                for bone in self.rig_logic_instance.head_rig.data.bones: # type: ignore
                    bone.select = False
            
            from ..bindings import meta_human_dna_core
            for bone_name in meta_human_dna_core.HEAD_BONE_SELECTION_GROUPS.get(self.rig_logic_instance.head_rig_bone_groups, []): # type: ignore
                bone = self.rig_logic_instance.head_rig.data.bones.get(bone_name) # type: ignore
                if bone:
                    bone.select = True

            if self.rig_logic_instance.head_rig_bone_groups.startswith(TOPO_GROUP_PREFIX):
                for bone in utilities.get_topology_group_surface_bones(
                    mesh_object=self.rig_logic_instance.head_mesh,
                    armature_object=self.rig_logic_instance.head_rig,
                    vertex_group_name=self.rig_logic_instance.head_rig_bone_groups,
                    dna_reader=self.dna_reader
                ):
                    bone.select = True

            self.rig_logic_instance.head_rig.hide_set(False)
            utilities.switch_to_pose_mode(self.rig_logic_instance.head_rig) # type: ignore

    def set_face_pose(self):        
        if self.rig_logic_instance.face_board:
            thumbnail_file = Path(bpy.context.window_manager.meta_human_dna.face_pose_previews) # type: ignore
            json_file_path = thumbnail_file.parent / 'pose.json'
            if json_file_path.exists():
                logger.info(f'Applying face pose from {json_file_path}')
                # dont evaluate while updating the face board transforms
                self.window_manager_properties.evaluate_dependency_graph = False
                with open(json_file_path, 'r') as file:
                    data = json.load(file)
                                        
                    # clear the pose location for all the control bones
                    for pose_bone in self.rig_logic_instance.face_board.pose.bones:
                        if not pose_bone.bone.children and pose_bone.name.startswith('CTRL_'):
                            pose_bone.location = Vector((0.0, 0.0, 0.0))

                    for bone_name, transform_data in data.items():
                        pose_bone = self.rig_logic_instance.face_board.pose.bones.get(bone_name) # type: ignore
                        if pose_bone:
                            pose_bone.location = Vector(transform_data['location'])

                self.window_manager_properties.evaluate_dependency_graph = True
                # now evaluate the face board
                self.rig_logic_instance.evaluate()

    def shrink_wrap_vertex_group(self):
        if self.rig_logic_instance and self.rig_logic_instance.head_mesh:
            modifier = self.rig_logic_instance.head_mesh.modifiers.get(self.rig_logic_instance.head_mesh_topology_groups)
            if not modifier:
                modifier = self.rig_logic_instance.head_mesh.modifiers.new(name=self.rig_logic_instance.head_mesh_topology_groups, type='SHRINKWRAP')
                modifier.show_viewport = False
                modifier.wrap_method = 'PROJECT'
                modifier.use_negative_direction = True

            modifier.target = self.rig_logic_instance.head_shrink_wrap_target
            modifier.vertex_group = self.rig_logic_instance.head_mesh_topology_groups
            # toggle the visibility of the modifier
            modifier.show_viewport = not modifier.show_viewport

            utilities.set_vertex_selection(
                mesh_object=self.rig_logic_instance.head_mesh, 
                vertex_indexes=[],
                add=False
            )
            utilities.select_vertex_group(
                mesh_object=self.rig_logic_instance.head_mesh,
                vertex_group_name=self.rig_logic_instance.head_mesh_topology_groups
            )

    @preserve_context
    def revert_bone_transforms_to_dna(self):
        if self.head_rig_object:
            extra_bone_lookup = dict(EXTRA_BONES)
            # make sure the dna importer has the rig object set
            self.dna_importer.rig_object = self.head_rig_object
            
            bone_names = [pose_bone.name for pose_bone in bpy.context.selected_pose_bones] # type: ignore
            utilities.switch_to_bone_edit_mode(self.rig_logic_instance.head_rig)
            
            for bone_name in bone_names:
                edit_bone = self.head_rig_object.data.edit_bones[bone_name] # type: ignore
                extra_bone = extra_bone_lookup.get(bone_name)
                if bone_name == 'root':
                    edit_bone.matrix = self.head_rig_object.matrix_world
                # reverts the default bone transforms back to their default values
                elif extra_bone:
                    location = extra_bone['location']
                    rotation = extra_bone['rotation']
                    # Scale the location of the bones based on the height scale factor
                    location.y = location.y * self.dna_importer.get_height_scale_factor()
                    global_matrix = Matrix.Translation(location) @ rotation.to_matrix().to_4x4()
                    # default values are stored in Y-up, so convert to Z-up
                    edit_bone.matrix = Matrix.Rotation(math.radians(90), 4, 'X').to_4x4() @ global_matrix
                else:
                    bone_matrix = self.dna_importer.get_bone_matrix(bone_name=bone_name)
                    if bone_matrix:
                        edit_bone.matrix = bone_matrix

    @utilities.exclude_rig_logic_evaluation
    def import_shape_keys(self, commands_queue: queue.Queue) -> list:
        if not self.head_mesh_object:
            raise ValueError('Head mesh object not found!')
        
        commands = []

        def get_initialize_kwargs(index: int, mesh_index: int):
            mesh_dna_name = self.dna_reader.getMeshName(mesh_index)
            mesh_object = bpy.data.objects.get(f'{self.name}_{mesh_dna_name}')
            return {
                'mesh_object': mesh_object,
            }

        def get_create_kwargs(index: int, mesh_index: int):
            channel_index = self.dna_reader.getBlendShapeChannelIndex(mesh_index, index)
            shape_key_name = self.dna_reader.getBlendShapeChannelName(channel_index)
            mesh_dna_name = self.dna_reader.getMeshName(mesh_index)
            mesh_object = bpy.data.objects.get(f'{self.name}_{mesh_dna_name}')
            return {
                'index': index,
                'mesh_index': mesh_index,
                'mesh_object': mesh_object,
                'reader': self.dna_reader,
                'name': shape_key_name,
                'is_neutral': self.rig_logic_instance.generate_neutral_shapes,
                'linear_modifier': self.linear_modifier,
                'prefix': f'{mesh_dna_name}__'
            }

        for mesh_index in range(self.dna_reader.getMeshCount()):
            count = self.dna_reader.getBlendShapeTargetCount(mesh_index)
            if count > 0:
                commands_queue.put((
                    0, 
                    mesh_index,
                    'Initializing basis shape...',
                    get_initialize_kwargs,
                    lambda **kwargs: utilities.initialize_basis_shape_key(**kwargs)
                ))
                
            for index in range(count):
                commands_queue.put((
                    index, 
                    mesh_index,
                    f'{index}/{count}' + ' {name} ...',
                    get_create_kwargs,
                    lambda **kwargs: create_shape_key(**kwargs)
                ))
        
        return commands