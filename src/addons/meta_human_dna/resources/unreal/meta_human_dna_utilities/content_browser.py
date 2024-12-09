import unreal
from pathlib import Path
from typing import List


def get_assets_in_folder(content_folder: str, recursive: bool =False) -> List[unreal.Object]:
    """
    Get assets in the given content folder.

    Args:
        content_folder (str): The path where this asset is located in the project. i.e. '/Game/MyFolder'
        recursive (bool, optional): Whether to search all folders under that path. Defaults to False.

    Returns:
        List[unreal.Object]: A list of assets.
    """
    assets = []
    asset_library = unreal.EditorAssetLibrary()
    for asset_path in asset_library.list_assets(content_folder, recursive=recursive, include_folder=False):
        asset = unreal.load_asset(asset_path)
        if asset:
            assets.append(asset)
    return assets

def create_asset(
        asset_path: str, 
        asset_class: unreal.Class, 
        asset_factory: unreal.Factory, 
        unique_name: bool = True
    ) -> unreal.Object:
    """
    Creates a new unreal asset.

    Args:
        asset_path (str): The project path to the asset.
        
        asset_class (unreal.Class): The unreal asset class.
        
        asset_factory (unreal.Factory): The unreal factory.
        
        unique_name (bool, optional): Whether or not to check if the name 
            is unique before creating the asset. Defaults to True.

    Returns:
        unreal.Object: The created asset.
    """
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    if unique_name:
        asset_path, _ = asset_tools.create_unique_asset_name(
            base_package_name=asset_path,
            suffix=''
        )
    path, name = asset_path.rsplit("/", 1)
    return asset_tools.create_asset(
        asset_name=name,
        package_path=path,
        asset_class=asset_class,
        factory=asset_factory
    )


def copy_asset_to_folder(
        asset_path: str, 
        content_folder: str, 
        overwrite: bool = False,
        post_fix: str = ''
    ) -> unreal.Object:
    """
    Copy the assets to the given content folder.

    Args:
        asset_path (str): The path to the asset.
        
        content_folder (str): The path where the asset will be copied to.
        
        overwrite (bool): Whether to overwrite the asset if it already exists.
    
    Returns:
        unreal.Object | None: The copied asset.
    """
    asset_subsystem = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)

    asset_name = asset_path.split('/')[-1]
    asset = unreal.load_asset(asset_path)
    if not asset:
        raise FileExistsError(f"Asset {asset_path} does not exist.")
    
    destination_path = f'{content_folder}/{asset_name}{post_fix}'
    if asset_subsystem.does_asset_exist(destination_path) and not overwrite: # type: ignore
        return unreal.load_asset(destination_path)

    
    duplicated_asset = unreal.EditorAssetLibrary.duplicate_asset(
        source_asset_path=asset_path,
        destination_asset_path=destination_path
    )
    return duplicated_asset