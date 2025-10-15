import os
import bpy
import json
import logging
from typing import TYPE_CHECKING
from pathlib import Path
from mathutils import Euler
from ..constants import (
    Axis, 
    SCALE_FACTOR,  
    EYE_AIM_BONES,
    FACE_BOARD_SWITCHES
)
from . import (
    switch_to_pose_mode,
    switch_to_object_mode,
    apply_transforms
)

if TYPE_CHECKING:
    from ..rig_logic import RigLogicInstance

logger = logging.getLogger(__name__)

def set_keys_on_bone(
        action: bpy.types.Action, 
        bone_name: str, 
        data_path: str | None, 
        axis: Axis, 
        keys: list[tuple[int, float]]
    ):
    # controls in world space like the eyes need to be scaled by down and inverted
    scale_factor = -0.01

    index_lookup = {
        'x': 0,
        'y': 1,
        'z': 2
    }
    if not data_path:
        data_path = 'location'
        scale_factor = 1.0
    elif data_path == 'rotation':
        data_path = 'rotation_euler'
    else:
        data_path = data_path.lower()

    # create the fcurve
    index = index_lookup.get(axis.lower())
    fcurve = action.fcurves.new(
        data_path=f'pose.bones["{bone_name}"].{data_path}',
        index=index
    )
    # then add as many points as keyframes
    fcurve.keyframe_points.add(len(keys))
    # then set all its values
    for (frame, value), keyframe_point in zip(keys, fcurve.keyframe_points):
        keyframe_point.co[0] = frame
        keyframe_point.co[1] = value * scale_factor

def remove_object_scale_keyframes(actions: list[bpy.types.Action]):
    for action in actions:
        for fcurve in action.fcurves:
            if fcurve.data_path == 'scale':
                action.fcurves.remove(fcurve)

def scale_object_actions(
        unordered_objects: list[bpy.types.Object], 
        actions: list[bpy.types.Action], 
        scale_factor: float
    ):
    # get the list of objects that do not have parents
    no_parents = [unordered_object for unordered_object in unordered_objects if not unordered_object.parent]

    # get the list of objects that have parents
    parents = [unordered_object for unordered_object in unordered_objects if unordered_object.parent]

    # re-order the imported objects to have the top of the hierarchies iterated first
    ordered_objects = no_parents + parents

    for ordered_object in ordered_objects:
        # run the export iteration but with "scale" set to the scale of the object as it was imported
        scale = (
            ordered_object.scale[0] * scale_factor,
            ordered_object.scale[1] * scale_factor,
            ordered_object.scale[2] * scale_factor
        )

        # if the imported object is an armature
        if ordered_object.type == 'ARMATURE':
            # iterate over any imported actions first this time...
            for action in actions:
                # iterate through the location curves
                for fcurve in [fcurve for fcurve in action.fcurves if fcurve.data_path.endswith('location')]:
                    # the location fcurve of the object
                    if fcurve.data_path == 'location':
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

def convert_action_rotation_from_euler_to_quaternion(
        action: bpy.types.Action, 
        bone_names: list[str] | None = None
    ):
    rotation_curves_by_bone = {}
    if bone_names is None:
        bone_names = []

    for fcurve in action.fcurves:
        # save the euler rotation curves by bone for later conversion
        if 'rotation_euler' in fcurve.data_path:
            bone_name = fcurve.data_path.split('"')[1]
            # if we have a list of bone names to filter by, skip any that are not in the list
            if bone_name not in bone_names:
                continue

            rotation_curves_by_bone[bone_name] = rotation_curves_by_bone.get(bone_name, {})
            rotation_curves_by_bone[bone_name][fcurve.array_index] = fcurve
    
    # convert euler curves to quaternion curves
    for bone_name, euler_curves in rotation_curves_by_bone.items():
        # collect all frames from all euler curves
        frames = set()
        for fcurve in euler_curves.values():
            for keyframe in fcurve.keyframe_points:
                frames.add(int(keyframe.co[0]))
        
        # create quaternion fcurves
        quat_fcurves = {}
        for i in range(4):  # w, x, y, z
            quat_fcurves[i] = action.fcurves.new(
                data_path=f'pose.bones["{bone_name}"].rotation_quaternion',
                index=i
            )
            quat_fcurves[i].keyframe_points.add(len(frames))
        
        # convert euler values to quaternion for each frame
        for frame_idx, frame in enumerate(sorted(frames)):
            euler_values = [0.0, 0.0, 0.0]
            for axis, fcurve in euler_curves.items():
                euler_values[axis] = fcurve.evaluate(frame)
            
            # convert euler to quaternion
            euler = Euler(euler_values, 'XYZ')
            quat = euler.to_quaternion()
            
            # set quaternion keyframe values
            for i, value in enumerate([quat.w, quat.x, quat.y, quat.z]):
                quat_fcurves[i].keyframe_points[frame_idx].co = (frame, value)
        
        # remove original euler curves
        for fcurve in euler_curves.values():
            action.fcurves.remove(fcurve)

