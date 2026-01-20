# standard library imports
import logging

from dataclasses import dataclass, field
from enum import Enum

# third party imports
from mathutils import Quaternion, Vector

# local imports
from ...constants import BONE_DELTA_THRESHOLD
from ...typing import *  # noqa: F403


logger = logging.getLogger(__name__)


# Storage key for pose editor data in RigInstance.data
POSE_EDITOR_DATA_KEY = "pose_editor_data"


class ChangeType(Enum):
    """Types of changes that can be tracked."""

    POSE_ADDED = "pose_added"
    POSE_REMOVED = "pose_removed"
    POSE_RENAMED = "pose_renamed"
    SOLVER_ADDED = "solver_added"
    SOLVER_REMOVED = "solver_removed"
    DRIVEN_BONE_ADDED = "driven_bone_added"
    DRIVEN_BONE_REMOVED = "driven_bone_removed"
    DRIVER_MODIFIED = "driver_modified"
    DRIVEN_LOCATION = "driven_location"
    DRIVEN_ROTATION = "driven_rotation"
    DRIVEN_SCALE = "driven_scale"


@dataclass
class BoneChange:
    """Represents a change to a single bone's transform."""

    bone_name: str
    pose_name: str
    solver_name: str
    change_type: ChangeType
    old_value: tuple | None = None
    new_value: tuple | None = None

    @property
    def summary(self) -> str:
        """Get a human-readable summary of this change."""
        type_labels = {
            ChangeType.DRIVEN_LOCATION: "location",
            ChangeType.DRIVEN_ROTATION: "rotation",
            ChangeType.DRIVEN_SCALE: "scale",
            ChangeType.DRIVER_MODIFIED: "driver rotation",
        }
        label = type_labels.get(self.change_type, self.change_type.value)
        return f"{self.bone_name}: {label} modified"


@dataclass
class StructuralChange:
    """Represents a structural change (add/remove pose, solver, bone)."""

    change_type: ChangeType
    name: str
    parent_name: str = ""  # For poses: solver name. For bones: pose name.

    @property
    def summary(self) -> str:
        """Get a human-readable summary of this change."""
        if self.change_type == ChangeType.POSE_ADDED:
            return f"Added pose '{self.name}' to {self.parent_name}"
        if self.change_type == ChangeType.POSE_REMOVED:
            return f"Removed pose '{self.name}' from {self.parent_name}"
        if self.change_type == ChangeType.SOLVER_ADDED:
            return f"Added solver '{self.name}'"
        if self.change_type == ChangeType.SOLVER_REMOVED:
            return f"Removed solver '{self.name}'"
        if self.change_type == ChangeType.DRIVEN_BONE_ADDED:
            return f"Added bone '{self.name}' to {self.parent_name}"
        if self.change_type == ChangeType.DRIVEN_BONE_REMOVED:
            return f"Removed bone '{self.name}' from {self.parent_name}"
        if self.change_type == ChangeType.POSE_RENAMED:
            return f"Renamed pose to '{self.name}'"
        return f"{self.change_type.value}: {self.name}"


@dataclass
class PoseEditorSnapshot:
    """
    A snapshot of the RBF solver data at a point in time.

    Used to compare current state against initial state to track changes.
    """

    # Solver name -> {pose_name -> {bone_name -> transforms}}
    solvers: dict = field(default_factory=dict)
    # Solver name -> list of pose names
    solver_poses: dict = field(default_factory=dict)
    # Solver name -> pose_name -> list of driven bone names
    pose_driven_bones: dict = field(default_factory=dict)
    # Solver name -> pose_name -> {driver_name -> quaternion}
    pose_drivers: dict = field(default_factory=dict)

    def is_empty(self) -> bool:
        """Check if the snapshot is empty."""
        return len(self.solvers) == 0


