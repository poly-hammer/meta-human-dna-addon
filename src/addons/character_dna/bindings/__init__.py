"""Platform/Python selection and loader for the OpenRigLogic Python bindings."""

import os
import platform
import sys
import types

from pathlib import Path

from ..exceptions import UnsupportedPlatformError


BINDINGS_FOLDER = Path(__file__).parent
is_dev_mode = os.getenv("CHARACTER_DNA_DEV", "0") == "1"

# ---------------------------------------------------------------------------
# Resolve the platform/architecture/python-version combo folder.
# ---------------------------------------------------------------------------
arch = "x64"
if "arm" in platform.processor().lower():
    arch = "arm64"

if sys.platform == "win32":
    os_name = "windows"
elif sys.platform == "linux":
    os_name = "linux"
elif sys.platform == "darwin":
    os_name = "macos"
else:
    raise UnsupportedPlatformError

if sys.version_info[:2] == (3, 11):
    python_version = "py311"
elif sys.version_info[:2] == (3, 13):
    python_version = "py313"
else:
    raise UnsupportedPlatformError

combo_folder = BINDINGS_FOLDER / os_name / arch / python_version


def _load_module_from_file(module_name, file_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"Could not load bindings module '{module_name}' from '{file_path}'.")
    module = importlib.util.module_from_spec(spec)
    # Register before exec so the wrappers' own absolute imports resolve to it
    # (``riglogic.py`` does ``import dna``; both do ``import _py3...``).
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_bindings(folder):
    folder_path = str(folder)
    if folder_path not in sys.path:
        # The generated SWIG wrappers use absolute imports to reach their
        # compiled siblings (``import _py3dna...`` / ``import _py3riglogic...``).
        sys.path.insert(0, folder_path)

    # ``riglogic.py`` does ``import dna``, so load and register ``dna`` first.
    dna_module = _load_module_from_file("dna", folder / "dna.py")
    riglogic_module = _load_module_from_file("riglogic", folder / "riglogic.py")
    return dna_module, riglogic_module


def _make_fake_module(module_name, attributes):
    """Build a placeholder module used when the real bindings are absent."""
    module = types.ModuleType(module_name)
    module.__is_fake__ = True  # type: ignore[attr-defined]
    for attr in attributes:
        setattr(module, attr, object)
    return module


# ---------------------------------------------------------------------------
# Load (or reuse) the two modules and expose them as ``dna`` / ``riglogic``.
# ---------------------------------------------------------------------------
# In a packaged release the compiled dependencies must not be reloaded, so reuse
# an already-loaded pair unless we are explicitly in dev mode.
_already_loaded = "dna" in sys.modules and "riglogic" in sys.modules
_should_load = is_dev_mode or not _already_loaded

try:
    if not _should_load and _already_loaded:
        dna = sys.modules["dna"]
        riglogic = sys.modules["riglogic"]
    elif combo_folder.exists():
        dna, riglogic = _load_bindings(combo_folder)
    else:
        raise ModuleNotFoundError

except ModuleNotFoundError:
    # On CI fail hard if the bindings are missing.
    if os.environ.get("RUNNING_CI"):
        raise

    dna = _make_fake_module(
        "dna",
        (
            "BinaryStreamReader",
            "BinaryStreamWriter",
            "JSONStreamReader",
            "JSONStreamWriter",
            "FileStream",
            "Status",
            "MemoryResource",
        ),
    )
    riglogic = _make_fake_module(
        "riglogic",
        (
            "RigLogic",
            "RigInstance",
            "Configuration",
        ),
    )
