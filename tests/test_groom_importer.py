import bpy
import numpy as np
import pytest

from character_dna.groom_io import (
    GroomGeometry,
    GroomImporter,
    build_curves_object,
    discover_grooms,
    read_groom_geometry,
    source_to_blender_linear,
    write_groom_geometry,
)
from constants import TEST_GROOM_FOLDER


EYELASHES_FOLDER = TEST_GROOM_FOLDER / "eyelashes"


# ----------------------------------------------------------------------------
# Binary codec
# ----------------------------------------------------------------------------
def test_binary_round_trip(tmp_path):
    offsets = np.array([0, 3, 7], dtype=np.int32)
    positions = np.arange(7 * 3, dtype=np.float32).reshape(-1, 3)
    geometry = GroomGeometry(
        curve_offsets=offsets,
        positions=positions,
        widths=np.full(7, 0.01, dtype=np.float32),
        root_uv=np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32),
        group_id=np.array([0, 1], dtype=np.int32),
    )
    path = tmp_path / "round_trip.cdgr"
    write_groom_geometry(path, geometry)

    loaded = read_groom_geometry(path)
    assert loaded.curve_count == 2
    assert loaded.point_count == 7
    assert np.array_equal(loaded.curve_offsets, offsets)
    assert np.allclose(loaded.positions, positions)
    assert np.allclose(loaded.widths, geometry.widths)
    assert np.allclose(loaded.root_uv, geometry.root_uv)
    assert np.array_equal(loaded.group_id, geometry.group_id)
    assert loaded.guide is None


def test_read_rejects_non_groom_file(tmp_path):
    bad = tmp_path / "bad.cdgr"
    bad.write_bytes(b"NOPE" + b"\x00" * 32)
    with pytest.raises(ValueError):
        read_groom_geometry(bad)


# ----------------------------------------------------------------------------
# Coordinate transform
# ----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("space", "source_point", "expected"),
    [
        # Unreal (cm, Z-up, left-handed) -> Blender (m, Z-up, right-handed): negate Y, * 0.01
        ({"units": "cm", "up_axis": "Z", "handedness": "left"}, (10.0, 20.0, 30.0), (0.10, -0.20, 0.30)),
        # Right-handed Z-up source only scales.
        ({"units": "cm", "up_axis": "Z", "handedness": "right"}, (10.0, 20.0, 30.0), (0.10, 0.20, 0.30)),
        # Maya/Alembic Y-up (right-handed) -> Z-up: (x, y, z) -> (x, -z, y) * 0.01
        ({"units": "cm", "up_axis": "Y", "handedness": "right"}, (10.0, 20.0, 30.0), (0.10, -0.30, 0.20)),
        # Metres stay 1:1 in magnitude.
        ({"units": "m", "up_axis": "Z", "handedness": "left"}, (1.0, 2.0, 3.0), (1.0, -2.0, 3.0)),
    ],
)
def test_source_to_blender_transform(space, source_point, expected):
    matrix = source_to_blender_linear(space)
    result = np.array(source_point, dtype=np.float32) @ matrix.T
    assert np.allclose(result, expected, atol=1e-6)


def test_transform_preserves_length():
    # A 5 cm Unreal strand stays 0.05 m in Blender (scale only, no shear).
    space = {"units": "cm", "up_axis": "Z", "handedness": "left"}
    matrix = source_to_blender_linear(space)
    a = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    b = np.array([1.0, 2.0, 8.0], dtype=np.float32)  # 5 cm apart along Z
    length = np.linalg.norm((b @ matrix.T) - (a @ matrix.T))
    assert length == pytest.approx(0.05, abs=1e-6)


# ----------------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------------
def test_discovery_picks_highest_detail():
    sources = discover_grooms(EYELASHES_FOLDER)
    # The fixture manifest lists the same groom as both strands (LOD0) and cards
    # (LOD2); discovery must collapse to the single strands entry.
    assert len(sources) == 1
    source = sources[0]
    assert source.name == "Eyelashes_S_Sparse"
    assert source.is_strands
    assert source.space["units"] == "cm"
    assert source.geometry_path.name == "Eyelashes_S_Sparse.cdgr"