@dataclass
class PoseEditorChangeTracker:
    """
    Tracks all changes made during a pose editing session.

    Stores the initial snapshot when editing begins and provides methods
    to compute the differences from the current state.
    """

    initial_snapshot: PoseEditorSnapshot = field(default_factory=PoseEditorSnapshot)
    bone_changes: list[BoneChange] = field(default_factory=list)
    structural_changes: list[StructuralChange] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Check if there are any tracked changes."""
        return len(self.bone_changes) > 0 or len(self.structural_changes) > 0

    @property
    def change_count(self) -> int:
        """Get the total number of changes."""
        return len(self.bone_changes) + len(self.structural_changes)

    def get_summary_lines(self, max_lines: int = 5) -> list[str]:
        """
        Get a list of summary lines describing the changes.

        Args:
            max_lines: Maximum number of lines to return.

        Returns:
            List of human-readable change summary strings.
        """
        lines: list[str] = []

        # Structural changes first (more significant)
        lines.extend(change.summary for change in self.structural_changes[:max_lines])

        # Then bone changes
        remaining = max_lines - len(lines)
        if remaining > 0:
            lines.extend(change.summary for change in self.bone_changes[:remaining])

        # Add overflow indicator
        total = self.change_count
        shown = len(lines)
        if total > shown:
            lines.append(f"... and {total - shown} more changes")

        return lines

    def get_bone_changes_by_pose(self) -> dict[str, list[BoneChange]]:
        """Group bone changes by pose name."""
        by_pose: dict[str, list[BoneChange]] = {}
        for change in self.bone_changes:
            if change.pose_name not in by_pose:
                by_pose[change.pose_name] = []
            by_pose[change.pose_name].append(change)
        return by_pose

    def clear(self) -> None:
        """Clear all tracked changes."""
        self.bone_changes.clear()
        self.structural_changes.clear()
        self.initial_snapshot = PoseEditorSnapshot()


def create_snapshot(instance: "RigInstance") -> PoseEditorSnapshot:
    """
    Create a snapshot of the current RBF solver data.

    Args:
        instance: The active rig instance.

    Returns:
        A PoseEditorSnapshot capturing the current state.
    """
    from ...bindings import meta_human_dna_core  # pyright: ignore[reportAttributeAccessIssue]

    snapshot = PoseEditorSnapshot()

    if not instance or not instance.body_dna_reader:
        return snapshot

    # Get the original data from DNA
    for solver_data in meta_human_dna_core.get_rbf_solver_data(instance.body_dna_reader):
        solver_name = solver_data.name
        snapshot.solvers[solver_name] = {}
        snapshot.solver_poses[solver_name] = []
        snapshot.pose_driven_bones[solver_name] = {}
        snapshot.pose_drivers[solver_name] = {}

        for pose_data in solver_data.poses:
            pose_name = pose_data.name
            snapshot.solver_poses[solver_name].append(pose_name)
            snapshot.solvers[solver_name][pose_name] = {}
            snapshot.pose_driven_bones[solver_name][pose_name] = []
            snapshot.pose_drivers[solver_name][pose_name] = {}

            # Store driven bone transforms
            for driven_data in pose_data.driven:
                bone_name = driven_data.name
                snapshot.pose_driven_bones[solver_name][pose_name].append(bone_name)
                snapshot.solvers[solver_name][pose_name][bone_name] = {
                    "location": tuple(driven_data.location),
                    "rotation": tuple(driven_data.euler_rotation),
                    "scale": tuple(driven_data.scale),
                }

            # Store driver bone quaternions
            for driver_data in pose_data.drivers:
                snapshot.pose_drivers[solver_name][pose_name][driver_data.name] = tuple(driver_data.quaternion_rotation)

    return snapshot


def _compare_driven_transforms(
    tracker: PoseEditorChangeTracker,
    pose: "RBFPoseData",
    solver_name: str,
    initial_pose_data: dict,
) -> None:
    """Compare driven bone transforms and add changes to tracker."""
    pose_name = pose.name

    for driven in pose.driven:
        bone_name = driven.name

        if bone_name not in initial_pose_data:
            continue

        initial_transforms = initial_pose_data[bone_name]

        # Compare location
        initial_loc = Vector(initial_transforms["location"])
        current_loc = Vector(driven.location[:])
        if (current_loc - initial_loc).length > BONE_DELTA_THRESHOLD:
            tracker.bone_changes.append(
                BoneChange(
                    bone_name=bone_name,
                    pose_name=pose_name,
                    solver_name=solver_name,
                    change_type=ChangeType.DRIVEN_LOCATION,
                    old_value=initial_loc[:],
                    new_value=current_loc[:],
                )
            )

        # Compare rotation
        initial_rot = Vector(initial_transforms["rotation"])
        current_rot = Vector(driven.euler_rotation[:])
        if (current_rot - initial_rot).length > BONE_DELTA_THRESHOLD:
            tracker.bone_changes.append(
                BoneChange(
                    bone_name=bone_name,
                    pose_name=pose_name,
                    solver_name=solver_name,
                    change_type=ChangeType.DRIVEN_ROTATION,
                    old_value=initial_rot[:],
                    new_value=current_rot[:],
                )
            )

        # Compare scale
        initial_scale = Vector(initial_transforms["scale"])
        current_scale = Vector(driven.scale[:])
        if (current_scale - initial_scale).length > BONE_DELTA_THRESHOLD:
            tracker.bone_changes.append(
                BoneChange(
                    bone_name=bone_name,
                    pose_name=pose_name,
                    solver_name=solver_name,
                    change_type=ChangeType.DRIVEN_SCALE,
                    old_value=initial_scale[:],
                    new_value=current_scale[:],
                )
            )


def _compare_driver_rotations(
    tracker: PoseEditorChangeTracker,
    pose: "RBFPoseData",
    solver_name: str,
    initial_drivers: dict,
) -> None:
    """Compare driver bone rotations and add changes to tracker."""
    pose_name = pose.name

    for driver in pose.drivers:
        driver_name = driver.name
        if driver_name not in initial_drivers:
            continue

        initial_quat = Quaternion(initial_drivers[driver_name])
        current_quat = Quaternion(driver.quaternion_rotation[:])
        rotation_diff = initial_quat.normalized().rotation_difference(current_quat.normalized()).angle

        if rotation_diff > BONE_DELTA_THRESHOLD:
            tracker.bone_changes.append(
                BoneChange(
                    bone_name=driver_name,
                    pose_name=pose_name,
                    solver_name=solver_name,
                    change_type=ChangeType.DRIVER_MODIFIED,
                    old_value=initial_quat[:],
                    new_value=current_quat[:],
                )
            )


def _compare_pose_bones(
    tracker: PoseEditorChangeTracker,
    pose: "RBFPoseData",
    solver_name: str,
    initial_snapshot: PoseEditorSnapshot,
) -> None:
    """Compare pose's driven and driver bones against initial snapshot."""
    pose_name = pose.name

    if pose_name not in initial_snapshot.solvers.get(solver_name, {}):
        return

    initial_pose_data = initial_snapshot.solvers[solver_name][pose_name]
    initial_driven_bones = set(initial_snapshot.pose_driven_bones.get(solver_name, {}).get(pose_name, []))
    current_driven_bones = {d.name for d in pose.driven}

    # Detect added driven bones
    for bone_name in current_driven_bones - initial_driven_bones:
        tracker.structural_changes.append(
            StructuralChange(
                change_type=ChangeType.DRIVEN_BONE_ADDED,
                name=bone_name,
                parent_name=f"{solver_name}/{pose_name}",
            )
        )

    # Detect removed driven bones
    for bone_name in initial_driven_bones - current_driven_bones:
        tracker.structural_changes.append(
            StructuralChange(
                change_type=ChangeType.DRIVEN_BONE_REMOVED,
                name=bone_name,
                parent_name=f"{solver_name}/{pose_name}",
            )
        )

    # Compare transforms
    _compare_driven_transforms(tracker, pose, solver_name, initial_pose_data)

    # Compare driver rotations
    initial_drivers = initial_snapshot.pose_drivers.get(solver_name, {}).get(pose_name, {})
    _compare_driver_rotations(tracker, pose, solver_name, initial_drivers)


