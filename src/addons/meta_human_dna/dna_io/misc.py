import os
import bpy
import math
import logging
from pathlib import Path
from mathutils import Vector, Matrix
from typing import Literal, TYPE_CHECKING
from ..constants import SHAPE_KEY_GROUP_PREFIX
from ..utilities import (
    exclude_rig_logic_evaluation, 
    switch_to_object_mode,
    update_mesh
)

if TYPE_CHECKING:
    from ..bindings import riglogic

logger = logging.getLogger(__name__)

FileFormat = Literal['binary', 'json']
DataLayer = Literal[
    'Descriptor', 
    'Definition', 
    'Behavior',
    'Geometry',
    'GeometryWithoutBlendShapes',
    'AllWithoutBlendShapes',
    'All',
]

def get_dna_reader(
        file_path: Path,
        file_format: FileFormat = 'binary',
        data_layer: DataLayer = 'All'
    ) -> 'riglogic.BinaryStreamReader':
    from ..bindings import riglogic # noqa: F811 
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File '{file_path}' does not exist.")
    
    mode = riglogic.OpenMode.Binary
    # if file_format.lower() == 'json':
    #     mode = riglogic.OpenMode.Text

    stream = riglogic.FileStream.create( 
        path=str(file_path),
        accessMode=riglogic.AccessMode.Read, 
        openMode=mode, 
        memRes=None
    )
    if file_format.lower() == 'json':
        reader = riglogic.JSONStreamReader.create( 
            stream,
            getattr(riglogic.DataLayer, data_layer), 
            riglogic.UnknownLayerPolicy.Preserve, 
            0,  # Provide appropriate int value
            None  # Assuming MemoryResource is None
        )
    elif file_format.lower() == 'binary':
        reader = riglogic.BinaryStreamReader.create( 
            stream,
            getattr(riglogic.DataLayer, data_layer), 
            riglogic.UnknownLayerPolicy.Preserve, 
            0,  # Provide appropriate int value
            None  # Assuming MemoryResource is None
        )
    else:
        raise ValueError(f"Invalid file format '{file_format}'. Must be 'binary' or 'json'.")
    
    try:
        reader.read()
    except IndexError as error:
        logger.debug(f"Error reading DNA file '{file_path}': {error}")
        return

    if not riglogic.Status.isOk(): 
        status = riglogic.Status.get() 
        raise RuntimeError(f'Error loading DNA: {status.message} from "{file_path}"')
    return reader


def get_dna_writer(
        file_path: Path,
        file_format: FileFormat = 'binary'
    ) -> 'riglogic.BinaryStreamWriter':
    from ..bindings import riglogic # noqa: F811 
    file_path = Path(file_path)
    os.makedirs(file_path.parent, exist_ok=True)

    mode = riglogic.OpenMode.Binary
    # if file_format.lower() == 'json':
    #     mode = riglogic.OpenMode.Text

    stream = riglogic.FileStream.create( 
        path=str(file_path),
        accessMode=riglogic.AccessMode.Write,
        openMode=mode,
    )
    if file_format.lower() == 'json':
        writer = riglogic.JSONStreamWriter.create(stream)
    elif file_format.lower() == 'binary':
        writer = riglogic.BinaryStreamWriter.create(stream)
    else:
        raise ValueError(f"Invalid file format '{file_format}'. Must be 'binary' or 'json'.")
    
    return writer

@exclude_rig_logic_evaluation
def create_shape_key(
        index: int,
        mesh_index: int,
        mesh_object: bpy.types.Object,
        reader: 'riglogic.BinaryStreamReader',
        name: str,
        prefix: str = '',
        is_neutral: bool = False,
        linear_modifier: float = 1.0,
        delta_threshold: float = 0.0001
    ) -> bpy.types.ShapeKey:
    if not mesh_object:
        logger.error(f"Mesh object not found for shape key {name}. Skipping creation.")
        return

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

    # Import the deltas if the shape key is not supposed to be neutral
    if not is_neutral:
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
            index=[int(x) for x in offset_vertex_indices], # type: ignore
            weight=1.0,
            type='REPLACE'
        )

    shape_key_block.lock_shape = True

    update_mesh(mesh_object)

    return shape_key_block