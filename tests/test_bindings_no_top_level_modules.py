"""Permanent guard against the Blender "Policy violation with top level module" warning.

Blender's extension validator (``addon_utils._extensions_warnings_get``) iterates
``sys.modules`` and reports a *"Policy violation with top level module: <name>"* for
any entry whose name is **not** namespaced under ``bl_ext.`` but whose ``__file__``
resolves **inside** the extension's directory. Entries without a ``__file__`` are
skipped.

The OpenRigLogic SWIG wrappers register bare top-level names (``dna``, ``riglogic``)
and their compiled siblings (``_py3dna*``, ``_py3riglogic*``, ``swig_runtime_data*``)
whose files live in ``character_dna/bindings/...``. The bindings loader must therefore
ensure that, once loaded, none of those names remain in ``sys.modules`` with a
``__file__`` pointing inside the bindings folder (it strips the bare names and nulls
the wrappers' ``__file__``). This test reproduces Blender's detection logic so any
future regression that re-leaks a top-level module fails here instead of in a user's
extension panel.
"""

import os
import sys

import pytest


# The fake-module fallback (no compiled bindings present) cannot leak a top-level
# module, but it also doesn't exercise the real loader, so the guard is meaningless.
from character_dna import bindings  # noqa: E402


pytestmark = pytest.mark.skipif(
    getattr(bindings.dna, "__is_fake__", False) or getattr(bindings.riglogic, "__is_fake__", False),
    reason="Real compiled bindings are required to exercise the top-level-module guard.",
)


def _bindings_folder() -> str:
    return os.path.abspath(str(bindings.BINDINGS_FOLDER))


def _leaked_top_level_modules() -> list[tuple[str, str]]:
    """Return ``(name, file)`` for every ``sys.modules`` entry that Blender would
    flag: a non-namespaced (no ``bl_ext.`` prefix, no dotted submodule) name whose
    ``__file__`` lives inside the bindings folder."""
    bindings_folder = _bindings_folder()
    leaked = []
    for name, module in list(sys.modules.items()):
        # Blender only flags non-namespaced names (extensions live under ``bl_ext.``,
        # and their own dotted submodules are ignored by the validator).
        if "." in name or name.startswith("bl_ext"):
            continue
        module_file = getattr(module, "__file__", None) or ""
        if not module_file:
            # Mirrors the validator: modules without ``__file__`` are skipped.
            continue
        if os.path.abspath(module_file).startswith(bindings_folder):
            leaked.append((name, module_file))
    return leaked


def test_no_top_level_binding_modules_after_load():
    """No bare binding module may remain in ``sys.modules`` with a ``__file__``
    inside the extension's bindings folder."""
    leaked = _leaked_top_level_modules()
    assert not leaked, (
        f"Top-level binding modules leaked into sys.modules (Blender would report a policy violation): {leaked}"
    )


def test_wrapper_modules_have_no_file_attribute():
    """The ``dna`` / ``riglogic`` wrappers must expose ``__file__ = None`` so they
    stay invisible to the validator even if the meta-path loader re-serves them into
    ``sys.modules`` on a later re-entrant ``import dna`` / ``import riglogic``."""
    assert getattr(bindings.dna, "__file__", None) is None
    assert getattr(bindings.riglogic, "__file__", None) is None


def test_reimporting_dna_does_not_leak():
    """A bare ``import dna`` (which the SWIG wrappers and cross-module type sharing
    perform) must not re-introduce a flaggable top-level module."""
    import importlib

    # Force the import machinery to resolve ``dna`` again via the persistent loader.
    sys.modules.pop("dna", None)
    try:
        importlib.import_module("dna")
    except ModuleNotFoundError:
        # No loader served it, so nothing could have leaked either.
        return
    try:
        assert not _leaked_top_level_modules()
    finally:
        sys.modules.pop("dna", None)
