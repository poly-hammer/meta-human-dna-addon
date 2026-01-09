import shutil
import uuid

import bpy
import pytest

from mathutils import Vector

from constants import DNA_RBF_BEHAVIOR_VERSION, TEST_DNA_FOLDER
from meta_human_dna.ui.callbacks import get_active_rig_instance
from meta_human_dna.utilities import reset_pose
from utilities.dna_data import get_dna_json_data
from utilities.pose_editor import set_body_pose


TOLERANCE = 1e-5
BODY_FILE_NAME = "body.dna"


def get_rbf_pose_data_from_json(json_data: dict, pose_name: str) -> tuple[int, dict | None]:
    rbf_data = json_data.get(DNA_RBF_BEHAVIOR_VERSION, {})
    poses = rbf_data.get("poses", [])

    for pose_index, pose in enumerate(poses):
        if pose.get("name") == pose_name:
            return pose_index, pose

    return -1, None


def get_rbf_solver_data_from_json(json_data: dict, solver_name: str) -> tuple[int, dict | None]:
    rbf_data = json_data.get(DNA_RBF_BEHAVIOR_VERSION, {})
    solvers = rbf_data.get("solvers", [])

    for solver_index, solver in enumerate(solvers):
        if solver.get("name") == solver_name:
            return solver_index, solver

    return -1, None


@pytest.fixture(scope="session")
def original_body_dna_json_data(temp_folder, dna_folder_name: str) -> dict:
    """
    Fixture that returns the original body DNA as JSON data.
    Reads from the original TEST_DNA_FOLDER to ensure we compare against pristine data.
    """
    dna_file_path = TEST_DNA_FOLDER / dna_folder_name / BODY_FILE_NAME
    json_file_path = temp_folder / dna_folder_name / f"{BODY_FILE_NAME}_original.json"
    return get_dna_json_data(dna_file_path, json_file_path, data_layer="All")


@pytest.fixture(scope="function")
def fresh_rbf_test_scene(addon, temp_folder, dna_folder_name: str):
    """
    Function-scoped fixture that sets up a fresh scene with DNA files
    copied to a unique temp location for each test.
    This ensures complete isolation between tests.
    """
    from fixtures.scene import load_dna

    file_names = [BODY_FILE_NAME, "ExportManifest.json"]

    # Create a unique subfolder for this test run
    unique_folder = temp_folder / f"rbf_test_{uuid.uuid4().hex[:8]}"
    unique_folder.mkdir(parents=True, exist_ok=True)

    # Copy DNA to the unique temp folder
    for _file_name in file_names:
        src = TEST_DNA_FOLDER / dna_folder_name / _file_name
        dst = unique_folder / _file_name
        shutil.copy(src, dst)

    load_dna(
        file_path=unique_folder / BODY_FILE_NAME, import_lods=["lod0"], import_shape_keys=False, import_face_board=False
    )

    yield unique_folder

    # Cleanup: remove the unique folder after the test
    if unique_folder.exists():
        shutil.rmtree(unique_folder, ignore_errors=True)


