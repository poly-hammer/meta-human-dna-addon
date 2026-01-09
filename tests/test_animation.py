import bpy
import pytest

from constants import TEST_ANIMATION_FOLDER
from meta_human_dna.constants import IS_BLENDER_5
from meta_human_dna.ui.callbacks import get_active_rig_instance


@pytest.mark.parametrize(
    ("component", "file_name"),
    [
        ("body", "MHC_BodyROM.fbx"),
        ("head", "MHC_HeadROM.fbx"),
    ],
)
def test_import_component_animation(load_full_dna_for_animation, component: str, file_name: str):
    instance = get_active_rig_instance()
    file_path = TEST_ANIMATION_FOLDER / component / file_name

    bpy.ops.meta_human_dna.import_component_animation(component_type=component, filepath=str(file_path))

    if component == "body":
        assert instance.body_rig.animation_data.action.name == f"{instance.name}_{component}_{file_path.stem}"
    elif component == "head":
        assert instance.head_rig.animation_data.action.name == f"{instance.name}_{component}_{file_path.stem}"


@pytest.mark.parametrize(
    ("file_name"),
    [
        ("MHC_FaceBoardROM.fbx"),
    ],
)
def test_import_face_board_animation(load_full_dna_for_animation, file_name: str):
    instance = get_active_rig_instance()
    file_path = TEST_ANIMATION_FOLDER / "head" / file_name

    bpy.ops.meta_human_dna.import_face_board_animation(filepath=str(file_path))

    assert instance.face_board.animation_data.action.name == f"{instance.name}_face_board_{file_path.stem}"


@pytest.mark.parametrize(
    ("component", "action_name", "prefix_instance_name", "prefix_component_name", "replace_action"),
    [
        ("body", "test", True, True, False),
        ("body", "test", True, True, True),
        # ('head', 'test', True, True, False),
    ],
)
def test_bake_component_animation(
    load_full_dna_for_animation,
    component: str,
    action_name: str,
    prefix_instance_name: bool,
    prefix_component_name: bool,
    replace_action: bool,
):
    instance = get_active_rig_instance()
    bpy.context.window_manager.meta_human_dna.current_component_type = component

    if IS_BLENDER_5:
        previous_object_action_names = [a.name for a in bpy.data.actions if a.slots[0].target_id_type == "OBJECT"]
        [a.name for a in bpy.data.actions if a.slots[0].target_id_type == "NODETREE"]
    else:
        previous_object_action_names = [a.name for a in bpy.data.actions if a.id_root == "OBJECT"]
        [a.name for a in bpy.data.actions if a.id_root == "NODETREE"]

    bpy.ops.meta_human_dna.bake_component_animation(
        start_frame=1,
        end_frame=10,
        component_type=component,
        action_name=action_name,
        prefix_instance_name=prefix_instance_name,
        prefix_component_name=prefix_component_name,
        replace_action=replace_action,
    )

    if IS_BLENDER_5:
        expected_object_action_names = [a.name for a in bpy.data.actions if a.slots[0].target_id_type == "OBJECT"]
        [a.name for a in bpy.data.actions if a.slots[0].target_id_type == "NODETREE"]
    else:
        expected_object_action_names = [a.name for a in bpy.data.actions if a.id_root == "OBJECT"]
        [a.name for a in bpy.data.actions if a.id_root == "NODETREE"]

    new_object_actions = set(expected_object_action_names) - set(previous_object_action_names)

    if not replace_action:
        assert len(new_object_actions) == 1, "A new action should be created when not replacing an existing action."
        assert (
            new_object_actions.pop() == f"{instance.name}_{component}_{action_name}"
        ), "The baked action name is not as expected."


@pytest.mark.parametrize(
    ("action_name", "prefix_instance_name", "prefix_component_name", "replace_action"),
    [
        ("face_board_test", True, True, False),
        ("face_board_test", True, True, True),
    ],
)
def test_bake_face_board_animation(
    load_full_dna_for_animation,
    action_name: str,
    prefix_instance_name: bool,
    prefix_component_name: bool,
    replace_action: bool,
):
    instance = get_active_rig_instance()

    if IS_BLENDER_5:
        previous_object_action_names = [
            a.name
            for a in bpy.data.actions
            if a.slots[0].target_id_type == "OBJECT" and a.name != f"{instance.name}_head_{action_name}"
        ]
        previous_node_tree_action_names = [
            a.name
            for a in bpy.data.actions
            if a.slots[0].target_id_type == "NODETREE" and a.name != f"{instance.name}_head_{action_name}_shader"
        ]
    else:
        previous_object_action_names = [
            a.name
            for a in bpy.data.actions
            if a.id_root == "OBJECT" and a.name != f"{instance.name}_head_{action_name}"
        ]
        previous_node_tree_action_names = [
            a.name
            for a in bpy.data.actions
            if a.id_root == "NODETREE" and a.name != f"{instance.name}_head_{action_name}_shader"
        ]

    bpy.ops.meta_human_dna.bake_face_board_animation(
        start_frame=1,
        end_frame=10,
        action_name=action_name,
        prefix_instance_name=prefix_instance_name,
        prefix_component_name=prefix_component_name,
        replace_action=replace_action,
    )

    if IS_BLENDER_5:
        expected_object_action_names = [a.name for a in bpy.data.actions if a.slots[0].target_id_type == "OBJECT"]
        expected_node_tree_action_names = [a.name for a in bpy.data.actions if a.slots[0].target_id_type == "NODETREE"]
    else:
        expected_object_action_names = [a.name for a in bpy.data.actions if a.id_root == "OBJECT"]
        expected_node_tree_action_names = [a.name for a in bpy.data.actions if a.id_root == "NODETREE"]

    new_object_actions = set(expected_object_action_names) - set(previous_object_action_names)
    new_node_tree_action_names = set(expected_node_tree_action_names) - set(previous_node_tree_action_names)

    if not replace_action:
        assert len(new_object_actions) == 1, "A new action should be created when not replacing an existing action."

        assert (
            new_object_actions.pop() == f"{instance.name}_head_{action_name}"
        ), "The baked action name is not as expected."

    assert (
        len(new_node_tree_action_names) == 1
    ), "A new node tree action should always be created for face board baking."
    assert any(
        name == f"{instance.name}_head_{action_name}_shader" for name in expected_node_tree_action_names
    ), "The baked node tree action name is not as expected."
