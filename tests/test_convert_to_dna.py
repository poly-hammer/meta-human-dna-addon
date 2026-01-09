from pathlib import Path

import bpy
import pytest

from meta_human_dna import utilities
from meta_human_dna.ui.callbacks import get_active_rig_instance


@pytest.mark.parametrize(
    ("component", "name"),
    [
        ("head", "TestMetaHuman01"),
        ("body", "TestMetaHuman01"),
    ],
)
def test_convert_component_to_dna(load_mhc_conformed_topology_meshes, temp_folder: Path, component: str, name: str):
    # select the component mesh
    utilities.select_only(bpy.data.objects[f"{component}_lod0_mesh"])

    folder = temp_folder / "converted_dna"
    folder.mkdir(parents=True, exist_ok=True)

    # set the current component type in the UI
    bpy.context.window_manager.meta_human_dna.current_component_type = component  # type: ignore
    # convert to DNA
    bpy.ops.meta_human_dna.convert_selected_to_dna(  # type: ignore
        new_instance_name=name, new_folder=str(folder)
    )  # type: ignore

    instance = get_active_rig_instance()

    assert instance is not None, "Rig instance should be created"
    if component == "body":
        assert instance.body_rig is not None, f"Body rig should be created for {name}"
        assert instance.body_mesh is not None, f"Body mesh should be created for {name}"
        assert instance.body_dna_file_path is not None, f"Body DNA file path should be set for {name}"
    elif component == "head":
        assert instance.head_rig is not None, f"Head rig should be created for {name}"
        assert instance.head_mesh is not None, f"Head mesh should be created for {name}"
        assert instance.head_dna_file_path is not None, f"Head DNA file path should be set for {name}"
    assert instance.name == name, f"Instance name should be {name}"