# ----------------------------------------------------------------------------
# Curves builder
# ----------------------------------------------------------------------------
def _make_surface() -> bpy.types.Object:
    mesh = bpy.data.meshes.new("groom_surface")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
    mesh.update()
    mesh.uv_layers.new(name="DiffuseUV")
    scene_object = bpy.data.objects.new("groom_surface", mesh)
    bpy.context.scene.collection.objects.link(scene_object)
    return scene_object


def test_build_curves_object_from_fixture():
    source = discover_grooms(EYELASHES_FOLDER)[0]
    geometry = read_groom_geometry(source.geometry_path)
    surface = _make_surface()

    curves_object = build_curves_object(source, geometry, surface_object=surface, attach_to_surface=True)
    assert curves_object.type == "CURVES"

    curves = curves_object.data
    assert len(curves.curves) == geometry.curve_count == 6
    assert len(curves.points) == geometry.point_count == 78

    # Positions are converted into Blender space (negate Y, * 0.01).
    matrix = source_to_blender_linear(source.space)
    expected = geometry.positions @ matrix.T
    actual = np.empty(geometry.point_count * 3, dtype=np.float32)
    curves.points.foreach_get("position", actual)
    assert np.allclose(actual.reshape(-1, 3), expected, atol=1e-5)

    # Each fixture strand is 0.83 cm long -> 0.0083 m after conversion.
    first_strand = expected[geometry.curve_offsets[0] : geometry.curve_offsets[1]]
    strand_length = np.linalg.norm(np.diff(first_strand, axis=0), axis=1).sum()
    assert strand_length == pytest.approx(0.0083, abs=1e-4)

    attribute_names = {attribute.name for attribute in curves.attributes}
    assert {"position", "radius", "curve_type", "surface_uv_coordinate", "groom_group_id"} <= attribute_names

    assert curves.surface == surface
    assert curves.surface_uv_map == "DiffuseUV"


# ----------------------------------------------------------------------------
# GroomImporter and the import operator
# ----------------------------------------------------------------------------
def test_groom_importer_run_and_idempotent():
    surface = _make_surface()
    importer = GroomImporter(
        folder_path=str(EYELASHES_FOLDER),
        surface_object=surface,
        collection_name="groom_importer_test",
        attach_to_surface=True,
    )
    valid, _title, message, _fix = importer.run()
    assert valid, message
    assert len(importer.imported_objects) == 1

    # Re-running clears the collection instead of duplicating.
    GroomImporter(
        folder_path=str(EYELASHES_FOLDER),
        surface_object=surface,
        collection_name="groom_importer_test",
    ).run()
    collection = bpy.data.collections.get("groom_importer_test")
    assert collection is not None
    assert len(collection.objects) == 1


def test_missing_folder_returns_invalid():
    valid, title, _message, _fix = GroomImporter(folder_path="/does/not/exist/groom").run()
    assert not valid
    assert title == "Groom Folder Not Found"


def test_import_groom_operator():
    bpy.ops.wm.read_homefile(app_template="")
    for scene_object in list(bpy.data.objects):
        bpy.data.objects.remove(scene_object, do_unlink=True)

    head = _make_surface()
    scene_properties = bpy.context.scene.character_dna
    instance = scene_properties.rig_instance_list.add()
    instance.name = "groom_op_test"
    instance.head_mesh = head
    scene_properties.rig_instance_list_active_index = len(scene_properties.rig_instance_list) - 1
    instance.output.groom_folder_path = str(EYELASHES_FOLDER)

    result = bpy.ops.character_dna.import_groom()
    assert result == {"FINISHED"}

    collection = bpy.data.collections.get(f"{instance.name}_grooms")
    assert collection is not None
    assert len(collection.objects) == 1
    curves_object = collection.objects[0]
    assert curves_object.type == "CURVES"
    assert len(curves_object.data.curves) == 6
    # The operator attaches the imported hair to the instance's head mesh.
    assert curves_object.data.surface == head
