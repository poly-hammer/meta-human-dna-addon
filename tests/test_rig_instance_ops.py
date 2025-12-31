import bpy
import pytest
from pathlib import Path

@pytest.mark.parametrize(
    ('metahuman_name',),
    [
        ('ada_copy',),
    ]
)
def test_duplicate_rig_instance(
    load_dna_for_rig_instance_ops,
    temp_folder: Path,
    metahuman_name: str
):
    temp_folder.mkdir(parents=True, exist_ok=True)

    bpy.ops.meta_human_dna.duplicate_rig_instance( # type: ignore
        new_name=metahuman_name,
        new_folder=str(temp_folder)
    )

    instances = [instance for instance in bpy.context.scene.meta_human_dna.rig_logic_instance_list] # type: ignore
    instance_names = [instance.name for instance in instances]

    assert metahuman_name in instance_names, f'Rig instance {metahuman_name} should be present in the scene' 

    for instance in instances:
        assert instance.body_rig is not None, f'Body rig should be set for {instance.name}'
        assert instance.body_mesh is not None, f'Body mesh should be set for {instance.name}'
        assert instance.body_dna_file_path is not None, f'Body DNA file path should be set for {instance.name}'
        assert instance.head_rig is not None, f'Head rig should be set for {instance.name}'
        assert instance.head_mesh is not None, f'Head mesh should be set for {instance.name}'
        assert instance.head_dna_file_path is not None, f'Head DNA file path should be set for {instance.name}'

@pytest.mark.parametrize(
    ('direction', 'name', 'initial_index', 'expected_index'),
    [
        ('UP', 'ada', 0, 1),
        ('DOWN', 'ada', 1, 0),
    ]
)
def test_rig_instance_entry_move(
    load_dna_for_rig_instance_ops,
    direction: str,
    name: str,
    initial_index: int,
    expected_index: int
    ):
    instance_names = [instance.name for instance in bpy.context.scene.meta_human_dna.rig_logic_instance_list] # type: ignore
    assert instance_names.index(name) == initial_index, f'Rig instance {name} should be at index {initial_index} before move'
    bpy.ops.meta_human_dna.rig_logic_instance_entry_move(active_index=initial_index, direction=direction)  # type: ignore
    instance_names = [instance.name for instance in bpy.context.scene.meta_human_dna.rig_logic_instance_list] # type: ignore
    assert instance_names.index(name) == expected_index, f'Rig instance {name} should be at index {expected_index} after move'

def test_rig_instance_entry_add():
    name = 'Untitled1'
    # open default scene
    bpy.ops.wm.read_homefile(app_template="")
    instance_names = [instance.name for instance in bpy.context.scene.meta_human_dna.rig_logic_instance_list] # type: ignore
    assert len(instance_names) == 0, 'Rig instance list should be empty before add'
    bpy.ops.meta_human_dna.rig_logic_instance_entry_add(active_index=0)  # type: ignore
    instance_names = [instance.name for instance in bpy.context.scene.meta_human_dna.rig_logic_instance_list] # type: ignore
    assert instance_names.index(name) == 0, f'Rig instance {name} should be at index 0 before move'

def test_rig_instance_entry_remove():
    name = 'Untitled1'
    instance_names = [instance.name for instance in bpy.context.scene.meta_human_dna.rig_logic_instance_list] # type: ignore
    assert instance_names.index(name) == 0, f'Rig instance {name} should be at index 0 from the previous "add" test'    
    bpy.ops.meta_human_dna.rig_logic_instance_entry_remove(active_index=0)  # type: ignore
    instance_names = [instance.name for instance in bpy.context.scene.meta_human_dna.rig_logic_instance_list] # type: ignore
    assert len(instance_names) == 0, 'Rig instance list should be empty after remove'