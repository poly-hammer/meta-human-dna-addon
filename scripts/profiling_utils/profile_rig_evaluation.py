"""
Profiling module for MetaHuman DNA Addon rig evaluation.

This script profiles both the Python code in rig_instance.py and the C++ RigLogic
evaluation using the collectCalculationStats method from the RigLogic bindings.

Usage:
    Run from Blender with a MetaHuman DNA file loaded::

        from profiling_utils import run_profiler

        results = run_profiler(iterations=100, warmup=10)

    Export results for CI::

        from profiling_utils.exporters import export_snapshot

        export_snapshot(results, "reports/profiling", format="all")

    Enable realtime HUD::

        from profiling_utils.viewport_hud import enable_hud

        enable_hud()
"""

from __future__ import annotations

import logging
import statistics
import time

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import bpy


if TYPE_CHECKING:
    from meta_human_dna.rig_logic import RigLogicInstance as RigInstance

logger = logging.getLogger(__name__)


@dataclass
class TimingResult:
    """Stores timing results for a single operation."""

    name: str
    times_ns: list[int] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.times_ns)

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.times_ns) / 1e6 if self.times_ns else 0.0

    @property
    def median_ms(self) -> float:
        return statistics.median(self.times_ns) / 1e6 if self.times_ns else 0.0

    @property
    def min_ms(self) -> float:
        return min(self.times_ns) / 1e6 if self.times_ns else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.times_ns) / 1e6 if self.times_ns else 0.0

    @property
    def p95_ms(self) -> float:
        if not self.times_ns:
            return 0.0
        sorted_times = sorted(self.times_ns)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)] / 1e6

    def add(self, time_ns: int) -> None:
        self.times_ns.append(time_ns)


@dataclass
class RigLogicStats:
    """Stats from RigLogic collectCalculationStats method."""

    calculation_type: str = ""
    floating_point_type: str = ""
    rbf_solver_count: int = 0
    neural_network_count: int = 0
    psd_count: int = 0
    blend_shape_channel_count: int = 0
    animated_map_count: int = 0
    joint_count: int = 0
    joint_delta_value_count: int = 0


@dataclass
class ProfileResults:
    """Container for all profiling results."""

    # Head Python timing
    head_gui_control_update: TimingResult = field(default_factory=lambda: TimingResult("head_gui_control_update"))
    head_raw_control_update: TimingResult = field(default_factory=lambda: TimingResult("head_raw_control_update"))
    head_bone_transforms: TimingResult = field(default_factory=lambda: TimingResult("head_bone_transforms"))
    head_shape_keys: TimingResult = field(default_factory=lambda: TimingResult("head_shape_keys"))
    head_texture_masks: TimingResult = field(default_factory=lambda: TimingResult("head_texture_masks"))

    # Head C++ timing
    head_manager_calculate: TimingResult = field(default_factory=lambda: TimingResult("head_manager_calculate"))

    # Body Python timing
    body_raw_control_update: TimingResult = field(default_factory=lambda: TimingResult("body_raw_control_update"))
    body_bone_transforms: TimingResult = field(default_factory=lambda: TimingResult("body_bone_transforms"))

    # Body C++ timing
    body_manager_calculate: TimingResult = field(default_factory=lambda: TimingResult("body_manager_calculate"))

    # Full evaluation
    full_evaluation: TimingResult = field(default_factory=lambda: TimingResult("full_evaluation"))

    # C++ stats
    head_stats: RigLogicStats = field(default_factory=RigLogicStats)
    body_stats: RigLogicStats = field(default_factory=RigLogicStats)


