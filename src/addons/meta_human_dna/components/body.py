# standard library imports
import json
import logging

from pathlib import Path

# third party imports
import bpy

from mathutils import Vector

# local imports
from .. import utilities
from ..constants import BODY_TOPOLOGY_VERTEX_GROUPS_FILE_PATH, IS_BLENDER_5, TOPO_GROUP_PREFIX
from ..dna_io import DNAExporter
from ..utilities import exclude_rig_instance_evaluation, preserve_context
from .base import MetaHumanComponentBase


logger = logging.getLogger(__name__)


class MetaHumanComponentBody(MetaHumanComponentBase):
    @exclude_rig_instance_evaluation
    def import_action(
        self,
        file_path: Path,
        round_sub_frames: bool = True,
        match_frame_rate: bool = True,
        prefix_instance_name: bool = True,
        prefix_component_name: bool = True,
    ):
        file_path = Path(file_path)

        if self.body_rig_object and self.body_rig_object.pose:
            # ensure the rig instance is initialized
            self.rig_instance.initialize()
            utilities.import_action_from_fbx(
                instance=self.rig_instance,
                file_path=file_path,
                component="body",
                armature=self.body_rig_object,
                # include animation only for body that are not driven by rig logic
                include_only_bones=[
                    b.name
                    for b in self.body_rig_object.pose.bones
                    if b.name
                    not in [
                        *self.rig_instance.body_driven_bone_names,
                        *self.rig_instance.body_swing_bone_names,
                        *self.rig_instance.body_twist_bone_names,
                    ]
                ],
            )

    def ingest(self, align: bool = True, constrain: bool = True) -> tuple[bool, str]:
        valid, message = self.dna_importer.run()
        self.rig_instance.body_rig = self.dna_importer.rig_object

        self._organize_viewport()
        self.import_materials()

        # Note that the topology vertex groups are only valid for the default metahuman body mesh with 32334 vertices
        if len(self.dna_reader.getVertexLayoutPositionIndices(0)) == 32334:
            self.create_topology_vertex_groups()

        # set the references on the rig instance
        self.rig_instance.body_mesh = self.body_mesh_object
        self.rig_instance.body_rig = self.body_rig_object
        self.rig_instance.body_dna_file_path = str(self.dna_importer.source_dna_file)
        self.rig_instance.body_initialize()

        if self.body_rig_object and self.body_mesh_object:
            utilities.set_body_bone_collections(
                mesh_object=self.body_mesh_object,
                rig_object=self.body_rig_object,
                swing_bone_names=self.rig_instance.body_swing_bone_names,
                twist_bone_names=self.rig_instance.body_twist_bone_names,
                driver_bone_names=self.rig_instance.body_driver_bone_names,
                driven_bone_names=self.rig_instance.body_driven_bone_names,
            )
            # if this isn't the first rig, move it to the right of the last body mesh
            if len(self.scene_properties.rig_instance_list) > 1:
                last_instance = self.scene_properties.rig_instance_list[-2]
                if last_instance.body_mesh:
                    self.body_rig_object.location.x = utilities.get_bounding_box_left_x(last_instance.body_mesh) - (
                        utilities.get_bounding_box_width(last_instance.body_mesh) / 2
                    )

        # focus the view on body object
        if self.rig_instance.body_mesh:
            utilities.select_only(self.rig_instance.body_mesh)
            utilities.focus_on_selected()

        # collapse the outliner
        utilities.toggle_expand_in_outliner()

        return valid, message

    @preserve_context
    def convert(self, mesh_object: bpy.types.Object, constrain: bool = True):
        from ..bindings import meta_human_dna_core  # pyright: ignore[reportAttributeAccessIssue]

        if self.body_mesh_object and self.body_rig_object:
            target_height = utilities.get_bounding_box_height(mesh_object)
            body_height = utilities.get_bounding_box_height(self.body_mesh_object)
            delta = target_height / body_height

            # scale the body rig and the body mesh to match the target height
            self.body_rig_object.scale.x *= delta
            self.body_rig_object.scale.y *= delta
            self.body_rig_object.scale.z *= delta

            self.body_rig_object.hide_set(False)
            utilities.apply_transforms(self.body_rig_object, scale=True, recursive=True)

            # adjust the head rig origin to zero
            utilities.switch_to_object_mode()
            # select all the objects and set their origins to the 3d cursor
            utilities.deselect_all()
            for item in self.rig_instance.output_body_item_list:
                if item.scene_object:
                    item.scene_object.hide_set(False)
                    item.scene_object.select_set(True)
                    if bpy.context.view_layer:
                        bpy.context.view_layer.objects.active = item.scene_object
            self.body_rig_object.select_set(True)
            if bpy.context.scene:
                bpy.context.scene.cursor.location = Vector((0, 0, 0))
            bpy.ops.object.origin_set(type="ORIGIN_CURSOR")

            from_bmesh_object = DNAExporter.get_bmesh(mesh_object=mesh_object, rotation=0)
            from_data = {
                "name": mesh_object.name,
                "uv_data": DNAExporter.get_mesh_vertex_uvs(from_bmesh_object),
                "vertex_data": DNAExporter.get_mesh_vertex_positions(from_bmesh_object),
            }
            to_bmesh_object = DNAExporter.get_bmesh(mesh_object=mesh_object, rotation=0)
            to_data = {
                "name": self.body_mesh_object.name,
                "uv_data": DNAExporter.get_mesh_vertex_uvs(to_bmesh_object),
                "vertex_data": DNAExporter.get_mesh_vertex_positions(to_bmesh_object),
                "dna_reader": self.dna_reader,
            }

            from_bmesh_object.free()
            to_bmesh_object.free()

            vertex_positions = meta_human_dna_core.calculate_dna_mesh_vertex_positions(from_data, to_data)
            if isinstance(self.body_mesh_object.data, bpy.types.Mesh):
                self.body_mesh_object.data.vertices.foreach_set("co", vertex_positions.ravel())  # type: ignore[attr-defined]
                self.body_mesh_object.data.update()

            utilities.auto_fit_bones(
                armature_object=self.body_rig_object,
                mesh_object=self.body_mesh_object,
                dna_reader=self.dna_reader,
                only_selected=False,
                component_type="body",
            )

            if constrain:
                self.snap_head_bones_to_body_bones()
                self.constrain_head_to_body()

    def export(self):
        pass

    def delete(self):
        for item in self.rig_instance.output_body_item_list:
            if item.scene_object:
                bpy.data.objects.remove(item.scene_object, do_unlink=True)
            if item.image_object:
                bpy.data.images.remove(item.image_object, do_unlink=True)

        self._delete_rig_instance()

    def create_topology_vertex_groups(self):
        if not self.dna_import_properties.import_mesh:
            return

        if self.body_mesh_object:
            with BODY_TOPOLOGY_VERTEX_GROUPS_FILE_PATH.open() as file:
                data = json.load(file)
                logger.info("Creating topology vertex groups...")
                for vertex_group_name, vertex_indexes in data.items():
                    # get the existing vertex_group or create a new one
                    vertex_group = self.body_mesh_object.vertex_groups.get(vertex_group_name)
                    if not vertex_group:
                        vertex_group = self.body_mesh_object.vertex_groups.new(name=vertex_group_name)

                    vertex_group.add(index=vertex_indexes, weight=1.0, type="REPLACE")

    def select_vertex_group(self):
        if self.rig_instance and self.rig_instance.body_mesh:
            # TODO: Fix once there are topology vertex groups for all LODS
            self.rig_instance.active_lod = "lod0"
            utilities.select_vertex_group(
                mesh_object=self.rig_instance.body_mesh,
                vertex_group_name=self.rig_instance.body_mesh_topology_groups,
                add=self.rig_instance.mesh_topology_selection_mode == "add",
            )

    def select_bone_group(self):
        if self.rig_instance and self.rig_instance.body_rig:
            if self.rig_instance.rig_bone_group_selection_mode != "add":
                # deselect all bones first
                for pose_bone in self.rig_instance.body_rig.pose.bones:
                    # Note: In Blender 5.0+, the select property moved from Bone to PoseBone
                    if IS_BLENDER_5:
                        pose_bone.select = False
                    else:
                        pose_bone.bone.select = False

            from ..bindings import meta_human_dna_core  # pyright: ignore[reportAttributeAccessIssue]

            for bone_name in meta_human_dna_core.BODY_BONE_SELECTION_GROUPS.get(
                self.rig_instance.body_rig_bone_groups, []
            ):
                pose_bone = self.rig_instance.body_rig.pose.bones.get(bone_name)
                if pose_bone:
                    if IS_BLENDER_5:
                        pose_bone.select = True
                    else:
                        pose_bone.bone.select = True

            if self.rig_instance.body_rig_bone_groups.startswith(TOPO_GROUP_PREFIX):
                for bone in utilities.get_topology_group_surface_bones(
                    mesh_object=self.rig_instance.body_mesh,
                    armature_object=self.rig_instance.body_rig,
                    vertex_group_name=self.rig_instance.body_rig_bone_groups,
                    dna_reader=self.dna_reader,
                ):
                    pose_bone = self.rig_instance.body_rig.pose.bones.get(bone.name)
                    if pose_bone:
                        if IS_BLENDER_5:
                            pose_bone.select = True
                        else:
                            pose_bone.bone.select = True

            self.rig_instance.body_rig.hide_set(False)
            utilities.switch_to_pose_mode(self.rig_instance.body_rig)

    def shrink_wrap_vertex_group(self):
        if self.rig_instance and self.rig_instance.body_mesh:
            modifier = self.rig_instance.body_mesh.modifiers.get(self.rig_instance.body_mesh_topology_groups)
            if not modifier:
                modifier = self.rig_instance.body_mesh.modifiers.new(
                    name=self.rig_instance.body_mesh_topology_groups, type="SHRINKWRAP"
                )
                modifier.show_viewport = False
                modifier.wrap_method = "PROJECT"
                modifier.use_negative_direction = True

            modifier.target = self.rig_instance.head_shrink_wrap_target
            modifier.vertex_group = self.rig_instance.body_mesh_topology_groups
            # toggle the visibility of the modifier
            modifier.show_viewport = not modifier.show_viewport

            utilities.set_vertex_selection(mesh_object=self.rig_instance.body_mesh, vertex_indexes=[], add=False)
            utilities.select_vertex_group(
                mesh_object=self.rig_instance.body_mesh, vertex_group_name=self.rig_instance.body_mesh_topology_groups
            )

    @preserve_context
    def revert_bone_transforms_to_dna(self):
        pass
