import bpy
import pytest

from character_dna.utilities import detect_legacy_data, migrate_legacy_data


@pytest.fixture
def empty_scene():
    """Provide a clean, empty scene with the addon enabled and reset afterward."""
    bpy.ops.wm.read_homefile(use_empty=True)
    yield bpy.context.scene
    bpy.ops.wm.read_homefile(use_empty=True)


def _make_sibling_instance(scene: bpy.types.Scene) -> dict:
    """Populate the read-only ``character_dna_pro`` sibling pointer to mimic a
    .blend saved by the other edition."""
    arm = bpy.data.objects.new("Ada_head_rig", bpy.data.armatures.new("Ada_head_rig"))
    mesh = bpy.data.objects.new("Ada_head_mesh", bpy.data.meshes.new("Ada_head_mesh"))
    body = bpy.data.objects.new("Ada_body_rig", bpy.data.armatures.new("Ada_body_rig"))
    mat = bpy.data.materials.new("Ada_head_shader")
    for obj in (arm, mesh, body):
        scene.collection.objects.link(obj)

    instance = scene.character_dna_pro.rig_instance_list.add()
    instance.name = "Ada"
    instance.head_rig = arm
    instance.head_mesh = mesh
    instance.body_rig = body
    instance.head_material = mat
    instance.head_dna_file_path = "//head.dna"
    instance.body_dna_file_path = "//body.dna"
    instance.output.folder_path = "//out"
    return {"head_rig": arm, "head_mesh": mesh, "body_rig": body, "head_material": mat}


def test_detect_cross_edition_data(empty_scene: bpy.types.Scene):
    _make_sibling_instance(empty_scene)
    assert detect_legacy_data(empty_scene) == ("character_dna_pro", "rig_instance_list")


def test_no_migration_for_current_edition_data(empty_scene: bpy.types.Scene):
    instance = empty_scene.character_dna.rig_instance_list.add()
    instance.name = "Ada"
    assert detect_legacy_data(empty_scene) is None


def test_cross_edition_migration_copies_all_fields(empty_scene: bpy.types.Scene):
    objects = _make_sibling_instance(empty_scene)

    result = migrate_legacy_data(bpy.context)
    assert result == "cross_edition"

    instances = list(empty_scene.character_dna.rig_instance_list)
    assert len(instances) == 1
    migrated = instances[0]
    assert migrated.name == "Ada"
    assert migrated.head_rig == objects["head_rig"]
    assert migrated.head_mesh == objects["head_mesh"]
    assert migrated.body_rig == objects["body_rig"]
    assert migrated.head_material == objects["head_material"]
    assert migrated.head_dna_file_path == "//head.dna"
    assert migrated.body_dna_file_path == "//body.dna"
    assert migrated.output.folder_path == "//out"

    # The migrated sibling list is cleared so it is neither re-detected nor re-saved.
    assert len(empty_scene.character_dna_pro.rig_instance_list) == 0
    assert detect_legacy_data(empty_scene) is None


def test_cross_edition_migration_skips_existing_names(empty_scene: bpy.types.Scene):
    _make_sibling_instance(empty_scene)
    existing = empty_scene.character_dna.rig_instance_list.add()
    existing.name = "Ada"

    migrate_legacy_data(bpy.context)

    # The existing instance is not duplicated.
    names = [instance.name for instance in empty_scene.character_dna.rig_instance_list]
    assert names.count("Ada") == 1
