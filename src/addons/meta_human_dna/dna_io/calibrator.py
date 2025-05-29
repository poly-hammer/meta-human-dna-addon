import logging
from mathutils import Vector
from typing import Callable
from .importer import DNAImporter
from .exporter import DNAExporter
from ..bindings import riglogic
from ..constants import EXTRA_BONES

logger = logging.getLogger(__name__)

class DNACalibrator(DNAExporter, DNAImporter):
    def calibrate_vertex_positions(self):
        mesh_index_lookup = {self._dna_reader.getMeshName(index): index for index in range(self._dna_reader.getMeshCount())}

        for lod_index, mesh_objects in self._export_lods.items():
            logger.info(f'Calibrating LOD {lod_index}...')
            for mesh_object, _ in mesh_objects:
                real_name = mesh_object.name.replace(f'{self._instance.name}_', '')
                logger.info(f'Calibrating "{real_name}"...')
                mesh_index = mesh_index_lookup[mesh_object.name.replace(f'{self._instance.name}_', '')]
                bmesh_object = self.get_bmesh(mesh_object)
                vertex_indices, vertex_positions = self.get_mesh_vertex_positions(bmesh_object)
                bmesh_object.free()

                # Read these from the DNA file and modify these arrays so that they match the vertex indices match
                x_values = self._dna_reader.getVertexPositionXs(mesh_index)
                y_values = self._dna_reader.getVertexPositionYs(mesh_index)
                z_values = self._dna_reader.getVertexPositionZs(mesh_index)

                for vertex_index in vertex_indices:
                    vertex_position = Vector(vertex_positions[vertex_index])
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
        
    def calibrate_bone_transforms(self):
        ignored_bone_names = [i for i, _ in EXTRA_BONES]

        logger.info('Calibrating bones...')
        dna_x_translations = self._dna_reader.getNeutralJointTranslationXs()
        dna_y_translations = self._dna_reader.getNeutralJointTranslationYs()
        dna_z_translations = self._dna_reader.getNeutralJointTranslationZs()
        dna_x_rotations = self._dna_reader.getNeutralJointRotationXs()
        dna_y_rotations = self._dna_reader.getNeutralJointRotationYs()
        dna_z_rotations = self._dna_reader.getNeutralJointRotationZs()

        self._bone_index_lookup = {
            self._dna_reader.getJointName(index): index
            for index in range(self._dna_reader.getJointCount())
        }

        _, bone_names, _, _, translations, rotations = self.get_bone_transforms(self._rig_object)
        for bone_name, bone_translation, bone_rotation  in zip(bone_names, translations, rotations):
            if bone_name in ignored_bone_names:
                continue

            dna_bone_index = self._bone_index_lookup.get(bone_name)
            if dna_bone_index is not None:
                dna_bone_translation = Vector((
                    dna_x_translations[dna_bone_index],
                    dna_y_translations[dna_bone_index],
                    dna_z_translations[dna_bone_index]
                ))
                translation_delta = Vector(bone_translation) - dna_bone_translation

                # Only modify the bone translations that are different to avoid floating point value drift
                if translation_delta.length > 1e-3:
                    dna_x_translations[dna_bone_index] = bone_translation[0]
                    dna_y_translations[dna_bone_index] = bone_translation[1]
                    dna_z_translations[dna_bone_index] = bone_translation[2]

                dna_bone_rotation = Vector((
                    dna_x_rotations[dna_bone_index],
                    dna_y_rotations[dna_bone_index],
                    dna_z_rotations[dna_bone_index]
                ))
                rotation_delta = Vector(bone_rotation) - dna_bone_rotation
                # Only modify the bone rotations that are different to avoid floating point value drift
                # TODO: Currently, we only calibrate facial bones we need to investigate why the local rotations of other bones are not matching
                if bone_name.startswith('FACIAL_') and rotation_delta.length > 1e-3: # and not is_leaf:
                    dna_x_rotations[dna_bone_index] = bone_rotation[0]
                    dna_y_rotations[dna_bone_index] = bone_rotation[1]
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
        valid, title, message, fix = self.validate()
        if not valid:
            return False, title, message, fix

        if self._include_meshes:
            self.calibrate_vertex_positions()
        if self._include_bones:
            self.calibrate_bone_transforms()        

        logger.info(f'Saving DNA to: "{self._target_dna_file}"...')
        self._dna_writer.write()

        if not riglogic.Status.isOk():
            status = riglogic.Status.get()
            raise RuntimeError(f"Error saving DNA: {status.message}")
        logger.info(f'DNA calibrated successfully to: "{self._target_dna_file}"')
        
        self.save_images()

        return True, "Success", "Calibration successful.", None