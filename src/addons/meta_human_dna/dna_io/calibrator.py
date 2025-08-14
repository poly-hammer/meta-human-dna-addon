import bpy
import math
import logging
from typing import Callable
from mathutils import Vector, Matrix
from .. import utilities
from .importer import DNAImporter
from .exporter import DNAExporter
from ..bindings import riglogic
from ..constants import (
    SHAPE_KEY_NAME_MAX_LENGTH,
    SHAPE_KEY_DELTA_THRESHOLD,
    HEAD_TO_BODY_LOD_MAPPING,
    BONE_DELTA_THRESHOLD,
    SHAPE_KEY_BASIS_NAME
)

logger = logging.getLogger(__name__)

class DNACalibrator(DNAExporter, DNAImporter):

    def _get_body_bone_lookups(self) -> tuple[dict, dict, dict, dict]:
        dna_body_bone_translation_lookup = {}
        dna_body_bone_rotation_lookup = {}
        body_bone_translation_lookup = {}
        body_bone_rotation_lookup = {}

        # Ensure the body DNA reader is initialized
        if not self._instance.body_dna_reader:
            self._instance.initialize()

        # If this is the head, and the align head and body option is on, then we want to use the
        # exact same transforms for the body and head bones so that they match perfectly. So we need to 
        # create a body bone lookup so these can be used as the source of truth.
        if (
            self._component_type == 'head' and
            self._instance.output_method == 'calibrate' and
            self._instance.output_align_head_and_body and
            self._instance.body_dna_reader and
            self._instance.body_rig
        ):
            # Extract the body bone transforms from the dna file
            body_dna_x_translations = self._instance.body_dna_reader.getNeutralJointTranslationXs()
            body_dna_y_translations = self._instance.body_dna_reader.getNeutralJointTranslationYs()
            body_dna_z_translations = self._instance.body_dna_reader.getNeutralJointTranslationZs()
            body_dna_x_rotations = self._instance.body_dna_reader.getNeutralJointRotationXs()
            body_dna_y_rotations = self._instance.body_dna_reader.getNeutralJointRotationYs()
            body_dna_z_rotations = self._instance.body_dna_reader.getNeutralJointRotationZs()
            dna_body_bone_translation_lookup = {
                self._instance.body_dna_reader.getJointName(index): 
                    Vector((
                    body_dna_x_translations[index],
                    body_dna_y_translations[index],
                    body_dna_z_translations[index]
                ))
                for index in range(self._instance.body_dna_reader.getJointCount())
            }
            dna_body_bone_rotation_lookup = {
                self._instance.body_dna_reader.getJointName(index): 
                    Vector((
                        body_dna_x_rotations[index],
                        body_dna_y_rotations[index],
                        body_dna_z_rotations[index]
                    ))
                for index in range(self._instance.body_dna_reader.getJointCount())
            }

            # Extract the body bone transforms from the scene
            indices, bone_names, _, _, translations, rotations = self.get_bone_transforms(self._instance.body_rig, extra_bones=[])

            body_bone_translation_lookup = {
                bone_name: Vector(translations[index])
                for index, bone_name in zip(indices, bone_names)
            }

            body_bone_rotation_lookup = {
                bone_name: Vector(rotations[index])
                for index, bone_name in zip(indices, bone_names)
            }

        return (
            dna_body_bone_translation_lookup, 
            dna_body_bone_rotation_lookup, 
            body_bone_translation_lookup, 
            body_bone_rotation_lookup
        )

    def _get_body_mesh_lookup(
            self, 
            lod_index: int,
            mesh_name: str,
            head_to_body_edge_loop_mapping: dict[str, dict[int, int]]
        ) -> dict[int, Vector]:
        # If this is the head, and the align head and body option is on, then we want to use the
        # exact same vertex positions for the body and head vertices where they overlap. This needs to
        # be precised to the exact floating point value.
        if mesh_name != f'{self._instance.name}_head_lod{lod_index}_mesh':
            return {}

        body_lod_index = HEAD_TO_BODY_LOD_MAPPING.get(lod_index)
        body_mesh_name = f'{self._instance.name}_body_lod{body_lod_index}_mesh'
        body_mesh_lod = bpy.data.objects.get(body_mesh_name)
        if (
            self._component_type == 'head' and
            self._instance.output_method == 'calibrate' and
            self._instance.output_align_head_and_body and
            body_mesh_lod
        ):
            bmesh_object = self.get_bmesh(body_mesh_lod)
            vertex_indices, vertex_positions = self.get_mesh_vertex_positions(bmesh_object)
            bmesh_object.free()
            vert_lookup = dict(zip(vertex_indices, vertex_positions))

            try:
                return {
                    int(head_vertex_index): Vector(vert_lookup[body_vertex_index])
                    for head_vertex_index, body_vertex_index in head_to_body_edge_loop_mapping.get(str(lod_index), {}).items()
                }
            except KeyError as error:
                logger.warning(
                    f'Head to body vertex mapping not found for LOD {lod_index}: {error}. A vertex on '
                    f'mesh {mesh_name} or {body_mesh_name} may have been deleted.'
                )
        return {}

    def calibrate_vertex_positions(self):
        additional_meshes_by_lod = {}
        mesh_index_lookup = {self._dna_reader.getMeshName(index): index for index in range(self._dna_reader.getMeshCount())}
        head_to_body_edge_loop_mapping = utilities.get_head_to_body_edge_loop_mapping()

        for lod_index, mesh_objects in self._export_lods.items():
            logger.info(f'Calibrating LOD {lod_index} vertex positions...')
            for mesh_object, _ in mesh_objects:
                body_mesh_lookup = self._get_body_mesh_lookup(
                    lod_index=lod_index, 
                    mesh_name=mesh_object.name,
                    head_to_body_edge_loop_mapping=head_to_body_edge_loop_mapping
                )

                real_name = mesh_object.name.replace(f'{self._instance.name}_', '')
                logger.info(f'Calibrating "{real_name}" vertex positions...')
                mesh_index = mesh_index_lookup.get(real_name)
                
                # If the mesh index is not found, we assume that the mesh is not part of the DNA
                # And we can add it to the additional meshes for this LOD
                if mesh_index is None:
                    additional_meshes_by_lod[lod_index] = additional_meshes_by_lod.get(lod_index, [])
                    additional_meshes_by_lod[lod_index].append(mesh_object)
                    logger.warning(f'Mesh "{real_name}" not found in DNA. This mesh will not be calibrated...')
                    continue

                bmesh_object = self.get_bmesh(mesh_object)
                vertex_indices, vertex_positions = self.get_mesh_vertex_positions(bmesh_object)
                bmesh_object.free()

                # Read these from the DNA file and modify these arrays so that they match the vertex indices match
                x_values = self._dna_reader.getVertexPositionXs(mesh_index)
                y_values = self._dna_reader.getVertexPositionYs(mesh_index)
                z_values = self._dna_reader.getVertexPositionZs(mesh_index)

                for vertex_index in vertex_indices:
                    # See if we can get the vertex position from the body mesh lookup first, so that we have an exact match
                    vertex_position = body_mesh_lookup.get(int(vertex_index), Vector(vertex_positions[vertex_index]))
                    dna_vertex_position = Vector((x_values[vertex_index], y_values[vertex_index], z_values[vertex_index]))
                    delta = vertex_position - dna_vertex_position
                    # This ensures that we only modify the vertex positions that are different to avoid floating value drift
                    if delta.length > 1e-6:
                        x_values[vertex_index] = vertex_position.x
                        y_values[vertex_index] = vertex_position.y
                        z_values[vertex_index] = vertex_position.z

                self._dna_writer.setVertexPositions(
                    meshIndex=mesh_index, 
                    positions=[[x,y,z] for x,y,z in zip(x_values, y_values, z_values)]
                )

    def calibrate_shape_keys(self):
        if self._component_type != 'head':
            # currently, we only calibrate shape keys for the head component
            return
        
        for lod_index in range(self._dna_reader.getLODCount()):
            # Skip LODs without blend shape channels
            if len(self._dna_reader.getBlendShapeChannelIndicesForLOD(lod_index)) == 0:
                continue

            logger.info(f'Calibrating shape keys for {self._component_type} component LOD {lod_index}...')

            for mesh_index in self._dna_reader.getMeshIndicesForLOD(lod_index):
                mesh_name = self._dna_reader.getMeshName(mesh_index)
                real_mesh_name = f'{self._prefix}_{mesh_name}'
                mesh_object = bpy.data.objects.get(real_mesh_name)
                if not mesh_object:
                    logger.error(f"Mesh object '{real_mesh_name}' not found for shape key calibration. Skipping...")
                    continue

                if not mesh_object.data or not mesh_object.data.shape_keys: # type: ignore
                    logger.warning(f"Mesh object '{mesh_object.name}' has no shape key data in the blender scene. Skipping shape key calibration...")
                    continue

                shape_key_basis = mesh_object.data.shape_keys.key_blocks.get(SHAPE_KEY_BASIS_NAME) # type: ignore
                if not shape_key_basis:
                    raise RuntimeError(f"Shape key '{SHAPE_KEY_BASIS_NAME}' not found for mesh '{real_mesh_name}'. This is needed for calibration!")
                
                # helps to track the largest delta count for the shape keys
                largest_delta_count = 0
                    
                # Get the vertex positions for the mesh object
                bmesh_object = self.get_bmesh(mesh_object)
                vertex_indices, _ = self.get_mesh_vertex_positions(bmesh_object)
                bmesh_object.free()
                
                # DNA is Y-up, Blender is Z-up, so we need to rotate the deltas
                rotation_matrix = Matrix.Rotation(math.radians(-90), 4, 'X')

                for index in range(self._dna_reader.getBlendShapeTargetCount(mesh_index)):
                    channel_index = self._dna_reader.getBlendShapeChannelIndex(mesh_index, index)
                    shape_key_name = self._dna_reader.getBlendShapeChannelName(channel_index)

                    # Currently, Blender has a limit of 63 characters for shape key names
                    if len(f'{mesh_name}__{shape_key_name}') > SHAPE_KEY_NAME_MAX_LENGTH:
                        continue

                    shape_key_block = mesh_object.data.shape_keys.key_blocks.get(f'{mesh_name}__{shape_key_name}') # type: ignore
                    if not shape_key_block:
                        logger.error(f"Shape key '{shape_key_name}' not found for mesh '{real_mesh_name}'. Skipping calibration...")
                        continue

                    dna_delta_vertex_indices = []
                    dna_delta_values = []

                    # the new shape key is the dna shape key with the deltas from the blender shape key applied
                    for vertex_index in vertex_indices:
                        # get the positions of the points
                        # Get the delta between the current shape key and the basis (rest) shape key
                        new_delta = rotation_matrix @ (shape_key_block.data[vertex_index].co.copy() - shape_key_basis.data[vertex_index].co) # type: ignore

                        # Only modify the vertex positions that are different to avoid floating value drift
                        if new_delta.length > SHAPE_KEY_DELTA_THRESHOLD:
                            # Apply the coordinate system conversion and linear modifier for the scene units to the delta
                            converted_delta = new_delta / self._linear_modifier
                            dna_delta_vertex_indices.append(vertex_index)
                            dna_delta_values.append((
                                converted_delta.x,
                                converted_delta.y,
                                converted_delta.z
                            ))

                    if len(dna_delta_vertex_indices) > largest_delta_count:
                        largest_delta_count = len(dna_delta_vertex_indices)

                    # Set the vertex indices for the delta values array for the shape key
                    self._dna_writer.setBlendShapeTargetVertexIndices(
                        meshIndex=mesh_index,
                        blendShapeTargetIndex=index,
                        vertexIndices=dna_delta_vertex_indices
                    )
                    # Set the actual delta value array for the shape key
                    self._dna_writer.setBlendShapeTargetDeltas(
                        meshIndex=mesh_index,
                        blendShapeTargetIndex=index,
                        deltas=dna_delta_values
                    )

                logger.debug(f'Largest Shape Key delta count for mesh {real_mesh_name} is {largest_delta_count}')

    def calibrate_bone_transforms(self):
        ignored_bone_names = [i for i, _ in self._extra_bones]

        logger.info('Calibrating bones...')
        dna_x_translations = self._dna_reader.getNeutralJointTranslationXs()
        dna_y_translations = self._dna_reader.getNeutralJointTranslationYs()
        dna_z_translations = self._dna_reader.getNeutralJointTranslationZs()
        dna_x_rotations = self._dna_reader.getNeutralJointRotationXs()
        dna_y_rotations = self._dna_reader.getNeutralJointRotationYs()
        dna_z_rotations = self._dna_reader.getNeutralJointRotationZs()

        # If this is the head, and the align head and body option is on, then we want to use the
        # exact same transforms for the body and head bones that match.
        (
            dna_body_translation_lookup, 
            dna_body_rotation_lookup, 
            body_translation_lookup, 
            body_rotation_lookup
        ) = self._get_body_bone_lookups()

        self._bone_index_lookup = {
            self._dna_reader.getJointName(index): index
            for index in range(self._dna_reader.getJointCount())
        }

        _, bone_names, _, _, translations, rotations = self.get_bone_transforms(self._rig_object, extra_bones=self._extra_bones)
        for bone_name, bone_translation, bone_rotation  in zip(bone_names, translations, rotations):
            if bone_name in ignored_bone_names:
                continue

            # First check for the matching body bone, and use that instead if it exists
            bone_translation = body_translation_lookup.get(bone_name, Vector(bone_translation))
            bone_rotation = body_rotation_lookup.get(bone_name, Vector(bone_rotation))

            dna_bone_index = self._bone_index_lookup.get(bone_name)
            if dna_bone_index is not None:
                # first check for the matching body bone, and use that instead if it exists
                dna_bone_translation = dna_body_translation_lookup.get(
                    bone_name,
                    Vector((
                        dna_x_translations[dna_bone_index],
                        dna_y_translations[dna_bone_index],
                        dna_z_translations[dna_bone_index]
                    ))
                )
                translation_delta = bone_translation - dna_bone_translation

                # Only modify the bone translations that are different to avoid floating point value drift
                if translation_delta.length > BONE_DELTA_THRESHOLD:
                    dna_x_translations[dna_bone_index] = bone_translation[0]
                    dna_y_translations[dna_bone_index] = bone_translation[1]
                    dna_z_translations[dna_bone_index] = bone_translation[2]

                # Get the DNA bone rotation from the body rotation lookup, and use that if it exists
                dna_bone_rotation = dna_body_rotation_lookup.get(
                    bone_name, 
                    Vector((
                        dna_x_rotations[dna_bone_index],
                        dna_y_rotations[dna_bone_index],
                        dna_z_rotations[dna_bone_index]
                    ))
                )
                rotation_delta = bone_rotation - dna_bone_rotation

                # Only modify the bone rotations that are different to avoid floating point value drift
                # Also, handle angle wrapping (e.g., 180 vs -180 degrees) issues
                if BONE_DELTA_THRESHOLD < abs(rotation_delta.x) < 360:
                    dna_x_rotations[dna_bone_index] = bone_rotation[0]
                if BONE_DELTA_THRESHOLD < abs(rotation_delta.y) < 360:
                    dna_y_rotations[dna_bone_index] = bone_rotation[1]
                if BONE_DELTA_THRESHOLD < abs(rotation_delta.z) < 360:
                    dna_z_rotations[dna_bone_index] = bone_rotation[2]
            else:
                logger.warning(f'No DNA bone index found for bone "{bone_name}". Ignored from calibration...')
        
        self._dna_writer.setNeutralJointTranslations([
            [x, y, z] for x, y, z in zip(dna_x_translations, dna_y_translations, dna_z_translations)
        ])
        self._dna_writer.setNeutralJointRotations([
            [x, y, z] for x, y, z in zip(dna_x_rotations, dna_y_rotations, dna_z_rotations)
        ])

    def run(self) -> tuple[bool, str, str, Callable| None]:
        self.initialize_scene_data()
        if self._instance.output_run_validations:
            valid, title, message, fix = self.validate()
            if not valid:
                return False, title, message, fix

        if self._include_meshes:
            self.calibrate_vertex_positions()
        if self._include_shape_keys:
            self.calibrate_shape_keys()
        if self._include_bones:
            self.calibrate_bone_transforms()

        logger.info(f'Saving DNA to: "{self._target_dna_file}"...')
        self._dna_writer.write()

        if not riglogic.Status.isOk():
            status = riglogic.Status.get()
            raise RuntimeError(f"Error saving DNA: {status.message}")
        logger.info(f'DNA calibrated successfully to: "{self._target_dna_file}"')
        
        self.save_images()

        return True, "Success", f"Calibration of {self._component_type} successful.", None