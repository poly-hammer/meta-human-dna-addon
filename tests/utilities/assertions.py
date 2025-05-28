import pytest
from mathutils import Euler, Vector

def assert_bone_definitions(
    expected_data: dict,
    current_data: dict,
    bone_name: str,
    attribute: str,
    axis_name: str,
    changed_bone_name: str,
    changed_bone_rotation: tuple[Euler, Euler],
    changed_bone_location: tuple[Vector, Vector],
    tolerance: float = 1e-3
):
    expected_bone_index = expected_data['definition']['jointNames'].index(bone_name)
    current_bone_index = current_data['definition']['jointNames'].index(bone_name)
    assert current_bone_index == expected_bone_index, f'Bone index mismatch. {bone_name} should be at index {expected_bone_index} but is at {current_bone_index}'
    
    expected_hierarchy = expected_data['definition']['jointHierarchy'][expected_bone_index]
    current_hierarchy = current_data['definition']['jointHierarchy'][current_bone_index]
    assert current_hierarchy == expected_hierarchy, f'Bone hierarchy mismatch. {bone_name} should have hierarchy {expected_hierarchy} but has {current_hierarchy}'
    
    expected_value = expected_data['definition'][attribute][f'{axis_name}s'][expected_bone_index]
    current_value = current_data['definition'][attribute][f'{axis_name}s'][current_bone_index]

    # this ensures that we don't assert that the bone was moved in the dna if it was not moved in blender
    changed_location = False
    if attribute == 'neutralJointTranslations':
        changed_location = getattr(changed_bone_location[0], axis_name) != 0.0

    changed_rotation = False
    if attribute == 'neutralJointRotations':
        changed_rotation = getattr(changed_bone_rotation[0], axis_name) != 0.0
        # reduce the tolerance for joint rotations since they are in degrees
        tolerance = 1e-2

    if bone_name == changed_bone_name and (changed_rotation or changed_location):
        assert current_value != pytest.approx(expected_value, abs=tolerance), \
            f'{axis_name} bone {bone_name} {attribute} should not match, since it was moved in blender.'
    else:
        assert current_value == pytest.approx(expected_value, abs=tolerance), \
            f'{axis_name} bone {attribute} mismatch. {bone_name} should have {axis_name} {attribute} {expected_value} but has {current_value}.'
        
    
def assert_bone_behaviors(
    expected_data: dict,
    current_data: dict,
    bone_name: str
):
    # First get the bone index from its name
    expected_bone_index = expected_data['definition']['jointNames'].index(bone_name)
    current_bone_index = current_data['definition']['jointNames'].index(bone_name)
    assert current_bone_index == expected_bone_index, f'Bone index mismatch. {bone_name} should be at index {expected_bone_index} but is at {current_bone_index}'
    
    expected_row_count = expected_data['behavior']['joints']['rowCount']
    current_row_count = current_data['behavior']['joints']['rowCount']
    assert current_row_count == expected_row_count, f'Row count mismatch. {bone_name} should have row count {expected_row_count} but has {current_row_count}'

    expected_column_count = expected_data['behavior']['joints']['colCount']
    current_column_count = current_data['behavior']['joints']['colCount']
    assert current_column_count == expected_column_count, f'Column count mismatch. {bone_name} should have column count {expected_column_count} but has {current_column_count}'

    expected_joint_groups = expected_data['behavior']['joints']['jointGroups']
    current_joint_groups = current_data['behavior']['joints']['jointGroups']

    for joint_group_index, (expected_joint_group_data, current_joint_group_data) in enumerate(zip(expected_joint_groups, current_joint_groups)):
        if expected_bone_index in expected_joint_group_data['jointIndices']:
            assert current_bone_index in current_joint_group_data['jointIndices']
            break

        

def assert_mesh_geometry(
    expected_data: dict, 
    current_data: dict,
    mesh_name: str,
    attribute: str,
    axis_name: str,
    changed_mesh_name: int,
    changed_vertex_index: int,
    changed_vertex_location: tuple[Vector, Vector, Vector],
    assert_mesh_indices: bool = True,
    assert_index_order: bool = True,
    tolerance: float = 1e-3
):
    expected_mesh_index = expected_data['definition']['meshNames'].index(mesh_name)
    current_mesh_index = current_data['definition']['meshNames'].index(mesh_name)

    if assert_mesh_indices:
        assert expected_mesh_index == current_mesh_index, \
            f'Mesh index mismatch. {mesh_name} should be at index {expected_mesh_index} but is at {current_mesh_index}'
    
    # this ensures that we don't assert that the vertex was moved in the dna if it was not moved in blender by
    # comparing the original and new dna vertex positions
    changed_position = False
    if attribute == 'positions':
        changed_position = getattr(changed_vertex_location[1], axis_name) - getattr(changed_vertex_location[-1], axis_name) != 0.0

    expected_indices = expected_data['geometry']['meshes'][expected_mesh_index]['layouts'][attribute]
    current_indices = current_data['geometry']['meshes'][current_mesh_index]['layouts'][attribute]

    expected_values = expected_data['geometry']['meshes'][expected_mesh_index][attribute][f'{axis_name}s']
    current_values = current_data['geometry']['meshes'][current_mesh_index][attribute][f'{axis_name}s']

    # The mesh indices should be the same
    if assert_index_order:
        assert len(expected_indices) == len(current_indices), \
            f'Mesh {mesh_name} {attribute} indices length mismatch. Expected {len(expected_indices)} indices but has {len(current_indices)}.'

        for index, (expected_index, current_index) in enumerate(zip(expected_indices, current_indices)):
            assert expected_index == current_index, \
                f'Mesh {mesh_name} {attribute} indices order mismatch at array index {index}. Expected {expected_index} but has {current_index}.'
            
        for expected_index, current_index in zip(expected_indices, current_indices):
            expected_value = expected_values[expected_index]
            current_value = current_values[current_index]

            # if this is the changed vertex and the axis value is not ignored
            if mesh_name == changed_mesh_name and expected_index == changed_vertex_index and changed_position:
                assert expected_value != pytest.approx(current_value, abs=tolerance), \
                    f'Mesh {mesh_name} {attribute} {axis_name} vertex index {changed_vertex_index} should not match, since it was moved in blender.'
            else:
                assert expected_value == pytest.approx(current_value, abs=tolerance), \
                    f'Mesh {mesh_name} {attribute} {axis_name} vertex index {expected_index} mismatch. Expected {expected_value} but has {current_value}.'
    
    # Otherwise, the mesh indices can be in any order but still the number unique indices should be the same
    else:     
        sorted_expected_values = expected_values
        sorted_current_values = current_values
        # remove duplicate values and sort the lists for UVs since there can be multiple UVs for the same vertex
        if attribute == 'textureCoordinates':
            sorted_expected_values = sorted(set(expected_values))
            sorted_current_values = sorted(set(current_values))
        
        for expected_value, current_value in zip(sorted_expected_values, sorted_current_values):
            if expected_value != pytest.approx(current_value, abs=tolerance) and changed_position:
                assert expected_values[changed_vertex_index] == expected_value, \
                f'Mesh {mesh_name} {attribute} {axis_name} value mismatch. The vertex index that was moved was {changed_vertex_index} but this is not that one.'
            else:
                assert expected_value == pytest.approx(current_value, abs=tolerance), \
                    f'Mesh {mesh_name} {attribute} {axis_name} value mismatch. Expected {expected_value} but has {current_value}.'
        
        