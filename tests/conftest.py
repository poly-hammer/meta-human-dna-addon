import math
import os
import platform
import sys


ARCH = "x64"
if "arm" in platform.processor().lower():
    ARCH = "arm64"
if sys.platform == "win32" and ARCH == "x64":
    ARCH = "x64"
if sys.platform == "linux" and ARCH == "x64":
    ARCH = "x64"


OS_NAME = "windows"
if sys.platform == "darwin":
    OS_NAME = "macos"
elif sys.platform == "linux":
    OS_NAME = "linux"

PYTHON_VERSION = "py311"
if sys.version_info.major == 3 and sys.version_info.minor == 11:
    PYTHON_VERSION = "py311"
elif sys.version_info.major == 3 and sys.version_info.minor == 13:
    PYTHON_VERSION = "py313"

import shutil  # noqa: E402

from pathlib import Path  # noqa: E402

# import this to ensure that mathutils is available
import bpy   # pyright: ignore
import pytest  # noqa: E402

from mathutils import Euler, Vector  # noqa: E402

from constants import REPO_ROOT  # noqa: E402


_session_exit_code = 0


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Capture the exit code before unconfigure."""
    global _session_exit_code
    _session_exit_code = exitstatus


def pytest_unconfigure() -> None:
    """Force exit to prevent bpy's C++ cleanup from hanging/crashing on teardown.

    Blender's C++ teardown (and its guarded allocator's "Not freed memory
    blocks" report) runs during interpreter/DLL shutdown and can raise a benign
    access violation. ``os._exit`` still triggers Windows ``ExitProcess``, which
    runs the DLL detach handlers that crash. To keep the test run output clean
    we flush buffered output, disable pytest's ``faulthandler`` so no crash dump
    is printed, then terminate the process immediately:

    - On Windows, ``TerminateProcess`` skips ``DLL_PROCESS_DETACH`` entirely,
      avoiding both the access violation and the allocator's memory report.
    - Elsewhere, ``os._exit`` is sufficient.
    """
    import faulthandler

    # Flush buffered output before the hard exit so nothing is lost.
    sys.stdout.flush()
    sys.stderr.flush()

    # pytest installs faulthandler; disable it so the hard exit stays quiet.
    faulthandler.disable()

    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # Use explicit 64-bit-safe signatures so the (HANDLE)-1 current-process
        # pseudo handle isn't truncated by ctypes' default c_int marshalling.
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel32.TerminateProcess.restype = ctypes.c_int
        kernel32.TerminateProcess(kernel32.GetCurrentProcess(), _session_exit_code)

    os._exit(_session_exit_code)


def pytest_configure():
    """
    Installs the bindings for the addon.
    """

    bindings_source_folder = REPO_ROOT.parent / "character-dna-bindings"
    bindings_destination_folder = REPO_ROOT / "src" / "addons" / "character_dna" / "bindings"

    bindings_specific_source_folder = bindings_source_folder / OS_NAME / ARCH / PYTHON_VERSION
    bindings_specific_destination_folder = bindings_destination_folder / OS_NAME / ARCH / PYTHON_VERSION

    # Copy the bindings folder to the src directory if they doesn't exist
    if not bindings_specific_destination_folder.exists():
        if not bindings_specific_source_folder.exists():
            raise FileNotFoundError(
                f'The bindings in "{bindings_specific_destination_folder}" are missing. '
                "Please add them to run the tests."
            )

        # Copy the bindings to the destination folder
        shutil.copytree(
            src=bindings_specific_source_folder, dst=bindings_specific_destination_folder, dirs_exist_ok=True
        )

    # ensure the addon module is on the python path
    sys.path.append(str(REPO_ROOT / "src" / "addons"))

from fixtures.addon import addon, disable_auto_save  # pyright: ignore[reportUnusedImport] # noqa: E402, F401
from fixtures.dna_data import (  # noqa: E402, F401
    calibrated_head_dna_json_data, #  pyright: ignore[reportUnusedImport]
    exported_head_dna_json_data, #  pyright: ignore[reportUnusedImport]
    original_head_dna_json_data, #  pyright: ignore[reportUnusedImport]
)
from fixtures.scene import (  # noqa: E402, F401
    head_armature, #  pyright: ignore[reportUnusedImport]
    head_bmesh, #  pyright: ignore[reportUnusedImport]
    load_body_dna, #  pyright: ignore[reportUnusedImport]
    load_body_dna_for_pose_editing, #  pyright: ignore[reportUnusedImport]
    load_body_dna_for_pose_roundtrip,  #  pyright: ignore[reportUnusedImport]
    load_dna_for_rig_instance_ops, #  pyright: ignore[reportUnusedImport]
    load_full_dna_for_animation, #  pyright: ignore[reportUnusedImport]
    load_head_dna, #  pyright: ignore[reportUnusedImport]
    load_mhc_conformed_topology_meshes, #  pyright: ignore[reportUnusedImport]
    modify_head_scene, #  pyright: ignore[reportUnusedImport]
    setup_reference_blend_file, #  pyright: ignore[reportUnusedImport]
)


@pytest.fixture(scope="session")
def addons() -> list:
    return [("character_dna", Path(__file__).parent.parent / "src")]


@pytest.fixture(scope="session")
def dna_folder_name() -> str:
    return "ada"


@pytest.fixture(scope="session")
def import_shape_keys() -> bool:
    return False


@pytest.fixture(scope="session")
def import_lods() -> list:
    return ["lod0"]


@pytest.fixture(scope="session")
def changed_head_bone_name() -> str:
    return "FACIAL_C_12IPV_Chin3"  # has no children


@pytest.fixture(scope="session")
def changed_head_bone_location() -> tuple[Vector, Vector]:
    # change bone location (blender value, dna value)
    return (
        Vector((0.0, 0.005, 0.02)),  # relative change blender value Z-up
        # Vector((0.0671469, 0.319794, 9.78912)), # original dna value Y-up
        Vector((0.0671469, 0.643585, 11.8251)),  # new dna value Y-up
    )


@pytest.fixture(scope="session")
def changed_head_bone_rotation() -> tuple[Euler, Euler]:
    # change rotation of bone (blender value, dna value)
    return (Euler((math.radians(60), math.radians(0), math.radians(0))), Euler((60.0, 0.0, 0.0)))


@pytest.fixture(scope="session")
def changed_head_mesh_name() -> str:
    return "head_lod0_mesh"


@pytest.fixture(scope="session")
def changed_head_vertex_index() -> int:
    return 11955


@pytest.fixture(scope="session")
def changed_head_vertex_location() -> tuple[Vector, Vector, Vector]:
    # change vertex location (blender value, dna value)
    # Moves vertex on the back of the head up 0.01 meters
    return (
        Vector((0.008358, 0.059853, 1.75288)),  # new blender value Z-up
        Vector((0.85206276, 170.66174, -4.644782)),  # original dna value Y-up
        Vector((0.8358, 175.288, -5.9853077)),  # new dna value Y-up
    )


@pytest.fixture(scope="session")
def changed_head_vertex_group_name() -> str:
    return "FACIAL_L_12IPV_NeckB7"


@pytest.fixture(scope="session")
def changed_head_vertex_group_vertex_index() -> int:
    return 11525


@pytest.fixture(scope="session")
def changed_head_vertex_group_weight() -> float:
    return 0.01


@pytest.fixture(scope="session")
def temp_folder():
    temp_folder = Path(__file__).parent / "temp"
    if temp_folder.exists():
        shutil.rmtree(temp_folder)

    os.makedirs(temp_folder, exist_ok=True)

    yield temp_folder

    # Cleanup the temp folder
    if not os.environ.get("TESTS_KEEP_TEMP_FOLDER") and temp_folder.exists():
        shutil.rmtree(temp_folder)
