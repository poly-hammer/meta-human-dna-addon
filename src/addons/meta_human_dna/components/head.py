# standard library imports
import json
import logging
import math
import queue

from pathlib import Path

# third party imports
import bpy

from mathutils import Matrix, Vector

# local imports
from .. import utilities
from ..constants import (
    DEFAULT_HEAD_MESH_VERTEX_POSITION_COUNT,
    EXTRA_BONES,
    HEAD_TOPOLOGY_VERTEX_GROUPS_FILE_PATH,
    IS_BLENDER_5,
    TOPO_GROUP_PREFIX,
)
from ..dna_io import DNAExporter, create_shape_key
from ..utilities import exclude_rig_instance_evaluation, preserve_context
from .base import MetaHumanComponentBase


logger = logging.getLogger(__name__)


class MetaHumanComponentHead(MetaHumanComponentBase):
    @exclude_rig_instance_evaluation
    def import_action(
        self,
        file_path: Path,
        is_face_board: bool = True,
        round_sub_frames: bool = True,
        match_frame_rate: bool = True,
        prefix_instance_name: bool = True,
        prefix_component_name: bool = True,
    ):
        file_path = Path(file_path)

        if is_face_board and self.face_board_object:
            if file_path.suffix.lower() == ".json":
                utilities.import_face_board_action_from_json(file_path, self.face_board_object)
            elif file_path.suffix.lower() == ".fbx":
                utilities.import_face_board_action_from_fbx(
                    instance=self.rig_instance,
                    file_path=file_path,
                    armature=self.face_board_object,
                    round_sub_frames=round_sub_frames,
                    match_frame_rate=match_frame_rate,
                    prefix_instance_name=prefix_instance_name,
                    prefix_component_name=prefix_component_name,
                )
        elif self.head_rig_object:
            utilities.import_action_from_fbx(
                instance=self.rig_instance,
                file_path=file_path,
                component="head",
                armature=self.head_rig_object,
                round_sub_frames=round_sub_frames,
                match_frame_rate=match_frame_rate,
                prefix_instance_name=prefix_instance_name,
                prefix_component_name=prefix_component_name,
            )

    def ingest(self, align: bool = True, constrain: bool = True) -> tuple[bool, str]:  # noqa: PLR0912
        valid, message = self.dna_importer.run()
        self.rig_instance.head_rig = self.dna_importer.rig_object

        self._organize_viewport()
        self.import_materials()

        face_board_object = None
        # import the face board if one does not already exist in the scene
        if not any(i.face_board for i in self.scene_properties.rig_instance_list):
            if self.dna_import_properties.import_face_board:
                face_board_object = utilities.import_face_board(name=self.name)

        elif not self.rig_instance.face_board and not self.dna_import_properties.reuse_face_board:
            if self.dna_import_properties.import_face_board:
                face_board_object = utilities.duplicate_face_board(name=self.name)
        else:
            face_board_object = next(i.face_board for i in self.scene_properties.rig_instance_list if i.face_board)

        # Note that the topology vertex groups are only valid for the default metahuman head mesh with 24408 vertices
        if len(self.dna_reader.getVertexLayoutPositionIndices(0)) == DEFAULT_HEAD_MESH_VERTEX_POSITION_COUNT:
            self.create_topology_vertex_groups()

        # set the references on the rig instance
        self.rig_instance.head_mesh = self.head_mesh_object
        self.rig_instance.head_rig = self.head_rig_object
        self.rig_instance.face_board = face_board_object

        if self.head_rig_object and self.head_mesh_object and self.head_rig_object.pose:
            utilities.set_head_bone_collections(
                mesh_object=self.head_mesh_object,
                rig_object=self.head_rig_object,
            )

            if self.body_rig_object and self.body_rig_object.pose:
                # Add the additional driver bones from the head to the body rig,
                # since they share these same bones for driving the neck rbfs
                utilities.reassign_to_body_bone_collections(
                    rig_object=self.body_rig_object,
                    driver_bone_names=tuple(
                        self.dna_reader.getRawControlName(i).split(".")[0]
                        for i in range(self.dna_reader.getRawControlCount())
                    ),
                )

                if align:
                    # Align the head rig with the body rig if it exists
                    body_object_head_bone = self.body_rig_object.pose.bones.get("head")
                    head_object_head_bone = self.head_rig_object.pose.bones.get("head")
                    if body_object_head_bone and head_object_head_bone:
                        # get the location offset between the body head bone and the head head bone
                        body_head_location = body_object_head_bone.matrix @ Vector((0, 0, 0))
                        head_head_location = head_object_head_bone.matrix @ Vector((0, 0, 0))
                        delta = body_head_location - head_head_location
                        # move the head rig object to align with the body rig head bone
                        self.head_rig_object.location += delta
            # if this isn't the first rig, move it to the right of the last head mesh
            elif len(self.scene_properties.rig_instance_list) > 1:
                last_instance = self.scene_properties.rig_instance_list[-2]
                if last_instance.head_mesh:
                    self.head_rig_object.location.x = utilities.get_bounding_box_left_x(last_instance.head_mesh) - (
                        utilities.get_bounding_box_width(last_instance.head_mesh) / 2
                    )

        # constrain the head rig to the body rig if it exists
        if constrain:
            self.constrain_head_to_body()

        # focus the view on head object
        if self.rig_instance.head_mesh:
            utilities.select_only(self.rig_instance.head_mesh)
            utilities.focus_on_selected()

        # collapse the outliner
        utilities.toggle_expand_in_outliner()

        # switch to pose mode on the face gui object
        if face_board_object and bpy.context.view_layer:
            bpy.context.view_layer.objects.active = face_board_object
            utilities.position_face_board(
                head_mesh_object=self.head_mesh_object,
                head_rig_object=self.head_rig_object,
                face_board_object=face_board_object,
            )
            utilities.move_to_collection(scene_objects=[face_board_object], collection_name=self.name, exclusively=True)
            utilities.switch_to_pose_mode(face_board_object)
            # constrain the face board to the head rig if it was just created
            if not self.dna_import_properties.reuse_face_board:
                utilities.constrain_face_board_to_head(
                    face_board_object=face_board_object,
                    head_rig_object=self.rig_instance.head_rig,
                    body_rig_object=self.rig_instance.body_rig,
                    bone_name="CTRL_faceGUI",
                )
                utilities.constrain_face_board_to_head(
                    face_board_object=face_board_object,
                    head_rig_object=self.rig_instance.head_rig,
                    body_rig_object=self.rig_instance.body_rig,
                    bone_name="CTRL_C_eyesAim",
                )

        return valid, message

    @preserve_context
    def convert(self, mesh_object: bpy.types.Object, constrain: bool = True):
        from ..bindings import meta_human_dna_core  # pyright: ignore[reportAttributeAccessIssue]

        if (
            self.head_mesh_object
            and self.face_board_object
            and self.head_rig_object
            and isinstance(self.head_rig_object.data, bpy.types.Armature)
        ):
            target_center = utilities.get_bounding_box_center(mesh_object)
            head_center = utilities.get_bounding_box_center(self.head_mesh_object)
            delta = target_center - head_center

            # translate the head rig and the face board
            self.head_rig_object.location += delta
            self.face_board_object.location += delta

            # must be unhidden to switch to edit bone mode
            self.head_rig_object.hide_set(False)
            utilities.switch_to_bone_edit_mode(self.head_rig_object)
            # adjust the root bone so the root bone is still at zero
            root_bone = self.head_rig_object.data.edit_bones.get("root")
            if root_bone:
                root_bone.head.z -= delta.z
                root_bone.tail.z -= delta.z

            # adjust the head rig origin to zero
            utilities.switch_to_object_mode()
            # select all the objects and set their origins to the 3d cursor
            utilities.deselect_all()
            for item in self.rig_instance.output_head_item_list:
                if item.scene_object:
                    item.scene_object.hide_set(False)
                    item.scene_object.select_set(True)
                    if bpy.context.view_layer:
                        bpy.context.view_layer.objects.active = item.scene_object
            self.face_board_object.select_set(True)
            self.head_rig_object.select_set(True)

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
                "name": self.head_mesh_object.name,
                "uv_data": DNAExporter.get_mesh_vertex_uvs(to_bmesh_object),
                "vertex_data": DNAExporter.get_mesh_vertex_positions(to_bmesh_object),
                "dna_reader": self.dna_reader,
            }

            from_bmesh_object.free()
            to_bmesh_object.free()

            vertex_positions = meta_human_dna_core.calculate_dna_mesh_vertex_positions(from_data, to_data)
            if isinstance(self.head_mesh_object.data, bpy.types.Mesh):
                self.head_mesh_object.data.vertices.foreach_set("co", vertex_positions.ravel())  # type: ignore[attr-defined]
                self.head_mesh_object.data.update()

            utilities.auto_fit_bones(
                armature_object=self.head_rig_object,
                mesh_object=self.head_mesh_object,
                dna_reader=self.dna_reader,
                only_selected=False,
                component_type="head",
            )

            if constrain:
                self.snap_head_bones_to_body_bones()
                self.constrain_head_to_body()

    def export(self):
        pass

    def delete(self):
        for item in self.rig_instance.output_head_item_list:
            if item.scene_object:
                bpy.data.objects.remove(item.scene_object, do_unlink=True)
            if item.image_object:
                bpy.data.images.remove(item.image_object, do_unlink=True)

        self._delete_rig_instance()

    def create_topology_vertex_groups(self):
        if not self.dna_import_properties.import_mesh:
            return

        if self.head_mesh_object:
            with HEAD_TOPOLOGY_VERTEX_GROUPS_FILE_PATH.open() as file:
                data = json.load(file)
                logger.info("Creating topology vertex groups...")
                for vertex_group_name, vertex_indexes in data.items():
                    # get the existing vertex_group or create a new one
                    vertex_group = self.head_mesh_object.vertex_groups.get(vertex_group_name)
                    if not vertex_group:
                        vertex_group = self.head_mesh_object.vertex_groups.new(name=vertex_group_name)

                    vertex_group.add(index=vertex_indexes, weight=1.0, type="REPLACE")

    def select_vertex_group(self):
        if self.rig_instance and self.rig_instance.head_mesh:
            # TODO: Fix once there are topology vertex groups for all LODS
            self.rig_instance.active_lod = "lod0"
            utilities.select_vertex_group(
                mesh_object=self.rig_instance.head_mesh,
                vertex_group_name=self.rig_instance.head_mesh_topology_groups,
                add=self.rig_instance.mesh_topology_selection_mode == "add",
            )

    def select_bone_group(self):
        if self.rig_instance and self.rig_instance.head_rig:
            self.rig_instance.head_rig.hide_set(False)
            utilities.switch_to_pose_mode(self.rig_instance.head_rig)

            if self.rig_instance.rig_bone_group_selection_mode != "add":
                # deselect all bones first
                # Note: In Blender 5.0+, the select property moved from Bone to PoseBone
                for pose_bone in self.rig_instance.head_rig.pose.bones:
                    if IS_BLENDER_5:
                        pose_bone.select = False
                    else:
                        pose_bone.bone.select = False

            from ..bindings import meta_human_dna_core  # pyright: ignore[reportAttributeAccessIssue]

            for bone_name in meta_human_dna_core.HEAD_BONE_SELECTION_GROUPS.get(
                self.rig_instance.head_rig_bone_groups, []
            ):
                pose_bone = self.rig_instance.head_rig.pose.bones.get(bone_name)
                if pose_bone:
                    if IS_BLENDER_5:
                        pose_bone.select = True
                    else:
                        pose_bone.bone.select = True

            if self.rig_instance.head_rig_bone_groups.startswith(TOPO_GROUP_PREFIX):
                for pose_bone in utilities.get_topology_group_surface_bones(
                    mesh_object=self.rig_instance.head_mesh,
                    armature_object=self.rig_instance.head_rig,
                    vertex_group_name=self.rig_instance.head_rig_bone_groups,
                    dna_reader=self.dna_reader,
                ):
                    if IS_BLENDER_5:
                        pose_bone.select = True
                    else:
                        pose_bone.bone.select = True  # type: ignore[attr-defined]

    def set_face_pose(self):
        if self.rig_instance.face_board:
            thumbnail_file = Path(self.window_manager_properties.face_pose_previews)
            json_file_path = thumbnail_file.parent / "pose.json"
            if json_file_path.exists():
                logger.info(f"Applying face pose from {json_file_path}")
                # dont evaluate while updating the face board transforms
                self.window_manager_properties.evaluate_dependency_graph = False
                with json_file_path.open() as file:
                    data = json.load(file)

                    # clear the pose location for all the control bones
                    for pose_bone in self.rig_instance.face_board.pose.bones:
                        if not pose_bone.bone.children and pose_bone.name.startswith("CTRL_"):
                            pose_bone.location = Vector((0.0, 0.0, 0.0))

                    for bone_name, transform_data in data.items():
                        pose_bone = self.rig_instance.face_board.pose.bones.get(bone_name)
                        if pose_bone:
                            pose_bone.location = Vector(transform_data["location"])

                self.window_manager_properties.evaluate_dependency_graph = True
                # now evaluate the face board
                self.rig_instance.evaluate()

    def shrink_wrap_vertex_group(self):
        if self.rig_instance and self.rig_instance.head_mesh:
            modifier = self.rig_instance.head_mesh.modifiers.get(self.rig_instance.head_mesh_topology_groups)
            if not modifier:
                modifier = self.rig_instance.head_mesh.modifiers.new(
                    name=self.rig_instance.head_mesh_topology_groups, type="SHRINKWRAP"
                )
                modifier.show_viewport = False
                modifier.wrap_method = "PROJECT"
                modifier.use_negative_direction = True

            modifier.target = self.rig_instance.head_shrink_wrap_target
            modifier.vertex_group = self.rig_instance.head_mesh_topology_groups
            # toggle the visibility of the modifier
            modifier.show_viewport = not modifier.show_viewport

            utilities.set_vertex_selection(mesh_object=self.rig_instance.head_mesh, vertex_indexes=[], add=False)
            utilities.select_vertex_group(
                mesh_object=self.rig_instance.head_mesh, vertex_group_name=self.rig_instance.head_mesh_topology_groups
            )

    @preserve_context
    def revert_bone_transforms_to_dna(self):
        if self.head_rig_object and isinstance(self.head_rig_object.data, bpy.types.Armature):
            extra_bone_lookup = dict(EXTRA_BONES)
            # make sure the dna importer has the rig object set
            self.dna_importer.rig_object = self.head_rig_object

            bone_names = [pose_bone.name for pose_bone in bpy.context.selected_pose_bones]
            utilities.switch_to_bone_edit_mode(self.rig_instance.head_rig)

            for bone_name in bone_names:
                edit_bone = self.head_rig_object.data.edit_bones[bone_name]
                extra_bone = extra_bone_lookup.get(bone_name)
                if bone_name == "root":
                    edit_bone.matrix = self.head_rig_object.matrix_world
                # reverts the default bone transforms back to their default values
                elif extra_bone:
                    location = extra_bone["location"]
                    rotation = extra_bone["rotation"]
                    # Scale the location of the bones based on the height scale factor
                    location.y = location.y * self.dna_importer.get_height_scale_factor()
                    global_matrix = Matrix.Translation(location) @ rotation.to_matrix().to_4x4()
                    # default values are stored in Y-up, so convert to Z-up
                    edit_bone.matrix = Matrix.Rotation(math.radians(90), 4, "X").to_4x4() @ global_matrix  # type: ignore[arg-type]
                else:
                    bone_matrix = self.dna_importer.get_bone_matrix(bone_name=bone_name)
                    if bone_matrix:
                        edit_bone.matrix = bone_matrix

    @utilities.exclude_rig_instance_evaluation
    def import_shape_keys(self, commands_queue: queue.Queue) -> list:
        if not self.head_mesh_object:
            raise ValueError("Head mesh object not found!")

        commands = []

        def get_initialize_kwargs(_: int, mesh_index: int) -> dict:
            mesh_dna_name = self.dna_reader.getMeshName(mesh_index)
            mesh_object = bpy.data.objects.get(f"{self.name}_{mesh_dna_name}")
            return {
                "mesh_object": mesh_object,
            }

        def get_create_kwargs(index: int, mesh_index: int) -> dict:
            channel_index = self.dna_reader.getBlendShapeChannelIndex(mesh_index, index)
            shape_key_name = self.dna_reader.getBlendShapeChannelName(channel_index)
            mesh_dna_name = self.dna_reader.getMeshName(mesh_index)
            mesh_object = bpy.data.objects.get(f"{self.name}_{mesh_dna_name}")
            return {
                "index": index,
                "mesh_index": mesh_index,
                "mesh_object": mesh_object,
                "reader": self.dna_reader,
                "name": shape_key_name,
                "prefix": f"{mesh_dna_name}__",
                "is_neutral": self.rig_instance.generate_neutral_shapes,
                "linear_modifier": self.linear_modifier,
            }

        for mesh_index in range(self.dna_reader.getMeshCount()):
            count = self.dna_reader.getBlendShapeTargetCount(mesh_index)
            if count > 0:
                commands_queue.put(
                    (
                        0,
                        mesh_index,
                        "Initializing basis shape...",
                        get_initialize_kwargs,
                        lambda **kwargs: utilities.initialize_basis_shape_key(**kwargs),
                    )
                )

            for index in range(count):
                commands_queue.put(
                    (
                        index,
                        mesh_index,
                        f"{index}/{count}" + " {name} ...",
                        get_create_kwargs,
                        lambda **kwargs: create_shape_key(**kwargs),
                    )
                )

        return commands
