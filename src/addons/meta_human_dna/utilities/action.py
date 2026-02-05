# standard library imports
import json
import logging

from pathlib import Path

# third party imports
import bpy

from mathutils import Quaternion

# local imports
from ..constants import EYE_AIM_BONES, FACE_BOARD_SWITCHES, IS_BLENDER_5, SCALE_FACTOR, Axis, ComponentType, ToolInfo
from ..typing import *  # noqa: F403
from .misc import apply_transforms, switch_to_object_mode, switch_to_pose_mode


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

        # TODO: Change this to actually support these?
        # skip any eye aim controls
        if curve_name in EYE_AIM_BONES + FACE_BOARD_SWITCHES + ["CTRL_C_eye"]:
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


def bake_control_curve_values_for_frame(
    instance: "RigInstance",
    texture_logic_node: bpy.types.ShaderNodeGroup | None,
    action: bpy.types.Action,
    frame: int,
    masks: bool = True,
    shape_keys: bool = True,
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
            for shape_key, value in instance.update_head_shape_keys():
                shape_key.value = value
                shape_key.keyframe_insert("value", frame=frame)
        elif component == "body":
            # TODO: implement body shape key baking
            pass

    # now bake the texture mask values
    if texture_logic_node and masks:
        if component == "head":
            for slider_name, value in instance.update_head_texture_masks():
                texture_logic_node.inputs[slider_name].default_value = value  # type: ignore[attr-defined]
                texture_logic_node.inputs[slider_name].keyframe_insert("default_value", frame=frame)
        elif component == "body":
            # TODO: implement body texture mask baking
            pass


def bake_face_board_to_action(  # noqa: PLR0912
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
            action = instance.face_board.animation_data.action
            if not action or not armature_object.pose:
                return

            instance.auto_evaluate_head = True
            switch_to_object_mode()
            armature_object.hide_set(False)
            if bpy.context.view_layer:
                bpy.context.view_layer.objects.active = armature_object
            switch_to_pose_mode(armature_object)

            # TODO: Do we want to provide more granular control over which bones to bake?
            # collect all bone names to be baked
            baked_bone_names = [bone.name for bone in armature_object.data.bones]  # type: ignore[attr-defined]

            # select all secondary bones that are effected by rig logic
            for pose_bone in armature_object.pose.bones:
                if pose_bone.name in baked_bone_names:
                    if IS_BLENDER_5:
                        pose_bone.select = True  # pyright: ignore[reportAttributeAccessIssue]
                    else:
                        pose_bone.bone.select = True
                        pose_bone.bone.select_head = True
                        pose_bone.bone.select_tail = True
                elif IS_BLENDER_5:
                    pose_bone.select = False  # pyright: ignore[reportAttributeAccessIssue]
                else:
                    pose_bone.bone.select = False
                    pose_bone.bone.select_head = False
                    pose_bone.bone.select_tail = False

            if IS_BLENDER_5:
                current_object_actions = [
                    a for a in bpy.data.actions if len(a.slots) > 0 and a.slots[0].target_id_type == "OBJECT"
                ]
                current_node_tree_actions = [
                    a for a in bpy.data.actions if len(a.slots) > 0 and a.slots[0].target_id_type == "NODETREE"
                ]
            else:
                current_object_actions = [a for a in bpy.data.actions if a.id_root == "OBJECT"]
                current_node_tree_actions = [a for a in bpy.data.actions if a.id_root == "NODETREE"]

            # bake the visual keying of the pose bones
            bpy.ops.nla.bake(
                frame_start=start_frame,
                frame_end=end_frame,
                step=step,
                only_selected=True,
                visual_keying=True,
                use_current_action=replace_action,
                bake_types={"POSE"},
                clean_curves=clean_curves,
                channel_types=channel_types,
            )
            instance.auto_evaluate_head = False

            window_manager_properties: MetahumanWindowMangerProperties = getattr(
                bpy.context.window_manager, ToolInfo.NAME
            )
            window_manager_properties.evaluate_dependency_graph = False
            texture_logic_node = get_head_texture_logic_node(instance.head_material)
            for frame in range(start_frame, end_frame + 1):
                # modulo the step to only bake every nth frame
                if frame % step == 0:
                    bake_control_curve_values_for_frame(
                        instance=instance,
                        texture_logic_node=texture_logic_node,
                        action=action,
                        frame=frame,
                        shape_keys=shape_keys,
                        masks=masks,
                        component="head",
                    )

            # rename the newly created object action
            for _action in bpy.data.actions:
                if (
                    getattr(_action, "id_root", None) == "OBJECT"
                    or (len(_action.slots) > 0 and _action.slots[0].target_id_type == "OBJECT")
                ) and _action not in current_object_actions:
                    _action.name = action_name
                    break

            # rename the newly created node tree action
            for _action in bpy.data.actions:
                if (
                    getattr(_action, "id_root", None) == "NODETREE"
                    or (len(_action.slots) > 0 and _action.slots[0].target_id_type == "NODETREE")
                ) and _action not in current_node_tree_actions:
                    _action.name = f"{action_name}_shader"
                    break

            # cleanup old action if replacing
            if replace_action:
                old_action = instance.face_board.animation_data.action
                instance.face_board.animation_data_clear()
                bpy.data.actions.remove(old_action, do_unlink=True)

            window_manager_properties.evaluate_dependency_graph = True


def bake_body_to_action(  # noqa: PLR0912
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
    if instance:
        if channel_types is None:
            channel_types = {"LOCATION", "ROTATION", "SCALE"}

        if instance.body_rig and instance.body_rig.animation_data and armature_object.pose:
            action = instance.body_rig.animation_data.action
            if not action:
                return

            instance.auto_evaluate_body = True
            switch_to_object_mode()
            armature_object.hide_set(False)
            if bpy.context.view_layer:
                bpy.context.view_layer.objects.active = armature_object
            switch_to_pose_mode(armature_object)

            # ensure the body is initialized
            if not instance.body_initialized:
                instance.body_initialize()

            # collect all bone names to be baked
            baked_bone_names = []
            if driven_bones:
                baked_bone_names += instance.body_driven_bone_names
            if twist_bones:
                baked_bone_names += instance.body_twist_bone_names
            if swing_bones:
                baked_bone_names += instance.body_swing_bone_names
            if driver_bones:
                baked_bone_names += instance.body_driver_bone_names
            if other_bones:
                # these are bones that are not any of the above
                baked_bone_names += [
                    bone.name
                    for bone in armature_object.data.bones  # type: ignore[attr-defined]
                    if bone.name
                    not in [
                        *instance.body_driver_bone_names,
                        *instance.body_driven_bone_names,
                        *instance.body_twist_bone_names,
                        *instance.body_swing_bone_names,
                    ]
                ]

            # select all secondary bones that are effected by rig logic
            for pose_bone in armature_object.pose.bones:
                if pose_bone.name in baked_bone_names:
                    if IS_BLENDER_5:
                        pose_bone.select = True  # pyright: ignore[reportAttributeAccessIssue]
                    else:
                        pose_bone.bone.select = True
                        pose_bone.bone.select_head = True
                        pose_bone.bone.select_tail = True
                elif IS_BLENDER_5:
                    pose_bone.select = False  # pyright: ignore[reportAttributeAccessIssue]
                else:
                    pose_bone.bone.select = False
                    pose_bone.bone.select_head = False
                    pose_bone.bone.select_tail = False

            if IS_BLENDER_5:
                current_object_actions = [
                    a for a in bpy.data.actions if len(a.slots) > 0 and a.slots[0].target_id_type == "OBJECT"
                ]
                current_node_tree_actions = [
                    a for a in bpy.data.actions if len(a.slots) > 0 and a.slots[0].target_id_type == "NODETREE"
                ]
            else:
                current_object_actions = [a for a in bpy.data.actions if a.id_root == "OBJECT"]
                current_node_tree_actions = [a for a in bpy.data.actions if a.id_root == "NODETREE"]

            # bake the visual keying of the pose bones
            bpy.ops.nla.bake(
                frame_start=start_frame,
                frame_end=end_frame,
                step=step,
                only_selected=True,
                visual_keying=True,
                use_current_action=replace_action,
                bake_types={"POSE"},
                clean_curves=clean_curves,
                channel_types=channel_types,
            )
            instance.auto_evaluate_body = False

            # rename the newly created action
            if replace_action:
                action.name = action_name
            else:
                # rename the newly created object action
                for _action in bpy.data.actions:
                    if (
                        getattr(_action, "id_root", None) == "OBJECT"
                        or (len(_action.slots) > 0 and _action.slots[0].target_id_type == "OBJECT")
                    ) and _action not in current_object_actions:
                        _action.name = action_name
                        break

            # rename the newly created node tree action
            for _action in bpy.data.actions:
                if (
                    getattr(_action, "id_root", None) == "NODETREE"
                    or (len(_action.slots) > 0 and _action.slots[0].target_id_type == "NODETREE")
                ) and _action not in current_node_tree_actions:
                    _action.name = f"{action_name}_shader"
                    break
