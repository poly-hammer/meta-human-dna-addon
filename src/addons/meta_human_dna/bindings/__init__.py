import sys
import platform
from pathlib import Path
from ..exceptions import UnsupportedPlatformError

BINDINGS_FOLDER = Path(__file__).parent

arch = 'x64'
if 'arm' in platform.processor().lower():
    arch = 'arm64'
if sys.platform == 'win32' and arch == 'x64':
    arch = 'x64'
if sys.platform == 'linux' and arch == 'x64':
    arch = 'x64'
if sys.platform == 'darwin' and arch == 'x64':
    arch = 'x64'

platform = None
if sys.platform == "win32":
    platform = "windows"
elif sys.platform == "linux":
    platform = "linux"
elif sys.platform == "darwin":
    platform = "macos"
else:
    raise UnsupportedPlatformError

python_version = None
if sys.version_info.major == 3 and sys.version_info.minor == 11:
    python_version = "py311"
elif sys.version_info.major == 3 and sys.version_info.minor == 13:
    python_version = "py313"
else:
    raise UnsupportedPlatformError

try:
    if platform == "macos" and arch == "arm64" and python_version == "py311" and (BINDINGS_FOLDER / "macos" / "arm64" / "py311").exists():
        from .macos.arm64.py311 import riglogic, meta_human_dna_core # pyright: ignore[reportMissingImports, reportAssignmentType]
    elif platform == "macos" and arch == "arm64" and python_version == "py313" and (BINDINGS_FOLDER / "macos" / "arm64" / "py313").exists():
        from .macos.arm64.py313 import riglogic, meta_human_dna_core # pyright: ignore[reportMissingImports, reportAssignmentType]
    elif platform == "windows" and arch == "x64" and python_version == "py311" and (BINDINGS_FOLDER / "windows" / "x64" / "py311").exists():
        from .windows.x64.py311 import riglogic, meta_human_dna_core # pyright: ignore[reportMissingImports, reportAssignmentType]
    elif platform == "windows" and arch == "x64" and python_version == "py313" and (BINDINGS_FOLDER / "windows" / "x64" / "py313").exists():
        from .windows.x64.py313 import riglogic, meta_human_dna_core # pyright: ignore[reportMissingImports, reportAssignmentType]
    elif platform == "linux" and arch == "x64" and python_version == "py311" and (BINDINGS_FOLDER / "linux" / "x64" / "py311").exists():
        from .linux.x64.py311 import riglogic, meta_human_dna_core # pyright: ignore[reportMissingImports, reportAssignmentType]
    elif platform == "linux" and arch == "x64" and python_version == "py313" and (BINDINGS_FOLDER / "linux" / "x64" / "py313").exists():
        from .linux.x64.py313 import riglogic, meta_human_dna_core # pyright: ignore[reportMissingImports, reportAssignmentType]
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
