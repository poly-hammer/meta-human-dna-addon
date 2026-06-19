# standard library imports
from functools import cached_property
from typing import ClassVar

# local imports
from .base import RigDefinition


# ----------------------------------------------------------------------------------------------
# Body rig definition
# ----------------------------------------------------------------------------------------------
class BodyRigDefinition(RigDefinition):
    """The body rig definition, parsed from the rich DNA-derived payload.

    Provides the validation contract (counts/meshes, via the base class), the
    body-specific counts, and the rich data (joint hierarchy, joint groups,
    blend-shape channels). DNA carries no joint colors or radii, so those are
    ``None``.
    """

    COMPONENT: ClassVar[str] = "body"
    DEFAULT_DB_NAME: ClassVar[str] = "MHB.1"

    @property
    def dna_name(self) -> str:
        return self._data["dna_name"]

    @property
    def blend_shape_channel_count(self) -> int:
        return self._data["blend_shape_channel_count"]

    @property
    def animated_map_count(self) -> int:
        return self._data["animated_map_count"]

    @cached_property
    def blend_shape_channels(self) -> tuple[str, ...]:
        return tuple(self._data.get("blend_shape_channels", []))