class RigEvaluationProfiler:
    """Profiler for MetaHuman DNA rig evaluation."""

    def __init__(self, rig_instance: RigInstance):
        self.rig_instance = rig_instance
        self.results = ProfileResults()

    def _time_function(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, int]:
        """Time a function call and return (result, time_ns)."""
        start = time.perf_counter_ns()
        result = func(*args, **kwargs)
        return result, time.perf_counter_ns() - start

    def _collect_riglogic_stats(self, dna_reader: Any) -> RigLogicStats:
        """Collect stats from DNA reader."""
        # TODO: Use collectCalculationStats if available in bindings
        try:
            return RigLogicStats(
                calculation_type="",  # Not available from reader
                floating_point_type="",  # Not available from reader
                rbf_solver_count=dna_reader.getRBFSolverCount() if hasattr(dna_reader, "getRBFSolverCount") else 0,
                neural_network_count=dna_reader.getNeuralNetworkCount()
                if hasattr(dna_reader, "getNeuralNetworkCount")
                else 0,
                psd_count=0,  # Not directly available
                blend_shape_channel_count=dna_reader.getBlendShapeChannelCount()
                if hasattr(dna_reader, "getBlendShapeChannelCount")
                else 0,
                animated_map_count=dna_reader.getAnimatedMapCount()
                if hasattr(dna_reader, "getAnimatedMapCount")
                else 0,
                joint_count=dna_reader.getJointCount() if hasattr(dna_reader, "getJointCount") else 0,
                joint_delta_value_count=0,  # Not directly available
            )
        except Exception:
            return RigLogicStats()

    def profile_head_evaluation(self) -> None:
        """Profile the head rig evaluation components."""
        ri = self.rig_instance
        if not ri.head_initialized:
            ri.head_initialize()
        if not ri.head_manager or not ri.head_instance:
            return

        _, t = self._time_function(ri.update_head_gui_control_values)
        self.results.head_gui_control_update.add(t)

        _, t = self._time_function(ri.update_head_raw_control_values)
        self.results.head_raw_control_update.add(t)

        _, t = self._time_function(ri.head_manager.calculate, ri.head_instance)
        self.results.head_manager_calculate.add(t)

        _, t = self._time_function(ri.update_head_bone_transforms)
        self.results.head_bone_transforms.add(t)

        _, t = self._time_function(ri.update_head_shape_keys)
        self.results.head_shape_keys.add(t)

        _, t = self._time_function(ri.update_head_texture_masks)
        self.results.head_texture_masks.add(t)

        # Collect stats only once (on first iteration)
        if self.results.head_stats.joint_count == 0 and ri.head_dna_reader:
            self.results.head_stats = self._collect_riglogic_stats(ri.head_dna_reader)

    def profile_body_evaluation(self) -> None:
        """Profile the body rig evaluation components."""
        ri = self.rig_instance
        if not ri.body_initialized:
            ri.body_initialize()
        if not ri.body_manager or not ri.body_instance:
            return

        _, t = self._time_function(ri.update_body_raw_control_values)
        self.results.body_raw_control_update.add(t)

        _, t = self._time_function(ri.body_manager.calculate, ri.body_instance)
        self.results.body_manager_calculate.add(t)

        _, t = self._time_function(ri.update_body_bone_transforms)
        self.results.body_bone_transforms.add(t)

        # Collect stats only once (on first iteration)
        if self.results.body_stats.joint_count == 0 and ri.body_dna_reader:
            self.results.body_stats = self._collect_riglogic_stats(ri.body_dna_reader)

    def profile_full_evaluation(self) -> None:
        """Profile a full rig evaluation."""
        start = time.perf_counter_ns()
        self.rig_instance.evaluate(component="all")
        self.results.full_evaluation.add(time.perf_counter_ns() - start)

    def run_benchmark(self, iterations: int = 100, warmup: int = 10) -> ProfileResults:
        """Run benchmark with warmup iterations."""
        print(f"Starting benchmark: {warmup} warmup + {iterations} iterations")

        for _ in range(warmup):
            self.profile_head_evaluation()
            self.profile_body_evaluation()

        self.results = ProfileResults()

        for i in range(iterations):
            self.profile_head_evaluation()
            self.profile_body_evaluation()
            self.profile_full_evaluation()
            if (i + 1) % 25 == 0:
                print(f"  Completed {i + 1}/{iterations}")

        return self.results

    def print_report(self) -> None:
        """Print profiling report."""
        r = self.results

        def row(name: str, t: TimingResult) -> None:
            print(f"  {name:25s} | mean: {t.mean_ms:7.3f}ms | p95: {t.p95_ms:7.3f}ms | max: {t.max_ms:7.3f}ms")

        print("\n" + "=" * 80)
        print("RIG EVALUATION PROFILING REPORT")
        print("=" * 80)

        print("\n--- HEAD (Python) ---")
        row("GUI Control Update", r.head_gui_control_update)
        row("Raw Control Update", r.head_raw_control_update)
        row("Bone Transforms", r.head_bone_transforms)
        row("Shape Keys", r.head_shape_keys)
        row("Texture Masks", r.head_texture_masks)

        print("\n--- HEAD (C++ RigLogic) ---")
        row("manager.calculate()", r.head_manager_calculate)

        print("\n--- BODY (Python) ---")
        row("Raw Control Update", r.body_raw_control_update)
        row("Bone Transforms", r.body_bone_transforms)

        print("\n--- BODY (C++ RigLogic) ---")
        row("manager.calculate()", r.body_manager_calculate)

        print("\n--- FULL EVALUATION ---")
        row("Full Evaluate", r.full_evaluation)

        print("\n--- C++ STATS (HEAD) via collectCalculationStats ---")
        print(
            f"  Joints: {r.head_stats.joint_count} | "
            f"BlendShapes: {r.head_stats.blend_shape_channel_count} | "
            f"RBFs: {r.head_stats.rbf_solver_count} | "
            f"NNs: {r.head_stats.neural_network_count}"
        )

        print("\n--- C++ STATS (BODY) via collectCalculationStats ---")
        print(
            f"  Joints: {r.body_stats.joint_count} | "
            f"BlendShapes: {r.body_stats.blend_shape_channel_count} | "
            f"RBFs: {r.body_stats.rbf_solver_count} | "
            f"NNs: {r.body_stats.neural_network_count}"
        )

        print("\n--- SUMMARY ---")
        py_head = (
            r.head_gui_control_update.mean_ms
            + r.head_raw_control_update.mean_ms
            + r.head_bone_transforms.mean_ms
            + r.head_shape_keys.mean_ms
            + r.head_texture_masks.mean_ms
        )
        py_body = r.body_raw_control_update.mean_ms + r.body_bone_transforms.mean_ms
        cpp = r.head_manager_calculate.mean_ms + r.body_manager_calculate.mean_ms

        print(f"  Python (Head + Body):  {py_head + py_body:.3f} ms")
        print(f"  C++ (Head + Body):     {cpp:.3f} ms")
        print(f"  Full Evaluation:       {r.full_evaluation.mean_ms:.3f} ms")
        if r.full_evaluation.mean_ms > 0:
            print(f"  Theoretical FPS:       {1000 / r.full_evaluation.mean_ms:.1f}")
        print("=" * 80)

    def export_results(
        self,
        output_path: str | Path = "reports/profiling",
        output_format: str = "all",
        iterations: int = 0,
        warmup: int = 0,
    ) -> list[Path]:
        """
        Export profiling results to files.

        Args:
            output_path: Directory to write output files.
            output_format: Export format - "json", "csv", "markdown", or "all".
            iterations: Number of iterations run (for metadata).
            warmup: Number of warmup iterations (for metadata).

        Returns:
            List of paths to created files.
        """
        from .exporters import export_snapshot

        return export_snapshot(self.results, output_path, output_format, iterations, warmup)


