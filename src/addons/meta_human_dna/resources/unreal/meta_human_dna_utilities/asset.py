import unreal
from typing import Any

def create_asset(
        asset_path: str, 
        asset_class: Any = None, 
        asset_factory: Any = None, 
        unique_name: bool = True
    ) -> unreal.Object:
    """
    Creates a new unreal asset.

    Args:
        asset_path (str): The project path to the asset.
        
        asset_class (Any, optional): The unreal asset class. Defaults to None.
        
        asset_factory (Any, optional): The unreal factory. Defaults to None.
        
        unique_name (bool, optional): Whether or not the check if the name is 
            unique before creating the asset. Defaults to True.

    Returns:
        unreal.Object: A new unreal asset.
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