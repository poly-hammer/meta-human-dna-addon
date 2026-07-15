# standard library imports
import logging
import shutil

from pathlib import Path
from types import ModuleType

# third party imports
import bpy

from ..constants import MASKS_TEXTURE, MASKS_TEXTURE_FILE_PATH, UV_MAP_NAME, ComponentType

# local imports
from .misc import editors_available, exclude_rig_instance_evaluation


logger = logging.getLogger(__name__)


def get_topology_texture_constants() -> ModuleType | None:
    if not editors_available():
        return None
    from ..editors.shared import constants as shared_constants

    return shared_constants


@exclude_rig_instance_evaluation
def copy_materials(
    mesh_object: bpy.types.Object, old_prefix: str, new_prefix: str, new_folder: Path
) -> bpy.types.Material | None:
    # duplicate the head mesh materials
    first_new_mesh_material = None
    for slot in mesh_object.material_slots:
        material = slot.material
        if material:
            new_material = material.copy()
            new_material.name = material.name.replace(old_prefix, new_prefix)
            slot.material = new_material
            if not first_new_mesh_material:
                first_new_mesh_material = new_material

            # duplicate the image nodes
            if new_material.node_tree:
                for node in new_material.node_tree.nodes:
                    if node.type == "TEX_IMAGE":
                        image = node.image  # type: ignore[attr-defined]
                        new_image = image.copy()
                        new_image.name = f"{new_prefix}_{image.name}".replace(f"{old_prefix}_", "")
                        # copy the image files to the new folder
                        if new_image.filepath and not new_image.packed_file:
                            image_file_path = Path(bpy.path.abspath(new_image.filepath))
                            if image_file_path.exists():
                                new_image_file_path = new_folder / "Maps" / image_file_path.name
                                new_image_file_path.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy(image_file_path, new_image_file_path)
                                new_image.filepath = str(new_image_file_path)
                        # assign the new image to the node
                        node.image = new_image  # type: ignore[attr-defined]
    return first_new_mesh_material


def prefix_material_image_names(material: bpy.types.Material, prefix: str):
    if material.node_tree:
        for node in material.node_tree.nodes:
            if node.type == "TEX_IMAGE":
                image = node.image  # type: ignore[attr-defined]
                name = image.name.removesuffix(".001")
                image.name = f"{prefix}_{name}"


def create_new_material(
    name: str, color: tuple[float, float, float, float] | None = None, alpha: float | None = None
) -> bpy.types.Material:
    material = bpy.data.materials.new(name=name)
    # `Material.use_nodes` is deprecated (removed in Blender 6.0); every material
    # already has a node tree by default on the addon's supported Blender range
    # (4.5+), so no explicit opt-in is needed.
    if not material.node_tree:
        logger.error(f"Material {name} has no node tree.")
        return material

    # Create a Principled BSDF shader node
    for node in material.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            if color:
                node.inputs["Base Color"].default_value = color  # type: ignore[attr-defined]
            if alpha is not None:
                node.inputs["Alpha"].default_value = alpha  # type: ignore[attr-defined]
    return material


def setup_texture_logic_node_groups(component_type: ComponentType):  # noqa: PLR0912
    """Load the placeholder mask/topology textures, assign them to every texture logic
    node group's image nodes, correct the UV map on the group's UVMAP and NORMAL_MAP
    nodes, and purge any duplicate placeholder images.
    """
    shared_constants = get_topology_texture_constants()

    # point the placeholder mask/topology images at the addon resources
    if component_type == "head":
        masks_image = bpy.data.images.get(MASKS_TEXTURE)
        if masks_image:
            masks_image.filepath = str(MASKS_TEXTURE_FILE_PATH)
        if shared_constants:
            head_topology_image = bpy.data.images.get(shared_constants.HEAD_TOPOLOGY_TEXTURE)
            if head_topology_image:
                head_topology_image.filepath = str(shared_constants.HEAD_TOPOLOGY_TEXTURE_FILE_PATH)
    elif component_type == "body":
        if shared_constants:
            body_topology_image = bpy.data.images.get(shared_constants.BODY_TOPOLOGY_TEXTURE)
            if body_topology_image:
                body_topology_image.filepath = str(shared_constants.BODY_TOPOLOGY_TEXTURE_FILE_PATH)

    # the canonical placeholder image names for this component type
    if component_type == "head":
        image_names = [MASKS_TEXTURE]
        if shared_constants:
            image_names.append(shared_constants.HEAD_TOPOLOGY_TEXTURE)
    else:
        image_names = [shared_constants.BODY_TOPOLOGY_TEXTURE] if shared_constants else []

    # remove any duplicate mask/topology placeholder images (e.g. combined_masks.tga.001)
    for image in list(bpy.data.images):
        if image.name in image_names:
            continue
        if any(i in image.name for i in image_names if i != image.name):
            bpy.data.images.remove(image)

    # assign the placeholder textures and correct the UV maps on every texture logic node group
    for node_group in bpy.data.node_groups:
        for node in node_group.nodes:
            if node.type == "TEX_IMAGE":
                if component_type == "head":
                    if node.label == MASKS_TEXTURE and MASKS_TEXTURE in bpy.data.images:
                        node.image = bpy.data.images[MASKS_TEXTURE]  # type: ignore[attr-defined]
                    if (
                        shared_constants
                        and node.label == shared_constants.HEAD_TOPOLOGY_TEXTURE
                        and shared_constants.HEAD_TOPOLOGY_TEXTURE in bpy.data.images
                    ):
                        node.image = bpy.data.images[shared_constants.HEAD_TOPOLOGY_TEXTURE]  # type: ignore[attr-defined]
                elif component_type == "body":
                    if (
                        shared_constants
                        and node.label == shared_constants.BODY_TOPOLOGY_TEXTURE
                        and shared_constants.BODY_TOPOLOGY_TEXTURE in bpy.data.images
                    ):
                        node.image = bpy.data.images[shared_constants.BODY_TOPOLOGY_TEXTURE]  # type: ignore[attr-defined]

        # correct the UV map on the mask and texture logic node groups
        if node_group.name.startswith("Mask"):
            for node in node_group.nodes:
                if node.type == "UVMAP":
                    node.uv_map = UV_MAP_NAME  # type: ignore[attr-defined]
        if node_group.name.lower().rsplit(".", 1)[0].endswith("_texture_logic"):
            for node in node_group.nodes:
                if node.type == "NORMAL_MAP":
                    node.uv_map = UV_MAP_NAME  # type: ignore[attr-defined]
