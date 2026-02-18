# standard library imports

# third party imports
import bpy

# local imports
from ...typing import *  # noqa: F403
from . import core
from .function_curves import ensure_function_curves_exist


class RBFDrivenBoneSelectionItem(bpy.types.PropertyGroup):
    """Property group for bone selection in the AddRBFPose operator dialog."""

    name: bpy.props.StringProperty()  # pyright: ignore[reportInvalidTypeForm]
    selected: bpy.props.BoolProperty(default=False)  # pyright: ignore[reportInvalidTypeForm]
    joint_index: bpy.props.IntProperty(default=-1)  # pyright: ignore[reportInvalidTypeForm]
    is_in_existing_joint_group: bpy.props.BoolProperty(
        default=False, description="Whether this bone is already in the solver's joint group"
    )  # pyright: ignore[reportInvalidTypeForm]


class RBFDriverData(bpy.types.PropertyGroup):
    solver_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]
    pose_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]
    joint_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]
    name: bpy.props.StringProperty()  # pyright: ignore[reportInvalidTypeForm]
    rotation_mode: bpy.props.EnumProperty(
        items=[
            ("QUATERNION", "Quaternion", "Use the Quaternion rotation mode"),
            ("XYZ", "Euler XYZ", "Use the Euler XYZ rotation mode"),
        ],
        default="QUATERNION",
        description="The rotation mode of the pose transformation",
    )  # pyright: ignore[reportInvalidTypeForm]
    euler_rotation: bpy.props.FloatVectorProperty(default=(0.0, 0.0, 0.0), size=3)  # pyright: ignore[reportInvalidTypeForm]
    quaternion_rotation: bpy.props.FloatVectorProperty(default=(1.0, 0.0, 0.0, 0.0), size=4)  # pyright: ignore[reportInvalidTypeForm]


class RBFDrivenData(bpy.types.PropertyGroup):
    pose_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]
    joint_group_index: bpy.props.IntProperty(default=-1)  # pyright: ignore[reportInvalidTypeForm]
    joint_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]
    name: bpy.props.StringProperty()  # pyright: ignore[reportInvalidTypeForm]
    data_type: bpy.props.EnumProperty(
        items=[
            ("BONE", "Bone Transforms", "Drives the Bone Transforms"),
            ("SHAPE_KEY", "Shape Key Value", "Drives the Shape Key Value"),
            ("MASK", "Mask Value", "Drives the Mask Value"),
        ],
        default="BONE",
        description="The type of driven data",
    )  # pyright: ignore[reportInvalidTypeForm]
    rotation_mode: bpy.props.EnumProperty(
        items=[
            ("QUATERNION", "Quaternion", "Use the Quaternion rotation mode"),
            ("XYZ", "Euler XYZ", "Use the Euler XYZ rotation mode"),
        ],
        default="QUATERNION",
        description="The rotation mode of the pose transformation",
    )  # pyright: ignore[reportInvalidTypeForm]
    location: bpy.props.FloatVectorProperty(default=(0.0, 0.0, 0.0), size=3)  # pyright: ignore[reportInvalidTypeForm]
    euler_rotation: bpy.props.FloatVectorProperty(default=(0.0, 0.0, 0.0), size=3)  # pyright: ignore[reportInvalidTypeForm]
    quaternion_rotation: bpy.props.FloatVectorProperty(default=(1.0, 0.0, 0.0, 0.0), size=4)  # pyright: ignore[reportInvalidTypeForm]
    scale: bpy.props.FloatVectorProperty(default=(0.0, 0.0, 0.0), size=3)  # pyright: ignore[reportInvalidTypeForm]
    scalar_value: bpy.props.FloatProperty(default=0.0, min=0.0, max=1.0)  # pyright: ignore[reportInvalidTypeForm]

    # internal use only
    location_edited: bpy.props.BoolProperty(default=False)  # pyright: ignore[reportInvalidTypeForm]
    rotation_edited: bpy.props.BoolProperty(default=False)  # pyright: ignore[reportInvalidTypeForm]
    scale_edited: bpy.props.BoolProperty(default=False)  # pyright: ignore[reportInvalidTypeForm]


class RBFPoseData(bpy.types.PropertyGroup):
    solver_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]
    pose_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]
    joint_group_index: bpy.props.IntProperty(default=-1)  # pyright: ignore[reportInvalidTypeForm]
    name: bpy.props.StringProperty(
        default="",
        description="The name of the pose",
        set=core.set_body_rbf_pose_name,
        get=core.get_body_rbf_pose_name,
    )  # pyright: ignore[reportInvalidTypeForm]
    scale_factor: bpy.props.FloatProperty(default=1.0, description="The scale factor of the pose", min=0.0)  # pyright: ignore[reportInvalidTypeForm]
    target_enable: bpy.props.BoolProperty(
        default=True,
        description="Whether the target is enabled",
    )  # pyright: ignore[reportInvalidTypeForm]

    driven: bpy.props.CollectionProperty(type=RBFDrivenData)  # pyright: ignore[reportInvalidTypeForm]
    driven_active_index: bpy.props.IntProperty(update=core.update_body_rbf_driven_active_index)  # pyright: ignore[reportArgumentType, reportInvalidTypeForm]

    drivers: bpy.props.CollectionProperty(type=RBFDriverData)  # pyright: ignore[reportInvalidTypeForm]
    drivers_active_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]


