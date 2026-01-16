import sys
import platform
from pathlib import Path
from ..exceptions import UnsupportedPlatformError

BINDINGS_FOLDER = Path(__file__).parent

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

try:
    if platform == "mac" and arch == "arm64" and (BINDINGS_FOLDER / "mac" / "arm64").exists():
        from .mac.arm64 import riglogic, meta_human_dna_core # pyright: ignore[reportMissingImports, reportAssignmentType]
    elif platform == "windows" and arch == "amd64" and (BINDINGS_FOLDER / "windows" / "amd64").exists():
        from .windows.amd64 import riglogic, meta_human_dna_core # pyright: ignore[reportMissingImports, reportAssignmentType]
    elif platform == "linux" and arch == "x86_64" and (BINDINGS_FOLDER / "linux" / "x86_64").exists():
        from .linux.x86_64 import riglogic, meta_human_dna_core # pyright: ignore[reportMissingImports, reportAssignmentType]
    else:
        raise ModuleNotFoundError
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

except ImportError as error:
    raise error

__all__ = [
    "riglogic",
    "meta_human_dna_core"
]
