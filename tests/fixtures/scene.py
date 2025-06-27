import bpy
import bmesh
import pytest
from mathutils import Vector, Euler
from constants import TEST_DNA_FOLDER

@pytest.fixture(scope='session')
def load_dna(
    addon, 
    dna_file_name: str, 
    import_shape_keys: bool,
    import_lods: list,
):
    file_path = TEST_DNA_FOLDER / dna_file_name

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
        import_face_board=True,
        **lods_to_import
    )

@pytest.fixture(scope='session')
def head_bmesh(load_dna) -> bmesh.types.BMesh | None:
    from meta_human_dna.utilities import get_active_head
    from meta_human_dna.dna_io.exporter import DNAExporter
    head = get_active_head()
    if head and head.head_mesh_object:
        return DNAExporter.get_bmesh(head.head_mesh_object)

@pytest.fixture(scope='session')
def head_armature(load_dna) -> bpy.types.Object | None:
    from meta_human_dna.utilities import get_active_head
    head = get_active_head()
    if head and head.head_rig_object:
        return head.head_rig_object

@pytest.fixture(scope='session')
def modify_scene(
    load_dna,
    dna_file_name: str,
    changed_bone_name: str,
    changed_bone_location: tuple[Vector, Vector],
    changed_bone_rotation: tuple[Euler, Euler],
    changed_mesh_name: str,
    changed_vertex_index: int,
    changed_vertex_location: tuple[Vector, Vector, Vector],
    temp_folder
    ):
    from utilities.modify import apply_bone_transform, apply_vertex_transform
    name = dna_file_name.split(".")[0]
    # Make some changes
    apply_vertex_transform(
        prefix=name,
        mesh_name=changed_mesh_name,
        vertex_index=changed_vertex_index,
        location=changed_vertex_location[0]
    )
    apply_bone_transform(
        prefix=name,
        component='head',
        bone_name=changed_bone_name,
        location=changed_bone_location[0],
        rotation=changed_bone_rotation[0],
    )

    # Save the blend file
    bpy.ops.wm.save_as_mainfile(filepath=str(temp_folder / f'{name}_modified.blend'))