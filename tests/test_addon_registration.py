import bpy
import pytest

from meta_human_dna import operators
from meta_human_dna.ui import view_3d


def test_addons_are_enabled(addons):
    for addon_name, _ in addons:
        assert "meta_human_dna" in bpy.context.preferences.addons, f"{addon_name} is not enabled"  # type: ignore


@pytest.mark.parametrize(
    "panel_class",
    [
        view_3d.META_HUMAN_DNA_PT_output_panel,
        view_3d.META_HUMAN_DNA_PT_rig_instance,
        view_3d.META_HUMAN_DNA_PT_view_options,
        view_3d.META_HUMAN_DNA_PT_face_board,
    ],
)
def test_view_3d(panel_class):
    assert panel_class.is_registered, f'The Panel in the 3D View "{panel_class.bl_label}" is not registered.'


@pytest.mark.parametrize(
    "operator_class",
    [
        operators.ForceEvaluate,
        operators.ImportMetaHumanDna,
    ],
)
def test_operators(operator_class):
    assert operator_class.is_registered, f"Operator {operator_class.bl_idname} is not registered."
