"""Tests for locking pose bones outside the active raw control's joint
group while editing.

The Raw Control Editor only commits joints that the active control
drives (its joint group -- the same set soloing the control reveals).
Moving any other bone produces a misleading viewport preview that is
silently dropped at commit, so on entry every out-of-group bone's
transform channels are locked, and on commit/revert they are restored.

These tests exercise the headless helpers
:func:`lock_bones_outside_joint_group` and :func:`restore_locked_bones`
with lightweight fakes (no live Blender session)."""

from __future__ import annotations

import pytest

from character_dna.editors.raw_control_editor.constants import (
    DEFAULT_RAW_CONTROL_INDEX,
    CacheNamespace,
)


class _FakeReader:
    """4-joint chain ``root(0) -> mid(1) -> leafA(2), leafB(3)``. Joint
    group 0 is driven by raw control 5 and outputs the two leaves, so
    ``joints_driven_by_raw_control(5) == {2, 3}`` -- joints 0 and 1 are
    outside the group."""

    def getJointCount(self) -> int:
        return 4

    def getJointName(self, i: int) -> str:
        return ["FACIAL_C_FacialRoot", "mid", "leafA", "leafB"][i]

    def getJointGroupCount(self) -> int:
        return 1

    def getJointGroupInputIndices(self, jg: int) -> list[int]:
        return [5]

    def getJointGroupOutputIndices(self, jg: int) -> list[int]:
        return [2 * 9, 3 * 9]


class _FakePoseBone:
    def __init__(self, name: str) -> None:
        self.name = name
        self.lock_location = (False, False, False)
        self.lock_rotation = (False, False, False)
        self.lock_rotation_w = False
        self.lock_scale = (False, False, False)


class _FakeBones:
    def __init__(self, names: list[str]) -> None:
        self._bones = {name: _FakePoseBone(name) for name in names}

    def get(self, name: str) -> _FakePoseBone | None:
        return self._bones.get(name)


class _FakePose:
    def __init__(self, names: list[str]) -> None:
        self.bones = _FakeBones(names)


class _FakeRig:
    def __init__(self, name: str, bone_names: list[str]) -> None:
        self.name = name
        self.pose = _FakePose(bone_names)


class _FakeCache:
    """Stand-in for :class:`EditorCache` -- one persistent dict per
    namespace key."""

    def __init__(self) -> None:
        self._namespaces: dict[str, dict] = {}

    def namespace(self, key: CacheNamespace) -> dict:
        return self._namespaces.setdefault(str(key), {})


class _FakeInstance:
    def __init__(self, rig: _FakeRig, reader: _FakeReader) -> None:
        self.head_rig = rig
        self.head_dna_reader = reader


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch):
    from character_dna.editors.raw_control_editor import utilities

    cache = _FakeCache()
    monkeypatch.setattr(utilities, "session_cache", lambda _instance: cache)
    reader = _FakeReader()
    rig = _FakeRig("Ada_head_rig", [reader.getJointName(i) for i in range(reader.getJointCount())])
    instance = _FakeInstance(rig, reader)
    return utilities, instance, reader, rig, cache


def test_lock_locks_only_bones_outside_joint_group(patched) -> None:
    utilities, instance, reader, rig, _cache = patched

    locked = utilities.lock_bones_outside_joint_group(instance, reader, 5)

    # joints 0 (root) and 1 (mid) are outside the group -> locked.
    assert locked == 2
    bones = rig.pose.bones
    for name in ("FACIAL_C_FacialRoot", "mid"):
        pose_bone = bones.get(name)
        assert tuple(pose_bone.lock_location) == (True, True, True)
        assert tuple(pose_bone.lock_rotation) == (True, True, True)
        assert pose_bone.lock_rotation_w is True
        assert tuple(pose_bone.lock_scale) == (True, True, True)
    # joints 2 (leafA) and 3 (leafB) are in the group -> untouched.
    for name in ("leafA", "leafB"):
        pose_bone = bones.get(name)
        assert tuple(pose_bone.lock_location) == (False, False, False)
        assert tuple(pose_bone.lock_rotation) == (False, False, False)
        assert pose_bone.lock_rotation_w is False
        assert tuple(pose_bone.lock_scale) == (False, False, False)


def test_restore_returns_prior_lock_state(patched) -> None:
    utilities, instance, reader, rig, _cache = patched

    # leafA carries a pre-existing user lock that must survive untouched
    # (it is in the group, so lock never touches it).
    rig.pose.bones.get("leafA").lock_location = (True, False, False)

    utilities.lock_bones_outside_joint_group(instance, reader, 5)
    restored = utilities.restore_locked_bones(instance)

    assert restored == 2
    for name in ("FACIAL_C_FacialRoot", "mid"):
        pose_bone = rig.pose.bones.get(name)
        assert tuple(pose_bone.lock_location) == (False, False, False)
        assert tuple(pose_bone.lock_rotation) == (False, False, False)
        assert pose_bone.lock_rotation_w is False
        assert tuple(pose_bone.lock_scale) == (False, False, False)
    # The in-group bone's pre-existing lock is never altered.
    assert tuple(rig.pose.bones.get("leafA").lock_location) == (True, False, False)


def test_restore_clears_the_cache_entry(patched) -> None:
    utilities, instance, reader, _rig, cache = patched

    utilities.lock_bones_outside_joint_group(instance, reader, 5)
    assert cache.namespace(CacheNamespace.LOCKED_BONES)  # populated

    utilities.restore_locked_bones(instance)
    assert not cache.namespace(CacheNamespace.LOCKED_BONES)  # emptied

    # A second restore with nothing cached is a harmless no-op.
    assert utilities.restore_locked_bones(instance) == 0


def test_bind_pose_sentinel_locks_nothing(patched) -> None:
    """The bind-pose ("default") sentinel drives no joint group and
    writes neutral joints directly, so no bone should be locked."""
    utilities, instance, reader, rig, _cache = patched

    assert utilities.lock_bones_outside_joint_group(instance, reader, DEFAULT_RAW_CONTROL_INDEX) == 0
    for name in ("FACIAL_C_FacialRoot", "mid", "leafA", "leafB"):
        assert tuple(rig.pose.bones.get(name).lock_location) == (False, False, False)
