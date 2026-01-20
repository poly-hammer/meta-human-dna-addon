# standard library imports
import math

# third party imports
import bpy


# Constants
FUNCTION_TYPES = ["Gaussian", "Exponential", "Linear", "Cubic", "Quintic"]

# Cached preview image collections - keyed by size for dynamic resizing
_preview_collections: dict[str, bpy.utils.previews.ImagePreviewCollection] = {}


def get_function_curve_value(x: float, func_type: str) -> float:
    """Calculate the RBF function value at a given distance x.

    Args:
        x: The normalized distance (0 to 1).
        func_type: The function type name.

    Returns:
        The function value (0 to 1).
    """
    if func_type == "Gaussian":
        # Gaussian kernel: exp(-x^2) with scaling for visibility
        return math.exp(-x * x * 4)
    if func_type == "Exponential":
        # Exponential rise: 1 - exp(-x*k), starts at 0, quickly rises to 1
        return 1.0 - math.exp(-x * 10)
    if func_type == "Linear":
        # Linear kernel: max(0, 1 - x)
        return max(0.0, 1.0 - x)
    if func_type == "Cubic":
        # Cubic kernel: max(0, (1 - x)^3)
        return max(0.0, (1.0 - x) ** 3)
    if func_type == "Quintic":
        # Quintic kernel: max(0, (1 - x)^5)
        return max(0.0, (1.0 - x) ** 5)
    # Default to linear
    return max(0.0, 1.0 - x)


def _get_theme_colors() -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """Get colors from the current Blender theme.

    Returns:
        Tuple of (background_color, grid_color, curve_color) as RGBA tuples.
    """
    if not bpy.context.preferences:
        # Fallback colors if no context
        return (0.1, 0.1, 0.1, 1.0), (0.3, 0.3, 0.3, 1.0), (0.2, 0.6, 1.0, 1.0)

    theme = bpy.context.preferences.themes[0]

    # Background from node editor space
    node_bg = theme.node_editor.space.back
    bg_color = (node_bg[0], node_bg[1], node_bg[2], 1.0)

    # Grid from node editor
    node_grid = theme.node_editor.grid
    grid_color = (node_grid[0], node_grid[1], node_grid[2], 1.0)

    # Curve color - use active list item highlight color (blue)
    list_sel = theme.user_interface.wcol_list_item.inner_sel
    curve_color = (list_sel[0], list_sel[1], list_sel[2], 1.0)

    return bg_color, grid_color, curve_color


def _generate_curve_image(func_type: str, width: int = 256, height: int = 80) -> list[float]:
    """Generate pixel data for a curve image using Blender theme colors.

    Args:
        func_type: The function type name.
        width: Image width.
        height: Image height.

    Returns:
        Flat list of RGBA float values.
    """
    pixels: list[float] = []

    # Get colors from Blender theme
    bg_color, grid_color, curve_color = _get_theme_colors()

    # Padding from edges
    padding = 4
    graph_width = width - (padding * 2)
    graph_height = height - (padding * 2)

    for y in range(height):
        for x in range(width):
            # Check if in padding area
            in_graph = padding <= x < width - padding and padding <= y < height - padding

            if not in_graph:
                # Border/padding area - slightly lighter than background
                pixels.extend([bg_color[0] * 0.8, bg_color[1] * 0.8, bg_color[2] * 0.8, 1.0])
                continue

            # Normalized coordinates within graph area (0 to 1)
            # x goes from left (0) to right (1)
            nx = (x - padding) / (graph_width - 1) if graph_width > 1 else 0

            # Get curve value at this x position
            # For Exponential, use nx directly (formula already goes 0->1)
            # For others, mirror so they increase from left to right
            if func_type == "Exponential":
                curve_y = get_function_curve_value(nx, func_type)
            else:
                curve_y = get_function_curve_value(1.0 - nx, func_type)

            # Map curve_y (0-1) to pixel y coordinate
            # y=0 is bottom of image, y=height-1 is top
            curve_pixel_y = padding + curve_y * (graph_height - 1)
            distance = abs(y - curve_pixel_y)

            # Draw curve with anti-aliasing
            if distance < 2.0:
                # On or near the curve - blend based on distance
                alpha = max(0, 1.0 - distance / 2.0)
                r = bg_color[0] * (1 - alpha) + curve_color[0] * alpha
                g = bg_color[1] * (1 - alpha) + curve_color[1] * alpha
                b = bg_color[2] * (1 - alpha) + curve_color[2] * alpha
                pixels.extend([r, g, b, 1.0])
            else:
                # Check for grid lines
                graph_x = x - padding
                graph_y = y - padding

                # Draw grid lines at 25%, 50%, 75%
                is_grid_x = graph_x % (graph_width // 4) < 1 if graph_width >= 4 else False
                is_grid_y = graph_y % (graph_height // 4) < 1 if graph_height >= 4 else False

                if is_grid_x or is_grid_y:
                    # Grid line
                    pixels.extend([grid_color[0], grid_color[1], grid_color[2], 1.0])
                else:
                    # Background
                    pixels.extend(bg_color)

    return pixels


def get_function_preview_icon(func_type: str, width: int = 256, height: int = 80) -> int:
    """Get or create a preview icon for a function type at a specific size.

    Args:
        func_type: The function type name.
        width: Desired width of the preview.
        height: Desired height of the preview.

    Returns:
        The icon ID for use with template_icon.
    """
    # Create a size key for caching
    size_key = f"{width}x{height}"

    if size_key not in _preview_collections:
        _preview_collections[size_key] = bpy.utils.previews.new()

    collection = _preview_collections[size_key]

    # Check if already generated for this size
    if func_type in collection:
        return collection[func_type].icon_id

    # Generate the curve image
    pixels = _generate_curve_image(func_type, width, height)

    # Create a new preview image
    preview = collection.new(func_type)
    preview.image_size = (width, height)
    preview.image_pixels_float = pixels  # type: ignore[assignment]

    return preview.icon_id


def invalidate_previews() -> None:
    """Invalidate all cached previews to force regeneration.

    Call this when the theme changes or when a refresh is needed.
    """
    for collection in _preview_collections.values():
        bpy.utils.previews.remove(collection)
    _preview_collections.clear()


def ensure_function_curves_exist() -> None:
    """Ensure the function curve previews are generated.

    Call this during addon registration or when the pose editor is opened.
    """
    # Pre-generate default size previews
    for func_type in FUNCTION_TYPES:
        get_function_preview_icon(func_type)


def cleanup_function_curves() -> None:
    """Remove the function curve previews.

    Call this during addon un0registration.
    """
    for collection in _preview_collections.values():
        bpy.utils.previews.remove(collection)
    _preview_collections.clear()
