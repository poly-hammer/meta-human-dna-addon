"""
Realtime Performance HUD for Blender 3D Viewport.

This module provides a heads-up display (HUD) overlay in the Blender 3D viewport
that shows realtime performance metrics for MetaHuman DNA rig evaluation.

Features:
- Live FPS and frame time display
- Evaluation count per second
- Rolling average timing for head/body/C++ evaluation
- Dependency graph update frequency
- Toggle via operator or Python API

Usage:
    from profiling_utils.viewport_hud import enable_hud, disable_hud

    enable_hud()  # Show the HUD
    disable_hud()  # Hide the HUD

Blender Operator:
    bpy.ops.profiling.toggle_performance_hud()
"""

from __future__ import annotations

import time

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import blf
import bpy
import gpu

from gpu_extras.batch import batch_for_shader


# -----------------------------------------------------------------------------
# Data Structures
# -----------------------------------------------------------------------------


@dataclass
class RollingMetric:
    """A metric that maintains a rolling window of samples."""

    name: str
    samples: deque[float] = field(default_factory=lambda: deque(maxlen=60))
    unit: str = "ms"

    def add(self, value: float) -> None:
        """Add a sample to the rolling window."""
        self.samples.append(value)

    @property
    def current(self) -> float:
        """Get the most recent sample."""
        return self.samples[-1] if self.samples else 0.0

    @property
    def average(self) -> float:
        """Get the average of all samples in the window."""
        return sum(self.samples) / len(self.samples) if self.samples else 0.0

    @property
    def max(self) -> float:
        """Get the maximum value in the window."""
        return max(self.samples) if self.samples else 0.0

    def clear(self) -> None:
        """Clear all samples."""
        self.samples.clear()


@dataclass
class HUDState:
    """Mutable state for the HUD display."""

    # Frame timing
    last_frame_time_ns: int = 0
    frame_times: deque[float] = field(default_factory=lambda: deque(maxlen=60))

    # Evaluation tracking
    evaluations_this_second: int = 0
    evaluations_per_second: int = 0
    last_second_time: float = 0.0

    # Timing metrics
    head_python_ms: RollingMetric = field(default_factory=lambda: RollingMetric("Head Python"))
    head_cpp_ms: RollingMetric = field(default_factory=lambda: RollingMetric("Head C++"))
    body_python_ms: RollingMetric = field(default_factory=lambda: RollingMetric("Body Python"))
    body_cpp_ms: RollingMetric = field(default_factory=lambda: RollingMetric("Body C++"))
    full_eval_ms: RollingMetric = field(default_factory=lambda: RollingMetric("Full Eval"))

    # Depsgraph tracking
    depsgraph_updates_per_second: float = 0.0


# Global state
_hud_draw_handler: Any = None
_hud_state: HUDState | None = None
_hud_enabled: bool = False


# -----------------------------------------------------------------------------
# Drawing Functions
# -----------------------------------------------------------------------------


def draw_text(
    text: str,
    x: float,
    y: float,
    font_id: int = 0,
    size: float = 14.0,
    color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
    shadow: bool = True,
) -> None:
    """Draw text at the specified screen position."""
    blf.size(font_id, size)

    if shadow:
        blf.color(font_id, 0.0, 0.0, 0.0, 0.7)
        blf.position(font_id, x + 1, y - 1, 0)
        blf.draw(font_id, text)

    blf.color(font_id, *color)
    blf.position(font_id, x, y, 0)
    blf.draw(font_id, text)


def draw_background(x: float, y: float, width: float, height: float, alpha: float = 0.75) -> None:
    """Draw a semi-transparent background rectangle."""
    vertices = (
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x, y + height),
    )
    indices = ((0, 1, 2), (2, 3, 0))

    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(shader, "TRIS", {"pos": vertices}, indices=indices)

    gpu.state.blend_set("ALPHA")
    shader.bind()
    shader.uniform_float("color", (0.1, 0.1, 0.1, alpha))
    batch.draw(shader)
    gpu.state.blend_set("NONE")