def import_action_from_fbx(
        file_path: Path, 
        armature: bpy.types.Object,
        include_only_bones: list[str] | None = None
    ) -> bpy.types.Action:
    file_path = Path(file_path)

    # remove the action if it already exists
    new_action = bpy.data.actions.get(file_path.stem)
    if new_action:
        bpy.data.actions.remove(new_action)
    new_action = bpy.data.actions.new(name=file_path.stem)

    # remember the current actions and objects
    current_actions = [action for action in bpy.data.actions]
    current_objects = [scene_object for scene_object in bpy.data.objects]
    # remember the current frame rate
    current_frame_rate = bpy.context.scene.render.fps # type: ignore
    # then import the fbx
    bpy.ops.import_scene.fbx(filepath=str(file_path))

    # apply the scale fixes since this was exported from unreal at 100x scale
    imported_objects = [obj for obj in bpy.data.objects if obj not in current_objects]
    imported_actions = [action for action in bpy.data.actions if action not in current_actions]
    scale_object_actions(
        unordered_objects=imported_objects,
        actions=imported_actions,
        scale_factor=SCALE_FACTOR
    )
    remove_object_scale_keyframes(actions=imported_actions)

    # get the frame rate of the imported fbx
    imported_frame_rate = bpy.context.scene.render.fps # type: ignore
    # calculate the frame scale factor
    frame_scale_factor = current_frame_rate / imported_frame_rate
    # restore the original frame rate
    bpy.context.scene.render.fps = current_frame_rate # type: ignore

    # copy all the fcurves from the imported action to the new one
    for action in bpy.data.actions:
        if action in current_actions:
            continue

        for source_fcurve in action.fcurves:
            if len(source_fcurve.data_path.split('"')) > 1:
                bone_name = source_fcurve.data_path.split('"')[1]
                curve_name = source_fcurve.data_path.split('.')[-1]

                if not armature.pose.bones.get(bone_name): # type: ignore
                    logger.warning(f'Skipping fcurve for unknown bone: {bone_name}')
                    continue

                if include_only_bones and bone_name not in include_only_bones:
                    continue

                target_fcurve = new_action.fcurves.new(
                    data_path=f'pose.bones["{bone_name}"].{curve_name}',
                    index=source_fcurve.array_index
                )
                # then add as many points as keyframes
                target_fcurve.keyframe_points.add(len(source_fcurve.keyframe_points))
                # then set all all their values
                for index, keyframe in enumerate(source_fcurve.keyframe_points):
                    # Adjust keyframe position based on frame rate scale factor
                    target_fcurve.keyframe_points[index].co = (keyframe.co[0] * frame_scale_factor, keyframe.co[1])
                    target_fcurve.keyframe_points[index].interpolation = keyframe.interpolation

    # assign the new action to as the current action of the armature
    if not armature.animation_data:
        armature.animation_data_create()
    armature.animation_data.action = new_action # type: ignore
    armature.animation_data.action_slot = new_action.slots[0] # type: ignore

    # # remove the imported actions
    for action in bpy.data.actions:
        if action not in current_actions:
            bpy.data.actions.remove(action, do_unlink=True)

    # remove the imported objects
    for scene_object in bpy.data.objects:
        if scene_object not in current_objects:
            bpy.data.objects.remove(scene_object, do_unlink=True)

    return new_action


