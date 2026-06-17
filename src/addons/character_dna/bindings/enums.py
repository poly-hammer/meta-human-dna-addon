"""Typed enum mirrors for the OpenRigLogic DNA enums.

OpenRigLogic's SWIG bindings expose enums as *flat* integer constants
(``dna.TranslationUnit_cm``, ``dna.RBFSolverType_Additive`` ...) which give no
reverse name lookup.  A handful of call sites need the human-readable member
*name* -- UI labels in the importer panel, translation-unit / rotation-unit
detection, twist-axis resolution and RBF solver metadata round-tripping.

This module provides thin :class:`enum.IntEnum` mirrors whose members are pulled
from the real SWIG constants at import time, so the integer values are always
sourced from the loaded bindings (single source of truth) while still offering
attribute access (``enums.TranslationUnit.cm``), name lookup
(``enums.TranslationUnit(value).name``) and reverse construction
(``enums.RBFSolverType[name]``).
"""

import enum

from . import dna


def _mirror(name, *members):
    """Build an :class:`enum.IntEnum` from the flat ``dna.<name>_<member>`` constants."""
    if getattr(dna, "__is_fake__", False):
        # Bindings are absent; create a harmless placeholder so importing this
        # module does not fail. Any real use path requires loaded bindings.
        return enum.IntEnum(name, {member: index for index, member in enumerate(members)})
    return enum.IntEnum(name, {member: getattr(dna, f"{name}_{member}") for member in members})


TranslationUnit = _mirror("TranslationUnit", "cm", "m")
RotationUnit = _mirror("RotationUnit", "degrees", "radians")
Direction = _mirror("Direction", "left", "right", "up", "down", "front", "back")
Archetype = _mirror("Archetype", "asian", "black", "caucasian", "hispanic", "alien", "other")
Gender = _mirror("Gender", "male", "female", "other")
TwistAxis = _mirror("TwistAxis", "X", "Y", "Z")
RBFSolverType = _mirror("RBFSolverType", "Additive", "Interpolative")
RBFDistanceMethod = _mirror("RBFDistanceMethod", "Euclidean", "Quaternion", "SwingAngle", "TwistAngle")
RBFNormalizeMethod = _mirror("RBFNormalizeMethod", "OnlyNormalizeAboveOne", "AlwaysNormalize")
RBFFunctionType = _mirror("RBFFunctionType", "Gaussian", "Exponential", "Linear", "Cubic", "Quintic")
AutomaticRadius = _mirror("AutomaticRadius", "On", "Off")
