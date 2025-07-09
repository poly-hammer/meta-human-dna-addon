import bpy
import json
import logging
from pathlib import Path
from .. import utilities
from ..utilities import preserve_context
from .base import MetaHumanComponentBase
from ..constants import BODY_TOPOLOGY_VERTEX_GROUPS_FILE_PATH

logger = logging.getLogger(__name__)


class MetaHumanComponentBody(MetaHumanComponentBase):
    def import_action(self, file_path: Path):
        pass

    def ingest(self) -> tuple[bool, str]:        
        valid, message = self.dna_importer.run()
        self.rig_logic_instance.body_rig = self.dna_importer.rig_object

        self._organize_viewport()
        self.import_materials()

        # Note that the topology vertex groups are only valid for the default metahuman body mesh with 32334 vertices
        if len(self.dna_reader.getVertexLayoutPositionIndices(0)) == 32334:
            self.create_topology_vertex_groups()

        # set the references on the rig logic instance
        self.rig_logic_instance.body_mesh = self.body_mesh_object
        self.rig_logic_instance.body_rig = self.body_rig_object
        self.rig_logic_instance.body_dna_file_path = str(self.dna_importer.source_dna_file)

        if self.body_rig_object and self.body_mesh_object:
            utilities.set_body_bone_collections(
                mesh_object=self.body_mesh_object,
                rig_object=self.body_rig_object,
            )
            # if this isn't the first rig, move it to the right of the last body mesh
            if len(self.scene_properties.rig_logic_instance_list) > 1:
                last_instance = self.scene_properties.rig_logic_instance_list[-2] # type: ignore
                if last_instance.body_mesh:
                    self.body_rig_object.location.x = utilities.get_bounding_box_left_x(last_instance.body_mesh) - (utilities.get_bounding_box_width(last_instance.body_mesh) / 2)


        # focus the view on body object
        if self.rig_logic_instance.body_mesh:
            utilities.select_only(self.rig_logic_instance.body_mesh)
            utilities.focus_on_selected()

        # collapse the outliner
        utilities.toggle_expand_in_outliner()
        
        return valid, message

    @preserve_context
    def convert(self, mesh_object: bpy.types.Object):
        pass
        
    def export(self):
        pass

    def delete(self):
        pass

    def create_topology_vertex_groups(self):
        if not self.dna_import_properties.import_mesh:
            return

        if self.body_mesh_object:
            with open(BODY_TOPOLOGY_VERTEX_GROUPS_FILE_PATH, 'r') as file:
                data = json.load(file)
                logger.info("Creating topology vertex groups...")
                for vertex_group_name, vertex_indexes in data.items():
                    # get the existing vertex_group or create a new one
                    vertex_group = self.body_mesh_object.vertex_groups.get(vertex_group_name)
                    if not vertex_group:
                        vertex_group = self.body_mesh_object.vertex_groups.new(name=vertex_group_name)

                    vertex_group.add(
                        index=vertex_indexes,
                        weight=1.0,
                        type='REPLACE'
                    )

    def select_vertex_group(self):
        if self.rig_logic_instance and self.rig_logic_instance.body_mesh:
            utilities.select_vertex_group(
                mesh_object=self.rig_logic_instance.body_mesh,
                vertex_group_name=self.rig_logic_instance.body_mesh_topology_groups,
                add=self.rig_logic_instance.mesh_topology_selection_mode == 'add'
            )

    def select_bone_group(self):
        pass
            
    def shrink_wrap_vertex_group(self):
        if self.rig_logic_instance and self.rig_logic_instance.body_mesh:
            modifier = self.rig_logic_instance.body_mesh.modifiers.get(self.rig_logic_instance.body_mesh_topology_groups)
            if not modifier:
                modifier = self.rig_logic_instance.body_mesh.modifiers.new(name=self.rig_logic_instance.body_mesh_topology_groups, type='SHRINKWRAP')
                modifier.show_viewport = False
                modifier.wrap_method = 'PROJECT'
                modifier.use_negative_direction = True

            modifier.target = self.rig_logic_instance.head_shrink_wrap_target
            modifier.vertex_group = self.rig_logic_instance.body_mesh_topology_groups
            # toggle the visibility of the modifier
            modifier.show_viewport = not modifier.show_viewport

            utilities.set_vertex_selection(
                mesh_object=self.rig_logic_instance.body_mesh, 
                vertex_indexes=[],
                add=False
            )
            utilities.select_vertex_group(
                mesh_object=self.rig_logic_instance.body_mesh,
                vertex_group_name=self.rig_logic_instance.body_mesh_topology_groups
            )

    @preserve_context
    def revert_bone_transforms_to_dna(self):
        pass