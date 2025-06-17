import bpy
import logging
from pathlib import Path
from .. import utilities
from ..utilities import preserve_context
from .base import MetaHumanComponentBase

logger = logging.getLogger(__name__)


class MetaHumanComponentBody(MetaHumanComponentBase):
    def import_action(self, file_path: Path):
        pass

    def ingest(self) -> tuple[bool, str]:        
        valid, message = self.dna_importer.run()
        self.rig_logic_instance.head_rig = self.dna_importer.rig_object

        self._organize_viewport()
        self.import_materials()
        # import the face board if one does not already exist in the scene
        if not any(i.face_board for i in self.scene_properties.rig_logic_instance_list):
            face_board_object = self._import_face_board()
        else:
            face_board_object = next(i.face_board for i in self.scene_properties.rig_logic_instance_list if i.face_board)

        # Note that the topology vertex groups are only valid for the default metahuman head mesh with 24408 vertices
        if len(self.dna_reader.getVertexLayoutPositionIndices(0)) == 24408:
            self.create_topology_vertex_groups()

        # set the references on the rig logic instance
        self.rig_logic_instance.head_mesh = self.head_mesh_object
        self.rig_logic_instance.head_rig = self.head_rig_object
        self.rig_logic_instance.face_board = face_board_object

        if self.head_rig_object and self.head_mesh_object:
            utilities.set_bone_collections(
                mesh_object=self.head_mesh_object,
                rig_object=self.head_rig_object,
            )

            # if this isn't the first rig, move it to the right of the last head mesh
            if len(self.scene_properties.rig_logic_instance_list) > 1:
                last_instance = self.scene_properties.rig_logic_instance_list[-2] # type: ignore
                if last_instance.head_mesh:
                    self.head_rig_object.location.x = utilities.get_bounding_box_right_x(self.head_rig_object) - 0.5

            # then parent the rig to the face board
            self.head_rig_object.parent = face_board_object

        # focus the view on head object
        if self.rig_logic_instance.head_mesh:
            utilities.select_only(self.rig_logic_instance.head_mesh)
            utilities.focus_on_selected()

        # collapse the outliner
        utilities.toggle_expand_in_outliner()

        # switch to pose mode on the face gui object
        if face_board_object:
            bpy.context.view_layer.objects.active = face_board_object # type: ignore
            utilities.switch_to_pose_mode(face_board_object) # type: ignore
        
        return valid, message

    @preserve_context
    def convert(self, mesh_object: bpy.types.Object):
        pass
        
    def export(self):
        pass

    def delete(self):
        pass

    def create_topology_vertex_groups(self):
        pass

    def select_vertex_group(self):
        pass

    def select_bone_group(self):
        pass
            
    def shrink_wrap_vertex_group(self):
        pass

    @preserve_context
    def revert_bone_transforms_to_dna(self):
        pass