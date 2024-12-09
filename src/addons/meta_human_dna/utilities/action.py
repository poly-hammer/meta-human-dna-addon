import os
import bpy
import json
import logging
from pathlib import Path
from ..constants import Axis

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

def get_animation_curves_from_fbx(file_path: Path) -> dict:
    current_actions = [action for action in bpy.data.actions]
    current_objects = [scene_object for scene_object in bpy.data.objects]
    bpy.ops.import_scene.fbx(filepath=str(file_path))
    
    post_fix = '|Unreal Take|Base Layer'
    curves = {}

    axis_lookup = {
         0:'x',
         1:'y',
         2:'z'
    }

    for action in bpy.data.actions:
        if action.name.endswith(post_fix):
            curve_name = action.name.replace(post_fix, '').split('.')[0]
            curves[curve_name] = {}
            for fcurve in action.fcurves:
                curves[curve_name][fcurve.data_path] = curves[curve_name].get(fcurve.data_path, {})
                axis = axis_lookup.get(fcurve.array_index)
                curves[curve_name][fcurve.data_path][axis] = [
                    (keyframe.co[0], keyframe.co[1]) for keyframe in fcurve.keyframe_points
                ]

    # remove the imported objects
    for scene_object in bpy.data.objects:
        if scene_object not in current_objects:
            bpy.data.objects.remove(scene_object)
    # remove the imported actions
    for action in bpy.data.actions:
        if action not in current_actions:
            bpy.data.actions.remove(action)

    return curves


def import_action_from_fbx(file_path: Path, armature: bpy.types.Object):
    file_path = Path(file_path)
    curves = get_animation_curves_from_fbx(file_path)

    # remove the action if it already exists
    action = bpy.data.actions.get(file_path.stem)
    if action:
        bpy.data.actions.remove(action)
    action = bpy.data.actions.new(name=file_path.stem)

    for curve_name, curve_data in curves.items():
        for data_path, axis_data in curve_data.items():
            for axis, keys in axis_data.items():
                set_keys_on_bone(
                    action=action, 
                    bone_name=curve_name, 
                    data_path=data_path, 
                    axis=axis, 
                    keys=keys
                )

    if not armature.animation_data:
        armature.animation_data_create()

    armature.animation_data.action = action


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
    for pose_bone in armature.pose.bones:
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

    armature.animation_data.action = action