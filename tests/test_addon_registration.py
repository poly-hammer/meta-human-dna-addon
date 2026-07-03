import bpy
import pytest

from character_dna import operators, utilities
from character_dna.ui import view_3d


def test_addons_are_enabled(addons):
    for addon_name, _ in addons:
        assert "character_dna" in bpy.context.preferences.addons, f"{addon_name} is not enabled"  # type: ignore


@pytest.mark.parametrize(
    "panel_class",
    [
        view_3d.CHARACTER_DNA_PT_output_panel,
        view_3d.CHARACTER_DNA_PT_rig_instance,
        view_3d.CHARACTER_DNA_PT_view_options,
        view_3d.CHARACTER_DNA_PT_face_board,
    ],
)
def test_view_3d(panel_class):
    assert panel_class.is_registered, f'The Panel in the 3D View "{panel_class.bl_label}" is not registered.'


@pytest.mark.parametrize(
    "operator_class",
    [
        operators.ForceEvaluate,
        operators.RefreshOutputItems,
        operators.ImportCharacterDna,
    ],
)
def test_operators(operator_class):
    assert operator_class.is_registered, f"Operator {operator_class.bl_idname} is not registered."


def test_edition_specific_registration():
    """The upsell panel is always registered; editor panels only exist in the Pro edition."""
    # The upsell panel is always registered in both editions; its poll controls visibility.
    assert view_3d.CHARACTER_DNA_PT_pro_upsell.is_registered, "The upsell panel should always be registered."

    editors = utilities.get_editors()
    if utilities.editors_available():
        assert editors is not None, "Editors submodule present but registry failed to import."
        raw_control_editor_ui = editors.raw_control_editor_ui  # type: ignore[attr-defined]
        assert raw_control_editor_ui.CHARACTER_DNA_PT_raw_control_editor.is_registered, (
            "Pro edition should register the editor panels."
        )
    else:
        assert editors is None, "Free edition should not import an editors registry."