def get_fps_color(fps: float) -> tuple[float, float, float, float]:
    """Get color based on FPS (green = good, yellow = ok, red = bad)."""
    if fps >= 60:
        return (0.2, 1.0, 0.2, 1.0)  # Green
    if fps >= 30:
        return (1.0, 1.0, 0.2, 1.0)  # Yellow
    if fps >= 15:
        return (1.0, 0.6, 0.2, 1.0)  # Orange
    return (1.0, 0.2, 0.2, 1.0)  # Red


def draw_metric_bar(
    x: float,
    y: float,
    width: float,
    height: float,
    value: float,
    max_value: float,
    color: tuple[float, float, float, float],
) -> None:
    """Draw a horizontal bar representing a metric value."""
    # Background bar
    bg_vertices = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
    bg_indices = ((0, 1, 2), (2, 3, 0))

    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(shader, "TRIS", {"pos": bg_vertices}, indices=bg_indices)

    gpu.state.blend_set("ALPHA")
    shader.bind()
    shader.uniform_float("color", (0.2, 0.2, 0.2, 0.5))
    batch.draw(shader)

    # Value bar
    fill_width = min(width * (value / max_value), width) if max_value > 0 else 0
    if fill_width > 0:
        fill_vertices = ((x, y), (x + fill_width, y), (x + fill_width, y + height), (x, y + height))
        batch = batch_for_shader(shader, "TRIS", {"pos": fill_vertices}, indices=bg_indices)
        shader.uniform_float("color", color)
        batch.draw(shader)

    gpu.state.blend_set("NONE")


def draw_performance_hud() -> None:
    """Main draw callback for the performance HUD."""
    if not _hud_enabled or _hud_state is None:
        return

    # Update frame timing
    now_ns = time.perf_counter_ns()
    if _hud_state.last_frame_time_ns > 0:
        frame_time_ms = (now_ns - _hud_state.last_frame_time_ns) / 1e6
        _hud_state.frame_times.append(frame_time_ms)
    _hud_state.last_frame_time_ns = now_ns

    # Update evaluations per second counter
    now = time.time()
    if now - _hud_state.last_second_time >= 1.0:
        _hud_state.evaluations_per_second = _hud_state.evaluations_this_second
        _hud_state.evaluations_this_second = 0
        _hud_state.last_second_time = now

    # Get viewport region
    region = bpy.context.region
    if region is None:
        return

    # Calculate layout
    padding = 10
    line_height = 18
    bar_height = 6
    panel_width = 200
    panel_x = region.width - panel_width - padding
    panel_y = region.height - padding

    # Calculate panel height based on content
    num_lines = 11  # Title + FPS + Evals + blank + metrics
    panel_height = (num_lines * line_height) + (padding * 2)

    # Draw background
    draw_background(
        panel_x - padding,
        panel_y - panel_height,
        panel_width + (padding * 2),
        panel_height,
    )

    # Draw content
    font_id = 0
    x = panel_x
    y = panel_y - line_height

    # Title
    draw_text("PERFORMANCE HUD", x, y, font_id, 12.0, (0.7, 0.7, 0.7, 1.0))
    y -= line_height

    # FPS
    if _hud_state.frame_times:
        avg_frame_time = sum(_hud_state.frame_times) / len(_hud_state.frame_times)
        fps = 1000.0 / avg_frame_time if avg_frame_time > 0 else 0.0
    else:
        fps = 0.0
        avg_frame_time = 0.0

    fps_color = get_fps_color(fps)
    draw_text(f"FPS: {fps:.1f}  ({avg_frame_time:.1f}ms)", x, y, font_id, 14.0, fps_color)
    y -= line_height

    # Evaluations per second
    draw_text(f"Evals/sec: {_hud_state.evaluations_per_second}", x, y, font_id, 13.0, (0.9, 0.9, 0.9, 1.0))
    y -= line_height

    # Separator
    y -= 5

    # Metrics with bars
    max_time_ms = 20.0  # Scale bars to 20ms max (50 FPS budget)

    metrics = [
        ("Head Python", _hud_state.head_python_ms, (0.4, 0.7, 1.0, 1.0)),
        ("Head C++", _hud_state.head_cpp_ms, (0.3, 0.5, 0.8, 1.0)),
        ("Body Python", _hud_state.body_python_ms, (0.7, 0.4, 1.0, 1.0)),
        ("Body C++", _hud_state.body_cpp_ms, (0.5, 0.3, 0.8, 1.0)),
        ("Full Eval", _hud_state.full_eval_ms, (1.0, 0.8, 0.3, 1.0)),
    ]

    for label, metric, color in metrics:
        avg = metric.average
        draw_text(f"{label}: {avg:.2f}ms", x, y, font_id, 12.0, (0.85, 0.85, 0.85, 1.0))
        y -= bar_height + 2
        draw_metric_bar(x, y, panel_width - 10, bar_height, avg, max_time_ms, color)
        y -= line_height - bar_height

    # Depsgraph updates
    y -= 5
    draw_text(
        f"Depsgraph: {_hud_state.depsgraph_updates_per_second:.1f}/sec",
        x,
        y,
        font_id,
        11.0,
        (0.6, 0.6, 0.6, 1.0),
    )


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------


