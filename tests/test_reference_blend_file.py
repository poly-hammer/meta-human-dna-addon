import bpy
import pytest
from pathlib import Path
from meta_human_dna.ui.callbacks import get_active_rig_logic
from constants import TEST_DNA_FOLDER

@pytest.mark.parametrize(
    ('operation', 'metahuman_names', 'current_metahuman_name'),
    [
        ('APPEND', ['ada'], 'ada2'),
        ('LINK', ['ada'], 'ada2'),
    ]
)
def test_reference_blend_file(
    setup_reference_blend_file: Path,
    temp_folder: Path,
    operation: str,
    metahuman_names: list[str],
    current_metahuman_name: str
):
    from fixtures.scene import load_dna
    load_dna(
        file_path=TEST_DNA_FOLDER / 'ada' / 'head.dna',
        import_lods=['lod0'],
        import_shape_keys=False,
        import_face_board=True,
        include_body=True
    )
    instance = get_active_rig_logic()
    if not instance:
        pytest.fail('Rig instance should be created after loading DNA')

    # Rename the current instance to avoid name clashes
    instance.name = current_metahuman_name

    bpy.ops.meta_human_dna.append_or_link_metahuman( # type: ignore
        filepath=str(setup_reference_blend_file),
        operation_type=operation,
        meta_human_names=','.join(metahuman_names)
    )

    instances = [instance for instance in bpy.context.scene.meta_human_dna.rig_logic_instance_list] # type: ignore
    instance_names = [instance.name for instance in instances]

    for name in metahuman_names + [current_metahuman_name]:
        assert name in instance_names, f'Rig instance {name} should be present in the scene'    

    for instance in instances:
        assert instance.body_rig is not None, f'Body rig should be created for {name}'
        assert instance.body_mesh is not None, f'Body mesh should be created for {name}'
        assert instance.body_dna_file_path is not None, f'Body DNA file path should be set for {name}'
        assert instance.head_rig is not None, f'Head rig should be created for {name}'
        assert instance.head_mesh is not None, f'Head mesh should be created for {name}'
        assert instance.head_dna_file_path is not None, f'Head DNA file path should be set for {name}'