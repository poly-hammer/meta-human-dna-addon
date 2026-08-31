import bpy

from mathutils import Euler, Vector

from character_dna.utilities import apply_pose


def apply_bone_transform(
    prefix: str,
    component: str,
    bone_name: str,
    location: Vector,
    rotation: Euler,
):
    rig_object = bpy.data.objects[f"{prefix}_{component}_rig"]
    rig_object.pose.bones[bone_name].location = location  # type: ignore
    rig_object.pose.bones[bone_name].rotation_euler = rotation  # type: ignore
    apply_pose(rig_object)


def apply_vertex_transform(prefix: str, mesh_name: str, vertex_index: int, location: Vector):
    mesh_object = bpy.data.objects[f"{prefix}_{mesh_name}"]
    mesh_object.data.vertices[vertex_index].co = location  # type: ignore


def apply_vertex_normal(prefix: str, mesh_name: str, vertex_index: int, normal: Vector):
    """Point one vertex's custom split normal somewhere new on every corner that uses it.

    The DNA gives a normal per face corner, so this rewrites the whole corner array and hands
    it back -- there is no per-corner setter.
    """
    mesh_object = bpy.data.objects[f"{prefix}_{mesh_name}"]
    mesh = mesh_object.data
    # corner_normals is recomputed on demand, so take a copy before invalidating it.
    normals = [tuple(corner.vector) for corner in mesh.corner_normals]  # type: ignore[attr-defined]
    for loop_index, loop in enumerate(mesh.loops):  # type: ignore[attr-defined]
        if loop.vertex_index == vertex_index:
            normals[loop_index] = tuple(normal)
    mesh.normals_split_custom_set(normals)  # type: ignore[attr-defined]


def apply_vertex_group_weight(
    prefix: str,
    mesh_name: str,
    vertex_group_name: str,
    vertex_index: int,
    weight: float,
):
    mesh_object = bpy.data.objects[f"{prefix}_{mesh_name}"]
    vertex_group = mesh_object.vertex_groups.get(vertex_group_name)
    vertex_group.add(index=[vertex_index], weight=weight, type="REPLACE")