class RBFSolverData(bpy.types.PropertyGroup):
    solver_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]
    name: bpy.props.StringProperty(
        default="",
        description="The name of the RBF solver",
    )  # pyright: ignore[reportInvalidTypeForm]
    mode: bpy.props.EnumProperty(
        items=[
            ("Additive", "Additive", "Use the additive RBF solver mode"),
            ("Interpolative", "Interpolative", "Use the interpolative RBF solver mode"),
        ],
        default="Interpolative",
        description="The mode of the RBF solver",
    )  # pyright: ignore[reportInvalidTypeForm]
    radius: bpy.props.FloatProperty(
        default=50.0,
        description=(
            "The radius shows how close the driver transforms must be to the target pose in order for the "
            "pose to be active."
        ),
        min=0.0,
    )  # pyright: ignore[reportInvalidTypeForm]
    weight_threshold: bpy.props.FloatProperty(
        name="Weight Threshold",
        default=0.001,
        description="The minimum normalized distance that is required for a pose to activate.",
        min=0.0,
    )  # pyright: ignore[reportInvalidTypeForm]
    distance_method: bpy.props.EnumProperty(
        name="Distance Method",
        items=[
            # TODO: Should we support Euclidean?Z
            # ('Euclidean', 'Euclidean', 'Standard n-dimensional distance measure.'),  # noqa: ERA001
            ("Quaternion", "Quaternion", "Treat inputs as quaternion"),
            (
                "SwingAngle",
                "Swing Angle",
                (
                    "Treat inputs as quaternion, and find the distance between rotated TwistAxis "
                    "directions. Only uses the rotation values from the y + z axis (whatever hasn't "
                    "been set as the twist axis)."
                ),
            ),
            (
                "TwistAngle",
                "Twist Angle",
                (
                    "Treat inputs as quaternion, and find the distance between rotations around "
                    "the TwistAxis direction. Only uses the rotation of the axis defined by the twist axis."
                ),
            ),
        ],
        default="SwingAngle",
        description="The distance method of the RBF solver",
    )  # pyright: ignore[reportInvalidTypeForm]
    normalize_method: bpy.props.EnumProperty(
        name="Normalize Method",
        items=[
            (
                "OnlyNormalizeAboveOne",
                "Only Normalize Above One",
                "Use the Only Normalize Above One method for the normalization method of the RBF solver",
            ),
            (
                "AlwaysNormalize",
                "Always Normalize",
                "Use the Always Normalize method for the normalization method of the RBF solver",
            ),
        ],
        default="AlwaysNormalize",
        description=(
            "As you rotate the driven transform around, the solver will calculate a weight to show how "
            "much of the pose has been activated. This weight value is between 0 and 1. In some cases, "
            "the sum of all of the weights of all of the poses can exceed one and in other scenarios be "
            "less than one. This is where normalization comes into play.\nIt will always normalize above "
            "one, regardless if no normalization is selected. It is recommended to always normalize. DNA "
            "does not support no normalization and will generate an error if the solver is exported with "
            "this setting."
        ),
    )  # pyright: ignore[reportInvalidTypeForm]
    function_type: bpy.props.EnumProperty(
        items=[
            ("Gaussian", "Gaussian", "Use the Gaussian method for the function type of the RBF solver"),
            ("Exponential", "Exponential", "Use the Exponential method for the function type of the RBF solver"),
            ("Linear", "Linear", "Use the Linear method for the function type of the RBF solver"),
            ("Cubic", "Cubic", "Use the Cubic method for the function type of the RBF solver"),
            ("Quintic", "Quintic", "Use the Quintic method for the function type of the RBF solver"),
        ],
        default="Gaussian",
        description="The function type of the RBF solver",
    )  # pyright: ignore[reportInvalidTypeForm]
    twist_axis: bpy.props.EnumProperty(
        items=[
            ("X", "X-Axis", "Use the X axis for twisting"),
            ("Y", "Y-Axis", "Use the Y axis for twisting"),
            ("Z", "Z-Axis", "Use the Z axis for twisting"),
        ],
        default="X",
        description="The axis used during SwingAngle or TwistAngle distance method calculations.",
    )  # pyright: ignore[reportInvalidTypeForm]
    automatic_radius: bpy.props.BoolProperty(
        default=False,
        name="Automatic Radius",
        description=(
            "Enabling automatic radius will calculate the average distance between the default pose and "
            "each target pose. The min radius value and max radius value are debug values to show what "
            "the solver is using to calculate the automatic radius value. The automatic radius value is "
            "also a debug attribute showcasing the result. The min radius is calculated by taking the "
            "absolute distance between the default pose and the closest pose. The max radius is the sum "
            "of the absolute distance between the closest pose and the furthest pose."
        ),
    )  # pyright: ignore[reportInvalidTypeForm]

    poses: bpy.props.CollectionProperty(type=RBFPoseData)  # pyright: ignore[reportInvalidTypeForm]
    poses_active_index: bpy.props.IntProperty(update=core.update_body_rbf_poses_active_index)  # pyright: ignore[reportArgumentType, reportInvalidTypeForm]


def register():
    """Register the RBF editor properties and ensure function curves exist."""
    ensure_function_curves_exist()


def unregister():
    """Un-register the addon's property group classes when the addon is disabled."""
    from .function_curves import cleanup_function_curves

    cleanup_function_curves()
