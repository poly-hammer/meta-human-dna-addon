# standard library imports
import gzip
import json
import logging

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, ClassVar

# local imports
from ..constants import RIG_DEFINITIONS_FOLDER


logger = logging.getLogger(__name__)

DEFAULT_DB_NAME = "MH.6"


# ----------------------------------------------------------------------------------------------
# Shared value types
# ----------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class RigDefinitionMesh:
    """A single mesh entry shared by the slim validation contract.

    Only counts are stored - never vertex positions or skin weights.
    """

    name: str
    vertex_count: int
    uv_count: int
    blend_shape_count: int
    is_exported: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RigDefinitionMesh":
        return cls(
            name=data["name"],
            vertex_count=data["vertex_count"],
            uv_count=data["uv_count"],
            blend_shape_count=data["blend_shape_count"],
            is_exported=data["is_exported"],
        )


@dataclass(frozen=True)
class RigJoint:
    """A joint from the rich rig definition.

    ``color`` and ``radius`` are only populated for sources that carry them
    (the head RDF). They are ``None`` for DNA-derived definitions.
    """

    name: str
    parent: str | None
    color: tuple[float, ...] | None
    radius: float | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RigJoint":
        color = data.get("color")
        return cls(
            name=data["name"],
            parent=data.get("parent"),
            color=tuple(color) if color is not None else None,
            radius=data.get("radius"),
        )


@dataclass(frozen=True)
class RigJointGroup:
    """A named group of joints (imported as bone collections in Blender)."""

    name: str
    joints: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RigJointGroup":
        return cls(name=data["name"], joints=tuple(data["joints"]))


@dataclass(frozen=True)
class RigRegion:
    """A named region of joints (imported as vertex groups in Blender)."""

    name: str
    joints: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RigRegion":
        return cls(name=data["name"], joints=tuple(data["joints"]))


@dataclass(frozen=True)
class RigMeshDeformer:
    """How an expression deforms a single mesh."""

    mesh: str
    deformation_type: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RigMeshDeformer":
        return cls(mesh=data["mesh"], deformation_type=data["deformation_type"])


