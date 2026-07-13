# standard library imports
import json
import logging

from pathlib import Path

# third party imports
import bpy

from bpy.types import Action  # pyright: ignore[reportUnusedImport]
from mathutils import Euler, Quaternion, Vector

# local imports
from ..constants import EYE_AIM_BONES, FACE_BOARD_SWITCHES, IS_BLENDER_5, SCALE_FACTOR, Axis, ComponentType, ToolInfo
from ..typing import *  # noqa: F403
from .armature import get_pose_bone_local_transform
from .misc import apply_transforms


# blender 4.5 and 5.0 support
if IS_BLENDER_5:
    from bpy_extras import anim_utils
else:
    anim_utils = None

logger = logging.getLogger(__name__)


def get_action_name(
    instance: "RigInstance",
    action_name: str,
    prefix_component_name: bool,
    prefix_instance_name: bool,
    component: ComponentType = "head",
) -> str:
    if prefix_component_name and not prefix_instance_name:
        return f"{component}_{action_name}"
    if prefix_instance_name and not prefix_component_name:
        return f"{instance.name}_{action_name}"
    if prefix_instance_name and prefix_component_name:
        return f"{instance.name}_{component}_{action_name}"
    return action_name


def set_keys_on_bone(
    action: bpy.types.Action, bone_name: str, data_path: str | None, axis: Axis, keys: list[tuple[int, float]]
):
    # controls in world space like the eyes need to be scaled by down and inverted
    scale_factor = -0.01

    index_lookup = {"x": 0, "y": 1, "z": 2}
    if not data_path:
        data_path = "location"
        scale_factor = 1.0
    elif data_path == "rotation":
        data_path = "rotation_euler"
    else:
        data_path = data_path.lower()

    # create the fcurve
    index = index_lookup.get(axis.lower())

    if anim_utils:
        channel_bag = anim_utils.action_ensure_channelbag_for_slot(action, action.slots[0])
    else:
        channel_bag = action

    if channel_bag:
        fcurve = channel_bag.fcurves.new(data_path=f'pose.bones["{bone_name}"].{data_path}', index=index)
        # then add as many points as keyframes
        fcurve.keyframe_points.add(len(keys))
        # then set all its values
        for (frame, value), keyframe_point in zip(keys, fcurve.keyframe_points, strict=False):
            keyframe_point.co[0] = frame
            keyframe_point.co[1] = value * scale_factor


def remove_object_scale_keyframes(actions: list[bpy.types.Action]):
    for action in actions:
        if anim_utils:
            channel_bag = anim_utils.action_ensure_channelbag_for_slot(action, action.slots[0])
        else:
            channel_bag = action

        if channel_bag:
            # Collect fcurves to remove first to avoid modifying collection while iterating
            fcurves_to_remove = [fcurve for fcurve in channel_bag.fcurves if fcurve and fcurve.data_path == "scale"]
            for fcurve in fcurves_to_remove:
                channel_bag.fcurves.remove(fcurve)


def scale_object_actions(
    unordered_objects: list[bpy.types.Object], actions: list[bpy.types.Action], scale_factor: float
):
    # get the list of objects that do not have parents
    no_parents = [unordered_object for unordered_object in unordered_objects if not unordered_object.parent]

    # get the list of objects that have parents
    parents = [unordered_object for unordered_object in unordered_objects if unordered_object.parent]

    # re-order the imported objects to have the top of the hierarchies iterated first
    ordered_objects = no_parents + parents

    for ordered_object in ordered_objects:
        # run the export iteration but with "scale" set to the scale of the object as it was imported
        scale = ordered_object.scale[:]

        # if the imported object is an armature
        if ordered_object.type == "ARMATURE":
            # iterate over any imported actions first this time...
            for action in actions:
                if anim_utils:
                    channel_bag = anim_utils.action_ensure_channelbag_for_slot(action, action.slots[0])
                else:
                    channel_bag = action

                if not channel_bag:
                    continue

                # iterate through the location curves
                for fcurve in [fcurve for fcurve in channel_bag.fcurves if fcurve.data_path.endswith("location")]:
                    # the location fcurve of the object
                    if fcurve.data_path == "location":
                        for keyframe_point in fcurve.keyframe_points:
                            # just the location to preserve root motion
                            keyframe_point.co[1] = keyframe_point.co[1] * scale[fcurve.array_index] * scale_factor
                        # don't scale the objects location handles
                        continue

                    # and iterate through the keyframe values
                    for keyframe_point in fcurve.keyframe_points:
                        # multiply the location keyframes by the scale per channel
                        keyframe_point.co[1] = keyframe_point.co[1] * scale[fcurve.array_index]
                        keyframe_point.handle_left[1] = keyframe_point.handle_left[1] * scale[fcurve.array_index]
                        keyframe_point.handle_right[1] = keyframe_point.handle_right[1] * scale[fcurve.array_index]

            # apply the scale on the object
            apply_transforms(ordered_object, scale=True)


