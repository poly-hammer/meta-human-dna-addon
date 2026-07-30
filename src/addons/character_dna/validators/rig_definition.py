# standard library imports
import logging

# local imports
from ..rig_definition import RigDefinition, get_rig_definition
from ..typing import *  # noqa: F403
from .base import Severity, ValidationReport


logger = logging.getLogger(__name__)

DEFAULT_COMPONENT = "head"


# ----------------------------------------------------------------------------------------------
# Validator
# ----------------------------------------------------------------------------------------------
class RigDefinitionValidator:
    """Validate a DNA reader against a rig definition.

    The checks are deliberately count-based and run in a single pass so the
    validation stays cheap enough to call fast.
    """

    def __init__(self, rig_definition: RigDefinition, dna_reader: "dna.BinaryStreamReader") -> None:
        self._rig_definition = rig_definition
        self._dna_reader = dna_reader

    def validate(self) -> ValidationReport:
        report = ValidationReport(db_name=self._rig_definition.db_name)
        self._check_lod_count(report)
        self._check_joint_count(report)
        self._check_joint_group_count(report)
        self._check_meshes(report)
        return report

    def _check_lod_count(self, report: ValidationReport) -> None:
        expected = self._rig_definition.lod_count
        actual = self._dna_reader.getLODCount()
        if actual != expected:
            report.add(
                code="lod_count_mismatch",
                severity=Severity.ERROR,
                message=f"LOD count mismatch: expected {expected}, got {actual}.",
                expected=expected,
                actual=actual,
            )

    def _check_joint_count(self, report: ValidationReport) -> None:
        expected = self._rig_definition.joint_count
        actual = self._dna_reader.getJointCount()
        if actual != expected:
            report.add(
                code="joint_count_mismatch",
                severity=Severity.ERROR,
                message=f"Joint count mismatch: expected {expected}, got {actual}.",
                expected=expected,
                actual=actual,
            )

    def _check_joint_group_count(self, report: ValidationReport) -> None:
        expected = self._rig_definition.joint_group_count
        actual = self._dna_reader.getJointGroupCount()
        if actual != expected:
            report.add(
                code="joint_group_count_mismatch",
                severity=Severity.ERROR,
                message=f"Joint group count mismatch: expected {expected}, got {actual}.",
                expected=expected,
                actual=actual,
            )

    def _check_meshes(self, report: ValidationReport) -> None:
        # Build a single name -> vertex-count lookup from the DNA in one pass.
        dna_vertex_counts: dict[str, int] = {}
        for mesh_index in range(self._dna_reader.getMeshCount()):
            dna_vertex_counts[self._dna_reader.getMeshName(mesh_index)] = self._dna_reader.getVertexPositionCount(
                mesh_index
            )

        template_mesh_names = set()
        for mesh in self._rig_definition.meshes:
            template_mesh_names.add(mesh.name)
            actual_vertex_count = dna_vertex_counts.get(mesh.name)
            if actual_vertex_count is None:
                report.add(
                    code="mesh_missing",
                    severity=Severity.ERROR,
                    message=f"Mesh '{mesh.name}' is missing from the DNA.",
                    expected=mesh.name,
                    actual=None,
                )
            elif actual_vertex_count != mesh.vertex_count:
                report.add(
                    code="vertex_count_mismatch",
                    severity=Severity.ERROR,
                    message=(
                        f"Vertex count mismatch for mesh '{mesh.name}': "
                        f"expected {mesh.vertex_count}, got {actual_vertex_count}."
                    ),
                    expected=mesh.vertex_count,
                    actual=actual_vertex_count,
                )

        for dna_mesh_name in dna_vertex_counts:
            if dna_mesh_name not in template_mesh_names:
                report.add(
                    code="mesh_unexpected",
                    severity=Severity.WARNING,
                    message=(
                        f"DNA contains mesh '{dna_mesh_name}' that is not in the "
                        f"'{self._rig_definition.db_name}' rig definition."
                    ),
                    expected=None,
                    actual=dna_mesh_name,
                )


def validate_dna_compatibility(
    dna_reader: "dna.BinaryStreamReader",
    db_name: str | None = None,
    component: str = DEFAULT_COMPONENT,
) -> ValidationReport:
    """Validate a DNA reader against the ``db_name``/``component`` rig definition.

    When ``db_name`` is ``None`` the component's default database name is used.
    """
    rig_definition = get_rig_definition(component, db_name)
    return RigDefinitionValidator(rig_definition, dna_reader).validate()
