import os
import shutil
import bpy
import bmesh
import pytest
from pathlib import Path
from mathutils import Vector, Euler
from constants import TEST_DNA_FOLDER


def _load_dna(
        file_path: Path,
        import_lods: list,
        include_body: bool = True,
        import_shape_keys: bool = False,
        import_face_board: bool = True,
    ):
    # open default scene
    bpy.ops.wm.read_homefile(app_template="")

    # remove all default objects
    for obj in bpy.data.objects:
        bpy.data.objects.remove(obj, do_unlink=True)

    lods_to_import = {}
    # Set all LODs to False by default
    for index in range(8):
        lods_to_import[f'import_lod{index}'] = False
    # Set the LODs to True that are in the import_lods list
    for lod_name in import_lods:
        lods_to_import[f'import_{lod_name}'] = True

    bpy.ops.meta_human_dna.import_dna( # type: ignore
        filepath=str(file_path),
        import_mesh=True,
        import_bones=True,
        import_shape_keys=import_shape_keys,
        import_vertex_groups=True,
        import_materials=True,
        import_face_board=import_face_board,
        include_body=include_body,
        **lods_to_import
    )

def _load_temp_body_dna(
        file_name: str,
        temp_folder: Path,
        dna_folder_name: str,
        import_shape_keys: bool,
        import_lods: list
    ):
    destination_file_path = temp_folder / dna_folder_name / file_name

    # copy the dna file to the temp folder so we don't modify the original
    os.makedirs(destination_file_path.parent, exist_ok=True)
    shutil.copy(
        src=TEST_DNA_FOLDER / dna_folder_name / file_name, 
        dst=destination_file_path
    )
    # copy the export manifest as well (This is used for naming the imported instance)
    shutil.copy(
        src=TEST_DNA_FOLDER / dna_folder_name / 'ExportManifest.json', 
        dst=temp_folder / dna_folder_name / 'ExportManifest.json'
    )
    
    _load_dna(
        file_path=destination_file_path,
        import_lods=import_lods,
        import_shape_keys=import_shape_keys,
        import_face_board=False,
        include_body=False
    )

@pytest.fixture(scope='session')
def load_head_dna(
    addon, 
    dna_folder_name: str, 
    import_shape_keys: bool,
    import_lods: list,
):
    _load_dna(
        file_path=TEST_DNA_FOLDER / dna_folder_name / 'head.dna',
        import_lods=import_lods,
        import_shape_keys=import_shape_keys,
        import_face_board=True,
        include_body=True
    )


@pytest.fixture(scope='session')
def load_body_dna(
    addon, 
    dna_folder_name: str, 
    import_shape_keys: bool,
    import_lods: list,
):
    _load_dna(
        file_path=TEST_DNA_FOLDER / dna_folder_name / 'body.dna',
        import_lods=import_lods,
        import_shape_keys=import_shape_keys,
        import_face_board=False,
        include_body=False
    )


@pytest.fixture(scope='session')
def load_body_dna_for_pose_editing(
    addon, 
    temp_folder,
    dna_folder_name: str, 
    import_shape_keys: bool,
    import_lods: list,
):
    _load_temp_body_dna(
        file_name='body.dna',
        temp_folder=temp_folder,
        dna_folder_name=dna_folder_name,
        import_shape_keys=import_shape_keys,
        import_lods=import_lods
    )


@pytest.fixture(scope='session')
def load_body_dna_for_pose_roundtrip(
    addon, 
    temp_folder,
    dna_folder_name: str, 
    import_shape_keys: bool,
    import_lods: list,
):
    _load_temp_body_dna(
        file_name='body.dna',
        temp_folder=temp_folder,
        dna_folder_name=dna_folder_name,
        import_shape_keys=import_shape_keys,
        import_lods=import_lods
    )


@pytest.fixture(scope='session')
def load_full_dna_for_animation(
    addon,
    temp_folder,
    dna_folder_name: str,
    import_shape_keys: bool,
    import_lods: list,
):
    _load_dna(
        file_path=TEST_DNA_FOLDER / dna_folder_name / 'head.dna',
        import_lods=import_lods,
        import_shape_keys=import_shape_keys,
        import_face_board=True,
        include_body=True
    )


@pytest.fixture(scope='session')
def head_bmesh(load_head_dna) -> bmesh.types.BMesh | None:
    from meta_human_dna.utilities import get_active_head
    from meta_human_dna.dna_io.exporter import DNAExporter
    head = get_active_head()
    if head and head.head_mesh_object:
        return DNAExporter.get_bmesh(head.head_mesh_object)


@pytest.fixture(scope='session')
def head_armature(load_head_dna) -> bpy.types.Object | None:
    from meta_human_dna.utilities import get_active_head
    head = get_active_head()
    if head and head.head_rig_object:
        return head.head_rig_object


@pytest.fixture(scope='session')
def modify_head_scene(
    load_head_dna,
    dna_folder_name: str,
    changed_head_bone_name: str,
    changed_head_bone_location: tuple[Vector, Vector],
    changed_head_bone_rotation: tuple[Euler, Euler],
    changed_head_mesh_name: str,
    changed_head_vertex_index: int,
    changed_head_vertex_location: tuple[Vector, Vector, Vector],
    changed_head_vertex_group_name: str,
    changed_head_vertex_group_vertex_index: int,
    changed_head_vertex_group_weight: float,
    temp_folder
    ):
    from utilities.modify import (
        apply_bone_transform, 
        apply_vertex_transform,
        apply_vertex_group_weight
    )

    # Make some changes
    apply_vertex_transform(
        prefix=dna_folder_name,
        mesh_name=changed_head_mesh_name,
        vertex_index=changed_head_vertex_index,
        location=changed_head_vertex_location[0]
    )
    apply_bone_transform(
        prefix=dna_folder_name,
        component='head',
        bone_name=changed_head_bone_name,
        location=changed_head_bone_location[0],
        rotation=changed_head_bone_rotation[0],
    )
    apply_vertex_group_weight(
        prefix=dna_folder_name,
        mesh_name=changed_head_mesh_name,
        vertex_group_name=changed_head_vertex_group_name,
        vertex_index=changed_head_vertex_group_vertex_index,
        weight=changed_head_vertex_group_weight
    )

    # Save the blend file
    bpy.ops.wm.save_as_mainfile(filepath=str(temp_folder / f'{dna_folder_name}_head_modified.blend'))