def convert_action_rotation_from_quaternion_to_euler(action: bpy.types.Action, bone_names: list[str] | None = None):
    rotation_curves_by_bone = {}
    if bone_names is None:
        bone_names = []

    if anim_utils:
        channel_bag = anim_utils.action_ensure_channelbag_for_slot(action, action.slots[0])
    else:
        channel_bag = action

    if not channel_bag:
        return

    for fcurve in channel_bag.fcurves:
        # save the quaternion rotation curves by bone for later conversion
        if "rotation_quaternion" in fcurve.data_path:
            bone_name = fcurve.data_path.split('"')[1]
            # if we have a list of bone names to filter by, skip any that are not in the list
            if bone_name not in bone_names:
                continue

            rotation_curves_by_bone[bone_name] = rotation_curves_by_bone.get(bone_name, {})
            rotation_curves_by_bone[bone_name][fcurve.array_index] = fcurve

    # convert quaternion curves to euler curves
    for bone_name, quat_curves in rotation_curves_by_bone.items():
        # collect all frames from all quaternion curves
        frames = set()
        for fcurve in quat_curves.values():
            for keyframe in fcurve.keyframe_points:
                frames.add(int(keyframe.co[0]))

        # create euler fcurves
        euler_fcurves = {}
        for i in range(3):  # x, y, z
            euler_fcurves[i] = channel_bag.fcurves.new(data_path=f'pose.bones["{bone_name}"].rotation_euler', index=i)
            euler_fcurves[i].keyframe_points.add(len(frames))

        # convert quaternion values to euler for each frame
        for frame_index, frame in enumerate(sorted(frames)):
            quat_values = [1.0, 0.0, 0.0, 0.0]  # w, x, y, z
            for axis, fcurve in quat_curves.items():
                quat_values[axis] = fcurve.evaluate(frame)

            # convert quaternion to euler
            quat = Quaternion(quat_values)
            euler = quat.to_euler("XYZ")

            # set euler keyframe values
            for i, value in enumerate([euler.x, euler.y, euler.z]):
                euler_fcurves[i].keyframe_points[frame_index].co = (frame, value)

        # remove original quaternion curves
        for fcurve in quat_curves.values():
            channel_bag.fcurves.remove(fcurve)


def import_action_from_fbx(  # noqa: PLR0912, PLR0915
    instance: "RigInstance",
    file_path: Path,
    component: ComponentType,
    armature: bpy.types.Object,
    include_only_bones: list[str] | None = None,
    round_sub_frames: bool = True,
    match_frame_rate: bool = True,
    prefix_instance_name: bool = True,
    prefix_component_name: bool = True,
) -> bpy.types.Action:
    file_path = Path(file_path)

    action_name = get_action_name(
        instance=instance,
        action_name=file_path.stem,
        prefix_component_name=prefix_component_name,
        prefix_instance_name=prefix_instance_name,
        component=component,
    )

    # remove the action if it already exists
    new_action = bpy.data.actions.get(action_name)
    if new_action:
        bpy.data.actions.remove(new_action)
    new_action = bpy.data.actions.new(name=action_name)

    if anim_utils:
        if len(new_action.slots) == 0:
            new_action.slots.new("OBJECT", name=armature.name)
        new_channel_bag = anim_utils.action_ensure_channelbag_for_slot(new_action, new_action.slots[0])
    else:
        new_channel_bag = new_action

    if not new_channel_bag or not bpy.context.scene:
        return new_action

    # remember the current actions and objects
    current_actions = list(bpy.data.actions)
    current_objects = list(bpy.data.objects)
    # remember the current frame rate
    current_frame_rate = bpy.context.scene.render.fps
    # then import the fbx
    bpy.ops.import_scene.fbx(filepath=str(file_path))

    # apply the scale fixes since this was exported from unreal at 100x scale
    imported_objects = [obj for obj in bpy.data.objects if obj not in current_objects]
    imported_actions = [action for action in bpy.data.actions if action not in current_actions]
    scale_object_actions(unordered_objects=imported_objects, actions=imported_actions, scale_factor=SCALE_FACTOR)
    remove_object_scale_keyframes(actions=imported_actions)

    # get the frame rate of the imported fbx
    imported_frame_rate = bpy.context.scene.render.fps
    # calculate the frame scale factor
    if match_frame_rate:
        frame_scale_factor = current_frame_rate / imported_frame_rate
    else:
        frame_scale_factor = 1.0
    # restore the original frame rate
    bpy.context.scene.render.fps = current_frame_rate

    # copy all the fcurves from the imported action to the new one
    for action in bpy.data.actions:
        if action in current_actions:
            continue

        if anim_utils:
            channel_bag = anim_utils.action_ensure_channelbag_for_slot(action, action.slots[0])
        else:
            channel_bag = action

        if not channel_bag:
            continue

        for source_fcurve in channel_bag.fcurves:
            bone_name = None
            curve_name = None

            if len(source_fcurve.data_path.split('"')) > 1:
                bone_name = source_fcurve.data_path.split('"')[1]
                curve_name = source_fcurve.data_path.split(".")[-1]
            # object level transforms are mapped to the root bone
            elif source_fcurve.data_path in {"location", "rotation_euler", "rotation_quaternion", "scale"}:
                bone_name = "root"
                curve_name = source_fcurve.data_path

            if bone_name and curve_name and armature.pose:
                if not armature.pose.bones.get(bone_name):
                    logger.warning(f"Skipping fcurve for unknown bone: {bone_name}")
                    continue

                if include_only_bones and bone_name not in include_only_bones:
                    continue

                target_fcurve = new_channel_bag.fcurves.new(
                    data_path=f'pose.bones["{bone_name}"].{curve_name}', index=source_fcurve.array_index
                )
                # then add as many points as keyframes
                target_fcurve.keyframe_points.add(len(source_fcurve.keyframe_points))
                # then set all all their values
                for index, keyframe in enumerate(source_fcurve.keyframe_points):
                    # Adjust keyframe position based on frame rate scale factor
                    frame = keyframe.co[0] * frame_scale_factor

                    # optionally round sub frames to the nearest whole frame
                    if round_sub_frames:
                        frame = round(frame)

                    target_fcurve.keyframe_points[index].co = (frame, keyframe.co[1])
                    target_fcurve.keyframe_points[index].interpolation = keyframe.interpolation

    # assign the new action to as the current action of the armature
    if not armature.animation_data:
        armature.animation_data_create()
    if not armature.animation_data:
        raise RuntimeError("Failed to create animation data for armature.")

    armature.animation_data.action = new_action
    # assign the first action slot if there are any
    if new_action.slots:
        armature.animation_data.action_slot = new_action.slots[0]

    # remove the imported actions
    for action in bpy.data.actions:
        if action not in current_actions:
            bpy.data.actions.remove(action, do_unlink=True)

    # remove the imported objects
    for scene_object in bpy.data.objects:
        if scene_object not in current_objects:
            bpy.data.objects.remove(scene_object, do_unlink=True)

    if armature.pose:
        # match the keyframe rotation modes to the armature bones (all rotation is imported as quaternion)
        euler_bone_names = [b.name for b in armature.pose.bones if b.rotation_mode == "XYZ"]
        convert_action_rotation_from_quaternion_to_euler(action=new_action, bone_names=euler_bone_names)

    return new_action


