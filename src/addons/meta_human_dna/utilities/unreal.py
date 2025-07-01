import sys
import logging
import bpy
from pathlib import Path
from ..constants import EXTRA_BONES
from . import (
    send2ue_addon_is_valid,
    switch_to_pose_mode,
    apply_transforms,
    preserve_context
)
from mathutils import Vector


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..rig_logic import RigLogicInstance

logger = logging.getLogger(__name__)

def convert_unreal_to_blender_location(location) -> Vector:
    x = location[0] / 100
    y = location[1] / 100
    z = location[2] / 100
    return Vector((x, -y, z))

@preserve_context
def sync_spine_with_body_skeleton(instance: 'RigLogicInstance'):
    if instance.unreal_blueprint_asset_path and send2ue_addon_is_valid():
        from send2ue.dependencies.rpc.factory import make_remote # type: ignore
        from send2ue.dependencies.unreal import bootstrap_unreal_with_rpc_server # type: ignore

        import meta_human_dna_utilities
        folder = Path(meta_human_dna_utilities.__file__).parent.parent
        if Path(folder) not in [Path(path) for path in sys.path]:
            sys.path.append(str(folder))

        from meta_human_dna_utilities import get_body_bone_transforms

        bootstrap_unreal_with_rpc_server()
        remote_get_body_bone_transforms = make_remote(get_body_bone_transforms)
        bone_transforms = remote_get_body_bone_transforms(str(instance.unreal_blueprint_asset_path))
        
        instance.head_rig.hide_set(False)
        switch_to_pose_mode(instance.head_rig)

        # deselect all bones
        for bone in instance.head_rig.data.bones:
            bone.select = False
            bone.select_head = False
            bone.select_tail = False

        total_delta = Vector((0, 0, 0))
        for bone_name, _ in EXTRA_BONES:
            bone_data = bone_transforms.get(bone_name, {})
            instance.head_rig.hide_set(False)
            pose_bone = instance.head_rig.pose.bones.get(bone_name)
            if pose_bone and bone_data:
                unreal_location = convert_unreal_to_blender_location(bone_data['location'])
                blender_location = pose_bone.matrix.translation.copy()
                delta = unreal_location - blender_location
                # To avoid floating point value drift, set a minimum value for 
                # the delta to be considered "changed"
                if delta.length > 1e-3:
                    total_delta += delta
                    logger.info(f'Updating bone "{bone_name}" to world position {unreal_location.to_tuple()}')
                    # set the bone location
                    pose_bone.matrix.translation = unreal_location
                    # then select the bone
                    pose_bone.bone.select = True
                    pose_bone.bone.select_head = True
                    pose_bone.bone.select_tail = True

                    # apply the pose only to the selected bones
                    bpy.ops.pose.armature_apply(selected=True)

        if total_delta.length > 1e-3:
            # now update the head mesh positions based on the total delta
            for output_item in instance.output_head_item_list:
                if output_item.scene_object and output_item.scene_object.type == 'MESH':
                    output_item.scene_object.location += total_delta
                    apply_transforms(output_item.scene_object, location=True)

            # adjust the face board location
            if instance.face_board:
                # un-parent the face board children
                children = [i for i in instance.face_board.children]
                for child in children:
                    child.parent = None
                # move the face board                
                instance.face_board.location += total_delta
                apply_transforms(instance.face_board, location=True)
                # re-parent the children
                for child in children:
                    child.parent = instance.face_board

