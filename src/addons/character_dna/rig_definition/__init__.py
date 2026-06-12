# local imports
from .base import (
    DEFAULT_DB_NAME,
    RigDefinition,
    RigDefinitionMesh,
    RigExpression,
    RigJoint,
    RigJointGroup,
    RigMeshDeformer,
    RigPsdDefinition,
    RigPsdInput,
    RigPsdNet,
    RigRegion,
    full_path,
    load_full_data,
)
from .body import BodyRigDefinition
from .head import HeadRigDefinition


__all__ = [
    "DEFAULT_DB_NAME",
    "BodyRigDefinition",
    "HeadRigDefinition",
    "RigDefinition",
    "RigDefinitionMesh",
    "RigExpression",
    "RigJoint",
    "RigJointGroup",
    "RigMeshDeformer",
    "RigPsdDefinition",
    "RigPsdInput",
    "RigPsdNet",
    "RigRegion",
    "full_path",
    "get_rig_definition",
    "load_full_data",
]

# Map a component name onto the class that loads its rig definition.
_DEFINITION_BY_COMPONENT: dict[str, type[RigDefinition]] = {
    HeadRigDefinition.COMPONENT: HeadRigDefinition,
    BodyRigDefinition.COMPONENT: BodyRigDefinition,
}


def get_rig_definition(component: str, db_name: str | None = None) -> RigDefinition:
    """Return the :class:`RigDefinition` for ``component`` (``"head"``/``"body"``).

    Instances are cached for the lifetime of the Blender session on the global
    ``CharacterWindowManagerProperties.data["rig_definitions"]`` dict, keyed by
    ``(component, db_name)``, so the gzip payload is only read and decompressed
    once per definition.
    """
    # Deferred import avoids a circular import at module-load time.
    from ..properties import CharacterWindowManagerProperties

    try:
        definition_class = _DEFINITION_BY_COMPONENT[component]
    except KeyError as error:
        raise ValueError(f"Unknown rig-definition component '{component}'.") from error

    resolved_db_name = db_name or definition_class.DEFAULT_DB_NAME
    cache = CharacterWindowManagerProperties.data.setdefault("rig_definitions", {})
    key = (component, resolved_db_name)
    definition = cache.get(key)
    if definition is None:
        definition = definition_class.load(resolved_db_name)
        cache[key] = definition
    return definition