def import_face_board_action_from_fbx(  # noqa: PLR0912
    instance: "RigInstance",
    file_path: Path,
    armature: bpy.types.Object,
    round_sub_frames: bool = True,
    match_frame_rate: bool = True,
    prefix_instance_name: bool = True,
    prefix_component_name: bool = True,
):
    file_path = Path(file_path)
    if not bpy.context.scene:
        return

    action_name = get_action_name(
        instance=instance,
        action_name=file_path.stem,
        prefix_component_name=prefix_component_name,
        prefix_instance_name=prefix_instance_name,
        component="face_board",  # type: ignore[arg-type]
    )

    # remove the action if it already exists
    face_board_action = bpy.data.actions.get(action_name)
    if face_board_action:
        bpy.data.actions.remove(face_board_action)
    face_board_action = bpy.data.actions.new(name=action_name)

    if anim_utils:
        if len(face_board_action.slots) == 0:
            face_board_action.slots.new("OBJECT", name=armature.name)
        face_board_channel_bag = anim_utils.action_ensure_channelbag_for_slot(
            face_board_action, face_board_action.slots[0]
        )
    else:
        face_board_channel_bag = face_board_action

    # remember the current actions and objects
    current_actions = list(bpy.data.actions)
    current_objects = list(bpy.data.objects)
    # remember the current frame rate
    current_frame_rate = bpy.context.scene.render.fps
    # then import the fbx
    bpy.ops.import_scene.fbx(filepath=str(file_path))
    # get the frame rate of the imported fbx
    imported_frame_rate = bpy.context.scene.render.fps
    # calculate the frame scale factor
    if match_frame_rate:
        frame_scale_factor = current_frame_rate / imported_frame_rate
    else:
        frame_scale_factor = 1.0
    # restore the original frame rate
    bpy.context.scene.render.fps = current_frame_rate

    # copy all the fcurves from the imported action to the new one
    for action in bpy.data.actions:
        if action in current_actions:
            continue

        curve_name = action.name.split(".")[0]
        # skip the face board action, only import controls
        if curve_name == action.name:
            continue

        # TODO: Change this to actually support these?
        # skip any eye aim controls
        if curve_name in EYE_AIM_BONES + FACE_BOARD_SWITCHES:
            continue

        if anim_utils:
            channel_bag = anim_utils.action_ensure_channelbag_for_slot(action, action.slots[0])
        else:
            channel_bag = action

        if not channel_bag or not face_board_channel_bag:
            continue

        for source_fcurve in channel_bag.fcurves:
            target_fcurve = face_board_channel_bag.fcurves.new(
                data_path=f'pose.bones["{curve_name}"].{source_fcurve.data_path}', index=source_fcurve.array_index
            )
            # then add as many points as keyframes
            target_fcurve.keyframe_points.add(len(source_fcurve.keyframe_points))
            # then set all all their values
            for index, keyframe in enumerate(source_fcurve.keyframe_points):
                # Adjust keyframe position based on frame rate scale factor
                frame = keyframe.co[0] * frame_scale_factor

                # optionally round sub frames to the nearest whole frame
                if round_sub_frames:
                    frame = round(frame)

                target_fcurve.keyframe_points[index].co = (frame, keyframe.co[1])
                target_fcurve.keyframe_points[index].interpolation = keyframe.interpolation

    # remove the imported objects
    for scene_object in bpy.data.objects:
        if scene_object not in current_objects:
            bpy.data.objects.remove(scene_object)
    # remove the imported actions
    for action in bpy.data.actions:
        if action not in current_actions:
            bpy.data.actions.remove(action)

    # assign the new action to the face board
    if not armature.animation_data:
        armature.animation_data_create()
    if not armature.animation_data:
        raise RuntimeError("Failed to create animation data for armature.")

    armature.animation_data.action = face_board_action
    # assign the first action slot if there are any
    if face_board_action.slots:
        armature.animation_data.action_slot = face_board_action.slots[0]


