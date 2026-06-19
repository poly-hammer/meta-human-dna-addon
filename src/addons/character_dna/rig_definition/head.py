# standard library imports
from functools import cached_property
from typing import Any, ClassVar

# local imports
from .base import (
    RigDefinition,
    RigExpression,
    RigPsdDefinition,
    RigPsdNet,
    RigRegion,
)


# ----------------------------------------------------------------------------------------------
# Head rig definition
# ----------------------------------------------------------------------------------------------
class HeadRigDefinition(RigDefinition):
    """The head rig definition, parsed from the rich RDF payload.

    Exposes the validation contract (counts/meshes, via the base class), the
    head-specific counts, the ``extras`` raw-control mappings used by the Raw
    Control Editor, and the rich structured data (regions, expressions, PSD
    nets) the importer uses for joint colors, vertex groups and bone groups.
    """

    COMPONENT: ClassVar[str] = "head"

    # ------------------------------------------------------------------
    # Head-specific metadata / counts
    # ------------------------------------------------------------------
    @property
    def rdf_fileformat_version(self) -> str:
        return self._data["rdf_fileformat_version"]

    @property
    def rdf_model_version(self) -> str:
        return self._data["rdf_model_version"]

    @cached_property
    def region_names(self) -> tuple[str, ...]:
        return tuple(self._data["region_names"])

    @property
    def gui_control_count(self) -> int:
        return self._data["gui_control_count"]

    @property
    def control_count(self) -> int:
        return self._data["control_count"]

    @property
    def expression_count(self) -> int:
        return self._data["expression_count"]

    # ------------------------------------------------------------------
    # Extras accessors (raw-control -> original joints / meshes)
    # ------------------------------------------------------------------
    # The ``extras`` block is baked from the canonical default DNA at dump
    # time. It is the authoritative record of which joints/meshes each raw
    # control *originally* drives, so the Raw Control Editor can tell a
    # rig-definition target mesh apart from one the artist added, and keep
    # the ML matcher's inputs restricted to the original joint set.
    def original_meshes_for_raw_control(self, raw_control_name: str) -> tuple[str, ...]:
        """LOD0 mesh names the named raw control influences in the default
        rig. Empty tuple when unknown (e.g. pre-``extras`` definitions)."""
        meshes = self.extras.get("raw_control_meshes", {})
        return tuple(meshes.get(raw_control_name, ()))

    def original_joint_names_for_raw_control(self, raw_control_name: str) -> tuple[str, ...]:
        """Joint names the named raw control drives in the default rig.
        Empty tuple when unknown (e.g. pre-``extras`` definitions)."""
        joints = self.extras.get("raw_control_joints", {})
        return tuple(joints.get(raw_control_name, ()))

    # ------------------------------------------------------------------
    # Rich structured data
    # ------------------------------------------------------------------
    @cached_property
    def regions(self) -> tuple[RigRegion, ...]:
        return tuple(RigRegion.from_dict(item) for item in self._data.get("regions", []))

    @cached_property
    def expressions(self) -> tuple[RigExpression, ...]:
        return tuple(RigExpression.from_dict(item) for item in self._data.get("expressions", []))

    @cached_property
    def psd_definitions(self) -> tuple[RigPsdDefinition, ...]:
        return tuple(RigPsdDefinition.from_dict(item) for item in self._data.get("psd_definitions", []))

    @cached_property
    def psd_nets(self) -> tuple[RigPsdNet, ...]:
        return tuple(RigPsdNet.from_dict(item) for item in self._data.get("psd_nets", []))

    @cached_property
    def descriptor(self) -> dict[str, Any]:
        return self._data.get("descriptor", {})
