import os
import sys

import platform
from pathlib import Path
from ..exceptions import UnsupportedPlatformError

BINDINGS_FOLDER = Path(__file__).parent

already_loaded = any(key for key in sys.modules.keys() if key.endswith('riglogic'))
is_dev_mode = os.getenv('META_HUMAN_DNA_DEV', '0') == '1'

# prevents reloading issues with compiled dependencies in releases
if is_dev_mode:
    should_import = True
else:
    should_import = not already_loaded

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
    if should_import and platform == "macos" and arch == "arm64" and python_version == "py311" and (BINDINGS_FOLDER / "macos" / "arm64" / "py311").exists():
        from .macos.arm64.py311 import riglogic, meta_human_dna_core # pyright: ignore[reportUnusedImport, reportMissingImports, reportAssignmentType]
    elif should_import and platform == "macos" and arch == "arm64" and python_version == "py313" and (BINDINGS_FOLDER / "macos" / "arm64" / "py313").exists():
        from .macos.arm64.py313 import riglogic, meta_human_dna_core # pyright: ignore[reportUnusedImport, reportMissingImports, reportAssignmentType]
    elif should_import and platform == "windows" and arch == "x64" and python_version == "py311" and (BINDINGS_FOLDER / "windows" / "x64" / "py311").exists():
        from .windows.x64.py311 import riglogic, meta_human_dna_core # pyright: ignore[reportUnusedImport, reportMissingImports, reportAssignmentType]
    elif should_import and platform == "windows" and arch == "x64" and python_version == "py313" and (BINDINGS_FOLDER / "windows" / "x64" / "py313").exists():
        from .windows.x64.py313 import riglogic, meta_human_dna_core # pyright: ignore[reportUnusedImport, reportMissingImports, reportAssignmentType]
    elif should_import and platform == "linux" and arch == "x64" and python_version == "py311" and (BINDINGS_FOLDER / "linux" / "x64" / "py311").exists():
        from .linux.x64.py311 import riglogic, meta_human_dna_core # pyright: ignore[reportUnusedImport, reportMissingImports, reportAssignmentType]
    elif should_import and platform == "linux" and arch == "x64" and python_version == "py313" and (BINDINGS_FOLDER / "linux" / "x64" / "py313").exists():
        from .linux.x64.py313 import riglogic, meta_human_dna_core # pyright: ignore[reportUnusedImport, reportMissingImports, reportAssignmentType]
    elif should_import:
        raise ModuleNotFoundError

    if "meta_human_dna_core" in sys.modules:
        sys.modules[__name__ + ".meta_human_dna_core"] = sys.modules.pop("meta_human_dna_core")

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