def import_face_board_action_from_json(file_path: Path, armature: bpy.types.Object):  # noqa: PLR0912
    if not armature.pose:
        return

    # create animation data if it does not exist
    if not armature.animation_data:
        armature.animation_data_create()
    if not armature.animation_data:
        raise RuntimeError("Failed to create animation data for armature.")

    # create action
    action_name = file_path.stem
    action = bpy.data.actions.get(action_name)
    if not action:
        action = bpy.data.actions.new(action_name)

    if anim_utils:
        if len(action.slots) == 0:
            action.slots.new("OBJECT", name=armature.name)
        channel_bag = anim_utils.action_ensure_channelbag_for_slot(action, action.slots[0])
    else:
        channel_bag = action

    if channel_bag:
        # delete all existing fcurves
        for fcurve in channel_bag.fcurves:
            channel_bag.fcurves.remove(fcurve)

    # ensure all bones are using euler xyz rotation
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "XYZ"

    with file_path.open() as file:
        data = json.load(file)
        for curve_name, keys in data.items():
            bone_name = None
            axis = None
            data_path = None

            chunks = curve_name.split(".")
            if len(chunks) == 3:
                bone_name, data_path, axis = chunks
            elif len(chunks) == 2:
                bone_name, axis = chunks
            elif len(chunks) == 1:
                bone_name = curve_name
                axis = "Y"

            if bone_name and axis:
                set_keys_on_bone(action=action, bone_name=bone_name, data_path=data_path, axis=axis, keys=keys)
            else:
                logger.error(f"failed to parse args from curve {curve_name}")

    armature.animation_data.action = action


def bake_control_curve_values_for_frame(  # noqa: PLR0912
    instance: "RigInstance",
    texture_logic_node: bpy.types.ShaderNodeGroup | None,
    action: bpy.types.Action,
    frame: int,
    masks: bool = True,
    shape_keys: bool = True,
    bones: bool = False,
    bone_keyframe_buffer: dict[str, dict[str, list[tuple[float, float]]]] | None = None,
    shape_key_buffer: dict[bpy.types.ShapeKey, list[tuple[float, float]]] | None = None,
    mask_buffer: dict[str, list[tuple[float, float]]] | None = None,
    channel_types: set[str] | None = None,
    component: ComponentType = "head",
):
    index_lookup = {0: "x", 1: "y", 2: "z"}
    control_curve_values = {}

    if anim_utils:
        channel_bag = anim_utils.action_ensure_channelbag_for_slot(action, action.slots[0])
    else:
        channel_bag = action

    if not channel_bag:
        return

    for fcurve in channel_bag.fcurves:
        control_curve_name, transform = fcurve.data_path.split('"].')
        if transform == "location" and fcurve.array_index != 2:
            control_curve_name = control_curve_name.replace('pose.bones["', "")
            axis = index_lookup[fcurve.array_index]

            control_curve_values[control_curve_name] = control_curve_values.get(control_curve_name, {})
            control_curve_values[control_curve_name].update({axis: fcurve.evaluate(frame)})

    # set and update the control curve values based on the fcurve values
    instance.update_head_gui_control_values(override_values=control_curve_values)

    # now get the calculated values and bake them to the shape keys value
    if shape_keys:
        if component == "head":
            for shape_key, value in instance.update_head_shape_keys(collect_values=True):
                if shape_key_buffer is not None:
                    if shape_key not in shape_key_buffer:
                        shape_key_buffer[shape_key] = []
                    shape_key_buffer[shape_key].append((float(frame), value))
                else:
                    shape_key.keyframe_insert("value", frame=frame)
        elif component == "body":
            # TODO: implement body shape key baking
            pass

    # now bake the texture mask values
    if texture_logic_node and masks:
        if component == "head":
            for slider_name, value in instance.update_head_texture_masks():
                if mask_buffer is not None:
                    if slider_name not in mask_buffer:
                        mask_buffer[slider_name] = []
                    mask_buffer[slider_name].append((float(frame), value))
                else:
                    texture_logic_node.inputs[slider_name].default_value = value  # type: ignore[attr-defined]
                    texture_logic_node.inputs[slider_name].keyframe_insert("default_value", frame=frame)
        elif component == "body":
            # TODO: implement body texture mask baking
            pass

    # accumulate bone transforms into the buffer for bulk writing later
    if bones and bone_keyframe_buffer is not None:
        if component == "head":
            bone_transforms = instance.update_head_bone_transforms(collect_transforms=True)
        elif component == "body":
            bone_transforms = instance.update_body_bone_transforms(collect_transforms=True)
        else:
            bone_transforms = []

        accumulate_bone_keyframes(bone_transforms, frame, bone_keyframe_buffer, channel_types)


def accumulate_bone_keyframes(  # noqa: PLR0912
    bone_transforms: list[tuple[str, Vector, Euler | Quaternion, Vector]],
    frame: int,
    buffer: dict[str, dict[str, list[tuple[float, float]]]],
    channel_types: set[str] | None = None,
) -> None:
    """Accumulate bone transform data for a single frame into the keyframe buffer.

    Args:
        bone_transforms: List of (bone_name, location, rotation, scale) tuples.
            Rotation can be Euler (writes rotation_euler fcurves) or Quaternion
            (writes rotation_quaternion fcurves).
        frame: The frame number.
        buffer: The keyframe buffer dict to accumulate into.
        channel_types: Set of channel types to include (e.g. {"LOCATION", "ROTATION", "SCALE"}).
    """
    if channel_types is None:
        channel_types = {"LOCATION", "ROTATION", "SCALE"}

    for bone_name, location, rotation, scale in bone_transforms:
        if bone_name not in buffer:
            buffer[bone_name] = {}

        bone_data = buffer[bone_name]

        if "LOCATION" in channel_types:
            for i, axis_val in enumerate((location.x, location.y, location.z)):
                key = f"location.{i}"
                if key not in bone_data:
                    bone_data[key] = []
                bone_data[key].append((float(frame), axis_val))

        if "ROTATION" in channel_types:
            if isinstance(rotation, Quaternion):
                for i, axis_val in enumerate((rotation.w, rotation.x, rotation.y, rotation.z)):
                    key = f"rotation_quaternion.{i}"
                    if key not in bone_data:
                        bone_data[key] = []
                    bone_data[key].append((float(frame), axis_val))
            else:
                for i, axis_val in enumerate((rotation.x, rotation.y, rotation.z)):
                    key = f"rotation_euler.{i}"
                    if key not in bone_data:
                        bone_data[key] = []
                    bone_data[key].append((float(frame), axis_val))

        if "SCALE" in channel_types:
            for i, axis_val in enumerate((scale.x, scale.y, scale.z)):
                key = f"scale.{i}"
                if key not in bone_data:
                    bone_data[key] = []
                bone_data[key].append((float(frame), axis_val))


