import unreal
from typing import Optional
from meta_human_dna_utilities import asset
from meta_human_dna_utilities.constants import FACE_GROOM_NAMES


def create_actor_blueprint(asset_path: str) -> unreal.Blueprint:
    asset_subsystem = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    blueprint_factory = unreal.BlueprintFactory()
    blueprint_factory.set_editor_property("parent_class", unreal.Actor)
    if not asset_subsystem.does_asset_exist(asset_path): # type: ignore
        return asset.create_asset(
            asset_path=asset_path,
            asset_class=None,
            asset_factory=blueprint_factory,
            unique_name=False
        ) # type: ignore
    else:
        return unreal.load_asset(asset_path)
    
def get_handle(blueprint: unreal.Blueprint, name: str) -> Optional[unreal.SubobjectDataHandle]:
    sub_object_data_subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    sub_object_data_library = unreal.SubobjectDataBlueprintFunctionLibrary()
    sub_object_data_handles = sub_object_data_subsystem.k2_gather_subobject_data_for_blueprint( # type: ignore
        context=blueprint
    ) or [] 
    for handle in sub_object_data_handles:
        data = sub_object_data_library.get_data(handle)
        variable_name = sub_object_data_library.get_variable_name(data)
        if variable_name == name:
            return handle
        
def update_groom_components(
        blueprint: unreal.Blueprint,
        skeletal_mesh: unreal.SkeletalMesh,
        groom_names: Optional[list[str]] = None
    ):
    if not groom_names:
        return

    sub_object_data_subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    sub_object_data_library = unreal.SubobjectDataBlueprintFunctionLibrary()
    sub_object_data_handles = sub_object_data_subsystem.k2_gather_subobject_data_for_blueprint( # type: ignore
        context=blueprint
    ) or [] 
    for handle in sub_object_data_handles:
        data = sub_object_data_library.get_data(handle)
        component_object = sub_object_data_library.get_object(data)
        # Check if it's a groom component
        if isinstance(component_object, unreal.GroomComponent):
            groom_name = sub_object_data_library.get_variable_name(data)
            if groom_name in groom_names:
                # update the binding asset for the groom component
                if component_object.binding_asset:
                    component_object.binding_asset.set_editor_property(
                        "target_skeletal_mesh", skeletal_mesh
                    )
        
def add_skeletal_mesh_component_to_blueprint(
        blueprint: unreal.Blueprint,
        handle: unreal.SubobjectDataHandle,
        component_name: str,
        skeletal_mesh: Optional[unreal.SkeletalMesh] = None
) -> unreal.SubobjectDataHandle:
    sub_object_data_subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    sub_object_data_library = unreal.SubobjectDataBlueprintFunctionLibrary()

    # create the sub-object data handle
    sub_object_data_handle, fail_reason = sub_object_data_subsystem.add_new_subobject( # type: ignore
        unreal.AddNewSubobjectParams(
            parent_handle=handle,
            new_class=unreal.SkeletalMeshComponent, # type: ignore
            blueprint_context=blueprint,
            conform_transform_to_parent=True
        )
    )
    if not fail_reason.is_empty():
        raise Exception("Failed to create component: {fail_reason}")
    
    # rename the handle
    sub_object_data_subsystem.rename_subobject( # type: ignore
        handle=sub_object_data_handle,
        new_name=unreal.Text(component_name)
    )
    
    # create the skeletal mesh component
    skeletal_mesh_component = sub_object_data_library.get_object(
        sub_object_data_library.get_data(sub_object_data_handle)
    )

    # set the skeletal mesh if provided
    if skeletal_mesh:
        skeletal_mesh_component.set_skeletal_mesh_asset(skeletal_mesh) # type: ignore

    return sub_object_data_handle

def get_root_handle(blueprint: unreal.Blueprint) -> Optional[unreal.SubobjectDataHandle]:
    sub_object_data_subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    sub_object_data_library = unreal.SubobjectDataBlueprintFunctionLibrary()
    sub_object_data_handles = sub_object_data_subsystem.k2_gather_subobject_data_for_blueprint( # type: ignore
        context=blueprint
    ) or []
    for handle in sub_object_data_handles:
        data = sub_object_data_library.get_data(handle)
        # find the root component
        if sub_object_data_library.is_root_component(data):
            variable_name = sub_object_data_library.get_variable_name(data)
            # ensure the root component is named 'Root'
            if variable_name != 'Root':
                sub_object_data_subsystem.rename_subobject( # type: ignore
                    handle=handle, 
                    new_name=unreal.Text('Root')
                )
            return handle

def add_face_component_to_blueprint(
        blueprint: unreal.Blueprint,
        skeletal_mesh: unreal.SkeletalMesh
    ):
    root_handle = get_root_handle(blueprint)
    if root_handle:
        # create the body component if it does not exist
        body_handle = get_handle(blueprint, 'Body')
        if not body_handle:
            body_handle = add_skeletal_mesh_component_to_blueprint(
                blueprint=blueprint,
                handle=root_handle,
                component_name='Body',
                skeletal_mesh=None
            )

        # add the face component with the face skeletal mesh
        face_handle = get_handle(blueprint, 'Face')
        if not face_handle:
            face_handle = add_skeletal_mesh_component_to_blueprint(
                blueprint=blueprint,
                handle=body_handle,
                component_name='Face',
                skeletal_mesh=skeletal_mesh
            )
        # otherwise update the existing skeletal mesh component
        elif skeletal_mesh:
            sub_object_data_library = unreal.SubobjectDataBlueprintFunctionLibrary()
            skeletal_mesh_component = sub_object_data_library.get_object(
                sub_object_data_library.get_data(face_handle)
            )
            skeletal_mesh_component.set_skeletal_mesh_asset(skeletal_mesh) 

        # update the groom bindings to be the face skeletal mesh
        if skeletal_mesh:
            update_groom_components(
                blueprint=blueprint,
                skeletal_mesh=skeletal_mesh,
                groom_names=FACE_GROOM_NAMES
            )

        # compile the blueprint to apply the changes
        unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    else:
        raise Exception("Could not find root component")
    

def get_body_skinned_mesh_component(blueprint: unreal.Blueprint) -> Optional[unreal.Skeleton]:
    sub_object_data_library = unreal.SubobjectDataBlueprintFunctionLibrary()
    body_handle = get_handle(blueprint, 'Body')
    if body_handle:
        skeletal_mesh_component = sub_object_data_library.get_object(
            sub_object_data_library.get_data(body_handle)
        )
        return skeletal_mesh_component
    return None


def create_child_anim_blueprint(
        parent_anim_blueprint: unreal.AnimBlueprint,
        target_skeleton: unreal.Skeleton,
        asset_path: str
) -> unreal.AnimBlueprint:
    """
    Create a child animation blueprint from a parent animation blueprint.
    """
    asset_subsystem = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    
    if not asset_subsystem.does_asset_exist(asset_path): # type: ignore
        # Create the factory for animation blueprints
        anim_blueprint_factory = unreal.AnimBlueprintFactory()
        
        # Set the parent class to the parent animation blueprint's generated class
        anim_blueprint_factory.set_editor_property("parent_class", parent_anim_blueprint.generated_class())
        
        # Set the target skeleton
        anim_blueprint_factory.set_editor_property("target_skeleton", target_skeleton)
        
        # Create the asset
        return asset.create_asset(
            asset_path=asset_path,
            asset_class=unreal.AnimBlueprint,
            asset_factory=anim_blueprint_factory,
            unique_name=False
        )
    else:
        return unreal.load_asset(asset_path)