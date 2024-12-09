import unreal
from pathlib import Path


def get_import_task(file_path: Path, content_folder: str):
    """
    Gets the import options.
    """
    import_task = unreal.AssetImportTask()
    import_task.set_editor_property('filename', str(file_path))
    import_task.set_editor_property('destination_path', content_folder)
    import_task.set_editor_property('replace_existing', True)
    import_task.set_editor_property('replace_existing_settings', True)
    import_task.set_editor_property('automated', True)
    return import_task

    
def run_import_task(import_task: unreal.AssetImportTask, options):
    """
    Runs the import task.
    """
    import_task.set_editor_property('options', options)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([import_task]) # type: ignore


def import_dna_file(
        file_path: Path, 
        skeletal_mesh_asset_path: str,
    ):
    skeletal_mesh = unreal.load_asset(skeletal_mesh_asset_path)
    if not skeletal_mesh:
        raise FileNotFoundError(f'Could not find skeletal mesh at "{skeletal_mesh_asset_path}"')

    options = unreal.DNAAssetImportUI() # type: ignore
    options.set_editor_property('skeletal_mesh', skeletal_mesh)

    content_folder = '/'+ '/'.join(skeletal_mesh_asset_path.strip('/').split('/')[:-1])
    import_task = get_import_task(file_path, content_folder)
    run_import_task(import_task, options)


def import_texture(file_path: Path, content_folder: str) -> unreal.Texture:
    options = unreal.TextureFactory()  # type: ignore
    import_task = get_import_task(file_path, content_folder)
    run_import_task(import_task, options)
    return unreal.load_asset(f'{content_folder}/{file_path.stem}')