def flush_bone_keyframes_to_action(
    action: bpy.types.Action,
    buffer: dict[str, dict[str, list[tuple[float, float]]]],
    clean_curves: bool = True,
) -> None:
    """Bulk-write accumulated bone keyframes to an action using foreach_set for performance.

    Args:
        action: The Blender action to write keyframes to.
        buffer: The keyframe buffer dict populated by accumulate_bone_keyframes.
        clean_curves: Whether to clean redundant keyframes from curves after writing.
    """
    if anim_utils:
        channel_bag = anim_utils.action_ensure_channelbag_for_slot(action, action.slots[0])
    else:
        channel_bag = action

    if not channel_bag:
        return

    for bone_name, channels in buffer.items():
        for channel_key, keyframes in channels.items():
            # parse "location.0" -> ("location", 0)
            data_path_base, index_str = channel_key.rsplit(".", 1)
            array_index = int(index_str)
            data_path = f'pose.bones["{bone_name}"].{data_path_base}'

            fcurve = channel_bag.fcurves.new(data_path=data_path, index=array_index)

            # bulk insert using foreach_set (much faster than per-keyframe insertion)
            num_keys = len(keyframes)
            fcurve.keyframe_points.add(num_keys)

            # build flat co array: [frame0, value0, frame1, value1, ...]
            flat_co = [0.0] * (num_keys * 2)
            for i, (frame, value) in enumerate(keyframes):
                flat_co[i * 2] = frame
                flat_co[i * 2 + 1] = value

            fcurve.keyframe_points.foreach_set("co", flat_co)

            # update the fcurve to recalculate handles
            fcurve.update()

            if clean_curves:
                # remove redundant keyframes where all values are identical
                # check if all values are the same
                values = flat_co[1::2]
                if len(set(values)) == 1:
                    # keep only the first and last keyframe
                    while len(fcurve.keyframe_points) > 2:
                        fcurve.keyframe_points.remove(fcurve.keyframe_points[1])
                    fcurve.update()


def _bulk_write_scalar_keyframes(
    channel_bag: "ActionChannelBag | Action",  # pyright: ignore[reportUndefinedVariable]
    data_path: str,
    keyframes: list[tuple[float, float]],
    clean_curves: bool = True,
) -> None:
    """Write a list of (frame, value) keyframes to a single scalar fcurve using foreach_set."""
    # remove any existing fcurve for this data path to avoid conflicts on re-bake
    existing = channel_bag.fcurves.find(data_path, index=0)
    if existing:
        channel_bag.fcurves.remove(existing)

    fcurve = channel_bag.fcurves.new(data_path=data_path, index=0)

    num_keys = len(keyframes)
    fcurve.keyframe_points.add(num_keys)

    flat_co = [0.0] * (num_keys * 2)
    for i, (frame, value) in enumerate(keyframes):
        flat_co[i * 2] = frame
        flat_co[i * 2 + 1] = value

    fcurve.keyframe_points.foreach_set("co", flat_co)
    fcurve.update()

    if clean_curves:
        values = flat_co[1::2]
        if len(set(values)) == 1:
            while len(fcurve.keyframe_points) > 2:
                fcurve.keyframe_points.remove(fcurve.keyframe_points[1])
            fcurve.update()


def flush_shape_key_keyframes_to_action(
    buffer: dict[bpy.types.ShapeKey, list[tuple[float, float]]],
    clean_curves: bool = True,
) -> None:
    """Bulk-write accumulated shape key keyframes using foreach_set for performance.

    Groups shape keys by their owning Key data-block and writes all fcurves
    in batch rather than using per-frame keyframe_insert calls.

    Args:
        buffer: Maps ShapeKey references to their accumulated (frame, value) keyframes.
        clean_curves: Whether to clean redundant keyframes from curves after writing.
    """
    if not buffer:
        return

    # group shape keys by their owning Key data-block
    key_groups: dict[bpy.types.Key, list[tuple[bpy.types.ShapeKey, list[tuple[float, float]]]]] = {}
    for shape_key, keyframes in buffer.items():
        if not shape_key.id_data or not isinstance(shape_key.id_data, bpy.types.Key):
            continue

        key_id: bpy.types.Key = shape_key.id_data
        if key_id not in key_groups:
            key_groups[key_id] = []
        key_groups[key_id].append((shape_key, keyframes))

    for key_data, shape_key_entries in key_groups.items():
        if not key_data.animation_data:
            key_data.animation_data_create()
        if not key_data.animation_data:
            continue

        action = key_data.animation_data.action
        if not action:
            action = bpy.data.actions.new(name=f"{key_data.name}Action")
            key_data.animation_data.action = action

        if anim_utils:
            if len(action.slots) == 0:
                action.slots.new("KEY", name=key_data.name)
            channel_bag = anim_utils.action_ensure_channelbag_for_slot(action, action.slots[0])
            if action.slots:
                key_data.animation_data.action_slot = action.slots[0]
        else:
            channel_bag = action

        if not channel_bag:
            continue

        for shape_key, keyframes in shape_key_entries:
            data_path = shape_key.path_from_id("value")
            _bulk_write_scalar_keyframes(channel_bag, data_path, keyframes, clean_curves)


