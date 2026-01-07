import bpy


def update_body_rbf_poses_active_index(self, context):
    # Avoid circular import
    from ...ui.callbacks import update_body_rbf_poses_active_index as _update_body_rbf_poses_active_index

    _update_body_rbf_poses_active_index(self, context)


def update_body_rbf_driven_active_index(self, context):
    # Avoid circular import
    from ...ui.callbacks import update_body_rbf_driven_active_index as _update_body_rbf_driven_active_index

    _update_body_rbf_driven_active_index(self, context)


class RBFDriverData(bpy.types.PropertyGroup):
    solver_index: bpy.props.IntProperty()  # type: ignore
    pose_index: bpy.props.IntProperty()  # type: ignore
    joint_index: bpy.props.IntProperty()  # type: ignore
    name: bpy.props.StringProperty()  # type: ignore
    rotation_mode: bpy.props.EnumProperty(
        items=[
            ("QUATERNION", "Quaternion", "Use the Quaternion rotation mode"),
            ("XYZ", "Euler XYZ", "Use the Euler XYZ rotation mode"),
        ],
        default="QUATERNION",
        description="The rotation mode of the pose transformation",
    )  # type: ignore
    euler_rotation: bpy.props.FloatVectorProperty(default=(0.0, 0.0, 0.0), size=3)  # type: ignore
    quaternion_rotation: bpy.props.FloatVectorProperty(default=(1.0, 0.0, 0.0, 0.0), size=4)  # type: ignore


class RBFDrivenData(bpy.types.PropertyGroup):
    pose_index: bpy.props.IntProperty()  # type: ignore
    joint_group_index: bpy.props.IntProperty(default=-1)  # type: ignore
    joint_index: bpy.props.IntProperty()  # type: ignore
    name: bpy.props.StringProperty()  # type: ignore
    data_type: bpy.props.EnumProperty(
        items=[
            ("BONE", "Bone Transforms", "Drives the Bone Transforms"),
            ("SHAPE_KEY", "Shape Key Value", "Drives the Shape Key Value"),
            ("MASK", "Mask Value", "Drives the Mask Value"),
        ],
        default="BONE",
        description="The type of driven data",
    )  # type: ignore
    rotation_mode: bpy.props.EnumProperty(
        items=[
            ("QUATERNION", "Quaternion", "Use the Quaternion rotation mode"),
            ("XYZ", "Euler XYZ", "Use the Euler XYZ rotation mode"),
        ],
        default="QUATERNION",
        description="The rotation mode of the pose transformation",
    )  # type: ignore
    location: bpy.props.FloatVectorProperty(default=(0.0, 0.0, 0.0), size=3)  # type: ignore
    euler_rotation: bpy.props.FloatVectorProperty(default=(0.0, 0.0, 0.0), size=3)  # type: ignore
    quaternion_rotation: bpy.props.FloatVectorProperty(default=(1.0, 0.0, 0.0, 0.0), size=4)  # type: ignore
    scale: bpy.props.FloatVectorProperty(default=(0.0, 0.0, 0.0), size=3)  # type: ignore
    scalar_value: bpy.props.FloatProperty(default=0.0, min=0.0, max=1.0)  # type: ignore


class RBFPoseData(bpy.types.PropertyGroup):
    solver_index: bpy.props.IntProperty()  # type: ignore
    pose_index: bpy.props.IntProperty()  # type: ignore
    joint_group_index: bpy.props.IntProperty(default=-1)  # type: ignore
    name: bpy.props.StringProperty(
        default="",
        description="The name of the pose",
    )  # type: ignore
    scale_factor: bpy.props.FloatProperty(default=1.0, description="The scale factor of the pose", min=0.0)  # type: ignore
    target_enable: bpy.props.BoolProperty(
        default=True,
        description="Whether the target is enabled",
    )  # type: ignore

    driven: bpy.props.CollectionProperty(type=RBFDrivenData)  # type: ignore
    driven_active_index: bpy.props.IntProperty(update=update_body_rbf_driven_active_index)  # type: ignore

    drivers: bpy.props.CollectionProperty(type=RBFDriverData)  # type: ignore
    drivers_active_index: bpy.props.IntProperty()  # type: ignore
    # TODO: Implement blend shapes for RBF poses
    # shape_key_data: bpy.props.CollectionProperty(type=ShapeKeyData) # type: ignore


class RBFSolverData(bpy.types.PropertyGroup):
    solver_index: bpy.props.IntProperty()  # type: ignore
    name: bpy.props.StringProperty(
        default="",
        description="The name of the RBF solver",
    )  # type: ignore
    mode: bpy.props.EnumProperty(
        items=[
            ("Additive", "Additive", "Use the additive RBF solver mode"),
            ("Interpolative", "Interpolative", "Use the interpolative RBF solver mode"),
        ],
        default="Additive",
        description="The mode of the RBF solver",
    )  # type: ignore
    radius: bpy.props.FloatProperty(default=50.0, description="The radius of the RBF solver", min=0.0)  # type: ignore
    weight_threshold: bpy.props.FloatProperty(
        default=0.001, description="The weight threshold of the RBF solver", min=0.0
    )  # type: ignore
    distance_method: bpy.props.EnumProperty(
        items=[
            # TODO: Should we support Euclidean?
            # ('Euclidean', 'Euclidean', 'Use the Euclidean distance method for the RBF solver'),
            ("Quaternion", "Quaternion", "Use the Quaternion distance method for the RBF solver"),
            ("SwingAngle", "Swing Angle", "Use the Swing Angle distance method for the RBF solver"),
            ("TwistAngle", "Twist Angle", "Use the Twist Angle distance method for the RBF solver"),
        ],
        default="TwistAngle",
        description="The distance method of the RBF solver",
    )  # type: ignore
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
    )  # type: ignore
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
    )  # type: ignore
    twist_axis: bpy.props.EnumProperty(
        items=[
            ("X", "X-Axis", "Use the X axis for twisting"),
            ("Y", "Y-Axis", "Use the Y axis for twisting"),
            ("Z", "Z-Axis", "Use the Z axis for twisting"),
        ],
        default="X",
        description="The axis around which to twists are calculated",
    )  # type: ignore
    automatic_radius: bpy.props.BoolProperty(
        default=False,
        name="Automatic Radius",
        description="Whether to automatically calculate the radius for the RBF solver",
    )  # type: ignore

    poses: bpy.props.CollectionProperty(type=RBFPoseData)  # type: ignore
    poses_active_index: bpy.props.IntProperty(update=update_body_rbf_poses_active_index)  # type: ignore
