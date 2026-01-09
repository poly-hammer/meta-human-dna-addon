import bpy

from ...typing import *  # noqa: F403


def update_body_rbf_poses_active_index(self: "RBFSolverData", context: "Context"):
    # Avoid circular import
    from ...ui.callbacks import update_body_rbf_poses_active_index as _update_body_rbf_poses_active_index

    _update_body_rbf_poses_active_index(self, context)


def update_body_rbf_driven_active_index(self: "RBFPoseData", context: "Context"):
    # Avoid circular import
    from ...ui.callbacks import update_body_rbf_driven_active_index as _update_body_rbf_driven_active_index

    _update_body_rbf_driven_active_index(self, context)


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


class RBFPoseData(bpy.types.PropertyGroup):
    solver_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]
    pose_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]
    joint_group_index: bpy.props.IntProperty(default=-1)  # pyright: ignore[reportInvalidTypeForm]
    name: bpy.props.StringProperty(
        default="",
        description="The name of the pose",
    )  # pyright: ignore[reportInvalidTypeForm]
    scale_factor: bpy.props.FloatProperty(default=1.0, description="The scale factor of the pose", min=0.0)  # pyright: ignore[reportInvalidTypeForm]
    target_enable: bpy.props.BoolProperty(
        default=True,
        description="Whether the target is enabled",
    )  # pyright: ignore[reportInvalidTypeForm]

    driven: bpy.props.CollectionProperty(type=RBFDrivenData)  # pyright: ignore[reportInvalidTypeForm]
    driven_active_index: bpy.props.IntProperty(update=update_body_rbf_driven_active_index)  # pyright: ignore[reportArgumentType, reportInvalidTypeForm]

    drivers: bpy.props.CollectionProperty(type=RBFDriverData)  # pyright: ignore[reportInvalidTypeForm]
    drivers_active_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]
    # TODO: Implement blend shapes for RBF poses
    # shape_key_data: bpy.props.CollectionProperty(type=ShapeKeyData) # noqa: ERA001


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
        default="Additive",
        description="The mode of the RBF solver",
    )  # pyright: ignore[reportInvalidTypeForm]
    radius: bpy.props.FloatProperty(default=50.0, description="The radius of the RBF solver", min=0.0)  # pyright: ignore[reportInvalidTypeForm]
    weight_threshold: bpy.props.FloatProperty(
        default=0.001, description="The weight threshold of the RBF solver", min=0.0
    )  # pyright: ignore[reportInvalidTypeForm]
    distance_method: bpy.props.EnumProperty(
        items=[
            # TODO: Should we support Euclidean?
            # ('Euclidean', 'Euclidean', 'Use the Euclidean distance method for the RBF solver'),  # noqa: ERA001
            ("Quaternion", "Quaternion", "Use the Quaternion distance method for the RBF solver"),
            ("SwingAngle", "Swing Angle", "Use the Swing Angle distance method for the RBF solver"),
            ("TwistAngle", "Twist Angle", "Use the Twist Angle distance method for the RBF solver"),
        ],
        default="TwistAngle",
        description="The distance method of the RBF solver",
    )  # pyright: ignore[reportInvalidTypeForm]
    normalize_method: bpy.props.EnumProperty(
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
        description="The normalization method of the RBF solver",
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
        description="The axis around which to twists are calculated",
    )  # pyright: ignore[reportInvalidTypeForm]
    automatic_radius: bpy.props.BoolProperty(
        default=False,
        name="Automatic Radius",
        description="Whether to automatically calculate the radius for the RBF solver",
    )  # pyright: ignore[reportInvalidTypeForm]

    poses: bpy.props.CollectionProperty(type=RBFPoseData)  # pyright: ignore[reportInvalidTypeForm]
    poses_active_index: bpy.props.IntProperty(update=update_body_rbf_poses_active_index)  # pyright: ignore[reportArgumentType, reportInvalidTypeForm]
