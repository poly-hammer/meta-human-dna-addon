# standard library imports
import logging
import math

from pathlib import Path
from typing import Literal

# third party imports
import bpy
import numpy as np

from mathutils import Matrix

# local imports
from ..constants import SHAPE_KEY_BASIS_NAME, ComponentType
from ..typing import *  # noqa: F403
from ..utilities import (
    exclude_rig_instance_evaluation,
    get_addon_window_manager_properties,
    switch_to_object_mode,
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
    memory_resource: "dna.MemoryResource | None" = None,
) -> "dna.BinaryStreamReader":
    from ..bindings import dna  # type: ignore[reportAttributeAccessIssue]

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File '{file_path}' does not exist.")

    mode = dna.OpenMode_Binary
    # if file_format.lower() == 'json':
    #     mode = dna.OpenMode_Text  # noqa: ERA001

    stream = dna.FileStream.create(
        path=str(file_path), accessMode=dna.AccessMode_Read, openMode=mode, memRes=memory_resource
    )
    if file_format.lower() == "json":
        reader = dna.JSONStreamReader.create(
            stream,
            getattr(dna, f"DataLayer_{data_layer}"),
            dna.UnknownLayerPolicy_Preserve,
            0,  # Provide appropriate int value
            None,  # Assuming MemoryResource is None
        )
    elif file_format.lower() == "binary":
        reader = dna.BinaryStreamReader.create(
            stream,
            getattr(dna, f"DataLayer_{data_layer}"),
            dna.UnknownLayerPolicy_Preserve,
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

    if not dna.Status.isOk():
        status = dna.Status.get()
        raise RuntimeError(f'Error loading DNA: {status.message} from "{file_path}"')
    return reader


def get_dna_writer(file_path: Path, file_format: FileFormat = "binary") -> "dna.BinaryStreamWriter":
    from ..bindings import dna  # type: ignore[reportAttributeAccessIssue]

    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    mode = dna.OpenMode_Binary
    # if file_format.lower() == 'json':
    #     mode = dna.OpenMode_Text  # noqa: ERA001

    stream = dna.FileStream.create(
        path=str(file_path),
        accessMode=dna.AccessMode_Write,
        openMode=mode,
    )
    if file_format.lower() == "json":
        writer = dna.JSONStreamWriter.create(stream)
    elif file_format.lower() == "binary":
        writer = dna.BinaryStreamWriter.create(stream)
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
    reader: "dna.BinaryStreamReader",
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
    logger.debug(f"Creating shape key {name}")
    shape_key_name = f"{prefix}{name}"

    switch_to_object_mode()

    # remove any pre-existing key block with this name so re-imports overwrite cleanly
    shape_key = mesh_object.data.shape_keys.key_blocks.get(shape_key_name)  # type: ignore[attr-defined]
    if shape_key:
        shape_key.lock_shape = False
        mesh_object.shape_key_remove(shape_key)

    shape_key_block = mesh_object.shape_key_add(name=shape_key_name, from_mix=False)
    # zero the influence so the imported key is stored but not applied on top of the
    # basis (the delta geometry is written directly to the key block's data, so this
    # only affects the value slider, not the stored shape)
    shape_key_block.value = 0.0

    # Import the deltas if the shape key is not supposed to be neutral
    if not is_neutral:
        apply_blend_shape_deltas(
            mesh_object=mesh_object,
            shape_key_block=shape_key_block,
            reader=reader,
            mesh_index=mesh_index,
            index=index,
            name=name,
            linear_modifier=linear_modifier,
        )

    shape_key_block.lock_shape = True

    return shape_key_block


def apply_blend_shape_deltas(
    mesh_object: bpy.types.Object,
    shape_key_block: bpy.types.ShapeKey,
    reader: "dna.BinaryStreamReader",
    mesh_index: int,
    index: int,
    name: str,
    linear_modifier: float = 1.0,
) -> None:
    """Apply a DNA blend shape target's deltas onto ``shape_key_block`` using
    vectorized numpy + ``foreach_get``/``foreach_set`` for speed.

    Reads the basis (reference key) coordinates once, rotates the sparse deltas
    from DNA's Y-up space into Blender's Z-up space, scatters them onto the
    affected vertices, and writes the whole shape key in a single bulk call.
    """
    vertex_indices = reader.getBlendShapeTargetVertexIndices(mesh_index, index)
    if len(vertex_indices) == 0:
        return

    reference_key = mesh_object.data.shape_keys.reference_key  # type: ignore[attr-defined]
    vertex_count = len(reference_key.data)

    # read the basis coordinates once as a flat (x, y, z) array
    base_flat = np.empty(vertex_count * 3, dtype=np.float32)
    reference_key.data.foreach_get("co", base_flat)
    new_flat = base_flat.copy()
    base = base_flat.reshape(-1, 3)
    new = new_flat.reshape(-1, 3)

    vertex_indices = np.asarray(vertex_indices, dtype=np.int64)
    deltas = np.empty((len(vertex_indices), 3), dtype=np.float32)
    deltas[:, 0] = reader.getBlendShapeTargetDeltaXs(mesh_index, index)
    deltas[:, 1] = reader.getBlendShapeTargetDeltaYs(mesh_index, index)
    deltas[:, 2] = reader.getBlendShapeTargetDeltaZs(mesh_index, index)

    # DNA is Y-up, Blender is Z-up, so we need to rotate the deltas
    rotation = np.array(Matrix.Rotation(math.radians(90), 4, "X").to_3x3(), dtype=np.float32)
    rotated = (deltas * linear_modifier) @ rotation.T

    # guard against vertex indices that no longer exist on the base mesh
    valid = vertex_indices < vertex_count
    if not valid.all():
        logger.warning(
            f'Some vertex indices are missing for shape key "{name}". '
            f'Were they deleted on the base mesh "{mesh_object.name}"?'
        )
        vertex_indices = vertex_indices[valid]
        rotated = rotated[valid]

    # the new vertex layout is the original vertex layout with the deltas from the dna applied
    new[vertex_indices] = base[vertex_indices] + rotated
    shape_key_block.data.foreach_set("co", new_flat)