def import_face_board_action_from_fbx(
        file_path: Path, 
        armature: bpy.types.Object,
        round_sub_frames: bool = True,
        match_frame_rate: bool = True
    ):
    file_path = Path(file_path)

    # remove the action if it already exists
    face_board_action = bpy.data.actions.get(file_path.stem)
    if face_board_action:
        bpy.data.actions.remove(face_board_action)
    face_board_action = bpy.data.actions.new(name=file_path.stem)

    # remember the current actions and objects
    current_actions = [action for action in bpy.data.actions]
    current_objects = [scene_object for scene_object in bpy.data.objects]
    # remember the current frame rate
    current_frame_rate = bpy.context.scene.render.fps # type: ignore
    # then import the fbx
    bpy.ops.import_scene.fbx(filepath=str(file_path))
    # get the frame rate of the imported fbx
    imported_frame_rate = bpy.context.scene.render.fps # type: ignore
    # calculate the frame scale factor
    if match_frame_rate:
        frame_scale_factor = current_frame_rate / imported_frame_rate
    else:
        frame_scale_factor = 1.0
    # restore the original frame rate
    bpy.context.scene.render.fps = current_frame_rate # type: ignore

    # copy all the fcurves from the imported action to the new one
    for action in bpy.data.actions:
        if action in current_actions:
            continue

        curve_name = action.name.split('.')[0]

        # skip any eye aim controls
        if curve_name in EYE_AIM_BONES + FACE_BOARD_SWITCHES + ['CTRL_C_eye']:
            continue

        for source_fcurve in action.fcurves:
            target_fcurve = face_board_action.fcurves.new(
                data_path=f'pose.bones["{curve_name}"].{source_fcurve.data_path}',
                index=source_fcurve.array_index
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
    armature.animation_data.action = face_board_action # type: ignore

def import_face_board_action_from_json(file_path: Path, armature: bpy.types.Object):
    # create animation data if it does not exist
    if not armature.animation_data:
        armature.animation_data_create()

    # create action
    action_name = os.path.basename(file_path).split('.')[0]
    action = bpy.data.actions.get(action_name)
    if not action:
        action = bpy.data.actions.new(action_name) # type: ignore

    # delete all existing fcurves
    for fcurve in action.fcurves:
        action.fcurves.remove(fcurve)

    # ensure all bones are using euler xyz rotation
    for pose_bone in armature.pose.bones: # type: ignore
        pose_bone.rotation_mode = 'XYZ'

    with open(file_path, 'r') as file:
        data = json.load(file)
        for curve_name, keys in data.items():
            bone_name = None
            axis = None
            data_path = None

            chunks = curve_name.split('.')
            if len(chunks) == 3:
                bone_name, data_path, axis = chunks
            elif len(chunks) == 2:
                bone_name, axis = chunks
            elif len(chunks) == 1:
                bone_name = curve_name
                axis = 'Y'

            if bone_name and axis:
                set_keys_on_bone(
                    action=action,
                    bone_name=bone_name,
                    data_path=data_path,
                    axis=axis,
                    keys=keys
                )
            else:
                logger.error(f'failed to parse args from curve {curve_name}')

    armature.animation_data.action = action # type: ignore

def bake_control_curve_values_for_frame(
        instance: 'RigLogicInstance', 
        texture_logic_node: bpy.types.ShaderNodeGroup | None,
        action: bpy.types.Action, 
        frame: int,
        masks: bool = True,
        shape_keys: bool = True
    ):
    index_lookup = {
        0: 'x',
        1: 'y',
        2: 'z'
    }
    control_curve_values = {}

    for fcurve in action.fcurves:
        # type: ignore
        control_curve_name, transform = fcurve.data_path.split('"].')
        if transform == 'location' and fcurve.array_index != 2:
            control_curve_name = control_curve_name.replace('pose.bones["', '')
            axis = index_lookup[fcurve.array_index]
            
            control_curve_values[control_curve_name] = control_curve_values.get(control_curve_name, {})
            control_curve_values[control_curve_name].update({
                axis: fcurve.evaluate(frame)
            })

    # set and update the control curve values based on the fcurve values
    instance.update_head_gui_control_values(override_values=control_curve_values)
    
    # now get the calculated values and bake them to the shape keys value
    if shape_keys:
        for shape_key, value in instance.update_head_shape_keys():
            shape_key.value = value
            shape_key.keyframe_insert(data_path="value", frame=frame)

    # now bake the texture mask values
    if texture_logic_node and masks:
        for slider_name, value in instance.update_head_texture_masks():
            texture_logic_node.inputs[slider_name].default_value = value # type: ignore
            texture_logic_node.inputs[slider_name].keyframe_insert(
                data_path="default_value", 
                frame=frame
            )

def bake_to_action(
        armature_object: bpy.types.Object,
        action_name: str,
        start_frame: int,
        end_frame: int,
        step: int = 1,
        clean_curves: bool = True,
        channel_types: set | None = None,
        masks: bool = True,
        shape_keys: bool = True
    ):
    from ..ui.callbacks import get_active_rig_logic, get_head_texture_logic_node

    instance = get_active_rig_logic()
    if instance:
        if channel_types is None:
            channel_types = {"LOCATION", "ROTATION", "SCALE"}

        if instance.face_board and instance.face_board.animation_data:
            action = instance.face_board.animation_data.action
            if not action:
                return
            
            instance.auto_evaluate_head = True            
            switch_to_object_mode()
            armature_object.hide_set(False)
            bpy.context.view_layer.objects.active = armature_object # type: ignore
            switch_to_pose_mode(armature_object)
            
            # select all facial bones that are effected by rig logic
            for bone in armature_object.data.bones: # type: ignore
                if bone.name.startswith('FACIAL_'):
                    bone.select = True
                    bone.select_head = True
                    bone.select_tail = True
                else:
                    bone.select = False
                    bone.select_head = False
                    bone.select_tail = False

            # bake the visual keying of the pose bones
            bpy.ops.nla.bake(
                frame_start=start_frame,
                frame_end=end_frame,
                step=step,
                only_selected=True,
                visual_keying=True,
                use_current_action=True,
                bake_types={'POSE'},
                clean_curves=clean_curves,
                channel_types=channel_types
            )
            instance.auto_evaluate_head = False

            bpy.context.window_manager.meta_human_dna.evaluate_dependency_graph = False # type: ignore
            texture_logic_node = get_head_texture_logic_node(instance.head_material)
            for frame in range(start_frame, end_frame + 1): # type: ignore
                # modulo the step to only bake every nth frame
                if frame % step == 0:
                    bake_control_curve_values_for_frame(
                        instance=instance,
                        texture_logic_node=texture_logic_node,
                        action=action,
                        frame=frame,
                        shape_keys=shape_keys,
                        masks=masks
                    )

            action.name = action_name
            bpy.context.window_manager.meta_human_dna.evaluate_dependency_graph = True # type: ignore