@dataclass(frozen=True)
class RigExpression:
    """A rig expression (control driving meshes/joints)."""

    name: str
    type: str
    is_exported: bool
    phase_count: int
    control: str | None
    mesh_deformers: tuple[RigMeshDeformer, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RigExpression":
        return cls(
            name=data["name"],
            type=data["type"],
            is_exported=data["is_exported"],
            phase_count=data["phase_count"],
            control=data.get("control"),
            mesh_deformers=tuple(RigMeshDeformer.from_dict(item) for item in data.get("mesh_deformers", [])),
        )


@dataclass(frozen=True)
class RigPsdDefinition:
    """A pose-space deformation (PSD) definition."""

    name: str
    layer: int
    complex: str | None
    target: str | None
    corrective: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RigPsdDefinition":
        return cls(
            name=data["name"],
            layer=data["layer"],
            complex=data.get("complex"),
            target=data.get("target"),
            corrective=data.get("corrective"),
        )


@dataclass(frozen=True)
class RigPsdInput:
    """A single input expression and its multiplier within a PSD net."""

    expression: str | None
    multiplier: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RigPsdInput":
        return cls(expression=data.get("expression"), multiplier=data["multiplier"])


@dataclass(frozen=True)
class RigPsdNet:
    """A PSD net mapping input expressions to an output expression."""

    name: str
    output_expression: str | None
    psd_definition: str | None
    inputs: tuple[RigPsdInput, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RigPsdNet":
        return cls(
            name=data["name"],
            output_expression=data.get("output_expression"),
            psd_definition=data.get("psd_definition"),
            inputs=tuple(RigPsdInput.from_dict(item) for item in data.get("inputs", [])),
        )


# ----------------------------------------------------------------------------------------------
# File path helpers
# ----------------------------------------------------------------------------------------------
def full_path(db_name: str, component: str) -> Path:
    """Path of the rich (gzip) rig definition for a component."""
    return RIG_DEFINITIONS_FOLDER / f"{db_name}.{component}.json.gz"


def load_full_data(db_name: str, component: str) -> dict[str, Any]:
    """Read and decompress the rich rig-definition payload for a component."""
    file_path = full_path(db_name, component)
    if not file_path.exists():
        raise FileNotFoundError(f"No full rig definition found for '{db_name}.{component}' at '{file_path}'.")
    with gzip.open(file_path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


# ----------------------------------------------------------------------------------------------
# Rig definition base class
# ----------------------------------------------------------------------------------------------
class RigDefinition:
    """A rig definition backed by the rich (gzip) payload for a component.

    Wraps the decompressed JSON dict and exposes both the validation
    contract (counts, names, meshes - used by DNA-compatibility checks) and
    the rich structured data (joints, joint groups, etc.). Parsed wrapper
    objects are memoized per instance via :func:`functools.cached_property`.

    Instances are cached for the lifetime of the Blender session by
    :func:`rig_definition.get_rig_definition`, so the payload is only read
    and decompressed once per ``(component, db_name)``.
    """

    COMPONENT: ClassVar[str] = ""
    DEFAULT_DB_NAME: ClassVar[str] = DEFAULT_DB_NAME

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @classmethod
    def load(cls, db_name: str | None = None) -> "RigDefinition":
        """Read and decompress the rig definition for ``db_name``."""
        db_name = db_name or cls.DEFAULT_DB_NAME
        return cls(load_full_data(db_name, cls.COMPONENT))

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    @property
    def schema_version(self) -> int:
        return self._data["schema_version"]

    @property
    def db_name(self) -> str:
        return self._data["db_name"]

    @property
    def component(self) -> str:
        return self._data["component"]

    @property
    def db_complexity(self) -> str:
        return self._data["db_complexity"]

    # ------------------------------------------------------------------
    # Validation contract (counts / names / meshes)
    # ------------------------------------------------------------------
    @property
    def lod_count(self) -> int:
        return self._data["lod_count"]

    @property
    def joint_count(self) -> int:
        return self._data["joint_count"]

    @cached_property
    def joint_names(self) -> tuple[str, ...]:
        return tuple(self._data["joint_names"])

    @property
    def joint_group_count(self) -> int:
        return self._data["joint_group_count"]

    @cached_property
    def joint_group_names(self) -> tuple[str, ...]:
        return tuple(self._data["joint_group_names"])

    @cached_property
    def meshes(self) -> tuple[RigDefinitionMesh, ...]:
        return tuple(RigDefinitionMesh.from_dict(mesh) for mesh in self._data["meshes"])

    @cached_property
    def blend_shapes_by_mesh(self) -> dict[str, tuple[str, ...]]:
        return {mesh_name: tuple(channels) for mesh_name, channels in self._data["blend_shapes_by_mesh"].items()}

    @property
    def extras(self) -> dict[str, Any]:
        return self._data.get("extras", {})

    # ------------------------------------------------------------------
    # Rich structured data
    # ------------------------------------------------------------------
    @cached_property
    def joints(self) -> tuple[RigJoint, ...]:
        return tuple(RigJoint.from_dict(item) for item in self._data.get("joints", []))

    @cached_property
    def joint_groups(self) -> tuple[RigJointGroup, ...]:
        return tuple(RigJointGroup.from_dict(item) for item in self._data.get("joint_groups", []))

    @cached_property
    def color_by_joint_name(self) -> dict[str, tuple[float, ...]]:
        """Map of joint name to its authoring color, for joints that carry one.

        Colors live only in the rig definition (the DNA does not store them),
        so this is the authoritative source for per-bone coloring on import.
        """
        return {joint.name: joint.color for joint in self.joints if joint.color is not None}
