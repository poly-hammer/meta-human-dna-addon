import sys
import pytest
import bpy
from pathlib import Path

@pytest.fixture(scope='session', autouse=True)
def addon(addons: list[tuple[str, Path]]):
    for addon_name, scripts_folder in addons:
        script_directory = bpy.context.preferences.filepaths.script_directories.get(addon_name) # type: ignore
        if script_directory:
            bpy.context.preferences.filepaths.script_directories.remove(script_directory) # type: ignore

        script_directory = bpy.context.preferences.filepaths.script_directories.new() # type: ignore
        script_directory.name = addon_name
        script_directory.directory = str(scripts_folder)
        sys.path.append(str(scripts_folder))

    for addon_name, _ in addons:
        bpy.ops.preferences.addon_enable(module=addon_name)

    yield

    for addon_name, scripts_folder in addons:
        bpy.ops.preferences.addon_disable(module=addon_name)
        sys.path.remove(str(scripts_folder))
        bpy.context.preferences.filepaths.script_directories.remove(script_directory) # type: ignore

    # Forces Blender to free memory blocks
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # Close Blender
    bpy.ops.wm.quit_blender()