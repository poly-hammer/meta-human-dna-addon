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

# Bare ``sys.modules`` names the SWIG wrappers create transiently while loading.
# They are stripped after a successful load so the packaged extension does not
# register any top-level (non-namespaced) modules, which Blender's extension
# validator forbids.
_BARE_MODULE_PREFIXES = ("_py3dna", "_py3riglogic", "swig_runtime_data")
_BARE_MODULE_NAMES = ("dna", "riglogic")


class IsolatedModuleLoader:
    """``sys.meta_path`` hook the generated SWIG wrappers cooperate with.

    The wrappers (``dna.py`` / ``riglogic.py``) probe ``sys.meta_path`` for a
    class literally named ``IsolatedModuleLoader`` and, when found, ask it to
    load their compiled siblings via :meth:`load_module` instead of doing a bare
    ``import _py3dna...`` (which would pollute the top-level module namespace and
    require ``sys.path`` mutation). ``riglogic.py`` also calls
    :meth:`get_module_rootdir` to locate ``dna`` and performs an unconditional
    reentrant ``import dna``; the finder protocol below satisfies that by
    re-serving the already-loaded module without re-executing it.
    """

    # Populated per process; reset whenever this module is re-imported (dev
    # reload). Loaded compiled modules are also reused from ``sys.modules`` when
    # still present (dev mode keeps them), so the ``.pyd`` is never re-initialised.
    _loaded: dict = {}
    _rootdirs: dict = {}

    @classmethod
    def get_module_rootdir(cls, module_name):
        return cls._rootdirs.get(module_name)

    @classmethod
    def cached(cls, module_name):
        """Return the already-loaded module, or ``None`` if it is not loaded."""
        return cls._loaded.get(module_name)

    @classmethod
    def load_module(cls, module_name, rootdir=None):
        cached = cls._loaded.get(module_name)
        if cached is not None:
            return cached

        if rootdir is not None:
            cls._rootdirs[module_name] = rootdir
        rootdir = cls._rootdirs.get(module_name) or str(combo_folder)

        # Reuse an already-loaded binding (e.g. across a dev-mode reload) so the
        # compiled extension is not initialised twice in the same process.
        existing = sys.modules.get(module_name)
        if existing is not None:
            existing_file = getattr(existing, "__file__", "") or ""
            if existing_file and os.path.dirname(os.path.abspath(existing_file)) == os.path.abspath(rootdir):
                cls._loaded[module_name] = existing
                return existing

        module = cls._exec_from_disk(module_name, rootdir)
        cls._loaded[module_name] = module
        return module

    @staticmethod
    def _exec_from_disk(module_name, rootdir):
        import importlib.machinery
        import importlib.util

        py_path = os.path.join(rootdir, module_name + ".py")
        if os.path.isfile(py_path):
            spec = importlib.util.spec_from_file_location(module_name, py_path)
        else:
            spec = None
            for suffix in importlib.machinery.EXTENSION_SUFFIXES:
                ext_path = os.path.join(rootdir, module_name + suffix)
                if os.path.isfile(ext_path):
                    loader = importlib.machinery.ExtensionFileLoader(module_name, ext_path)
                    spec = importlib.util.spec_from_file_location(module_name, ext_path, loader=loader)
                    break

        if spec is None or spec.loader is None:
            raise ModuleNotFoundError(f"Could not load bindings module '{module_name}' from '{rootdir}'.")

        module = importlib.util.module_from_spec(spec)
        # The wrappers' absolute imports and SWIG's cross-module type table look
        # the module up by its bare name during execution; register it for the
        # duration of the load and strip it again once everything is in place.
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    # -- finder/loader protocol -------------------------------------------------
    # ``riglogic.py`` does an unconditional ``import dna`` after popping it from
    # ``sys.modules``; serve the already-loaded module instead of re-executing.
    @classmethod
    def find_spec(cls, fullname, path=None, target=None):
        if fullname in cls._loaded:
            import importlib.util

            return importlib.util.spec_from_loader(fullname, cls)
        return None

    @classmethod
    def create_module(cls, spec):
        return cls._loaded.get(spec.name)

    @classmethod
    def exec_module(cls, module):
        # The module returned by ``create_module`` is already initialised.
        return None


def _register_loader():
    """Place a single fresh :class:`IsolatedModuleLoader` on ``sys.meta_path``."""
    sys.meta_path[:] = [
        entry for entry in sys.meta_path if getattr(entry, "__name__", None) != "IsolatedModuleLoader"
    ]
    sys.meta_path.insert(0, IsolatedModuleLoader)


def _strip_bare_binding_modules():
    """Remove the transient top-level binding modules the wrappers created."""
    for name in list(sys.modules):
        if name in _BARE_MODULE_NAMES or name.startswith(_BARE_MODULE_PREFIXES):
            module = sys.modules[name]
            module_file = getattr(module, "__file__", "") or ""
            # Only remove our own bindings, never an unrelated top-level ``dna``
            # (e.g. Maya's) that may legitimately live alongside us.
            if name.startswith(_BARE_MODULE_PREFIXES) or (
                module_file and os.path.abspath(module_file).startswith(os.path.abspath(str(BINDINGS_FOLDER)))
            ):
                del sys.modules[name]


def _load_bindings(folder):
    _register_loader()

    folder_path = str(folder)
    # Make the compiled extensions' sibling DLLs discoverable without mutating
    # ``sys.path`` (which the extension validator forbids).
    if sys.platform == "win32" and hasattr(os, "add_dll_directory") and os.path.isdir(folder_path):
        os.add_dll_directory(folder_path)

    # ``riglogic.py`` depends on ``dna``, so load ``dna`` first.
    dna_module = IsolatedModuleLoader.load_module("dna", rootdir=folder_path)
    riglogic_module = IsolatedModuleLoader.load_module("riglogic", rootdir=folder_path)

    # In a packaged release the extension validator runs and flags any leftover
    # top-level modules; strip them. In dev mode they are deliberately kept so a
    # subsequent reload reuses the already-initialised compiled extensions.
    if not is_dev_mode:
        _strip_bare_binding_modules()

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
_already_loaded = IsolatedModuleLoader.cached("dna") is not None and IsolatedModuleLoader.cached("riglogic") is not None
_should_load = is_dev_mode or not _already_loaded

try:
    if not _should_load and _already_loaded:
        dna = IsolatedModuleLoader.cached("dna")
        riglogic = IsolatedModuleLoader.cached("riglogic")
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
