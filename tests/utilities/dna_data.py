import json
from constants import SAMPLE_DNA_FILE
from pathlib import Path
from meta_human_dna.bindings import dna
from meta_human_dna.dna_io import (
    get_dna_reader, 
    get_dna_writer
)

def get_dna_json_data(dna_file_path: Path, json_file_path: Path) -> dict:
    reader = get_dna_reader(dna_file_path, 'binary')
    writer = get_dna_writer(json_file_path, 'json')
    writer.setFrom(reader)
    writer.write()
    if not dna.Status.isOk():
        status = dna.Status.get()
        raise RuntimeError(f"Error saving DNA: {status.message}")
    
    with open(json_file_path, 'r') as file:
        return json.load(file)
    

def get_bone_names(dna_file_path: Path) -> list[str]:
    reader = get_dna_reader(
        file_path=dna_file_path, 
        file_format='binary',
        data_layer='Definition'
    )
    return [reader.getJointName(index) for index in range(reader.getJointCount())]

def get_mesh_names(dna_file_path: Path) -> list[str]:
    reader = get_dna_reader(
        file_path=dna_file_path, 
        file_format='binary',
        data_layer='Definition'
    )    
    return [reader.getMeshName(index) for index in range(reader.getMeshCount())]


def get_test_bone_definitions_params():

    for bone_name in get_bone_names(SAMPLE_DNA_FILE):
        attributes = ['neutralJointRotations', 'neutralJointTranslations']
        axis_names = ['x', 'y', 'z']
        for attribute in attributes:
            for axis_name in axis_names:
                yield bone_name, attribute, axis_name

def get_test_bone_behaviors_params():
    for bone_name in get_bone_names(SAMPLE_DNA_FILE):
        yield bone_name

def get_test_mesh_geometry_params(
        lods: list[int] | None = None,
        vertex_positions: bool = True,
        normals: bool = True,
        uvs: bool = True
    ):
    for mesh_name in get_mesh_names(SAMPLE_DNA_FILE):
        if lods:
            # skip checking meshes that are not in the specified lods
            if not any(mesh_name.endswith(f'_lod{lod}_mesh') for lod in lods):
                continue
        
        attributes = []
        if vertex_positions:
            attributes.append('positions')
        if normals:
            attributes.append('normals')
        if uvs:
            attributes.append('textureCoordinates')

        for attribute in attributes:
            axis_names = ['x', 'y', 'z']
            if attribute == 'textureCoordinates':
                axis_names = ['u', 'v']

            for axis_name in axis_names:
                yield mesh_name, attribute, axis_name