def flush_texture_mask_keyframes_to_action(
    texture_logic_node: bpy.types.ShaderNodeGroup,
    buffer: dict[str, list[tuple[float, float]]],
    action_name: str | None = None,
    clean_curves: bool = True,
) -> bpy.types.Action | None:
    """Bulk-write accumulated texture mask keyframes using foreach_set for performance.

    Args:
        texture_logic_node: The shader node group containing the mask inputs.
        buffer: Maps slider names to their accumulated (frame, value) keyframes.
        action_name: Name for the created action. Defaults to node tree name + "Action".
        clean_curves: Whether to clean redundant keyframes from curves after writing.

    Returns:
        The created or updated action, or None if the buffer is empty.
    """
    if not buffer:
        return None

    node_tree = texture_logic_node.id_data
    if not isinstance(node_tree, bpy.types.NodeTree):
        return None

    if not node_tree.animation_data:
        node_tree.animation_data_create()
    if not node_tree.animation_data:
        return None

    action = node_tree.animation_data.action
    if not action:
        action = bpy.data.actions.new(name=action_name or f"{node_tree.name}Action")
        node_tree.animation_data.action = action
        if not anim_utils:
            # blender 4.5: animation_data.action assignment does not set id_root
            action.id_root = "NODETREE"

    if anim_utils:
        if len(action.slots) == 0:
            action.slots.new("NODETREE", name=node_tree.name)
        channel_bag = anim_utils.action_ensure_channelbag_for_slot(action, action.slots[0])
        if action.slots:
            node_tree.animation_data.action_slot = action.slots[0]
    else:
        channel_bag = action

    if not channel_bag:
        return None

    for slider_name, keyframes in buffer.items():
        input_socket = texture_logic_node.inputs.get(slider_name)
        if not input_socket:
            continue
        data_path = input_socket.path_from_id("default_value")
        _bulk_write_scalar_keyframes(channel_bag, data_path, keyframes, clean_curves)

    # set the action name if provided
    if action_name:
        action.name = action_name

    return action


def bake_face_board_to_action(
    instance: "RigInstance",
    armature_object: bpy.types.Object,
    action_name: str,
    replace_action: bool,
    start_frame: int,
    end_frame: int,
    step: int = 1,
    clean_curves: bool = True,
    channel_types: set | None = None,
    masks: bool = True,
    shape_keys: bool = True,
):
    from ..ui.callbacks import get_head_texture_logic_node

    if instance:
        if channel_types is None:
            channel_types = {"LOCATION", "ROTATION", "SCALE"}

        if instance.face_board and instance.face_board.animation_data:
            source_action = instance.face_board.animation_data.action
            if not source_action or not armature_object.pose:
                return

            window_manager_properties: CharacterWindowManagerProperties = getattr(
                bpy.context.window_manager, ToolInfo.NAME
            )
            window_manager_properties.evaluate_dependency_graph = False

            # create or replace the target action for bone keyframes
            if replace_action:
                target_action = bpy.data.actions.get(action_name)
                if target_action:
                    bpy.data.actions.remove(target_action)
            target_action = bpy.data.actions.new(name=action_name)

            if anim_utils and len(target_action.slots) == 0:
                target_action.slots.new("OBJECT", name=armature_object.name)
            elif not anim_utils:
                # blender 4.5: animation_data.action assignment does not set id_root,
                # so set it explicitly so downstream code/tests can filter by it.
                target_action.id_root = "OBJECT"

            # assign the new action to the armature
            if not armature_object.animation_data:
                armature_object.animation_data_create()
            armature_object.animation_data.action = target_action  # pyright: ignore[reportOptionalMemberAccess]
            if anim_utils and target_action.slots:
                armature_object.animation_data.action_slot = target_action.slots[0]  # pyright: ignore[reportOptionalMemberAccess]

            texture_logic_node = get_head_texture_logic_node(instance.head_material)
            bone_keyframe_buffer: dict[str, dict[str, list[tuple[float, float]]]] = {}
            shape_key_buffer: dict[bpy.types.ShapeKey, list[tuple[float, float]]] = {}
            mask_buffer: dict[str, list[tuple[float, float]]] = {}

            for frame in range(start_frame, end_frame + 1):
                # modulo the step to only bake every nth frame
                if frame % step == 0:
                    bake_control_curve_values_for_frame(
                        instance=instance,
                        texture_logic_node=texture_logic_node,
                        action=source_action,
                        frame=frame,
                        shape_keys=shape_keys,
                        masks=masks,
                        bones=True,
                        bone_keyframe_buffer=bone_keyframe_buffer,
                        shape_key_buffer=shape_key_buffer,
                        mask_buffer=mask_buffer,
                        channel_types=channel_types,
                        component="head",
                    )

            # bulk-write all keyframes
            flush_bone_keyframes_to_action(target_action, bone_keyframe_buffer, clean_curves=clean_curves)

            if shape_keys:
                flush_shape_key_keyframes_to_action(shape_key_buffer, clean_curves=clean_curves)

            if texture_logic_node and masks:
                flush_texture_mask_keyframes_to_action(
                    texture_logic_node,
                    mask_buffer,
                    action_name=f"{action_name}_shader",
                    clean_curves=clean_curves,
                )

            window_manager_properties.evaluate_dependency_graph = True


