# third party imports
import blf
import bpy
import gpu

from gpu_extras.batch import batch_for_shader

# local imports
from ...typing import *  # noqa: F403
from ...ui.toast import get_toast_manager
from ...utilities import get_active_rig_instance, get_addon_preferences
from .change_tracker import get_change_tracker


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
    Also draws toast notifications regardless of edit mode state.
    """
    # Get the current 3D viewport region first - needed for toasts
    region = bpy.context.region
    if region is None:
        return

    # Always draw toasts, regardless of pose editor state
    _draw_toasts()

    if not bpy.context.preferences:
        return

    addon_preferences = get_addon_preferences()
    if not addon_preferences:
        return

    # Check if overlay is enabled in preferences
    if not addon_preferences.pose_editor_show_viewport_overlay:
        return

    instance = get_active_rig_instance()
    if instance is None:
        return

    if not instance.editing_rbf_solver:
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
    small_size = 12.0
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
    blf.size(font_id, small_size)
    _, small_height = blf.dimensions(font_id, "X")

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

    # Draw title (top-most of main info)
    draw_text_2d(
        text=title_text,
        x=left_margin,
        y=current_y,
        size=title_size,
        color=(1.0, 0.6, 0.2, 1.0),  # Orange
        shadow=True,
        shadow_offset=(1, -1),
    )
    current_y += info_height + line_spacing * 2

    # Draw change summary if there are changes
    tracker = get_change_tracker(instance)
    if tracker and tracker.has_changes:
        # Draw separator line
        current_y += 5

        # Draw changes header
        change_count = tracker.change_count
        changes_header = f"Pending Changes ({change_count}):"
        draw_text_2d(
            text=changes_header,
            x=left_margin,
            y=current_y,
            size=info_size,
            color=(0.9, 0.75, 0.3, 1.0),  # Gold/amber
            shadow=True,
            shadow_offset=(1, -1),
        )
        current_y += info_height + line_spacing

        # Draw change summary lines
        summary_lines = tracker.get_summary_lines(max_lines=4)
        for line in summary_lines:
            draw_text_2d(
                text=f"  • {line}",
                x=left_margin,
                y=current_y,
                size=small_size,
                color=(0.75, 0.75, 0.75, 0.9),
                shadow=True,
                shadow_offset=(1, -1),
            )
            current_y += small_height + 2


def _draw_toasts() -> None:
    """
    Draw toast notifications at the top-center of the viewport.

    Toasts stack downward from the top.
    """
    toast_manager = get_toast_manager()
    toasts = toast_manager.get_visible_toasts()

    if not toasts:
        return

    # Get viewport region for centering
    region = bpy.context.region
    if region is None:
        return

    font_id = 0
    toast_size = 14.0
    toast_padding = 10
    toast_spacing = 5
    top_margin = 50

    # Start from top and stack downward
    current_y = region.height - top_margin

    for toast in toasts:  # Oldest at top, newest below
        blf.size(font_id, toast_size)
        text_width, text_height = blf.dimensions(font_id, toast.message)

        # Calculate background dimensions
        bg_width = text_width + toast_padding * 2
        bg_height = text_height + toast_padding * 2

        # Center horizontally
        bg_x = (region.width - bg_width) / 2
        bg_y = current_y - bg_height

        # Get color with opacity from toast
        r, g, b, a = toast.color

        # Draw background with toast color
        bg_color = (r * 0.15, g * 0.15, b * 0.15, 0.9 * a)
        draw_rounded_rect(bg_x, bg_y, bg_width, bg_height, bg_color)

        # Draw text
        draw_text_2d(
            text=toast.message,
            x=bg_x + toast_padding,
            y=bg_y + toast_padding,
            size=toast_size,
            color=(r, g, b, a),
            shadow=True,
            shadow_color=(0.0, 0.0, 0.0, 0.6 * a),
            shadow_offset=(1, -1),
        )

        current_y -= bg_height + toast_spacing


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
