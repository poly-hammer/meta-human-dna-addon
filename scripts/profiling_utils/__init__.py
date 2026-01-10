"""
Profiling utilities for MetaHuman DNA Addon.

This package provides comprehensive profiling tools for:
- Rig evaluation benchmarking with detailed timing breakdowns
- Realtime HUD overlay for viewport performance monitoring
- CI-compatible snapshot exports for regression detection
- Dependency graph update tracking

Modules:
    profile_rig_evaluation: Main profiler for rig evaluation timing
    viewport_hud: Realtime performance HUD overlay in the 3D viewport
    exporters: Export profiling results to JSON/CSV for CI
    depsgraph_tracker: Track dependency graph update frequency

Usage:
    # Run benchmarks from Blender
    from scripts.profiling_utils import run_profiler
    results = run_profiler(iterations=100, warmup=10)

    # Export results for CI
    from scripts.profiling_utils import run_profiler
    results = run_profiler(iterations=100, export_path="reports/profiling")

    # Enable realtime HUD
    from scripts.profiling_utils import hud
    hud.enable()

    # Track depsgraph updates
    from scripts.profiling_utils import depsgraph
    depsgraph.start_tracking()
    # ... work in Blender ...
    stats = depsgraph.get_stats()
"""

from __future__ import annotations

# Submodule aliases for convenient access
from . import depsgraph_tracker as depsgraph, exporters, viewport_hud as hud
from .depsgraph_tracker import (
    DepsgraphStats,
    DepsgraphTracker,
    get_stats as get_depsgraph_stats,
    start_tracking,
    stop_tracking,
)
from .exporters import (
    HardwareInfo,
    compare_snapshots,
    export_csv,
    export_json,
    export_markdown,
    export_snapshot,
    get_hardware_info,
)
from .profile_rig_evaluation import (
    ProfileResults,
    RigEvaluationProfiler,
    RigLogicStats,
    TimingResult,
    get_active_rig_instance,
    run_profiler,
)


__all__ = [
    "DepsgraphStats",
    "DepsgraphTracker",
    "HardwareInfo",
    "ProfileResults",
    "RigEvaluationProfiler",
    "RigLogicStats",
    "TimingResult",
    "compare_snapshots",
    "depsgraph",
    "export_csv",
    "export_json",
    "export_markdown",
    "export_snapshot",
    "exporters",
    "get_active_rig_instance",
    "get_depsgraph_stats",
    "get_hardware_info",
    "hud",
    "run_profiler",
    "start_tracking",
    "stop_tracking",
]
