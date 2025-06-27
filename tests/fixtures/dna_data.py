import pytest
from constants import TEST_DNA_FOLDER


@pytest.fixture(scope="session")
def original_dna_json_data(temp_folder, dna_file_name: str) -> dict:
    from utilities.dna_data import get_dna_json_data

    dna_file_path = TEST_DNA_FOLDER / dna_file_name
    json_file_path = temp_folder / f"{dna_file_name.split('.')[0]}.json"
    return get_dna_json_data(dna_file_path, json_file_path)


@pytest.fixture(scope="session")
def exported_dna_json_data(
    modify_scene,
    temp_folder,
    dna_file_name: str
) -> dict:
    from utilities.dna_data import get_dna_json_data
    from meta_human_dna.utilities import get_active_head
    from meta_human_dna.dna_io import DNAExporter

    head = get_active_head()
    name = dna_file_name.split(".")[0]
    export_folder = temp_folder / "export"
    dna_file_path = export_folder / dna_file_name
    json_file_path = export_folder / f"{name}.json"
    export_folder.mkdir(exist_ok=True)

    if head and head.rig_logic_instance:
        head.rig_logic_instance.output_folder_path = str(export_folder)
        DNAExporter(
            instance=head.rig_logic_instance, 
            linear_modifier=head.linear_modifier
        ).run()
        return get_dna_json_data(dna_file_path, json_file_path)

    return {}


@pytest.fixture(scope="session")
def calibrated_dna_json_data(
    modify_scene,
    temp_folder,
    dna_file_name: str
) -> dict:
    from utilities.dna_data import get_dna_json_data
    from meta_human_dna.utilities import get_active_head
    from meta_human_dna.dna_io import DNACalibrator

    head = get_active_head()
    name = dna_file_name.split(".")[0]
    calibrate_folder = temp_folder / "calibrate"
    dna_file_path = calibrate_folder / dna_file_name
    json_file_path = calibrate_folder / f"{name}.json"
    calibrate_folder.mkdir(exist_ok=True)

    if head and head.rig_logic_instance:
        head.rig_logic_instance.output_folder_path = str(calibrate_folder)
        DNACalibrator(
            instance=head.rig_logic_instance, 
            linear_modifier=head.linear_modifier
        ).run()
        
        return get_dna_json_data(dna_file_path, json_file_path)

    return {}
