# standard library imports
import logging
import math

from pathlib import Path
from typing import Literal

# third party imports
import bpy

from mathutils import Matrix, Vector

# local imports
from ..constants import SHAPE_KEY_BASIS_NAME, ComponentType
from ..typing import *  # noqa: F403
from ..utilities import (
    exclude_rig_instance_evaluation,
    get_addon_window_manager_properties,
    switch_to_object_mode,
    update_mesh,
)


logger = logging.getLogger(__name__)

FileFormat = Literal["binary", "json"]
DataLayer = Literal[
    "Descriptor",
    "Definition",
    "Behavior",
    "Geometry",
    "GeometryWithoutBlendShapes",
    "MachineLearnedBehavior",
    "RBFBehavior",
    "JointBehaviorMetadata",
    "TwistSwingBehavior",
    "All",
]


def get_dna_reader(
    file_path: Path,
    file_format: FileFormat = "binary",
    data_layer: DataLayer = "All",
    memory_resource: "riglogic.MemoryResource| None" = None,
) -> "riglogic.BinaryStreamReader":
    from ..bindings import riglogic  # type: ignore[reportAttributeAccessIssue]

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File '{file_path}' does not exist.")

    mode = riglogic.OpenMode.Binary
    # if file_format.lower() == 'json':
    #     mode = riglogic.OpenMode.Text  # noqa: ERA001

    stream = riglogic.FileStream.create(
        path=str(file_path), accessMode=riglogic.AccessMode.Read, openMode=mode, memRes=memory_resource
    )
    if file_format.lower() == "json":
        reader = riglogic.JSONStreamReader.create(
            stream,
            getattr(riglogic.DataLayer, data_layer),
            riglogic.UnknownLayerPolicy.Preserve,
            0,  # Provide appropriate int value
            None,  # Assuming MemoryResource is None
        )
    elif file_format.lower() == "binary":
        reader = riglogic.BinaryStreamReader.create(
            stream,
            getattr(riglogic.DataLayer, data_layer),
            riglogic.UnknownLayerPolicy.Preserve,
            0,  # Provide appropriate int value
            None,  # Assuming MemoryResource is None
        )
    else:
        raise ValueError(f"Invalid file format '{file_format}'. Must be 'binary' or 'json'.")

    try:
        reader.read()
    except IndexError as error:
        logger.debug(f"Error reading DNA file '{file_path}': {error}")
        return None

    if not riglogic.Status.isOk():
        status = riglogic.Status.get()
        raise RuntimeError(f'Error loading DNA: {status.message} from "{file_path}"')
    return reader


def get_dna_writer(file_path: Path, file_format: FileFormat = "binary") -> "riglogic.BinaryStreamWriter":
    from ..bindings import riglogic  # type: ignore[reportAttributeAccessIssue]

    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    mode = riglogic.OpenMode.Binary
    # if file_format.lower() == 'json':
    #     mode = riglogic.OpenMode.Text  # noqa: ERA001

    stream = riglogic.FileStream.create(
        path=str(file_path),
        accessMode=riglogic.AccessMode.Write,
        openMode=mode,
    )
    if file_format.lower() == "json":
        writer = riglogic.JSONStreamWriter.create(stream)
    elif file_format.lower() == "binary":
        writer = riglogic.BinaryStreamWriter.create(stream)
    else:
        raise ValueError(f"Invalid file format '{file_format}'. Must be 'binary' or 'json'.")

    return writer


def get_dna_component_type(file_path: Path) -> ComponentType | None:
    """
    Determine the DNA component type based on the mesh names in the DNA file.
    """
    component_type = None
    dna_reader = get_dna_reader(file_path=file_path, file_format="binary", data_layer="Definition")
    if dna_reader:
        for index in range(dna_reader.getMeshCount()):
            mesh_name = dna_reader.getMeshName(index)
            if "head" in mesh_name.lower():
                component_type = "head"
            elif "body" in mesh_name.lower():
                component_type = "body"
    return component_type


@exclude_rig_instance_evaluation
def create_shape_key(
    index: int,
    mesh_index: int,
    mesh_object: bpy.types.Object,
    reader: "riglogic.BinaryStreamReader",
    name: str,
    prefix: str = "",
    is_neutral: bool = False,
    linear_modifier: float = 1.0,
) -> bpy.types.ShapeKey | None:
    if not mesh_object:
        logger.error(f"Mesh object not found for shape key {name}. Skipping creation.")
        return None
    if not mesh_object.data or not isinstance(mesh_object.data, bpy.types.Mesh):
        logger.error(
            f"Object '{mesh_object.name}' has no mesh data in the blender scene. Skipping shape key creation..."
        )
        return None
    if not mesh_object.data.shape_keys:
        mesh_object.shape_key_add(name=SHAPE_KEY_BASIS_NAME, from_mix=False)

    window_manager_properties = get_addon_window_manager_properties()
    window_manager_properties.progress_mesh_name = mesh_object.name
    # create the new key block on the shape key
    logger.info(f"Creating shape key {name}")
    shape_key_name = f"{prefix}{name}"

    switch_to_object_mode()

    # Ensure no existing shape key influence is active before we create a new one
    if mesh_object.data.shape_keys:
        for key_block in mesh_object.data.shape_keys.key_blocks:
            key_block.value = 0.0
        mesh_object.active_shape_key_index = 0

    shape_key = mesh_object.data.shape_keys.key_blocks.get(shape_key_name)  # type: ignore[attr-defined]
    if shape_key:
        shape_key.lock_shape = False
        mesh_object.shape_key_remove(shape_key)

    shape_key_block = mesh_object.shape_key_add(name=shape_key_name, from_mix=False)

    # Import the deltas if the shape key is not supposed to be neutral
    if not is_neutral:
        # DNA is Y-up, Blender is Z-up, so we need to rotate the deltas
        rotation_matrix = Matrix.Rotation(math.radians(90), 4, "X")  # type: ignore[arg-type]

        delta_x_values = reader.getBlendShapeTargetDeltaXs(mesh_index, index)
        delta_y_values = reader.getBlendShapeTargetDeltaYs(mesh_index, index)
        delta_z_values = reader.getBlendShapeTargetDeltaZs(mesh_index, index)
        vertex_indices = reader.getBlendShapeTargetVertexIndices(mesh_index, index)

        # the new vertex layout is the original vertex layout with the deltas from the dna applied
        for vertex_index, delta_x, delta_y, delta_z in zip(
            vertex_indices, delta_x_values, delta_y_values, delta_z_values, strict=False
        ):
            try:
                delta = Vector((delta_x, delta_y, delta_z)) * linear_modifier
                rotated_delta = rotation_matrix @ delta

                # set the positions of the shape key vertices
                base_co = mesh_object.data.shape_keys.reference_key.data[vertex_index].co.copy()  # type: ignore[attr-defined]
                shape_key_block.data[vertex_index].co = base_co + rotated_delta
            except IndexError:
                logger.warning(
                    f'Vertex index {vertex_index} is missing for shape key "{name}". Was this deleted '
                    f'on the base mesh "{mesh_object.name}"?'
                )

    shape_key_block.lock_shape = True

    update_mesh(mesh_object)

    return shape_key_block