def enable_hud() -> None:
    """Enable the performance HUD overlay."""
    global _hud_draw_handler, _hud_state, _hud_enabled

    if _hud_enabled:
        return

    _hud_state = HUDState()
    _hud_enabled = True

    if _hud_draw_handler is None:
        _hud_draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            draw_performance_hud,
            (),
            "WINDOW",
            "POST_PIXEL",
        )

    print("[PerformanceHUD] Enabled")


def disable_hud() -> None:
    """Disable the performance HUD overlay."""
    global _hud_draw_handler, _hud_state, _hud_enabled

    if not _hud_enabled:
        return

    _hud_enabled = False

    if _hud_draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_hud_draw_handler, "WINDOW")
        _hud_draw_handler = None

    _hud_state = None
    print("[PerformanceHUD] Disabled")


def toggle_hud() -> bool:
    """Toggle the HUD on/off. Returns new state."""
    if _hud_enabled:
        disable_hud()
        return False
    enable_hud()
    return True


def is_hud_enabled() -> bool:
    """Check if the HUD is currently enabled."""
    return _hud_enabled


def record_timing(
    head_python_ms: float = 0.0,
    head_cpp_ms: float = 0.0,
    body_python_ms: float = 0.0,
    body_cpp_ms: float = 0.0,
    full_eval_ms: float = 0.0,
) -> None:
    """
    Record timing values for display in the HUD.

    This should be called from the rig evaluation code to update the HUD.

    Args:
        head_python_ms: Time for head Python operations.
        head_cpp_ms: Time for head C++ RigLogic.calculate().
        body_python_ms: Time for body Python operations.
        body_cpp_ms: Time for body C++ RigLogic.calculate().
        full_eval_ms: Time for full evaluation cycle.
    """
    if _hud_state is None:
        return

    if head_python_ms > 0:
        _hud_state.head_python_ms.add(head_python_ms)
    if head_cpp_ms > 0:
        _hud_state.head_cpp_ms.add(head_cpp_ms)
    if body_python_ms > 0:
        _hud_state.body_python_ms.add(body_python_ms)
    if body_cpp_ms > 0:
        _hud_state.body_cpp_ms.add(body_cpp_ms)
    if full_eval_ms > 0:
        _hud_state.full_eval_ms.add(full_eval_ms)

    _hud_state.evaluations_this_second += 1


def update_depsgraph_stats(updates_per_second: float) -> None:
    """Update the depsgraph update frequency display."""
    if _hud_state is not None:
        _hud_state.depsgraph_updates_per_second = updates_per_second


# -----------------------------------------------------------------------------
# Blender Operator
# -----------------------------------------------------------------------------


class PROFILING_OT_toggle_performance_hud(bpy.types.Operator):
    """Toggle the performance HUD overlay in the 3D viewport"""

    bl_idname = "profiling.toggle_performance_hud"
    bl_label = "Toggle Performance HUD"
    bl_description = "Toggle the realtime performance HUD overlay"
    bl_options = {"REGISTER"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        enabled = toggle_hud()
        state = "enabled" if enabled else "disabled"
        self.report({"INFO"}, f"Performance HUD {state}")

        # Force redraw
        for area in context.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()

        return {"FINISHED"}


# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------


_classes = (PROFILING_OT_toggle_performance_hud,)


def register() -> None:
    """Register the HUD module with Blender."""
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister() -> None:
    """Unregister the HUD module from Blender."""
    disable_hud()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