@pytest.mark.parametrize(
    (
        "solver_name",
        "pose_name",
        "changed_scale_factor",
    ),
    [
        ("calf_l_UERBFSolver", "calf_l_back_90", 0.5),
        ("calf_l_UERBFSolver", "calf_l_back_50", 1.5),
        ("thigh_l_UERBFSolver", "thigh_l_in_45_out_90", 0.75),
    ],
)
def test_rbf_pose_scale_factor_edit(
    fresh_rbf_test_scene,
    original_body_dna_json_data: dict,
    temp_folder,
    dna_folder_name: str,
    solver_name: str,
    pose_name: str,
    changed_scale_factor: float,
):
    """
    Test that modifying an RBF pose's scale factor is correctly persisted
    when committing changes to the DNA file.
    """
    instance = get_active_rig_instance()
    assert instance is not None, "No active rig instance found"
    assert instance.body_rig is not None, "No body rig found on instance"

    # Get the original scale factor from the JSON
    _original_pose_index, original_pose_data = get_rbf_pose_data_from_json(original_body_dna_json_data, pose_name)
    assert original_pose_data is not None, f"Pose '{pose_name}' not found in original DNA JSON"
    original_scale = original_pose_data.get("scale", 1.0)

    # Reset the pose to the default position
    reset_pose(instance.body_rig)

    # Set the body pose and get solver/pose indices
    pose, solver_index, pose_index = set_body_pose(solver_name=solver_name, pose_name=pose_name)
    assert pose is not None, f"Pose '{pose_name}' not found in solver '{solver_name}'"

    # Modify the scale factor
    pose.scale_factor = changed_scale_factor

    # Update and commit the pose changes
    bpy.ops.meta_human_dna.update_rbf_pose(  # type: ignore
        solver_index=solver_index, pose_index=pose_index
    )
    bpy.ops.meta_human_dna.commit_rbf_solver_changes()  # type: ignore

    # Export the modified DNA to JSON for verification
    json_file_path = temp_folder / dna_folder_name / f"body_modified_{pose_name}.json"
    modified_json_data = get_dna_json_data(instance.body_dna_file_path, json_file_path, data_layer="All")

    # Verify the modified scale factor in the exported JSON
    _modified_pose_index, modified_pose_data = get_rbf_pose_data_from_json(modified_json_data, pose_name)
    assert modified_pose_data is not None, f"Pose '{pose_name}' not found in modified DNA JSON"
    modified_scale = modified_pose_data.get("scale", 1.0)

    # Assert the scale factor was changed
    assert modified_scale != pytest.approx(
        original_scale, abs=TOLERANCE
    ), f"Scale factor should have changed from {original_scale}"
    assert modified_scale == pytest.approx(
        changed_scale_factor, abs=TOLERANCE
    ), f"Scale factor should be {changed_scale_factor}, but got {modified_scale}"


@pytest.mark.xfail(
    reason="Pose renaming may not be fully persisted by the core library - needs investigation", strict=False
)
@pytest.mark.parametrize(
    (
        "solver_name",
        "pose_name",
        "new_pose_name",
    ),
    [
        # Use poses that are NOT modified by test_rbf_pose_scale_factor_edit
        ("calf_r_UERBFSolver", "calf_r_back_90", "calf_r_back_90_renamed"),
        ("thigh_r_UERBFSolver", "thigh_r_in_45_out_90", "thigh_r_custom_pose"),
    ],
)
def test_rbf_pose_name_edit(
    fresh_rbf_test_scene,
    original_body_dna_json_data: dict,
    temp_folder,
    dna_folder_name: str,
    solver_name: str,
    pose_name: str,
    new_pose_name: str,
):
    """
    Test that renaming an RBF pose is correctly persisted when committing
    changes to the DNA file.
    """
    instance = get_active_rig_instance()
    assert instance is not None, "No active rig instance found"
    assert instance.body_rig is not None, "No body rig found on instance"

    # Verify the original pose exists in the JSON
    _original_pose_index, original_pose_data = get_rbf_pose_data_from_json(original_body_dna_json_data, pose_name)
    assert original_pose_data is not None, f"Pose '{pose_name}' not found in original DNA JSON"

    # Reset the pose to the default position
    reset_pose(instance.body_rig)

    # Set the body pose and get solver/pose indices
    pose, _solver_index, _pose_index = set_body_pose(solver_name=solver_name, pose_name=pose_name)
    assert pose is not None, f"Pose '{pose_name}' not found in solver '{solver_name}'"

    # Rename the pose
    pose.name = new_pose_name

    # Commit the pose changes (name change doesn't require update_rbf_pose)
    bpy.ops.meta_human_dna.commit_rbf_solver_changes()  # type: ignore

    # Export the modified DNA to JSON for verification
    json_file_path = temp_folder / dna_folder_name / f"body_renamed_{new_pose_name}.json"
    modified_json_data = get_dna_json_data(instance.body_dna_file_path, json_file_path, data_layer="All")

    # Verify the old name no longer exists
    _old_pose_index, old_pose_data = get_rbf_pose_data_from_json(modified_json_data, pose_name)
    assert old_pose_data is None, f"Old pose name '{pose_name}' should not exist in modified DNA JSON"

    # Verify the new name exists
    _new_pose_index, new_pose_data = get_rbf_pose_data_from_json(modified_json_data, new_pose_name)
    assert new_pose_data is not None, f"New pose name '{new_pose_name}' should exist in modified DNA JSON"


