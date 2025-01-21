import os
import sys
import math
import platform
import pytest
import shutil
from typing import TYPE_CHECKING
from pathlib import Path
from constants import REPO_ROOT

if TYPE_CHECKING:
    import bpy # import this to ensure that mathutils is available  # noqa: F401
    from mathutils import Vector, Euler

# Ensure that the riglogic module is not reloaded
if "riglogic" in sys.modules:
    riglogic = sys.modules["riglogic"]
else:
    import riglogic
    sys.modules["riglogic"] = riglogic

def pytest_configure():
    """
    Installs the bindings for the addon.
    """

    bindings_source_folder = REPO_ROOT.parent / 'meta-human-dna-bindings'
    core_source_folder = REPO_ROOT.parent / 'meta-human-dna-core'
    bindings_destination_folder = REPO_ROOT / 'src' / 'addons' / 'meta_human_dna' / 'bindings'

    arch = 'x64'
    if 'arm' in platform.processor().lower():
        arch = 'arm64'
    if sys.platform == 'win32' and arch == 'x64':
        arch = 'amd64'
    if sys.platform == 'linux' and arch == 'x64':
        arch = 'x86_64'


    os_name = 'windows'
    if sys.platform == 'darwin':
        os_name = 'mac'
    elif sys.platform == 'linux':
        os_name = 'linux'

    bindings_specific_source_folder = bindings_source_folder / os_name / arch
    bindings_specific_destination_folder = bindings_destination_folder / os_name / arch

    # Copy the bindings folder to the src directory if they doesn't exist
    if not bindings_specific_destination_folder.exists():
        if not bindings_specific_source_folder.exists():
            raise FileNotFoundError(
                f'The bindings in "{bindings_specific_destination_folder}" are missing. '
                'Please add them to run the tests.'
            )

        # Copy the bindings to the destination folder
        shutil.copytree(
            src=bindings_specific_source_folder,
            dst=bindings_specific_destination_folder,
            dirs_exist_ok=True
        )
        
        # If running tests on the CI, copy core to the specific destination folder
        if core_source_folder.exists() and os.environ.get('RUNNING_CI'):
            shutil.copytree(
                src=core_source_folder,
                dst=bindings_specific_destination_folder,
                dirs_exist_ok=True
            )   

    # ensure the addon module is on the python path
    sys.path.append(str(REPO_ROOT / 'src' / 'addons'))
        

from fixtures.addon import addon  # noqa: E402, F401
from fixtures.dna_data import ( # noqa: E402, F401
    original_dna_json_data,
    exported_dna_json_data,
    calibrated_dna_json_data
)
from fixtures.scene import (  # noqa: E402, F401
    load_dna,
    head_bmesh,
    head_armature,
    modify_scene
)

@pytest.fixture(scope='session')
def addons() -> list:
    return [
        ('meta_human_dna', Path(__file__).parent.parent / 'src')
    ]

@pytest.fixture(scope='session')
def dna_file_name() -> str:
    return 'ada.dna'

@pytest.fixture(scope='session')
def import_shape_keys() -> bool:
    return False

@pytest.fixture(scope='session')
def import_lods() -> list:
    return [
        'lod0'
    ]

@pytest.fixture(scope='session')
def changed_bone_name() -> str:
    return 'FACIAL_C_12IPV_Chin3' # has no children

@pytest.fixture(scope='session')
def changed_bone_location() -> 'tuple[Vector, Vector]':
    # change bone location (blender value, dna value)
    return (
        Vector((0.0, 0.005, 0.02)),  # relative change blender value Z-up
        # Vector((0.0671469, 0.319794, 9.78912)), # original dna value Y-up
        Vector((0.0671469, 0.643585, 11.8251)) # new dna value Y-up
    )

@pytest.fixture(scope='session')
def changed_bone_rotation() -> 'tuple[Euler, Euler]':
    # change rotation of bone (blender value, dna value)
    return (
        Euler((
        math.radians(60),
        math.radians(0),
        math.radians(0)
        )),
        Euler((60.0, 0.0, 0.0))
    )

@pytest.fixture(scope='session')
def changed_mesh_name() -> str:
    return 'head_lod0_mesh'

@pytest.fixture(scope='session')
def changed_vertex_index() -> int:
    return 11955

@pytest.fixture(scope='session')
def changed_vertex_location() -> 'tuple[Vector, Vector, Vector]':
    # change vertex location (blender value, dna value)
    # Moves vertex on the back of the head up 0.01 meters
    return (
        Vector((0.008358, 0.047561, 1.67178)),  # new blender value Z-up
        Vector((0.8358, 166.178, 4.7561)),  # original dna value Y-up
        Vector((0.8358, 167.178, 4.7561)), # new dna value Y-up
    )

@pytest.fixture(scope='session')
def temp_folder():
    temp_folder = Path(__file__).parent / 'temp'
    if temp_folder.exists():
        shutil.rmtree(temp_folder)  

    os.makedirs(temp_folder, exist_ok=True)
    
    yield temp_folder

    # Cleanup the temp folder
    if not os.environ.get('TESTS_KEEP_TEMP_FOLDER'):
        if temp_folder.exists():
            shutil.rmtree(temp_folder)


