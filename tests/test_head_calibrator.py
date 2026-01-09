import pytest

from mathutils import Euler, Vector

from constants import HEAD_DNA_FILE, IGNORED_BONE_ROTATIONS_ON_CALIBRATE, TOLERANCE
from utilities.assertions import (
    assert_bone_behaviors,
    assert_bone_definitions,
    assert_mesh_geometry,
    assert_skin_weights,
)
from utilities.dna_data import (
    get_test_bone_behaviors_params,
    get_test_bone_definitions_params,
    get_test_mesh_geometry_params,
    get_test_skin_weights_params,
)


@pytest.mark.parametrize(
    ("bone_name", "attribute", "axis_name"), get_test_bone_definitions_params(dna_file_path=HEAD_DNA_FILE)
)
def test_bone_definitions(
    original_head_dna_json_data,
    calibrated_head_dna_json_data,
    bone_name: str,
    attribute: str,
    axis_name: str,
    changed_head_bone_name: str,
    changed_head_bone_rotation: tuple[Euler, Euler],
    changed_head_bone_location: tuple[Vector, Vector],
):
    assert_bone_definitions(
        expected_data=original_head_dna_json_data,
        current_data=calibrated_head_dna_json_data,
        bone_name=bone_name,
        attribute=attribute,
        axis_name=axis_name,
        changed_bone_name=changed_head_bone_name,
        changed_bone_rotation=changed_head_bone_rotation,
        changed_bone_location=changed_head_bone_location,
        output_method="calibrate",
        ignored_bones=IGNORED_BONE_ROTATIONS_ON_CALIBRATE,
    )


@pytest.mark.parametrize("bone_name", get_test_bone_behaviors_params(dna_file_path=HEAD_DNA_FILE))
def test_bone_behaviors(original_head_dna_json_data, calibrated_head_dna_json_data, bone_name: str):
    assert_bone_behaviors(
        expected_data=original_head_dna_json_data, current_data=calibrated_head_dna_json_data, bone_name=bone_name
    )


@pytest.mark.parametrize(
    ("mesh_name", "attribute", "axis_name"),
    get_test_mesh_geometry_params(vertex_positions=True, normals=True, uvs=True, dna_file_path=HEAD_DNA_FILE),
)
def test_mesh_geometry(
    original_head_dna_json_data,
    calibrated_head_dna_json_data,
    mesh_name: str,
    attribute: str,
    axis_name: str,
    changed_head_mesh_name: int,
    changed_head_vertex_index: int,
    changed_head_vertex_location: tuple[Vector, Vector, Vector],
):
    assert_mesh_geometry(
        expected_data=original_head_dna_json_data,
        current_data=calibrated_head_dna_json_data,
        mesh_name=mesh_name,
        attribute=attribute,
        axis_name=axis_name,
        changed_mesh_name=changed_head_mesh_name,
        changed_vertex_index=changed_head_vertex_index,
        changed_vertex_location=changed_head_vertex_location,
        tolerance=TOLERANCE[attribute],
        assert_mesh_indices=True,
        output_method="calibrate",
    )


@pytest.mark.parametrize(
    ("mesh_name", "attribute", "mesh_vertex_count"), get_test_skin_weights_params(dna_file_path=HEAD_DNA_FILE)
)
def test_skin_weights(
    original_head_dna_json_data,
    calibrated_head_dna_json_data,
    mesh_name: str,
    attribute: str,
    mesh_vertex_count: int,
    changed_head_mesh_name: int,
    changed_head_vertex_group_name: str,
    changed_head_vertex_group_vertex_index: int,
    changed_head_vertex_group_weight: float,
):
    assert_skin_weights(
        expected_data=original_head_dna_json_data,
        current_data=calibrated_head_dna_json_data,
        mesh_name=mesh_name,
        mesh_vertex_count=mesh_vertex_count,
        attribute=attribute,
        changed_mesh_name=changed_head_mesh_name,
        changed_vertex_group_name=changed_head_vertex_group_name,
        changed_vertex_group_vertex_index=changed_head_vertex_group_vertex_index,
        changed_vertex_group_weight=changed_head_vertex_group_weight,
        tolerance=TOLERANCE[attribute],
    )
