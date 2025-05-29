import unreal
from pathlib import Path
from meta_human_dna_utilities.material import update_material_instance_params
from meta_human_dna_utilities.content_browser import copy_asset_to_folder
from meta_human_dna_utilities.blueprint import create_child_anim_blueprint
from meta_human_dna_utilities.constants import (
    RecomputeTangentsVertexMaskChannel,
    SKELETAL_MESH_LOD_INFO_PROPERTIES
)


def get_skeletal_mesh_materials(skeletal_mesh: unreal.SkeletalMesh) -> dict:
    materials = {}
    for index, material in enumerate(skeletal_mesh.materials):
        materials[str(material.get_editor_property('imported_material_slot_name'))] = index
    return materials

def set_material_slots(skeletal_mesh: unreal.SkeletalMesh, material_instances: dict):
    new_materials = unreal.Array(unreal.SkeletalMaterial)
    for material in skeletal_mesh.materials:
        slot_name = material.get_editor_property('imported_material_slot_name')
        material_instance = material_instances.get(str(slot_name))
        if material_instance:
            new_materials.append(unreal.SkeletalMaterial(
                material_interface=material_instance,
                material_slot_name=slot_name,
            ))
        else:
            new_materials.append(material)

    skeletal_mesh.set_editor_property('materials', new_materials)

def set_head_mesh_settings(
        skeletal_mesh: unreal.SkeletalMesh, 
        head_material_name: str,
        face_control_rig_asset: unreal.ControlRig,
        face_anim_bp_asset: unreal.Blueprint,
        material_instances: dict,
        texture_disk_folder: Path,
        texture_content_folder: str
    ) -> unreal.SkeletalMesh:
    skeletal_mesh_subsystem = unreal.get_editor_subsystem(
        unreal.SkeletalMeshEditorSubsystem
    )

    if head_material_name:
        section_index = get_skeletal_mesh_materials(skeletal_mesh).get(head_material_name)

        if section_index is None:
            raise ValueError(
                f"Head material {head_material_name} was not found in {skeletal_mesh.get_path_name()}"
            )

        # first turn on recompute tangents for the section
        skeletal_mesh_subsystem.set_section_recompute_tangent( # type: ignore
            skeletal_mesh=skeletal_mesh,
            lod_index=0,
            section_index=section_index,
            recompute_tangent=True
        )
        # then set the recompute tangents vertex mask channel to green
        skeletal_mesh_subsystem.set_section_recompute_tangents_vertex_mask_channel( # type: ignore
            skeletal_mesh=skeletal_mesh,
            lod_index=0,
            section_index=section_index,
            recompute_tangents_vertex_mask_channel=RecomputeTangentsVertexMaskChannel.GREEN
        )

    # set the skin cache usage to enabled
    lods_info = skeletal_mesh.get_editor_property('lod_info').copy() # type: ignore
    lod0_info = unreal.SkeletalMeshLODInfo()
    # transfer the values from the original lod0_info to the new lod0_info
    if len(lods_info) >= 1:
        for property_name in SKELETAL_MESH_LOD_INFO_PROPERTIES:
            lod0_info.set_editor_property(
                property_name,
                lods_info[0].get_editor_property(property_name)
            )
    # make sure to set the skin cache usage to enabled
    lod0_info.set_editor_property('skin_cache_usage', unreal.SkinCacheUsage.ENABLED)
    lod_info_array = unreal.Array(unreal.SkeletalMeshLODInfo)
    lod_info_array.append(lod0_info)

    # transfer the values from the original lod_info array to the new lod_info array
    # if there are more than one lod_info elements
    if len(lods_info) > 1:
        for i in range(1, len(lods_info)):
            lod_info_array.append(lods_info[i])
    
    # re-assign the lod_info array to the skeletal mesh
    skeletal_mesh.set_editor_property('lod_info', lod_info_array)

    # set the control rig
    skeletal_mesh.set_editor_property('default_animating_rig', face_control_rig_asset)
    
    # set the post process anim blueprint
    animation_blueprint = unreal.EditorAssetLibrary.load_blueprint_class(face_anim_bp_asset.get_path_name())
    skeletal_mesh.set_editor_property(
        'post_process_anim_blueprint', 
        animation_blueprint
    )

    # set the user asset data
    asset_user_data = unreal.Array(unreal.AssetUserData)
    asset_user_data.append(unreal.DNAAsset()) # type: ignore
    asset_user_data.append(unreal.AssetGuideline())
    skeletal_mesh.set_editor_property('asset_user_data', asset_user_data)

    # set the material slots on the skeletal mesh
    set_material_slots(skeletal_mesh, material_instances)

    # set the material instance params
    for material_instance in material_instances.values():
        update_material_instance_params(
            material_instance=material_instance,
            maps_folder=texture_disk_folder,
            content_folder=texture_content_folder
        )

    return skeletal_mesh


def get_head_mesh_assets(
        content_folder: str,
        skeletal_mesh: unreal.SkeletalMesh,
        face_control_rig_asset_path: str, 
        face_anim_bp_asset_path: str, 
        material_slot_to_instance_mapping: dict, 
        copy_assets: bool = False,
        post_fix: str = ''
    ) -> tuple[unreal.ControlRig, unreal.Blueprint, dict]:
    # copy the needed assets to the content folder if copy_assets is True
    if copy_assets:
        face_control_rig_asset = copy_asset_to_folder(
            asset_path=face_control_rig_asset_path,
            content_folder=content_folder,
            overwrite=False,
            post_fix=post_fix
        )
        # Todo: https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/ControlRigBlueprint?application_version=5.4#unreal.ControlRigBlueprint.set_preview_mesh

        face_anim_bp_asset = copy_asset_to_folder(
            asset_path=face_anim_bp_asset_path,
            content_folder=content_folder,
            overwrite=False,
            post_fix=post_fix
        )
        # face_anim_bp_asset = create_child_anim_blueprint(
        #     parent_anim_blueprint=unreal.load_asset(face_anim_bp_asset_path),
        #     target_skeleton=skeletal_mesh.skeleton,
        #     asset_path=f"{content_folder}/ABP_{skeletal_mesh.get_name()}_FaceMesh_PostProcess"
        # )

        material_instances = {}
        for material_slot, material_asset_path in material_slot_to_instance_mapping.items():
            if material_asset_path:
                material_instances[material_slot] = copy_asset_to_folder(
                    asset_path=material_asset_path,
                    content_folder=content_folder + '/Materials',
                    overwrite=False,
                    post_fix=post_fix
                )
    else:
        face_control_rig_asset = unreal.load_asset(face_control_rig_asset_path)
        face_anim_bp_asset = unreal.load_asset(face_anim_bp_asset_path)
        material_instances = {}
        for material_slot, material_asset_path in material_slot_to_instance_mapping.items():
            if material_asset_path:
                material_instances[material_slot] = unreal.load_asset(material_asset_path)


    hierarchy_controller = face_control_rig_asset.get_hierarchy_controller() # type: ignore
    # remove all the bones from the hierarchy controller
    for key in face_control_rig_asset.hierarchy.get_all_keys(): # type: ignore
        if key.type == unreal.RigElementType.BONE:
            hierarchy_controller.remove_element(key)
    # then import the bones from the skeletal mesh
    hierarchy_controller.import_bones(
        skeletal_mesh.skeleton,
        replace_existing_bones=True
    ) # type: ignore

    # set the target skeleton for the face anim blueprint
    face_anim_bp_asset.set_editor_property('target_skeleton', skeletal_mesh.skeleton) # type: ignore

    return face_control_rig_asset, face_anim_bp_asset, material_instances # type: ignore