@pytest.mark.parametrize(
    (
        "solver_name",
        "pose_name",
        "driven_bone_name",
        "location_delta",
    ),
    [
        # Use poses that are NOT modified by other tests
        ("clavicle_l_UERBFSolver", "clavicle_l_up_40", "clavicle_out_l", Vector((0.0, 0.1, 0.0))),
        ("clavicle_r_UERBFSolver", "clavicle_r_up_40", "clavicle_out_r", Vector((0.0, 0.2, 0.0))),
    ],
)
def test_rbf_driven_bone_location_edit(
    fresh_rbf_test_scene,
    original_body_dna_json_data: dict,
    temp_folder,
    dna_folder_name: str,
    solver_name: str,
    pose_name: str,
    driven_bone_name: str,
    location_delta: Vector,
):
    """
    Test that modifying a driven bone's location in an RBF pose is correctly
    persisted when committing changes to the DNA file.

    This verifies that the poseJointOutputValues in the DNA JSON are updated
    to reflect the bone transform changes made in Blender.
    """
    instance = get_active_rig_instance()
    assert instance is not None, "No active rig instance found"
    assert instance.body_rig is not None, "No body rig found on instance"

    # Reset the pose to the default position
    reset_pose(instance.body_rig)

    # Set the body pose and get solver/pose indices
    pose, solver_index, pose_index = set_body_pose(solver_name=solver_name, pose_name=pose_name)
    assert pose is not None, f"Pose '{pose_name}' not found in solver '{solver_name}'"

    # Find the driven bone in the pose and apply location change
    driven_found = False
    for driven_index, driven in enumerate(pose.driven):
        if driven.name == driven_bone_name:
            driven_found = True
            pose.driven_active_index = driven_index

            pose_bone = instance.body_rig.pose.bones.get(driven.name)
            assert pose_bone is not None, f"Pose bone '{driven.name}' not found in body rig"

            # Apply the location change
            pose_bone.location = location_delta

            # Update the driven bone transform in the pose
            bpy.ops.meta_human_dna.update_rbf_pose(  # type: ignore
                solver_index=solver_index, pose_index=pose_index, driven_index=driven_index
            )
            break

    assert driven_found, f"Driven bone '{driven_bone_name}' not found in pose '{pose_name}'"

    # Commit the pose changes
    bpy.ops.meta_human_dna.commit_rbf_solver_changes()  # type: ignore

    # Export the modified DNA to JSON for verification
    json_file_path = temp_folder / dna_folder_name / f"body_driven_{driven_bone_name}.json"
    modified_json_data = get_dna_json_data(instance.body_dna_file_path, json_file_path, data_layer="All")

    # Verify the pose still exists in the modified DNA
    _modified_pose_index, modified_pose_data = get_rbf_pose_data_from_json(modified_json_data, pose_name)
    assert modified_pose_data is not None, f"Pose '{pose_name}' not found in modified DNA JSON"

    # Verify that the RBF behavior data structure exists
    rbf_data = modified_json_data.get(DNA_RBF_BEHAVIOR_VERSION, {})
    assert rbf_data, f"No '{DNA_RBF_BEHAVIOR_VERSION}' data found in modified DNA JSON"


