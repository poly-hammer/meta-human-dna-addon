import os
import bpy
import math
import json
import bmesh
import logging
from typing import Callable
from pathlib import Path
from mathutils import Vector, Matrix
from .. import utilities
from ..utilities import preserve_context
from ..rig_logic import RigLogicInstance
from .misc import get_dna_writer, get_dna_reader
from ..bindings import riglogic
from ..exceptions import InvalidComponentTypeError
from ..constants import (
    SCALE_FACTOR, 
    TOPO_GROUP_PREFIX,
    EXTRA_BONES,
    ComponentType
)

logger = logging.getLogger(__name__)

class DNAExporter:
    def __init__(
            self, 
            instance: RigLogicInstance,
            linear_modifier: float,
            meshes: bool = True,
            shape_keys: bool = True,
            bones: bool = True,
            textures: bool = True,
            vertex_colors: bool = True,
            file_name: str | None = None,
            component_type: ComponentType | None = None,
            reader: 'riglogic.BinaryStreamReader | None' = None
        ):
        self._instance = instance
        self._linear_modifier = linear_modifier
        self._prefix = instance.name

        self._include_meshes = meshes
        self._include_shape_keys = shape_keys
        self._include_bones = bones
        self._include_textures = textures
        self._include_vertex_colors = vertex_colors
        self._component_type = component_type or instance.output_component

        self._output_folder = Path(bpy.path.abspath(instance.output_folder_path))

        if self._component_type == 'head':
            self.source_dna_file = Path(bpy.path.abspath(instance.head_dna_file_path))
        elif self._component_type == 'body':
            self.source_dna_file = Path(bpy.path.abspath(instance.body_dna_file_path))
        else:
            raise InvalidComponentTypeError(self._component_type)

        self._target_dna_file = Path(bpy.path.abspath(instance.output_folder_path)) / (file_name or f'{instance.name}.dna')

        # Open a read to the source DNA file if an existing reader is not provided
        if not reader:
            self._dna_reader = get_dna_reader(file_path=self.source_dna_file)
        else:
            self._dna_reader = reader

        self._dna_writer = get_dna_writer(
            file_path=self._target_dna_file,
            file_format=self._instance.output_format
        )
        # Populate the writer with the data from the reader
        self._dna_writer.setFrom(
            self._dna_reader,
            riglogic.DataLayer.All,
            riglogic.UnknownLayerPolicy.Preserve,
            None
        )

        # The head and body mesh are always the first mesh in the DNA file
        if self._component_type == 'head':
            self._export_lods = {
                0: [(instance.head_mesh, 0)]
            }
            self._extra_bones = EXTRA_BONES
            self._rig_object = instance.head_rig
        elif self._component_type == 'body':
            self._export_lods = {
                0: [(instance.body_mesh, 0)]
            }
            self._extra_bones = []
            self._rig_object = instance.body_rig
        else:
            raise InvalidComponentTypeError(self._component_type)
        
        self._mesh_indices = [0]
        self._non_lod_mesh_objects = []
        self._images = []
        self._bone_index_lookup = {}
        self._vertex_color_data = []

    def initialize_scene_data(self):
        mesh_objects = []
        output_items = []
        main_mesh_object = None

        if self._component_type == 'head':
            output_items = self._instance.output_head_item_list
            main_mesh_object = self._instance.head_mesh
        elif self._component_type == 'body':
            output_items = self._instance.output_body_item_list
            main_mesh_object = self._instance.body_mesh

        for output_item in output_items:
            if output_item.include:
                if output_item.scene_object and output_item.scene_object.type == 'ARMATURE':                    
                    self._rig_object = output_item.scene_object
                elif main_mesh_object and output_item.scene_object == main_mesh_object:
                    continue
                elif output_item.scene_object and output_item.scene_object.type == 'MESH':
                    if not self._include_meshes:
                        continue
                    mesh_objects.append(output_item.scene_object)
                elif output_item.image_object:
                    self._images.append((output_item.image_object, output_item.name))

        # Sort the meshes by the order in the ORDER dictionary
        mesh_objects.sort(key=lambda x: x.name.replace(f'{self._prefix}_', ''))

        # Populate the LODs with the mesh objects and their indices
        mesh_index = 1
        for mesh_object in mesh_objects:
            index = utilities.get_lod_index(mesh_object.name)
            if index == -1:
                self._non_lod_mesh_objects.append(mesh_object)
            else:
                self._export_lods[index] = self._export_lods.get(index, [])
                self._export_lods[index].append((mesh_object, mesh_index))
                self._mesh_indices.append(mesh_index)
                mesh_index += 1

        # Also check if the main mesh is not an LOD mesh
        if main_mesh_object and utilities.get_lod_index(main_mesh_object.name) == -1:
            self._non_lod_mesh_objects.append(main_mesh_object)

        # Initialize the vertex color data array
        self._vertex_color_data = [{
            'indices': [],
            'values': [],
        }] * len(self._mesh_indices)

    def validate(self) -> tuple[bool, str, str, Callable | None]:
        if not self._rig_object:
            return (
                False, 
                "No Rig Object",
                "No rig object found. Must link a head rig to export DNA.",
                None
            )
        
        if self._include_meshes:
            if self._non_lod_mesh_objects:
                mesh_names = '\n'.join([f'"{i.name}"' for i in self._non_lod_mesh_objects])
                return (
                    False,
                    "Invalid LOD names. Fix by renaming to LOD 0 meshes?",
                    mesh_names,
                    lambda: utilities.rename_as_lod0_meshes(self._non_lod_mesh_objects)
                )
            
            meshes_missing_uvs = []
            for _, mesh_objects in self._export_lods.items():
                for mesh_object, _ in mesh_objects:
                    if not mesh_object.data.uv_layers.active:
                        meshes_missing_uvs.append(mesh_object)
            if meshes_missing_uvs:
                mesh_names = '\n'.join([f'"{i.name}"' for i in meshes_missing_uvs])
                return (
                    False,
                    "Missing UVs. Auto unwrap the following meshes?",
                    mesh_names,
                    lambda: utilities.auto_unwrap_uvs(meshes_missing_uvs)
                )
            
            # make sure the mesh objects have the same origin as the rig
            meshes_with_mismatched_origins = []
            for _, mesh_objects in self._export_lods.items():
                for mesh_object, _ in mesh_objects:
                    if (self._rig_object.location.copy() - mesh_object.location).length > 1e-4:
                        meshes_with_mismatched_origins.append(mesh_object)
            
            if meshes_with_mismatched_origins:
                mesh_names = '\n'.join([f'"{i.name}"' for i in meshes_with_mismatched_origins])
                return (
                    False,
                    "Mesh origin mismatch. Fix by matching and applying to the rig's origin?",
                    mesh_names,
                    lambda: utilities.set_objects_origins(
                        meshes_with_mismatched_origins, 
                        location=self._rig_object.location.copy()
                    )
                )

        
        # TODO: Add more validations
        return (
                True, 
                "Success",
                "All validations passed.",
                None
            )


    @staticmethod
    def get_bmesh(mesh_object: bpy.types.Object, rotation: float = -90) -> bmesh.types.BMesh:
        # create an empty BMesh and fill it in from the mesh data
        bmesh_object = bmesh.new()
        bmesh_object.from_mesh(mesh=mesh_object.data) # type: ignore

        # Rotate the mesh so that it's Y-up before reading the vertex data
        bmesh.ops.rotate(
            bmesh_object, 
            cent=Vector((0,0,0)), 
            matrix=Matrix.Rotation(math.radians(rotation), 4, 'X'), 
            verts=bmesh_object.verts # type: ignore
        )
        bmesh_object.verts.index_update()
        bmesh_object.verts.ensure_lookup_table()
        return bmesh_object

    @staticmethod
    def get_mesh_faces(bmesh_object: bmesh.types.BMesh) -> list[tuple[int, list[int]]]:
        bmesh_object.faces.ensure_lookup_table()
        return [
            (face.index, [vert.index for vert in face.verts])
            for face in bmesh_object.faces # type: ignore
        ]
    
    @staticmethod
    @preserve_context
    def get_bone_transforms(
            armature_object: bpy.types.Object,
            extra_bones: list[tuple[str, dict]] = EXTRA_BONES,
        ) -> tuple[
            list[int],
            list[str],
            list[int],
            list[bool],
            list[list[float]],
            list[list[float]]
            ]:
        indices = []
        bone_names = []
        hierarchy = []
        is_leaf = []
        translations = []
        rotations = []

        hierarchy_lookup = {}

        # Change the rotation of the bones since DNA expects Y-up
        rotation_x = Matrix.Rotation(math.radians(-90), 4, 'X')
        global_matrix = rotation_x.to_4x4()

        # Switch to edit mode so we can get edit bone data
        armature_object.hide_set(False)
        utilities.switch_to_bone_edit_mode(armature_object)

        # Remove the extra bones from the list of bones
        ignored_bone_names = [i for i, _ in extra_bones]
        edit_bones = [i for i in armature_object.data.edit_bones if i.name not in ignored_bone_names] # type: ignore
        for index, edit_bone in enumerate(edit_bones): # type: ignore
            if index == 0:
                # get translation and rotation of the bone globally
                translation, rotation, _ = (global_matrix @ edit_bone.matrix).decompose()
            else:
                # get translation and rotation of relative to it's parent 
                local_matrix = edit_bone.parent.matrix.inverted() @ edit_bone.matrix # type: ignore
                translation, rotation, _ = local_matrix.decompose()

            indices.append(index)
            bone_names.append(edit_bone.name)
            is_leaf.append(not edit_bone.children)

            hierarchy_index = index
            # If the bone has a parent, get the index of the parent bone.
            # We don't want to include the extra bones as parents.
            if edit_bone.parent and edit_bone.parent.name not in ignored_bone_names:
                hierarchy_index = hierarchy_lookup[edit_bone.parent.name]
            
            hierarchy.append(hierarchy_index)
            # Store the index of the bone in the hierarchy lookup so we can find parent indices later
            hierarchy_lookup[edit_bone.name] = index

            # Convert translation from blender meters to centimeters
            translations.append([
                translation.x*SCALE_FACTOR, 
                translation.y*SCALE_FACTOR,
                translation.z*SCALE_FACTOR
            ])
            # Convert rotation from quaternion to euler
            euler_rotation = rotation.to_euler('XYZ')
            # Convert rotation from radians to degrees
            rotations.append([
                math.degrees(euler_rotation.x),
                math.degrees(euler_rotation.y),
                math.degrees(euler_rotation.z)
            ])

        return indices, bone_names, hierarchy, is_leaf, translations, rotations

    @staticmethod
    def get_mesh_vertex_positions(
            bmesh_object: bmesh.types.BMesh, 
            duplicate_lookup: dict | None = None
        ) -> tuple[list[int], list[list[float]]]:
        indices = []
        positions = []
        if not duplicate_lookup:
            duplicate_lookup = {}

        for vert in bmesh_object.verts: # type: ignore
            positions.append([
                vert.co.x*SCALE_FACTOR,
                vert.co.y*SCALE_FACTOR,
                vert.co.z*SCALE_FACTOR
            ])
            # Get the original vertex index if the vertex is a duplicate, otherwise use the current index
            vertex_index = duplicate_lookup.get(vert.index, vert.index)
            indices.append(vertex_index)
        return indices, positions

    @staticmethod
    def get_mesh_vertex_normals(bmesh_object: bmesh.types.BMesh) -> tuple[list[int], list[list[float]]]:
        indices = []
        normals = []
        # TODO: Use split_normals from Mesh instead. Also check if these are stored as triangles?
        # https://docs.blender.org/api/current/bpy.types.MeshLoopTriangle.html

        for vert in bmesh_object.verts: # type: ignore
            normals.append([
                vert.normal.x*SCALE_FACTOR, 
                vert.normal.y*SCALE_FACTOR, 
                vert.normal.z*SCALE_FACTOR
            ])
            indices.append(vert.index)
        return indices, normals

    @staticmethod
    def get_mesh_vertex_groups(mesh_object: bpy.types.Object) -> dict[str, list[tuple[int, float]]]:
        # Create a lookup table for the vertex group names by their index
        vertex_group_lookup = {vertex_group.index: vertex_group.name for vertex_group in mesh_object.vertex_groups}
        # Initialize the vertex groups dictionary
        vertex_groups = {vertex_group.name: [] for vertex_group in mesh_object.vertex_groups}

        # Loop through the vertices and get the vertex group names and the vertex and weights
        for vertex in mesh_object.data.vertices: # type: ignore
            vertex_group_names = [vertex_group_lookup.get(group.group, '') for group in vertex.groups]
            for vertex_group_name in vertex_group_names:
                # Skip the topology vertex groups
                if vertex_group_name.startswith(TOPO_GROUP_PREFIX):
                    continue

                vertex_group = mesh_object.vertex_groups.get(vertex_group_name)
                if vertex_group:
                    weight = vertex_group.weight(vertex.index)
                    if weight > 0:
                        vertex_groups[vertex_group_name].append((vertex.index, weight))

        return vertex_groups
    
    @staticmethod
    def get_mesh_vertex_uvs(bmesh_object: bmesh.types.BMesh) -> tuple[list[int], list[list[float]]]:
        uv_layer = bmesh_object.loops.layers.uv.active
        if not uv_layer:
            return [], []

        uv_indices = list(range(len(bmesh_object.verts)))
        uv_positions = []
        
        for face in bmesh_object.faces:
            for loop in face.loops:
                uv_indices[loop.vert.index] = loop.index
                uv_positions.append(list(loop[uv_layer].uv[:]))

        return uv_indices, uv_positions
    
    def set_dna_vertex_colors(self, mesh_index: int, bmesh_object: bmesh.types.BMesh):
        vertex_color_indices = list(range(len(bmesh_object.verts)))
        vertex_color_values = []
        color_layer = bmesh_object.loops.layers.color.active
        if color_layer:
            for face in bmesh_object.faces:
                for loop in face.loops:
                    vertex_color_indices[loop.vert.index] = loop.index
                    vertex_color_values.append(list(loop[color_layer][:]))

            self._vertex_color_data[mesh_index]['indices'] = vertex_color_indices
            self._vertex_color_data[mesh_index]['values'] = vertex_color_values
    
    def set_dna_vertex_positions(
            self,
            mesh_index: int, 
            positions: list[list[float]],
        ):
        self._dna_writer.setVertexPositions(
            meshIndex=mesh_index, 
            positions=positions
        )
    
    def set_dna_faces(self, mesh_index: int, face_layouts: list[tuple[int, list[int]]]):
        for face_index, face_vertex_indices in face_layouts:
            self._dna_writer.setFaceVertexLayoutIndices(
                meshIndex=mesh_index, 
                faceIndex=face_index, 
                layoutIndices=face_vertex_indices
            )
    
    def set_dna_normals(self, mesh_index: int, normals: list[list[float]]):
        self._dna_writer.setVertexNormals(
            meshIndex=mesh_index,
            normals=normals
        )

    def set_dna_uvs(self, mesh_index: int, uvs: list[list[float]]):
        self._dna_writer.setVertexTextureCoordinates(
            meshIndex=mesh_index,
            textureCoordinates=uvs
        )

    def set_dna_vertex_groups(self, mesh_index: int, mesh_object: bpy.types.Object):
        self._dna_writer.clearSkinWeights(meshIndex=mesh_index)
        # Create a lookup table for the vertex group names by their index
        vertex_group_lookup = {vertex_group.index: vertex_group.name for vertex_group in mesh_object.vertex_groups}

        # Loop through the vertices and get the vertex group names and the vertex and weights
        for vertex in mesh_object.data.vertices: # type: ignore
            vertex_group_names = [vertex_group_lookup.get(group.group, '') for group in vertex.groups]
            bone_indices = []
            weights = []

            for vertex_group_name in vertex_group_names:
                bone_index = self._bone_index_lookup.get(vertex_group_name)
                vertex_group = mesh_object.vertex_groups.get(vertex_group_name)
                if bone_index and vertex_group:    
                    weight = vertex_group.weight(vertex.index)
                    if weight > 0:
                        bone_indices.append(bone_index)
                        weights.append(weight)

            self._dna_writer.setSkinWeightsJointIndices(
                meshIndex=mesh_index, 
                vertexIndex=vertex.index, 
                jointIndices=bone_indices
            )
            self._dna_writer.setSkinWeightsValues(
                meshIndex=mesh_index, 
                vertexIndex=vertex.index,
                weights=weights
            )      

    def set_dna_bones(
            self, 
            indices: list[int],
            bone_names: list[str],
            hierarchy: list[int],
            translations: list[list[float]],
            rotations: list[list[float]]
        ):
        dna_x_rotations = self._dna_reader.getNeutralJointRotationXs()
        dna_y_rotations = self._dna_reader.getNeutralJointRotationYs()
        dna_z_rotations = self._dna_reader.getNeutralJointRotationZs()


        for index, bone_name in zip(indices, bone_names):
            self._dna_writer.setJointName(index=index, name=bone_name)
            self._bone_index_lookup[bone_name] = index
            
            dna_x_rotations[index] = rotations[index][0]
            dna_y_rotations[index] = rotations[index][1]
            dna_z_rotations[index] = rotations[index][2]
        
        self._dna_writer.setJointHierarchy(hierarchy)
        self._dna_writer.setNeutralJointTranslations(translations)
        self._dna_writer.setNeutralJointRotations([[x, y, z] for x, y, z in zip(dna_x_rotations, dna_y_rotations, dna_z_rotations)])
    
    def save_images(self):
        if not self._include_textures:
            return
        
        for image, file_name in self._images:
            new_image_path = self._target_dna_file.parent / 'Maps' / file_name
            os.makedirs(new_image_path.parent, exist_ok=True)
            if not image.packed_file and not image.filepath:
                logger.warning(f"Image {image.name} is not packed or saved. Skipping export.")
                continue

            try:
                image.save(filepath=str(new_image_path))
            except Exception:
                try:
                    image.save_render(filepath=str(new_image_path))
                except Exception as error:
                    logger.error(f"Failed to export image {image.name}: {error}")
            logger.info(f"Image {image.name} exported successfully to: {new_image_path}")

    def save_vertex_colors(self):
        if self._include_vertex_colors:
            vertex_colors_file = self._target_dna_file.parent / f'{self._prefix}_vertex_colors.json'
            with open(vertex_colors_file, 'w') as f:
                json.dump(self._vertex_color_data, f)
                logger.info(f'Vertex colors exported successfully to: "{vertex_colors_file}"')

    def run(self) -> tuple[bool, str, str, Callable| None]:
        self.initialize_scene_data()
        if self._instance.output_run_validations:
            valid, title, message, fix = self.validate()
            if not valid:
                return False, title, message, fix

        # Clear the mesh data
        self._dna_writer.clearMeshNames()
        self._dna_writer.clearMeshIndices()
        self._dna_writer.clearLODMeshMappings()
        self._dna_writer.clearMeshes()

        # Clear the bone data
        self._dna_writer.clearJointNames()
        self._dna_writer.clearJointIndices()
        self._dna_writer.clearLODJointMappings()

        # init the lod indices
        # TODO: Currently can't change this without messing up the joint behavior.
        # Default dna has 8 lods
        # self._dna_writer.setLODCount(len(self._export_lods.keys()))

        bone_indices, bone_names, hierarchy, is_leaf, translations, rotations = self.get_bone_transforms(
            armature_object=self._rig_object,
            extra_bones=self._extra_bones
        )

        # Set the bone data
        self.set_dna_bones(
            indices=bone_indices,
            bone_names=bone_names,
            hierarchy=hierarchy,
            translations=translations,
            rotations=rotations
        )

        for lod_index, mesh_objects in self._export_lods.items():
            # Set the joint indices
            self._dna_writer.setJointIndices(index=lod_index, jointIndices=bone_indices)
            self._dna_writer.setLODJointMapping(lod=lod_index, index=lod_index)
            
            # TODO: Currently we just copy this data from the default DNA file.
            # In the future maybe give the user control over this and the PSDs
            # self._dna_writer.setJointColumnCount
            # self._dna_writer.setJointRowCount
            # self._dna_writer.setJointGroupLODs
            # self._dna_writer.setJointGroupJointIndices
            # self._dna_writer.setJointGroupInputIndices
            # self._dna_writer.setJointGroupOutputIndices
            # self._dna_writer.setJointGroupValues

            # Set the mesh indices
            self._dna_writer.setMeshIndices(
                index=lod_index, 
                meshIndices=[mesh_index for _, mesh_index in mesh_objects]
            )
            self._dna_writer.setLODMeshMapping(lod=lod_index, index=lod_index)

            for mesh_object, mesh_index in mesh_objects:
                real_name = mesh_object.name.replace(f'{self._prefix}_', '')

                logger.info(f'Exporting mesh: "{mesh_object.name}" to DNA as "{real_name}"...')
                self._dna_writer.clearFaceVertexLayoutIndices(meshIndex=mesh_index)
                self._dna_writer.clearSkinWeights(meshIndex=mesh_index)
                self._dna_writer.clearBlendShapeTargets(meshIndex=mesh_index)

                # Set the mesh name
                self._dna_writer.setMeshName(index=mesh_index, name=real_name)
                bmesh_object = self.get_bmesh(mesh_object)
                # Split the mesh along UV islands so that we have all the UV loop indices needed for each vertex index
                split_to_original_vert_lookup = utilities.split_mesh_along_uv_islands(bmesh_object=bmesh_object)

                vertex_indices, vertex_positions = self.get_mesh_vertex_positions(
                    bmesh_object=bmesh_object,
                    duplicate_lookup=split_to_original_vert_lookup
                )
                normal_indices, normals = self.get_mesh_vertex_normals(bmesh_object=bmesh_object)
                uv_indices, uvs = self.get_mesh_vertex_uvs(bmesh_object=bmesh_object)
                faces = self.get_mesh_faces(bmesh_object=bmesh_object)
                
                # Set the vertex color data so it can be saved to JSON later
                if self._include_vertex_colors:
                    self.set_dna_vertex_colors(mesh_index=mesh_index, bmesh_object=bmesh_object)

                # Set the vertex layout so DNA knows how to read the vertex, 
                # normal, and uv data from their respective arrays
                self._dna_writer.setVertexLayouts(
                    meshIndex=mesh_index, 
                    layouts=[list(item) for item in zip(vertex_indices, uv_indices, normal_indices)]
                )

                self.set_dna_vertex_positions(mesh_index, vertex_positions)
                self.set_dna_faces(mesh_index, faces)
                self.set_dna_normals(mesh_index, normals)
                self.set_dna_uvs(mesh_index, uvs)
                self.set_dna_vertex_groups(mesh_index, mesh_object)

                # Now free the BMesh from memory without applying the changes back to the mesh
                bmesh_object.free()
        
        self._dna_writer.write()
        if not riglogic.Status.isOk():
            status = riglogic.Status.get()
            raise RuntimeError(f"Error saving DNA: {status.message}")
        logger.info(f'DNA exported successfully to: "{self._target_dna_file}"')

        self.save_images()
        self.save_vertex_colors()

        return True, "Success", "Export successful.", None