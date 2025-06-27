import os
import bpy
import json
import logging
from typing import TYPE_CHECKING
from pathlib import Path
from ..constants import Axis
from . import (
    switch_to_pose_mode,
    switch_to_object_mode
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


def import_action_from_fbx(file_path: Path, armature: bpy.types.Object):
    file_path = Path(file_path)

    # remove the action if it already exists
    face_board_action = bpy.data.actions.get(file_path.stem)
    if face_board_action:
        bpy.data.actions.remove(face_board_action)
    face_board_action = bpy.data.actions.new(name=file_path.stem)

    # remember the current actions and objects
    current_actions = [action for action in bpy.data.actions]
    current_objects = [scene_object for scene_object in bpy.data.objects]
    # then import the fbx
    bpy.ops.import_scene.fbx(filepath=str(file_path))

    # copy all the fcurves from the imported action to the new one
    for action in bpy.data.actions:
        if action in current_actions:
            continue

        curve_name = action.name.split('.')[0]
        for source_fcurve in action.fcurves:
            target_fcurve = face_board_action.fcurves.new(
                data_path=f'pose.bones["{curve_name}"].{source_fcurve.data_path}',
                index=source_fcurve.array_index
            )
            # then add as many points as keyframes
            target_fcurve.keyframe_points.add(len(source_fcurve.keyframe_points))
            # then set all all their values
            for index, keyframe in enumerate(source_fcurve.keyframe_points):
                target_fcurve.keyframe_points[index].co = keyframe.co
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


def import_action_from_json(file_path: Path, armature: bpy.types.Object):
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
    instance.update_gui_control_values(override_values=control_curve_values)
    
    # now get the calculated values and bake them to the shape keys value
    if shape_keys:
        for shape_key, value in instance.update_shape_keys():
            shape_key.value = value
            shape_key.keyframe_insert(data_path="value", frame=frame)

    # now bake the texture mask values
    if texture_logic_node and masks:
        for slider_name, value in instance.update_texture_masks():
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
            
            instance.auto_evaluate = True            
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
            instance.auto_evaluate = False

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