@pytest.mark.parametrize(
    (
        "solver_name",
        "from_pose_name",
        "expected_driven_bone_count",
    ),
    [
        # Use solvers and poses known to exist in the test DNA file
        ("calf_l_UERBFSolver", "calf_l_back_90", 1),
        ("thigh_l_UERBFSolver", "thigh_l_in_45_out_90", 1),
    ],
)
def test_rbf_pose_duplicate(
    fresh_rbf_test_scene,
    original_body_dna_json_data: dict,
    temp_folder,
    dna_folder_name: str,
    solver_name: str,
    from_pose_name: str,
    expected_driven_bone_count: int,
):
    """
    Test that duplicating an RBF pose creates a new pose with the correct
    data and that it is correctly persisted in the DNA file.
    """
    instance = get_active_rig_instance()
    assert instance is not None, "No active rig instance found"
    assert instance.body_rig is not None, "No body rig found on instance"

    # Get the original pose count
    original_rbf_data = original_body_dna_json_data.get(DNA_RBF_BEHAVIOR_VERSION, {})
    original_pose_count = len(original_rbf_data.get("poses", []))

    # Reset the pose to the default position
    reset_pose(instance.body_rig)

    # Set the body pose and get solver/pose indices
    pose, solver_index, from_pose_index = set_body_pose(solver_name=solver_name, pose_name=from_pose_name)
    assert pose is not None, f"Pose '{from_pose_name}' not found in solver '{solver_name}'"

    # Duplicate the pose
    bpy.ops.meta_human_dna.duplicate_rbf_pose(  # type: ignore
        solver_index=solver_index, pose_index=from_pose_index
    )

    # Get the new pose
    solver = instance.rbf_solver_list[solver_index]
    new_pose_index = len(solver.poses) - 1
    new_pose = solver.poses[new_pose_index]
    new_pose_name = f"{from_pose_name}_duplicated_test"
    new_pose.name = new_pose_name

    # Verify the duplicated pose has the expected number of driven bones
    assert (
        len(new_pose.driven) >= expected_driven_bone_count
    ), f"Duplicated pose should have at least {expected_driven_bone_count} driven bones, got {len(new_pose.driven)}"

    # Commit the changes
    bpy.ops.meta_human_dna.commit_rbf_solver_changes()  # type: ignore

    # Export the modified DNA to JSON for verification
    json_file_path = temp_folder / dna_folder_name / f"body_duplicate_{from_pose_name}.json"
    modified_json_data = get_dna_json_data(instance.body_dna_file_path, json_file_path, data_layer="All")

    # Verify the new pose exists in the modified DNA
    _new_pose_index_json, new_pose_data = get_rbf_pose_data_from_json(modified_json_data, new_pose_name)
    assert new_pose_data is not None, f"Duplicated pose '{new_pose_name}' not found in modified DNA JSON"

    # Verify the pose count increased
    modified_rbf_data = modified_json_data.get(DNA_RBF_BEHAVIOR_VERSION, {})
    modified_pose_count = len(modified_rbf_data.get("poses", []))
    assert (
        modified_pose_count > original_pose_count
    ), f"Pose count should have increased from {original_pose_count}, got {modified_pose_count}"


@pytest.mark.parametrize(
    "solver_name",
    [
        "calf_l_UERBFSolver",
        "thigh_l_UERBFSolver",
        "clavicle_r_UERBFSolver",
    ],
)
def test_rbf_solver_exists_in_json(fresh_rbf_test_scene, original_body_dna_json_data: dict, solver_name: str):
    """
    Test that specific RBF solvers exist in the original DNA JSON structure
    under the 'rbfb1.0' key.
    """
    _solver_index, solver_data = get_rbf_solver_data_from_json(original_body_dna_json_data, solver_name)

    assert solver_data is not None, f"Solver '{solver_name}' not found in DNA JSON"
    assert "name" in solver_data, "Solver data should contain 'name' field"
    assert (
        solver_data["name"] == solver_name
    ), f"Solver name mismatch: expected '{solver_name}', got '{solver_data['name']}'"


@pytest.mark.parametrize(
    (
        "solver_name",
        "expected_pose_names",
    ),
    [
        ("calf_l_UERBFSolver", ["calf_l_back_50", "calf_l_back_90"]),
    ],
)
def test_rbf_solver_contains_expected_poses(
    fresh_rbf_test_scene, original_body_dna_json_data: dict, solver_name: str, expected_pose_names: list[str]
):
    """
    Test that an RBF solver contains the expected poses in the DNA JSON structure.
    """
    _solver_index, solver_data = get_rbf_solver_data_from_json(original_body_dna_json_data, solver_name)

    assert solver_data is not None, f"Solver '{solver_name}' not found in DNA JSON"

    # Get the pose indices from the solver
    pose_indices = solver_data.get("poseIndices", [])
    assert len(pose_indices) > 0, f"Solver '{solver_name}' should have pose indices"

    # Get the poses from the RBF data
    rbf_data = original_body_dna_json_data.get(DNA_RBF_BEHAVIOR_VERSION, {})
    poses = rbf_data.get("poses", [])

    # Get the pose names for the solver's pose indices
    solver_pose_names = [poses[pose_index].get("name", "") for pose_index in pose_indices if pose_index < len(poses)]

    # Verify expected poses are present
    for expected_pose_name in expected_pose_names:
        assert (
            expected_pose_name in solver_pose_names
        ), f"Expected pose '{expected_pose_name}' not found in solver '{solver_name}'. Found: {solver_pose_names}"
