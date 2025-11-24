import bpy
import pytest
from meta_human_dna.ui.callbacks import get_active_rig_logic
from constants import TEST_ANIMATION_FOLDER


@pytest.mark.parametrize(
    ('component', 'file_name'),
    [
        ('body', 'MHC_BodyROM.fbx'),
        ('head', 'MHC_HeadROM.fbx'),
    ]
)
def test_import_component_animation(
    load_full_dna_for_animation,
    component: str,
    file_name: str
):
    instance = get_active_rig_logic()
    file_path = TEST_ANIMATION_FOLDER / component / file_name

    bpy.ops.meta_human_dna.import_component_animation(
        component_type=component,
        filepath=str(file_path)
    )

    if component == 'body':
        assert instance.body_rig.animation_data.action.name == f'{instance.name}_{component}_{file_path.stem}'
    elif component == 'head':
        assert instance.head_rig.animation_data.action.name == f'{instance.name}_{component}_{file_path.stem}'


@pytest.mark.parametrize(
    ('file_name'),
    [
        ('MHC_FaceBoardROM.fbx'),
    ]
)
def test_import_face_board_animation(
    load_full_dna_for_animation,
    file_name: str
):
    instance = get_active_rig_logic()
    file_path = TEST_ANIMATION_FOLDER / 'head' / file_name

    bpy.ops.meta_human_dna.import_face_board_animation(filepath=str(file_path)
    )

    assert instance.face_board.animation_data.action.name == f'{instance.name}_face_board_{file_path.stem}'