def _snapshot_source_fcurves(
    source_action: bpy.types.Action,
    frames: list[int],
    bone_names: set[str] | None = None,
) -> dict[str, dict[str, dict[int, list[float]]]]:
    """Pre-evaluate all source action fcurves into pure Python data.

    This snapshots all fcurve values so the source action can be safely removed
    afterward (e.g. for replace_action=True when source == target action name).

    Args:
        source_action: The Blender action to read fcurves from.
        frames: List of frame numbers to evaluate at.
        bone_names: Optional set of bone names to include. If None, all bones are included.

    Returns:
        A nested dict: {bone_name: {channel_type: {array_index: [values_per_frame]}}}
        where channel_type is "rotation_quaternion", "location", or "scale".
    """
    snapshot: dict[str, dict[str, dict[int, list[float]]]] = {}

    if anim_utils:
        channel_bag = anim_utils.action_ensure_channelbag_for_slot(source_action, source_action.slots[0])
    else:
        channel_bag = source_action

    if not channel_bag:
        return snapshot

    for fcurve in channel_bag.fcurves:
        # parse data_path like 'pose.bones["bone_name"].rotation_quaternion'
        parts = fcurve.data_path.split('"')
        if len(parts) < 2:
            continue

        bone_name = parts[1]
        if bone_names is not None and bone_name not in bone_names:
            continue

        channel_type = fcurve.data_path.split(".")[-1]
        if channel_type not in ("rotation_quaternion", "location", "scale"):
            continue

        if bone_name not in snapshot:
            snapshot[bone_name] = {}
        if channel_type not in snapshot[bone_name]:
            snapshot[bone_name][channel_type] = {}

        # pre-evaluate all frames into a list
        snapshot[bone_name][channel_type][fcurve.array_index] = [fcurve.evaluate(f) for f in frames]

    return snapshot


