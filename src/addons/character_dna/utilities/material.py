# standard library imports
import logging
import shutil

from pathlib import Path

# third party imports
import bpy

# local imports
from .misc import exclude_rig_instance_evaluation


logger = logging.getLogger(__name__)


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
    if hasattr(material, "use_nodes"):
        material.use_nodes = True
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
