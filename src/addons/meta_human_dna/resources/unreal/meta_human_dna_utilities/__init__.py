def update_meta_human_face(asset_path: str, dna_file_path: str, head_material_name: str, face_control_rig_asset_path: str, face_anim_bp_asset_path: str, blueprint_asset_path: str, unreal_level_sequence_asset_path: str, copy_assets: bool, material_slot_to_instance_mapping: dict): # type: ignore
    import unreal
    from pathlib import Path
    from meta_human_dna_utilities.ingest import import_dna_file
    from meta_human_dna_utilities.skeletal_mesh import set_head_mesh_settings, get_head_mesh_assets
    from meta_human_dna_utilities.blueprint import create_actor_blueprint, add_face_component_to_blueprint
    from meta_human_dna_utilities.level_sequence import add_asset_to_level_sequence, create_level_sequence

    # post_fix =  f"_{asset_path.split('/')[-1]}"
    post_fix =  f""
    skeletal_mesh = unreal.load_asset(asset_path)
    dna_file_path: Path = Path(dna_file_path)

    # load the head mesh assets
    face_control_rig_asset, face_anim_bp_asset, material_instances = get_head_mesh_assets(
        content_folder=asset_path.rsplit('/', 1)[0],
        skeletal_mesh=skeletal_mesh,
        face_control_rig_asset_path=face_control_rig_asset_path, 
        face_anim_bp_asset_path=face_anim_bp_asset_path, 
        material_slot_to_instance_mapping=material_slot_to_instance_mapping, 
        copy_assets=copy_assets,
        post_fix=post_fix
    )
    
    # set the head mesh settings
    skeletal_mesh = set_head_mesh_settings(
        skeletal_mesh=skeletal_mesh, 
        head_material_name=head_material_name,
        face_control_rig_asset=face_control_rig_asset, # type: ignore
        face_anim_bp_asset=face_anim_bp_asset, # type: ignore
        material_instances=material_instances,
        texture_disk_folder=dna_file_path.parent / 'maps',
        texture_content_folder=F"{asset_path.rsplit('/', 1)[0]}/Textures"
    )
    # then import the dna file onto the head mesh
    import_dna_file(
        dna_file_path,
        asset_path
    )

    if not blueprint_asset_path:
        blueprint_asset_path = f'{asset_path}_BP'

    # create the blueprint asset
    blueprint = create_actor_blueprint(blueprint_asset_path)

    # add the face component to the blueprint
    add_face_component_to_blueprint(
        blueprint=blueprint,
        skeletal_mesh=skeletal_mesh
    )
    
    # if a level sequence path is provided
    if unreal_level_sequence_asset_path:
        level_sequence = unreal.load_asset(unreal_level_sequence_asset_path)

        # if the level sequence does not exist, create it
        if not level_sequence:
            content_folder = '/' + '/'.join([i for i in unreal_level_sequence_asset_path.split('/')[:-1] if i])
            level_sequence_name = unreal_level_sequence_asset_path.split('/')[-1]
            create_level_sequence(
                content_folder=content_folder,
                name=level_sequence_name
            )

        # add the asset to the level
        add_asset_to_level_sequence(
            asset=blueprint,
            level_sequence=level_sequence,
            label=blueprint.get_name()
        )

    # recompile the control rig asset
    face_control_rig_asset.recompile_vm() # type: ignore


def get_body_bone_transforms(blueprint_asset_path: str) -> dict:
    import unreal
    from meta_human_dna_utilities.blueprint import get_body_skinned_mesh_component
    from meta_human_dna_utilities.skeleton import get_bone_transforms

    blueprint = unreal.load_asset(blueprint_asset_path)
    if blueprint:
        skeletal_mesh = get_body_skinned_mesh_component(blueprint=blueprint)
        return get_bone_transforms(skeletal_mesh)
    return {}