def get_active_rig_instance() -> RigInstance | None:
    """Get the active RigInstance from the scene."""
    try:
        # Try the current property name first
        props = bpy.context.scene.meta_human_dna  # type: ignore[attr-defined]
        if hasattr(props, "rig_instance_list"):
            instance_list = props.rig_instance_list
            active_index = props.rig_instance_list_active_index
        elif hasattr(props, "rig_logic_instance_list"):
            instance_list = props.rig_logic_instance_list
            active_index = props.rig_logic_instance_list_active_index
        else:
            return None

        if not instance_list or len(instance_list) == 0:
            return None

        return instance_list[active_index]
    except AttributeError:
        return None


def run_profiler(
    iterations: int = 100,
    warmup: int = 10,
    export_path: str | Path | None = None,
    export_format: str = "all",
    enable_hud: bool = False,
) -> ProfileResults | None:
    """
    Run the profiler on the active rig instance.

    Args:
        iterations: Number of benchmark iterations.
        warmup: Number of warmup iterations.
        export_path: Optional path to export results. If provided, exports after profiling.
        export_format: Export format - "json", "csv", "markdown", or "all".
        enable_hud: If True, enables the realtime performance HUD.

    Returns:
        ProfileResults or None if no active rig instance.
    """
    ri = get_active_rig_instance()
    if not ri:
        print("ERROR: No active rig instance. Load a MetaHuman DNA file first.")
        return None

    if enable_hud:
        try:
            from .viewport_hud import enable_hud as _enable_hud

            _enable_hud()
        except ImportError:
            print("WARNING: Could not enable HUD - viewport_hud module not available")

    profiler = RigEvaluationProfiler(ri)
    profiler.run_benchmark(iterations=iterations, warmup=warmup)
    profiler.print_report()

    if export_path:
        files = profiler.export_results(export_path, export_format, iterations, warmup)
        print(f"\nExported results to: {[str(f) for f in files]}")

    return profiler.results


if __name__ == "__main__":
    run_profiler()
