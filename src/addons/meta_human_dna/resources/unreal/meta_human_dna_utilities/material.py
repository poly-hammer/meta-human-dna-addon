import unreal
from pathlib import Path
from meta_human_dna_utilities.ingest import import_texture
from meta_human_dna_utilities.constants import MATERIAL_INSTANCE_PARAMETERS


def update_material_instance_params(
        material_instance: unreal.MaterialInstanceConstant,
        maps_folder: Path,
        content_folder: str
    ):
    for param_name, texture_name in MATERIAL_INSTANCE_PARAMETERS.get(material_instance.get_name(), {}).items():
        file_path = maps_folder / texture_name
        if file_path.exists():
            texture = import_texture(
                    file_path=file_path,
                    content_folder=content_folder
            )
            unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(
                instance=material_instance,
                parameter_name=unreal.Name(param_name),
                value=texture
            )

    # the roughness map is a special case where it is a composite texture of the base normal map
    head_roughness_map = unreal.load_asset(f'{content_folder}/head_roughness_map')
    head_normal_map = unreal.load_asset(f'{content_folder}/head_normal_map')
    if head_roughness_map and head_normal_map:
        head_roughness_map.set_editor_property('composite_texture', head_normal_map)
        head_roughness_map.set_editor_property('composite_texture_mode', unreal.CompositeTextureMode.CTM_NORMAL_ROUGHNESS_TO_GREEN)