def bake_body_to_action(  # noqa: PLR0912, PLR0915
    instance: "RigInstance",
    armature_object: bpy.types.Object,
    action_name: str,
    replace_action: bool,
    start_frame: int,
    end_frame: int,
    step: int = 1,
    clean_curves: bool = True,
    channel_types: set | None = None,
    masks: bool = True,  # noqa: ARG001
    shape_keys: bool = True,  # noqa: ARG001
    driver_bones: bool = True,
    driven_bones: bool = True,
    twist_bones: bool = True,
    swing_bones: bool = True,
    other_bones: bool = True,
):
    if instance and bpy.context.scene:
        if channel_types is None:
            channel_types = {"LOCATION", "ROTATION", "SCALE"}

        if instance.body_rig and armature_object.pose:
            # A control rig (e.g. a Rigify rig) drives the body rig's bones through constraints,
            # so the body rig's own bones have no local fcurves and their local rotation stays at
            # rest. When one is present and animated we must sample the evaluated (visual/world
            # space) transforms per frame and convert them back to local space, mirroring how
            # interactive evaluation reads the driver bones. Otherwise we read the driver bone
            # fcurves on the body rig's action directly.
            control_rig = instance.control_rig
            control_action = control_rig.animation_data.action if control_rig and control_rig.animation_data else None
            body_action = instance.body_rig.animation_data.action if instance.body_rig.animation_data else None
            use_visual_transforms = bool(control_rig and control_action)

            source_action = body_action or control_action
            if not source_action:
                return

            # ensure the body is initialized
            if not instance.body_initialized:
                instance.body_initialize()

            window_manager_properties: CharacterWindowManagerProperties = getattr(
                bpy.context.window_manager, ToolInfo.NAME
            )
            window_manager_properties.evaluate_dependency_graph = False
            original_frame = bpy.context.scene.frame_current

            try:
                # determine which bones RigLogic will recompute
                riglogic_bone_names: set[str] = set()
                if driven_bones:
                    riglogic_bone_names.update(instance.body_driven_bone_names)
                if twist_bones:
                    riglogic_bone_names.update(instance.body_twist_bone_names)
                if swing_bones:
                    riglogic_bone_names.update(instance.body_swing_bone_names)

                driver_bone_name_set = set(instance.body_driver_bone_names)
                all_categorized = (
                    driver_bone_name_set
                    | set(instance.body_driven_bone_names)
                    | set(instance.body_twist_bone_names)
                    | set(instance.body_swing_bone_names)
                )

                frames = [f for f in range(start_frame, end_frame + 1) if f % step == 0]

                driver_snapshot: dict[str, dict[str, dict[int, list[float]]]] = {}
                if use_visual_transforms:
                    # the body rig has no usable source action of its own; the driver/other bone
                    # values are sampled from the evaluated armature per frame below, so start
                    # from a fresh action and write everything via the keyframe buffer.
                    if replace_action:
                        existing = bpy.data.actions.get(action_name)
                        if existing:
                            bpy.data.actions.remove(existing)
                    target_action = bpy.data.actions.new(name=action_name)
                else:
                    # snapshot driver bone quaternion values for RigLogic input before
                    # the source action is potentially removed by replace_action
                    driver_snapshot = _snapshot_source_fcurves(source_action, frames, driver_bone_name_set)

                    # copy the entire source action to preserve ALL fcurves (driver bones,
                    # uncategorized bones like spine_03, custom properties, etc.)
                    target_action = source_action.copy()

                    if replace_action:
                        existing = bpy.data.actions.get(action_name)
                        if existing and existing != target_action:
                            bpy.data.actions.remove(existing)
                    target_action.name = action_name

                if anim_utils and len(target_action.slots) == 0:
                    target_action.slots.new("OBJECT", name=armature_object.name)

                # get the channel bag for fcurve manipulation
                if anim_utils:
                    channel_bag = anim_utils.action_ensure_channelbag_for_slot(target_action, target_action.slots[0])
                else:
                    channel_bag = target_action

                # the fresh action used for the visual-transform path has no pre-existing fcurves
                # to prune; everything is written from the keyframe buffer below.
                if not use_visual_transforms and channel_bag:
                    # remove fcurves for bones that RigLogic will recompute so they can
                    # be replaced with the RigLogic-calculated values
                    if riglogic_bone_names:
                        riglogic_prefixes = {f'pose.bones["{name}"]' for name in riglogic_bone_names}
                        fcurves_to_remove = [
                            fc
                            for fc in channel_bag.fcurves
                            if any(fc.data_path.startswith(p) for p in riglogic_prefixes)
                        ]
                        for fc in fcurves_to_remove:
                            channel_bag.fcurves.remove(fc)

                    # remove driver bone fcurves if not requested in the baked output
                    if not driver_bones:
                        driver_prefixes = {f'pose.bones["{name}"]' for name in driver_bone_name_set}
                        fcurves_to_remove = [
                            fc for fc in channel_bag.fcurves if any(fc.data_path.startswith(p) for p in driver_prefixes)
                        ]
                        for fc in fcurves_to_remove:
                            channel_bag.fcurves.remove(fc)

                    # remove "other" bone fcurves (bones not categorized as driver/driven/twist/swing)
                    if not other_bones:
                        fcurves_to_remove = []
                        for fc in channel_bag.fcurves:
                            parts = fc.data_path.split('"')
                            if len(parts) >= 2 and parts[1] not in all_categorized:
                                fcurves_to_remove.append(fc)
                        for fc in fcurves_to_remove:
                            channel_bag.fcurves.remove(fc)

                # compute RigLogic bone transforms per frame and accumulate
                bone_keyframe_buffer: dict[str, dict[str, list[tuple[float, float]]]] = {}

                for frame_index, frame in enumerate(frames):
                    # build RigLogic override_values from the driver bone quaternions
                    override_values: dict[str, dict[str, float]] = {}

                    if use_visual_transforms:
                        # step the scene so the control rig and its constraints evaluate, then read
                        # the body rig's evaluated (world space) transforms and convert them back to
                        # local space. This bakes the constrained driver/other bones into a
                        # standalone action and feeds the driver rotations into RigLogic.
                        bpy.context.scene.frame_set(frame)
                        depsgraph = bpy.context.evaluated_depsgraph_get()
                        evaluated = instance.body_rig.evaluated_get(depsgraph)
                        visual_transforms: list[tuple[str, Vector, Euler | Quaternion, Vector]] = []
                        if evaluated and evaluated.pose:
                            for pose_bone in evaluated.pose.bones:
                                name = pose_bone.name
                                # RigLogic recomputes these below; never bake their constrained values
                                if name in riglogic_bone_names:
                                    continue

                                is_driver = name in driver_bone_name_set
                                is_other = name not in all_categorized
                                if is_other and not other_bones:
                                    continue
                                if not is_driver and not is_other:
                                    # categorized as driven/twist/swing but excluded from the
                                    # requested RigLogic output; skip it
                                    continue

                                location, quaternion, scale = get_pose_bone_local_transform(pose_bone)

                                if is_driver:
                                    # feed the local rotation into RigLogic as a raw control input
                                    override_values[name] = {
                                        "w": quaternion.w,
                                        "x": quaternion.x,
                                        "y": quaternion.y,
                                        "z": quaternion.z,
                                    }
                                    # optionally omit the driver bones from the baked output
                                    if not driver_bones:
                                        continue

                                # respect the bone's rotation mode so the baked fcurves are honored
                                if pose_bone.rotation_mode == "QUATERNION":
                                    rotation: Euler | Quaternion = quaternion
                                else:
                                    rotation = quaternion.to_euler(pose_bone.rotation_mode)
                                visual_transforms.append((name, location, rotation, scale))

                        accumulate_bone_keyframes(visual_transforms, frame, bone_keyframe_buffer, channel_types)
                    else:
                        for bone_name in instance.body_driver_bone_names:
                            bone_data = driver_snapshot.get(bone_name, {})
                            quat_data = bone_data.get("rotation_quaternion")
                            if quat_data:
                                override_values[bone_name] = {
                                    "w": quat_data[0][frame_index] if 0 in quat_data else 1.0,
                                    "x": quat_data[1][frame_index] if 1 in quat_data else 0.0,
                                    "y": quat_data[2][frame_index] if 2 in quat_data else 0.0,
                                    "z": quat_data[3][frame_index] if 3 in quat_data else 0.0,
                                }

                    # compute driven/twist/swing bone transforms via RigLogic
                    instance.update_body_raw_control_values(override_values=override_values)
                    riglogic_transforms = instance.update_body_bone_transforms(collect_transforms=True)

                    # filter to only the requested RigLogic bone types
                    filtered_transforms = [
                        (name, location, rotation, scale)
                        for name, location, rotation, scale in riglogic_transforms
                        if name in riglogic_bone_names
                    ]
                    accumulate_bone_keyframes(filtered_transforms, frame, bone_keyframe_buffer, channel_types)

                # write RigLogic-computed bone fcurves to the target action
                flush_bone_keyframes_to_action(target_action, bone_keyframe_buffer, clean_curves=clean_curves)

                # assign the baked action to the armature
                if not armature_object.animation_data:
                    armature_object.animation_data_create()
                armature_object.animation_data.action = target_action  # pyright: ignore[reportOptionalMemberAccess]
                if anim_utils and target_action.slots:
                    armature_object.animation_data.action_slot = target_action.slots[0]  # pyright: ignore[reportOptionalMemberAccess]
            finally:
                if use_visual_transforms:
                    bpy.context.scene.frame_set(original_frame)
                window_manager_properties.evaluate_dependency_graph = True
