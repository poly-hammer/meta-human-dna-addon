import bpy
import shutil
from pathlib import Path
from .misc import exclude_rig_logic_evaluation

@exclude_rig_logic_evaluation
def copy_materials(
        mesh_object: bpy.types.Object, 
        old_prefix: str,
        new_prefix: str,
        new_folder: Path
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
                    if node.type == 'TEX_IMAGE':
                        new_image = node.image.copy() # type: ignore
                        new_image.name = f'{new_prefix}_{node.image.name}'.replace(f'{old_prefix}_', '') # type: ignore
                        # copy the image files to the new folder
                        if new_image.filepath and not new_image.packed_file:
                            image_file_path = Path(bpy.path.abspath(new_image.filepath))
                            if image_file_path.exists():
                                new_image_file_path = new_folder / 'Maps' / image_file_path.name
                                new_image_file_path.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy(image_file_path, new_image_file_path)
                                new_image.filepath = str(new_image_file_path)
                        # assign the new image to the node
                        node.image = new_image # type: ignore
    return first_new_mesh_material
    

def prefix_material_image_names(material: bpy.types.Material, prefix: str):
    if material.node_tree:
        for node in material.node_tree.nodes:
            if node.type == 'TEX_IMAGE':
                name = node.image.name.rstrip('.001') # type: ignore
                node.image.name = f'{prefix}_{name}' # type: ignore


def create_new_material(
        name: str, 
        color: tuple[float, float, float, float] | None = None,
        alpha: float | None = None
    ) -> bpy.types.Material:
    material = bpy.data.materials.new(name=name)
    material.use_nodes = True
    # Create a Principled BSDF shader node
    for node in material.node_tree.nodes: # type: ignore
        if node.type == 'BSDF_PRINCIPLED':
            if color:
                node.inputs['Base Color'].default_value = color # type: ignore
            if alpha is not None:
                node.inputs['Alpha'].default_value = alpha # type: ignore
    return material