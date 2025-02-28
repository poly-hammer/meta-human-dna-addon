import unreal


def get_bone_transforms(skinned_mesh_component: unreal.SkinnedMeshComponent) -> dict:
    bone_transforms = {}
    for bone_index in range(skinned_mesh_component.get_num_bones()):
        bone_name = skinned_mesh_component.get_bone_name(bone_index)
        skeleton = skinned_mesh_component.skeletal_mesh.skeleton
        if not skeleton:
            continue

        anim_pose = skeleton.get_reference_pose()
        for bone_name in anim_pose.get_bone_names():
            transform = anim_pose.get_bone_pose(bone_name, space=unreal.AnimPoseSpaces.WORLD)
            transform.translation
            bone_transforms[str(bone_name)] = {
                'location': transform.translation.to_tuple(),
                'rotation': transform.rotation.to_tuple(),
                'scale': transform.scale3d.to_tuple()
            }
    return bone_transforms