import os
import sys
import platform
from pathlib import Path
from ..exceptions import UnsupportedPlatformError


arch = 'x64'
if 'arm' in platform.processor().lower():
    arch = 'arm64'
if sys.platform == 'win32' and arch == 'x64':
    arch = 'amd64'
if sys.platform == 'linux' and arch == 'x64':
    arch = 'x86_64'
if sys.platform == 'mac' and arch == 'x64':
    arch = 'x86_64'

platform = None
if sys.platform == "win32":
    platform = "windows"
elif sys.platform == "linux":
    platform = "linux"
elif sys.platform == "darwin":
    platform = "mac"
else:
    raise UnsupportedPlatformError

# add the platform specific bindings path to the sys.path if there are not already
bindings_path = Path(__file__).parent / platform / arch
_current_working_directory = os.getcwd()
if bindings_path.exists():
    if bindings_path not in [Path(i) for i in sys.path]:
        sys.path.append(str(bindings_path))

    # linux and macos need to set the LD_LIBRARY_PATH and DYLD_LIBRARY_PATH and DYLD_FALLBACK_LIBRARY_PATH
    # This is needed to load the shared libraries that are in the bindings folder on linux and macos
    os.chdir(str(bindings_path))

try:
    riglogic = sys.modules.get("riglogic") # type: ignore[assigned]
    if not riglogic:
        import riglogic
    meta_human_dna_core = sys.modules.get("meta_human_dna_core") # type: ignore[assigned]
    if not meta_human_dna_core:
        import meta_human_dna_core
except ModuleNotFoundError:
    class riglogic:
        __is_fake__ = True
        RigLogic = object
        RigInstance = object
        BinaryStreamReader = object
        JSONStreamReader = object
        FileStream = object
        BinaryStreamWriter = object
        JSONStreamWriter = object

    class meta_human_dna_core:
        __is_fake__ = True
        pass

    sys.modules["riglogic"] = riglogic  # type: ignore[assigned]
    sys.modules["meta_human_dna_core"] = meta_human_dna_core  # type: ignore[assigned]

except ImportError as e:
    raise e


# restore the current working directory
os.chdir(_current_working_directory)

__all__ = [
    "riglogic",
    "meta_human_dna_core"
]
