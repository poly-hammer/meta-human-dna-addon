import os
import sys
import math
import platform

ARCH = 'x64'
if 'arm' in platform.processor().lower():
    ARCH = 'arm64'
if sys.platform == 'win32' and ARCH == 'x64':
    ARCH = 'amd64'
if sys.platform == 'linux' and ARCH == 'x64':
    ARCH = 'x86_64'


OS_NAME = 'windows'
if sys.platform == 'darwin':
    OS_NAME = 'mac'
elif sys.platform == 'linux':
    OS_NAME = 'linux'

# Ensure that the riglogic module is not reloaded
sys.path.append(os.path.join(os.getcwd(), os.pardir, 'meta-human-dna-bindings', OS_NAME, ARCH))
if "riglogic" in sys.modules:
    riglogic = sys.modules["riglogic"]
else:
    import riglogic
    sys.modules["riglogic"] = riglogic


import pytest # noqa: E402
import shutil # noqa: E402
import bpy # import this to ensure that mathutils is available  # noqa: E402, F401
from mathutils import Vector, Euler # noqa: E402
from pathlib import Path # noqa: E402
from constants import REPO_ROOT # noqa: E402

def pytest_configure():
    """
    Installs the bindings for the addon.
    """

    bindings_source_folder = REPO_ROOT.parent / 'meta-human-dna-bindings'
    core_source_folder = REPO_ROOT.parent / 'meta-human-dna-core'
    bindings_destination_folder = REPO_ROOT / 'src' / 'addons' / 'meta_human_dna' / 'bindings'

    

    bindings_specific_source_folder = bindings_source_folder / OS_NAME / ARCH
    bindings_specific_destination_folder = bindings_destination_folder / OS_NAME / ARCH

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
    core_destination_folder = bindings_specific_destination_folder / 'meta_human_dna_core'
    if core_source_folder.exists() and not core_destination_folder.exists() and os.environ.get('RUNNING_CI'):
        shutil.copytree(
            src=core_source_folder,
            dst=core_destination_folder,
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
def dna_folder_name() -> str:
    return 'ada'

@pytest.fixture(scope='session')
def import_shape_keys() -> bool:
    return False

@pytest.fixture(scope='session')
def import_lods() -> list:
    return [
        'lod0'
    ]

@pytest.fixture(scope='session')
def changed_head_bone_name() -> str:
    return 'FACIAL_C_12IPV_Chin3' # has no children

@pytest.fixture(scope='session')
def changed_head_bone_location() -> tuple[Vector, Vector]:
    # change bone location (blender value, dna value)
    return (
        Vector((0.0, 0.005, 0.02)),  # relative change blender value Z-up
        # Vector((0.0671469, 0.319794, 9.78912)), # original dna value Y-up
        Vector((0.0671469, 0.643585, 11.8251)) # new dna value Y-up
    )

@pytest.fixture(scope='session')
def changed_head_bone_rotation() -> tuple[Euler, Euler]:
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
def changed_head_mesh_name() -> str:
    return 'head_lod0_mesh'

@pytest.fixture(scope='session')
def changed_head_vertex_index() -> int:
    return 11955

@pytest.fixture(scope='session')
def changed_head_vertex_location() -> tuple[Vector, Vector, Vector]:
    # change vertex location (blender value, dna value)
    # Moves vertex on the back of the head up 0.01 meters
    return (
        Vector((0.008358, 0.059853, 1.75288)),  # new blender value Z-up
        Vector((0.85206276, 170.66174, -4.644782)),  # original dna value Y-up
        Vector((0.8358, 175.288, -5.9853077)), # new dna value Y-up
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


