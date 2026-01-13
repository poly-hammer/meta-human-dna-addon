# third party imports
import blf
import bpy
import gpu

from gpu_extras.batch import batch_for_shader

# local imports
from ..typing import *  # noqa: F403
from ..utilities import get_active_rig_instance, get_addon_preferences


# Global storage for draw handler
_meta_human_dna_pose_editor_draw_handler = None


def draw_text_2d(
    text: str,
    x: float,
    y: float,
    font_id: int = 0,
    size: float = 16.0,
    color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
    shadow: bool = True,
    shadow_color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.8),
    shadow_offset: tuple[int, int] = (2, -2),
) -> None:
    """
    Draw 2D text at the specified screen position.

    Args:
        text: The text string to draw.
        x: X coordinate in screen pixels.
        y: Y coordinate in screen pixels.
        font_id: The font ID to use (0 is default).
        size: Font size in pixels.
        color: RGBA color tuple for the text.
        shadow: Whether to draw a shadow behind the text.
        shadow_color: RGBA color tuple for the shadow.
        shadow_offset: X, Y offset for the shadow in pixels.
    """
    blf.size(font_id, size)

    # Draw shadow first if enabled
    if shadow:
        blf.color(font_id, *shadow_color)
        blf.position(font_id, x + shadow_offset[0], y + shadow_offset[1], 0)
        blf.draw(font_id, text)

    # Draw main text
    blf.color(font_id, *color)
    blf.position(font_id, x, y, 0)
    blf.draw(font_id, text)


def draw_rounded_rect(
    x: float, y: float, width: float, height: float, color: tuple[float, float, float, float] = (0.2, 0.2, 0.2, 0.8)
) -> None:
    """
    Draw a filled rectangle at the specified screen position.

    Args:
        x: X coordinate of bottom-left corner in screen pixels.
        y: Y coordinate of bottom-left corner in screen pixels.
        width: Width of the rectangle in pixels.
        height: Height of the rectangle in pixels.
        color: RGBA color tuple for the rectangle.
    """
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
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.blend_set("NONE")


def draw_pose_editor_overlay() -> None:
    """
    Draw the Pose Editor overlay when in edit mode.

    This function is called by the draw handler and renders an overlay
    in the 3D viewport indicating that the Pose Editor is in edit mode.
    Positioned in the lower left corner of the viewport.
    """
    if not bpy.context.preferences:
        return

    addon_preferences = get_addon_preferences()
    if not addon_preferences:
        return

    # Check if overlay is enabled in preferences
    if not addon_preferences.show_pose_editor_viewport_overlay:
        return

    instance = get_active_rig_instance()
    if instance is None:
        return

    if not instance.editing_rbf_solver:
        return

    # Get the current 3D viewport region
    region = bpy.context.region
    if region is None:
        return

    # Get active solver info
    solver_name = ""
    pose_name = ""

    if len(instance.rbf_solver_list) > 0:
        active_solver_index = instance.rbf_solver_list_active_index
        if active_solver_index < len(instance.rbf_solver_list):
            solver = instance.rbf_solver_list[active_solver_index]
            solver_name = solver.name

            if len(solver.poses) > 0:
                active_pose_index = solver.poses_active_index
                if active_pose_index < len(solver.poses):
                    pose_name = solver.poses[active_pose_index].name

    # Compact text settings
    font_id = 0
    title_size = 16.0
    info_size = 14.0
    line_spacing = 3

    # Build the overlay text lines
    title_text = "POSE EDITOR - EDIT MODE"
    solver_text = f"Solver: {solver_name}" if solver_name else "Solver: (none)"
    pose_text = f"Pose: {pose_name}" if pose_name else "Pose: (none)"
    hint_text = "'Commit' to save | 'Revert' to cancel"

    # Position in lower left corner of viewport
    left_margin = 22
    bottom_margin = 65  # Above the status bar area

    # Calculate text heights for positioning
    blf.size(font_id, title_size)
    _, _title_height = blf.dimensions(font_id, title_text)
    blf.size(font_id, info_size)
    _, info_height = blf.dimensions(font_id, solver_text)

    # Start from bottom and work up
    current_y = bottom_margin

    # Draw hint text (bottom-most)
    draw_text_2d(
        text=hint_text,
        x=left_margin,
        y=current_y,
        size=info_size,
        color=(0.6, 0.6, 0.6, 1.0),  # Dimmer
        shadow=True,
        shadow_offset=(1, -1),
    )
    current_y += info_height + line_spacing

    # Draw pose name
    draw_text_2d(
        text=pose_text,
        x=left_margin,
        y=current_y,
        size=info_size,
        color=(0.85, 0.85, 0.85, 1.0),
        shadow=True,
        shadow_offset=(1, -1),
    )
    current_y += info_height + line_spacing

    # Draw solver name
    draw_text_2d(
        text=solver_text,
        x=left_margin,
        y=current_y,
        size=info_size,
        color=(0.85, 0.85, 0.85, 1.0),
        shadow=True,
        shadow_offset=(1, -1),
    )
    current_y += info_height + line_spacing

    # Draw title (top-most)
    draw_text_2d(
        text=title_text,
        x=left_margin,
        y=current_y,
        size=title_size,
        color=(1.0, 0.6, 0.2, 1.0),  # Orange
        shadow=True,
        shadow_offset=(1, -1),
    )


def register_draw_handler() -> None:
    """
    Register the draw handler for the Pose Editor overlay.

    This should be called during addon registration to enable the overlay
    drawing in the 3D viewport.
    """
    global _meta_human_dna_pose_editor_draw_handler

    if _meta_human_dna_pose_editor_draw_handler is not None:
        return  # Already registered

    _meta_human_dna_pose_editor_draw_handler = bpy.types.SpaceView3D.draw_handler_add(
        draw_pose_editor_overlay, (), "WINDOW", "POST_PIXEL"
    )


def unregister_draw_handler() -> None:
    """
    Unregister the draw handler for the Pose Editor overlay.

    This should be called during addon un-registration to clean up
    the draw handler.
    """
    global _meta_human_dna_pose_editor_draw_handler

    if _meta_human_dna_pose_editor_draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_meta_human_dna_pose_editor_draw_handler, "WINDOW")
        _meta_human_dna_pose_editor_draw_handler = None


def register() -> None:
    """Register the overlay module."""
    register_draw_handler()


def unregister() -> None:
    """Unregister the overlay module."""
    unregister_draw_handler()
