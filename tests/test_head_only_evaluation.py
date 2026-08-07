"""Evaluation of a head DNA imported on its own, with no body rig to drive its neck bones.

With a full character the head rig's ``neck_01``/``neck_02``/``head`` bones are copy-transform
driven by the body rig, so posing the body is what the listener reacts to. Imported alone the
head rig is posed directly and is the only source of the neck quaternions that feed the head
RBFs and the eye aim solve.

Covers https://github.com/poly-hammer/character-dna-addon/issues/309 and
https://github.com/poly-hammer/character-dna-addon/issues/359.
"""

import bpy
import pytest

from mathutils import Quaternion

from character_dna import rig_instance


# 45 degrees about the head's local z, which is a neck-driver rotation the head RBFs read.
TURNED_HEAD = Quaternion((0.9239, 0.0, 0.0, 0.3827))


def get_instance():
    return bpy.context.scene.character_dna.rig_instance_list[0]  # type: ignore[attr-defined]


def enter_pose_mode(rig_object: bpy.types.Object):
    """The listener only evaluates from the viewport while in pose mode."""
    bpy.context.view_layer.objects.active = rig_object  # type: ignore[union-attr]
    bpy.ops.object.mode_set(mode="POSE")


def get_neck_raw_controls(instance) -> dict[str, float]:
    head_instance = instance.head_instance
    return {
        f"{name}.q{axis}": round(head_instance.getRawControl(index), 4)
        for index, name, axis in instance.head_raw_quat_plan
    }


def get_eye_gui_controls(instance) -> dict[str, float]:
    head_instance = instance.head_instance
    return {
        f"{name}.{axis}": round(head_instance.getGUIControl(index), 4)
        for index, name, axis in instance.head_gui_control_plan
        if name in ("CTRL_L_eye", "CTRL_R_eye")
    }


def test_head_only_import_has_no_body_to_drive_the_neck(load_head_only_dna):
    """The premise of the rest of this module: nothing else is driving the head rig."""
    instance = get_instance()

    assert instance.head_rig
    assert instance.body_rig is None

    for bone_name in ("neck_01", "neck_02", "head"):
        pose_bone = instance.head_rig.pose.bones[bone_name]
        assert [constraint for constraint in pose_bone.constraints if constraint.type == "COPY_TRANSFORMS"] == []


def test_head_rig_rotation_updates_the_neck_raw_controls(load_head_only_dna):
    """Issue #359: the head RBFs only re-solve if the neck quaternions reach the raw controls."""
    instance = get_instance()
    enter_pose_mode(instance.head_rig)

    before = get_neck_raw_controls(instance)
    assert before["head.qz"] == pytest.approx(0.0, abs=1e-3)

    instance.head_rig.pose.bones["head"].rotation_quaternion = TURNED_HEAD
    bpy.context.view_layer.update()

    after = get_neck_raw_controls(instance)
    assert after != before, "rotating the head bone did not reach rig logic without a Force Evaluate"
    assert after["head.qz"] == pytest.approx(0.3827, abs=1e-3)
    assert after["head.qw"] == pytest.approx(0.9239, abs=1e-3)


def test_head_rig_rotation_updates_the_eye_aim_solve(load_head_only_dna):
    """Issue #309: with the aim target world-fixed, turning the head must counter-rotate the eyes."""
    instance = get_instance()
    face_board_bones = instance.face_board.pose.bones

    # Aim the eyes at the eyes aim control, and leave that control behind when the head turns.
    face_board_bones["CTRL_lookAtSwitch"].location.y = 1.0
    face_board_bones["CTRL_eyesAimFollowHead"].location.y = 0.0

    enter_pose_mode(instance.head_rig)
    bpy.context.view_layer.update()
    assert instance.head_use_eye_aim

    before = get_eye_gui_controls(instance)
    instance.head_rig.pose.bones["head"].rotation_quaternion = TURNED_HEAD
    bpy.context.view_layer.update()
    after = get_eye_gui_controls(instance)

    assert after != before, "the eyes did not re-aim when the head bone was rotated"


def test_head_rig_updates_are_not_repeated_for_rig_logic_own_writes(load_head_only_dna):
    """Rig logic writes head bones, which re-tags the armature. That echo must not re-evaluate."""
    instance = get_instance()
    enter_pose_mode(instance.head_rig)

    instance.head_rig.pose.bones["head"].rotation_quaternion = TURNED_HEAD
    bpy.context.view_layer.update()

    armature_name = instance.head_rig.data.name
    dependency_graph = bpy.context.evaluated_depsgraph_get()

    assert rig_instance._get_armature_update_component(instance, armature_name, dependency_graph) is None

    # a genuine change to a driver bone is still picked up
    instance.head_rig.pose.bones["neck_01"].rotation_quaternion = TURNED_HEAD
    bpy.context.view_layer.update()
    dependency_graph = bpy.context.evaluated_depsgraph_get()
    instance.data.pop(instance.cache_key("head", "input_signature"), None)

    assert rig_instance._get_armature_update_component(instance, armature_name, dependency_graph) == "head"


def test_head_evaluates_without_a_face_board(load_head_only_dna):
    """The face board only supplies GUI control positions; the neck solve must not depend on it."""
    instance = get_instance()
    instance.face_board = None
    enter_pose_mode(instance.head_rig)

    before = get_neck_raw_controls(instance)
    instance.head_rig.pose.bones["head"].rotation_quaternion = TURNED_HEAD
    bpy.context.view_layer.update()
    after = get_neck_raw_controls(instance)

    assert after != before
    assert after["head.qz"] == pytest.approx(0.3827, abs=1e-3)