def compute_changes(instance: "RigInstance", initial_snapshot: PoseEditorSnapshot) -> PoseEditorChangeTracker:
    """
    Compute the differences between the initial snapshot and current state.

    Args:
        instance: The active rig instance with current state.
        initial_snapshot: The snapshot taken when editing began.

    Returns:
        A PoseEditorChangeTracker with all detected changes.
    """
    tracker = PoseEditorChangeTracker(initial_snapshot=initial_snapshot)

    if not instance or not instance.body_rig:
        return tracker

    # Get current solver names
    current_solver_names = {s.name for s in instance.rbf_solver_list}
    initial_solver_names = set(initial_snapshot.solvers.keys())

    # Detect added solvers
    for solver_name in current_solver_names - initial_solver_names:
        tracker.structural_changes.append(StructuralChange(change_type=ChangeType.SOLVER_ADDED, name=solver_name))

    # Detect removed solvers
    for solver_name in initial_solver_names - current_solver_names:
        tracker.structural_changes.append(StructuralChange(change_type=ChangeType.SOLVER_REMOVED, name=solver_name))

    # Compare poses and transforms for each solver
    for solver in instance.rbf_solver_list:
        solver_name = solver.name

        if solver_name not in initial_snapshot.solvers:
            continue

        initial_poses = set(initial_snapshot.solver_poses.get(solver_name, []))
        current_poses = {p.name for p in solver.poses}

        # Detect added poses
        for pose_name in current_poses - initial_poses:
            if pose_name != "default":
                tracker.structural_changes.append(
                    StructuralChange(
                        change_type=ChangeType.POSE_ADDED,
                        name=pose_name,
                        parent_name=solver_name,
                    )
                )

        # Detect removed poses
        for pose_name in initial_poses - current_poses:
            tracker.structural_changes.append(
                StructuralChange(
                    change_type=ChangeType.POSE_REMOVED,
                    name=pose_name,
                    parent_name=solver_name,
                )
            )

        # Compare transforms for existing poses
        for pose in solver.poses:
            _compare_pose_bones(tracker, pose, solver_name, initial_snapshot)

    return tracker


