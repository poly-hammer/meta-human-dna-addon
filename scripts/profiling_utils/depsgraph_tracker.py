"""
Dependency graph update tracker for MetaHuman DNA Addon.

This module tracks how often the dependency graph triggers rig evaluations,
providing insights into update frequency and potential performance issues.

Example:
    from profiling_utils.depsgraph_tracker import DepsgraphTracker
    tracker = DepsgraphTracker.get_instance()
    tracker.start()
    # ... work in Blender ...
    stats = tracker.get_stats()
    tracker.stop()
"""

from __future__ import annotations

import time

from collections import deque
from dataclasses import dataclass
from typing import Literal

import bpy


@dataclass
class DepsgraphStats:
    """Statistics for dependency graph updates."""

    total_updates: int = 0
    head_evaluations: int = 0
    body_evaluations: int = 0
    full_evaluations: int = 0
    updates_per_second: float = 0.0
    avg_update_interval_ms: float = 0.0
    min_update_interval_ms: float = 0.0
    max_update_interval_ms: float = 0.0
    tracking_duration_s: float = 0.0


@dataclass
class UpdateRecord:
    """Record of a single dependency graph update."""

    timestamp_ns: int
    component: Literal["head", "body", "all"]
    duration_ns: int = 0


class DepsgraphTracker:
    """
    Singleton tracker for dependency graph updates.

    This class hooks into the rig evaluation pipeline to track:
    - How often evaluations occur
    - Which components (head/body/all) are being evaluated
    - Timing between updates
    """

    _instance: DepsgraphTracker | None = None
    _original_evaluate: callable | None = None  # type: ignore[type-arg]

    def __init__(self) -> None:
        self._tracking = False
        self._start_time_ns: int = 0
        self._records: deque[UpdateRecord] = deque(maxlen=1000)
        self._handler: object | None = None
        self._last_update_ns: int = 0

    @classmethod
    def get_instance(cls) -> DepsgraphTracker:
        """Get the singleton tracker instance."""
        if cls._instance is None:
            cls._instance = DepsgraphTracker()
        return cls._instance

    @property
    def is_tracking(self) -> bool:
        """Check if tracking is currently active."""
        return self._tracking

    def start(self) -> None:
        """Start tracking dependency graph updates."""
        if self._tracking:
            return

        self._tracking = True
        self._start_time_ns = time.perf_counter_ns()
        self._last_update_ns = self._start_time_ns
        self._records.clear()

        # Register our handler
        if self._handler is None:
            self._handler = bpy.app.handlers.depsgraph_update_post.append(self._on_depsgraph_update)

        print("[DepsgraphTracker] Started tracking")

    def stop(self) -> None:
        """Stop tracking dependency graph updates."""
        if not self._tracking:
            return

        self._tracking = False

        # Remove our handler
        if self._handler is not None and self._on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(self._on_depsgraph_update)
            self._handler = None

        print("[DepsgraphTracker] Stopped tracking")

    def reset(self) -> None:
        """Reset all tracking data."""
        self._records.clear()
        self._start_time_ns = time.perf_counter_ns()
        self._last_update_ns = self._start_time_ns

    def record_evaluation(self, component: Literal["head", "body", "all"], duration_ns: int = 0) -> None:
        """
        Record a rig evaluation event.

        This should be called from the rig evaluation code to track updates.

        Args:
            component: Which component was evaluated.
            duration_ns: How long the evaluation took in nanoseconds.
        """
        if not self._tracking:
            return

        now = time.perf_counter_ns()
        self._records.append(
            UpdateRecord(
                timestamp_ns=now,
                component=component,
                duration_ns=duration_ns,
            )
        )
        self._last_update_ns = now

    def _on_depsgraph_update(self, scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph) -> None:
        """Handler for depsgraph_update_post events."""
        if not self._tracking:
            return

        # Check if any rig logic updates occurred
        for update in depsgraph.updates:
            if update.id and hasattr(update.id, "bl_rna"):
                data_type = update.id.bl_rna.name
                if data_type in ("Armature", "Action"):
                    self.record_evaluation("all")
                    break

    def get_stats(self) -> DepsgraphStats:
        """Get current tracking statistics."""
        if not self._records:
            return DepsgraphStats()

        now = time.perf_counter_ns()
        duration_s = (now - self._start_time_ns) / 1e9

        # Count component evaluations
        head_evals = sum(1 for r in self._records if r.component == "head")
        body_evals = sum(1 for r in self._records if r.component == "body")
        full_evals = sum(1 for r in self._records if r.component == "all")

        total = len(self._records)

        # Calculate update intervals
        intervals_ms = []
        records_list = list(self._records)
        for i in range(1, len(records_list)):
            interval_ns = records_list[i].timestamp_ns - records_list[i - 1].timestamp_ns
            intervals_ms.append(interval_ns / 1e6)

        return DepsgraphStats(
            total_updates=total,
            head_evaluations=head_evals,
            body_evaluations=body_evals,
            full_evaluations=full_evals,
            updates_per_second=total / duration_s if duration_s > 0 else 0.0,
            avg_update_interval_ms=sum(intervals_ms) / len(intervals_ms) if intervals_ms else 0.0,
            min_update_interval_ms=min(intervals_ms) if intervals_ms else 0.0,
            max_update_interval_ms=max(intervals_ms) if intervals_ms else 0.0,
            tracking_duration_s=duration_s,
        )

    def get_recent_records(self, count: int = 100) -> list[UpdateRecord]:
        """Get the most recent update records."""
        return list(self._records)[-count:]


# Convenience functions
def start_tracking() -> DepsgraphTracker:
    """Start the depsgraph tracker and return the instance."""
    tracker = DepsgraphTracker.get_instance()
    tracker.start()
    return tracker


def stop_tracking() -> DepsgraphStats:
    """Stop the depsgraph tracker and return final stats."""
    tracker = DepsgraphTracker.get_instance()
    stats = tracker.get_stats()
    tracker.stop()
    return stats


def get_stats() -> DepsgraphStats:
    """Get current tracking stats without stopping."""
    return DepsgraphTracker.get_instance().get_stats()
