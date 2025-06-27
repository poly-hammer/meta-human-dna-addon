import bpy
from mathutils import Vector, Euler
from meta_human_dna.utilities import apply_pose

def apply_bone_transform(
        prefix: str, 
        component: str, 
        bone_name: str, 
        location: Vector,
        rotation: Euler,
    ):
    rig_object = bpy.data.objects[f'{prefix}_{component}_rig']
    rig_object.pose.bones[bone_name].location = location # type: ignore
    rig_object.pose.bones[bone_name].rotation_euler = rotation # type: ignore
    apply_pose(rig_object)
    

def apply_vertex_transform(
        prefix: str, 
        mesh_name: str, 
        vertex_index: int, 
        location: Vector
    ):
    mesh_object = bpy.data.objects[f'{prefix}_{mesh_name}']
    mesh_object.data.vertices[vertex_index].co = location # type: ignore