def get_change_tracker(instance: "RigInstance") -> PoseEditorChangeTracker | None:
    """
    Get the change tracker from the instance's data dictionary.

    Args:
        instance: The active rig instance.

    Returns:
        The PoseEditorChangeTracker, or None if not initialized.
    """
    pose_editor_data = instance.data.get(POSE_EDITOR_DATA_KEY, {})
    return pose_editor_data.get("change_tracker")


def initialize_tracking(instance: "RigInstance") -> PoseEditorChangeTracker:
    """
    Initialize change tracking by taking a snapshot of current state.

    This should be called when entering pose editing mode.

    Args:
        instance: The active rig instance.

    Returns:
        The initialized PoseEditorChangeTracker.
    """
    from ...utilities import dependencies_are_valid

    if not dependencies_are_valid():
        logger.warning("Dependencies not valid, cannot initialize change tracking")
        return PoseEditorChangeTracker()

    snapshot = create_snapshot(instance)
    tracker = PoseEditorChangeTracker(initial_snapshot=snapshot)

    # Store in instance data
    if POSE_EDITOR_DATA_KEY not in instance.data:
        instance.data[POSE_EDITOR_DATA_KEY] = {}
    instance.data[POSE_EDITOR_DATA_KEY]["change_tracker"] = tracker
    instance.data[POSE_EDITOR_DATA_KEY]["initial_snapshot"] = snapshot

    logger.debug(f"Initialized pose editor change tracking with {len(snapshot.solvers)} solvers")
    return tracker


def update_tracking(instance: "RigInstance") -> PoseEditorChangeTracker:
    """
    Update the change tracker by computing differences from initial snapshot.

    This should be called after any modification to RBF data.

    Args:
        instance: The active rig instance.

    Returns:
        The updated PoseEditorChangeTracker.
    """
    pose_editor_data = instance.data.get(POSE_EDITOR_DATA_KEY, {})
    initial_snapshot = pose_editor_data.get("initial_snapshot")

    if initial_snapshot is None:
        # Not initialized, do it now
        return initialize_tracking(instance)

    tracker = compute_changes(instance, initial_snapshot)

    # Update stored tracker
    instance.data[POSE_EDITOR_DATA_KEY]["change_tracker"] = tracker

    return tracker


def clear_tracking(instance: "RigInstance") -> None:
    """
    Clear all change tracking data.

    This should be called when exiting pose editing mode.

    Args:
        instance: The active rig instance.
    """
    if POSE_EDITOR_DATA_KEY in instance.data:
        del instance.data[POSE_EDITOR_DATA_KEY]
    logger.debug("Cleared pose editor change tracking")
