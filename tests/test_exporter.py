import pytest
from mathutils import Euler, Vector
from constants import TOLERANCE
from utilities.dna_data import (
    get_test_bone_definitions_params, 
    get_test_mesh_geometry_params
)
from utilities.assertions import (
    assert_bone_definitions, 
    assert_mesh_geometry
)


@pytest.mark.parametrize(
    ('bone_name', 'attribute', 'axis_name'),
     get_test_bone_definitions_params()
)
def test_bone_definitions(
    original_dna_json_data, 
    exported_dna_json_data,
    bone_name: str,
    attribute: str,
    axis_name: str,
    changed_bone_name: str,
    changed_bone_rotation: tuple[Euler, Euler],
    changed_bone_location: tuple[Vector, Vector]
):
    assert_bone_definitions(
        expected_data=original_dna_json_data,
        current_data=exported_dna_json_data,
        bone_name=bone_name,
        attribute=attribute,
        axis_name=axis_name,
        changed_bone_name=changed_bone_name,
        changed_bone_rotation=changed_bone_rotation,
        changed_bone_location=changed_bone_location,
        tolerance=TOLERANCE[attribute]
    )


@pytest.mark.parametrize(
    ('mesh_name', 'attribute', 'axis_name'), 
    get_test_mesh_geometry_params(
        lods=[0],
        vertex_positions=True,
        normals=False,
        uvs=True
    )
)
def test_mesh_geometry(
    original_dna_json_data, 
    exported_dna_json_data,
    mesh_name: str,
    attribute: str,
    axis_name: str,
    changed_mesh_name: int,
    changed_vertex_index: int,
    changed_vertex_location: tuple[Vector, Vector, Vector],
):
    assert_mesh_geometry(
        expected_data=original_dna_json_data,
        current_data=exported_dna_json_data,
        mesh_name=mesh_name,
        attribute=attribute,
        axis_name=axis_name,
        changed_mesh_name=changed_mesh_name,
        changed_vertex_index=changed_vertex_index,
        changed_vertex_location=changed_vertex_location,
        assert_mesh_indices=False,
        assert_index_order=False,
        tolerance=TOLERANCE[attribute]
    )