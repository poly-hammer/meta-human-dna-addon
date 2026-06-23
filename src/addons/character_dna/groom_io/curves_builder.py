# standard library imports
import logging

# third party imports
import bpy
import numpy as np

# local imports
from ..constants import GROOM_DEFAULT_RADIUS, GROOM_GROUP_ID_ATTRIBUTE, GROOM_GUIDE_ATTRIBUTE
from .discovery import GroomSource
from .io import GroomGeometry


logger = logging.getLogger(__name__)

# Blender hair curves render as Catmull-Rom; this is the ``curve_type`` enum value.
_CURVE_TYPE_CATMULL_ROM = 0

_UNIT_TO_METERS = {"cm": 0.01, "mm": 0.001, "m": 1.0}


def unit_scale(space: dict) -> float:
    """Return the metres-per-source-unit scale for the manifest ``space`` block."""
    units = str(space.get("units", "cm")).lower()
    scale = _UNIT_TO_METERS.get(units)
    if scale is None:
        logger.warning("Unknown groom units '%s'; assuming centimeters.", units)
        return 0.01
    return scale


def source_to_blender_linear(space: dict) -> np.ndarray:
    """Build the 3x3 linear transform from the source space into Blender's space.

    Blender is metres, Z-up, right-handed. The default Unreal export space is
    centimetres, Z-up, left-handed, so the conversion is ``(x, y, z) ->
    (x, -y, z) * 0.01``. Negating Y is the inverse of the same Y/Z handling the
    DNA importer bakes into the head mesh (DNA Y-up cm -> Blender via a +90deg X
    rotation), so a groom exported in Unreal space lands in the imported head's
    space. The transform is fully driven by the manifest ``space`` block, so it
    can be re-tuned without code changes if a source uses other conventions.
    """
    up_axis = str(space.get("up_axis", "Z")).upper()
    handedness = str(space.get("handedness", "left")).lower()
    scale = unit_scale(space)

    if up_axis == "Y":
        # Y-up (Maya / Alembic) -> Blender Z-up: (x, y, z) -> (x, -z, y).
        axis = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]], dtype=np.float64)
        if handedness == "left":
            axis = axis @ np.diag([1.0, 1.0, -1.0])
    elif handedness == "left":
        # Unreal (Z-up, left-handed) -> Blender (Z-up, right-handed): negate Y.
        axis = np.diag([1.0, -1.0, 1.0])
    else:
        axis = np.eye(3, dtype=np.float64)

    return (scale * axis).astype(np.float32)


def _set_curve_attribute(curves: bpy.types.Curves, name: str, data_type: str, prop: str, values: np.ndarray) -> None:
    """Create (or reuse) a curve-domain attribute and bulk-fill it."""
    attribute = curves.attributes.get(name) or curves.attributes.new(name, data_type, "CURVE")
    attribute.data.foreach_set(prop, np.ascontiguousarray(values).reshape(-1))


def build_curves_object(
    source: GroomSource,
    geometry: GroomGeometry,
    *,
    collection: bpy.types.Collection | None = None,
    surface_object: bpy.types.Object | None = None,
    attach_to_surface: bool = True,
) -> bpy.types.Object:
    """Build a Blender hair ``Curves`` object from a groom's source geometry.

    Positions are converted from the source space into Blender's space and baked
    into the point data (the object keeps an identity transform, matching how the
    head mesh is imported). Widths become point ``radius`` (= width / 2), root
    UVs become ``surface_uv_coordinate``, and the group id / guide flag are
    authored as curve-domain attributes. All arrays are written in bulk via
    ``foreach_set`` so the 100k-curve main hair stays fast.
    """
    curves = bpy.data.hair_curves.new(source.name)
    curves.add_curves(geometry.curve_sizes.tolist())

    matrix = source_to_blender_linear(source.space)
    positions = np.ascontiguousarray(geometry.positions.astype(np.float32) @ matrix.T)
    curves.points.foreach_set("position", positions.reshape(-1))

    # Catmull-Rom curve type (explicit, even though it is the default), so the
    # curves interpolate the same way Unreal's strand CVs do.
    _set_curve_attribute(
        curves,
        "curve_type",
        "INT8",
        "value",
        np.full(geometry.curve_count, _CURVE_TYPE_CATMULL_ROM, dtype=np.int8),
    )

    if geometry.widths is not None:
        # Width is a diameter in source units; Blender radius is metres.
        radius = geometry.widths.astype(np.float32) * (unit_scale(source.space) * 0.5)
    else:
        # No width data shipped: use a small, visible default so the hair is not
        # zero-thickness (the source may simply not author widths).
        radius = np.full(geometry.point_count, GROOM_DEFAULT_RADIUS, dtype=np.float32)
    curves.points.foreach_set("radius", np.ascontiguousarray(radius))

    if geometry.root_uv is not None:
        _set_curve_attribute(curves, "surface_uv_coordinate", "FLOAT2", "vector", geometry.root_uv.astype(np.float32))

    group_id = geometry.group_id
    if group_id is None:
        group_id = np.full(geometry.curve_count, source.group_id, dtype=np.int32)
    _set_curve_attribute(curves, GROOM_GROUP_ID_ATTRIBUTE, "INT", "value", group_id.astype(np.int32))

    if geometry.guide is not None:
        _set_curve_attribute(curves, GROOM_GUIDE_ATTRIBUTE, "INT", "value", geometry.guide.astype(np.int32))

    curves_object = bpy.data.objects.new(source.name, curves)
    (collection or bpy.context.scene.collection).objects.link(curves_object)

    if attach_to_surface and surface_object is not None and surface_object.type == "MESH":
        curves.surface = surface_object
        active_uv = surface_object.data.uv_layers.active
        if active_uv:
            curves.surface_uv_map = active_uv.name

    logger.info(
        "Built groom '%s': %d curves, %d points%s.",
        source.name,
        geometry.curve_count,
        geometry.point_count,
        " (attached to surface)" if curves.surface else "",
    )
    return curves_object
