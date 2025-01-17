import os
import bpy
import math
import logging
from pathlib import Path
from mathutils import Vector, Matrix
from typing import Literal
from ..bindings import dna
from ..constants import SHAPE_KEY_GROUP_PREFIX
from ..utilities import (
    exclude_rig_logic_evaluation, 
    switch_to_object_mode,
    update_mesh
)

logger = logging.getLogger(__name__)

FileFormat = Literal['binary', 'json']


def get_dna_reader(
        file_path: Path, 
        file_format: FileFormat = 'binary',
        data_layer: Literal[
            'Descriptor', 
            'Definition', 
            'Behavior',
            'Geometry',
            'GeometryWithoutBlendShapes',
            'AllWithoutBlendShapes',
            'All',
        ] = 'All'
    ) -> dna.BinaryStreamReader | dna.JSONStreamReader:
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File '{file_path}' does not exist.")
    
    mode = dna.FileStream.OpenMode_Binary
    # if file_format.lower() == 'json':
    #     mode = dna.FileStream.OpenMode_Text

    stream = dna.FileStream(
        str(file_path),
        dna.FileStream.AccessMode_Read,
        mode
    )
    reader = dna.JSONStreamReader(stream)
    if file_format.lower() == 'json':
        reader = dna.JSONStreamReader(stream)
    elif file_format.lower() == 'binary':
        reader = dna.BinaryStreamReader(stream, getattr(dna, f'DataLayer_{data_layer}'))
    else:
        raise ValueError(f"Invalid file format '{file_format}'. Must be 'binary' or 'json'.")
    
    reader.read()
    if not dna.Status.isOk():
        status = dna.Status.get()
        raise RuntimeError(f"Error loading DNA: {status.message}")
    stream.close()
    return reader

def get_dna_writer(
        file_path: Path,
        file_format: FileFormat = 'binary'
    ) -> dna.BinaryStreamWriter | dna.JSONStreamWriter:
    file_path = Path(file_path)
    os.makedirs(file_path.parent, exist_ok=True)

    mode = dna.FileStream.OpenMode_Binary
    # if file_format.lower() == 'json':
    #     mode = dna.FileStream.OpenMode_Text

    stream = dna.FileStream(
        str(file_path),
        dna.FileStream.AccessMode_Write,
        mode
    )
    if file_format.lower() == 'json':
        writer = dna.JSONStreamWriter(stream)
    elif file_format.lower() == 'binary':
        writer = dna.BinaryStreamWriter(stream)
    else:
        raise ValueError(f"Invalid file format '{file_format}'. Must be 'binary' or 'json'.")
    return writer

@exclude_rig_logic_evaluation
def create_shape_key(
        index: int,
        mesh_index: int,
        mesh_object: bpy.types.Object,
        reader: dna.BinaryStreamReader,
        name: str,
        prefix: str = '',
        linear_modifier: float = 1.0,
        delta_threshold: float = 0.0001
    ) -> bpy.types.ShapeKey:
    bpy.context.window_manager.meta_human_dna.progress_mesh_name = mesh_object.name # type: ignore
    # create the new key block on the shape key 
    logger.info(f"Creating shape key {name}")
    shape_key_name = f'{prefix}{name}'
    
    switch_to_object_mode()
    shape_key = mesh_object.data.shape_keys.key_blocks.get(shape_key_name) # type: ignore
    if shape_key:
        shape_key.lock_shape = False
        mesh_object.shape_key_remove(shape_key)

    shape_key_block = mesh_object.shape_key_add(name=shape_key_name)

    # DNA is Y-up, Blender is Z-up, so we need to rotate the deltas
    rotation_matrix = Matrix.Rotation(math.radians(-90), 4, 'X')

    delta_x_values = reader.getBlendShapeTargetDeltaXs(mesh_index, index)
    delta_y_values = reader.getBlendShapeTargetDeltaYs(mesh_index, index)
    delta_z_values = reader.getBlendShapeTargetDeltaZs(mesh_index, index)
    vertex_indices = reader.getBlendShapeTargetVertexIndices(mesh_index, index)

    # Not all vertices in the shape key are, so we need to filter out the ones that are
    # past the threshold
    offset_vertex_indices = []

    # the new vertex layout is the original vertex layout with the deltas from the dna applied
    for vertex_index, delta_x, delta_y, delta_z in zip(vertex_indices, delta_x_values, delta_y_values, delta_z_values):
        try:
            delta = Vector((delta_x, delta_y, delta_z)) * linear_modifier
            rotated_delta = rotation_matrix @ delta
            
            # set the positions of the points
            shape_key_block.data[vertex_index].co = mesh_object.data.vertices[vertex_index].co + rotated_delta # type: ignore
            if delta.length > delta_threshold:
                offset_vertex_indices.append(vertex_index)
        except IndexError:
            logger.warning(f'Vertex index {vertex_index} is missing for shape key "{name}". Was this deleted on the base mesh "{mesh_object.name}"?')

    # create a vertex group for the shape key vertices so we can easily select
    vertex_group_name = f'{SHAPE_KEY_GROUP_PREFIX}{name}'
    vertex_group = mesh_object.vertex_groups.get(vertex_group_name)
    if vertex_group:
        mesh_object.vertex_groups.remove(vertex_group)
    vertex_group = mesh_object.vertex_groups.new(name=vertex_group_name)
    vertex_group.add(
        index=offset_vertex_indices,
        weight=1.0,
        type='REPLACE'
    )

    shape_key_block.lock_shape = True

    update_mesh(mesh_object)

    return shape_key_block