import re
import bpy
import json
import math
import bmesh
import logging
from pathlib import Path
from mathutils import Vector, Matrix
from bpy_extras.bmesh_utils import bmesh_linked_uv_islands
from .misc import (
    exclude_rig_logic_evaluation,
    switch_to_edit_mode,
    switch_to_object_mode,
    preserve_context
)
from ..constants import (
    LOD_REGEX,
    SHAPE_KEY_BASIS_NAME,
    Axis
)


logger = logging.getLogger(__name__)


@exclude_rig_logic_evaluation
def initialize_basis_shape_key(mesh_object: bpy.types.Object) -> bpy.types.Key:
    """
    Get the shape key that has the mesh as its user. If the shape 
    key does not exist, it will be created.

    Args:
        mesh_object (bpy.types.Object): The mesh object.

    Returns:
        bpy.types.Key: The shape key that has the mesh as its user.
    """
    if not mesh_object:
        logger.warning("Mesh object not found in scene that matches DNA. Skipping initialization of basis shape key.")
        return

    # clear all shape keys
    mesh_object.shape_key_clear()
        
    # create the basis shape key
    shape_key_block = mesh_object.shape_key_add(name=SHAPE_KEY_BASIS_NAME)
    # mesh_object.data.shape_keys.use_relative = False
    shape_key = shape_key_block.id_data

    # set the shape key name to the mesh object name
    shape_key.name = mesh_object.name

    return shape_key

def update_mesh(mesh_object: bpy.types.Object):
    depth = bpy.context.evaluated_depsgraph_get() # type: ignore
    depth.update()
    mesh_object.update_tag()
    bpy.context.view_layer.update() # type: ignore
    mesh_object.data.update() # type: ignore


def delete_vertices_by_index(
        mesh_object: bpy.types.Object, 
        vertex_indexes: list[int],
        inverse: bool = False
    ):
    # get the mesh data
    mesh_data = mesh_object.data 
    # get the bmesh data
    bmesh_data = bmesh.new()
    bmesh_data.from_mesh(mesh_data) # type: ignore

    bmesh_data.verts.ensure_lookup_table()
    # get the vertices to delete
    if inverse:
        vertices_to_delete = [i for i in bmesh_data.verts if i.index not in vertex_indexes]
    else:
        vertices_to_delete = [bmesh_data.verts[i] for i in vertex_indexes]

    # delete the vertices
    bmesh.ops.delete(bmesh_data, geom=vertices_to_delete, context='VERTS')
    # update the mesh data
    bmesh_data.to_mesh(mesh_data) # type: ignore
    # free the bmesh data
    bmesh_data.free()


def update_vertex_positions(
        mesh_object: bpy.types.Object, 
        vertex_indices: list[int],
        offset: Vector = Vector((0, 0, 0))
    ):
    # get the bmesh data
    bmesh_object = bmesh.new()
    bmesh_object.from_mesh(mesh_object.data) # type: ignore

    bmesh_object.verts.ensure_lookup_table()
    for vertex_index in vertex_indices:
        vert = bmesh_object.verts[vertex_index]
        vert.co += offset

    bmesh_object.to_mesh(mesh_object.data) # type: ignore
    bmesh_object.free()

def get_middle_vertices(mesh_object: bpy.types.Object) -> list[int]:
    verts = []
    # get the mesh data
    mesh_data = mesh_object.data 
    # get the bmesh data
    bmesh_data = bmesh.new()
    bmesh_data.from_mesh(mesh_data) # type: ignore

    bmesh_data.verts.ensure_lookup_table()
    for vert in bmesh_data.verts:
        if  0.001 > vert.co.x > -0.001:
            verts.append(vert.index)

    bmesh_data.free()

    return verts

def zero_x_on_middle_vertices(mesh_object: bpy.types.Object, threshold: float = 0.001):
    # get the mesh data
    mesh_data = mesh_object.data 
    # get the bmesh data
    bmesh_data = bmesh.new()
    bmesh_data.from_mesh(mesh_data) # type: ignore

    bmesh_data.verts.ensure_lookup_table()
    for vert in bmesh_data.verts:
        if  threshold > vert.co.x > -threshold:
            vert.co.x = 0.0

    bmesh_data.to_mesh(mesh_data) # type: ignore
    # free the bmesh data
    bmesh_data.free()


def set_vertex_selection(
        mesh_object: bpy.types.Object, 
        vertex_indexes: list[int],
        add: bool = False
    ):
    switch_to_edit_mode(mesh_object)
    # get the mesh data
    mesh_data = mesh_object.data 
    # get the bmesh data
    bmesh_data = bmesh.from_edit_mesh(mesh_data) # type: ignore
    
    for vert in bmesh_data.verts:
        if vert.index in vertex_indexes:
            vert.select_set(True)
        else:
            if not add:
                vert.select_set(False)

    bmesh_data.select_mode |= {'VERT'}
    bmesh_data.select_flush_mode()
        
    bmesh.update_edit_mesh(mesh_data) # type: ignore


def select_vertex_group(
        mesh_object: bpy.types.Object, 
        vertex_group_name: str,
        add: bool = False
    ):
    vertex_group = mesh_object.vertex_groups.get(vertex_group_name)
    if not vertex_group:
        return
    
    switch_to_edit_mode(mesh_object)
    # get the mesh data
    mesh_data = mesh_object.data
    # get the bmesh data
    bmesh_data = bmesh.from_edit_mesh(mesh_data) # type: ignore
    
    bmesh_data.verts.layers.deform.verify()
    deform = bmesh_data.verts.layers.deform.active

    for vert in bmesh_data.verts:
        for group_index, weight in vert[deform].items():
            if group_index == vertex_group.index and weight > 0.0:
                vert.select_set(True)
                break
        else:
            if not add:
                vert.select_set(False)

    bmesh_data.select_mode |= {'VERT'}
    bmesh_data.select_flush_mode()
        
    bmesh.update_edit_mesh(mesh_data) # type: ignore


def get_shape_key_delta_vertices(
        mesh_object: bpy.types.Object, 
        shape_key_name: str,
        basis_shape_key_name: str = SHAPE_KEY_BASIS_NAME,
        delta_threshold: float = 0.0001
    ) -> list[int]:
    switch_to_object_mode()
    
    # Make this the active shape key and show only this shape key
    shape_key_index = mesh_object.data.shape_keys.key_blocks.keys().index(shape_key_name) # type: ignore
    mesh_object.show_only_shape_key = True
    mesh_object.active_shape_key_index = shape_key_index
    update_mesh(mesh_object)

    shape_key_bmesh = bmesh.new()
    shape_key_bmesh.from_object(
        mesh_object,
        bpy.context.evaluated_depsgraph_get(), # type: ignore
        cage=True,
    )

    # Now do the same so we can extract the basis shape key
    basis_shape_key_index = mesh_object.data.shape_keys.key_blocks.keys().index(basis_shape_key_name) # type: ignore
    mesh_object.show_only_shape_key = True
    mesh_object.active_shape_key_index = basis_shape_key_index
    update_mesh(mesh_object)

    basis_shape_key_bmesh = bmesh.new()
    basis_shape_key_bmesh.from_object(
        mesh_object,
        bpy.context.evaluated_depsgraph_get(), # type: ignore
        cage=True,
    )
    
    vertex_indices = []
    basis_shape_key_bmesh.verts.ensure_lookup_table()
    for vert in shape_key_bmesh.verts:
        basis_vert = basis_shape_key_bmesh.verts[vert.index]
        if (basis_vert.co - vert.co).length > delta_threshold: # type: ignore
            vertex_indices.append(vert.index)

    shape_key_bmesh.free()
    basis_shape_key_bmesh.free()

    return vertex_indices


def get_lod_index(name: str) -> int:
    """
    Gets the LOD index from the given name.

    Args:
        name (str): A name of an object.

    Returns:
        int: The LOD index. Or -1 if no LOD index was found.
    """
    result = re.search(LOD_REGEX, name)
    if result:
        lod = result.groups()[-1]
        return int(lod[-1])
    return -1

def get_center_of_selected_vertices(mesh_object: bpy.types.Object) -> Vector:
    # Ensure we are in object mode
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Get the selected vertices in world space
    selected_vertices = [v.co for v in mesh_object.data.vertices if v.select] # type: ignore
    
    if not selected_vertices:
        return Vector((0, 0, 0))
    
    # Calculate the center of the selected vertices
    sum_x = sum_y = sum_z = 0
    num_vertices = len(selected_vertices)
    
    for vertex in selected_vertices:
        sum_x += vertex.x
        sum_y += vertex.y
        sum_z += vertex.z
    
    center_x = sum_x / num_vertices
    center_y = sum_y / num_vertices
    center_z = sum_z / num_vertices
    
    return Vector((center_x, center_y, center_z))


def get_center_of_vectors(vectors: list[Vector]) -> Vector:    
    sum_x = sum_y = sum_z = 0
    num_vectors = len(vectors)
    
    for vector in vectors:
        sum_x += vector.x
        sum_y += vector.y
        sum_z += vector.z
    
    center_x = sum_x / num_vectors
    center_y = sum_y / num_vectors
    center_z = sum_z / num_vectors
    
    return Vector((center_x, center_y, center_z))

def rotate_vector_around_origin(
        vector: Vector, 
        origin: Vector, 
        degrees: float,
        axis: Axis
    ) -> Vector:    
    rotation_matrix = Matrix.Rotation(math.radians(degrees), 4, axis.upper())
    # Translate the vector to the origin
    translated_vector = vector - origin
    # Apply the rotation matrix
    rotated_vector = rotation_matrix @ translated_vector
    # Translate the vector back
    return rotated_vector + origin

def rotate_vectors_around_origin(
        vectors: list[Vector], 
        origin: Vector, 
        degrees: float,
        axis: Axis
    ) -> list[Vector]:
    final_vectors = []
    
    rotation_matrix = Matrix.Rotation(math.radians(degrees), 4, axis.upper())

    for vector in vectors:
        # Translate the vector to the origin
        translated_vector = vector - origin
        # Apply the rotation matrix
        rotated_vector = rotation_matrix @ translated_vector
        # Translate the vector back
        final_vector = rotated_vector + origin
        final_vectors.append(final_vector)
        
    return final_vectors

def get_bounding_box_center(scene_object: bpy.types.Object) -> Vector:
    # Get the world coordinates of the bounding box corners
    bbox_corners = [scene_object.matrix_world @ Vector(corner) for corner in scene_object.bound_box]
    # Calculate the center of the bounding box
    bbox_center = sum(bbox_corners, Vector()) / 8
    return bbox_center

def get_bounding_box_left_x(scene_object: bpy.types.Object) -> float:
    # Get the world coordinates of the bounding box corners
    bbox_corners = [scene_object.matrix_world @ Vector(corner) for corner in scene_object.bound_box]
    # Extract the x values from the bounding box corners
    x_values = [corner.x for corner in bbox_corners]
    # Find the minimum x value
    return min(x_values)

def get_bounding_box_right_x(scene_object: bpy.types.Object) -> float:
    # Get the world coordinates of the bounding box corners
    bbox_corners = [scene_object.matrix_world @ Vector(corner) for corner in scene_object.bound_box]
    # Extract the x values from the bounding box corners
    x_values = [corner.x for corner in bbox_corners]
    # Find the maximum x value
    return max(x_values)

def get_bounding_box_width(scene_object: bpy.types.Object) -> float:
    # Ensure the object has a bounding box
    if not scene_object.bound_box:
        return 0.0

    # Extract the x-coordinates from the bounding box
    x_coords = [vertex[0] for vertex in scene_object.bound_box]

    # Calculate the width
    width = max(x_coords) - min(x_coords)
    return width

def get_bounding_box_height(scene_object: bpy.types.Object) -> float:
    # Ensure the object has a bounding box
    if not scene_object.bound_box:
        return 0.0

    # Extract the z-coordinates from the bounding box
    z_coords = [vertex[2] for vertex in scene_object.bound_box]

    # Calculate the height
    height = max(z_coords) - min(z_coords)
    return height

def find_closest_vertex(vertices, position):
    return min(
        vertices,
        key=lambda vert: (position - vert).length_squared
    )
    
@exclude_rig_logic_evaluation
def copy_mesh(
        mesh_object: bpy.types.Object, 
        new_mesh_name: str, 
        modifiers: bool = False,
        materials: bool = False
    ) -> bpy.types.Object:
    # remove the object if it already exists
    mesh_object_copy = bpy.data.objects.get(new_mesh_name) # type: ignore
    if mesh_object_copy:    
        bpy.data.objects.remove(mesh_object_copy)

    # remove the mesh data if it already exists
    mesh = bpy.data.meshes.get(new_mesh_name)
    if mesh:    
        bpy.data.meshes.remove(mesh)

    mesh_data = mesh_object.data.copy() # type: ignore
    mesh_data.name = new_mesh_name
    mesh_object_copy = bpy.data.objects.new(
        name=new_mesh_name, 
        object_data=mesh_data
    )

    # make sure the mesh is in the scene collection
    if mesh_object_copy not in bpy.context.scene.collection.objects.values(): # type: ignore
        bpy.context.scene.collection.objects.link(mesh_object_copy) # type: ignore

    if modifiers:
        for modifier in mesh_object.modifiers:
            if not mesh_object_copy.modifiers.get(modifier.name):
                mesh_object_copy.modifiers.new(
                    name=modifier.name, 
                    type=modifier.type
                )
    else:
        # remove any existing modifiers
        for modifier in mesh_object_copy.modifiers:
            mesh_object_copy.modifiers.remove(modifier)

    if not materials:
        mesh_data.materials.clear() # type: ignore

    return mesh_object_copy

def split_mesh_along_uv_islands(bmesh_object: bmesh.types.BMesh) -> dict[int, int]:
    uv_layer = bmesh_object.loops.layers.uv.active
    _uv_border_verts = []

    if not uv_layer:
        return {}    

    # get each uv island and it's loops
    for island_faces in bmesh_linked_uv_islands(bmesh_object, uv_layer):        
        island_loops = [loop for face in island_faces for loop in face.loops] # type: ignore
        for loop in island_loops:
            # Select border loops on the island
            loops = (loop, loop.link_loop_radial_next)
            if (loops[0] == loops[1]
                or loops[1].face not in island_faces
                or loops[0][uv_layer].uv != loops[1].link_loop_next[uv_layer].uv
                or loops[1][uv_layer].uv != loops[0].link_loop_next[uv_layer].uv):
                _uv_border_verts.append(loop.vert)

    uv_border_edges = []
    uv_border_verts = []
    for edge in bmesh_object.edges:
        if not edge.is_boundary and all(vert in _uv_border_verts for vert in edge.verts):
            uv_border_edges.append(edge)
            uv_border_verts.extend(list(edge.verts))

    # Split those edges
    split = bmesh.ops.split_edges(bmesh_object, edges=uv_border_edges)
    
    bmesh_object.verts.index_update()
    bmesh_object.faces.index_update()
    bmesh_object.verts.ensure_lookup_table()
    bmesh_object.faces.ensure_lookup_table()
    
    # Create a lookup table so we can map the new verts to the original verts
    # sharing the same position.
    split_to_original_vert_lookup = {}
    for edge in split['edges']:
        for vert in edge.verts:
            for _vert in uv_border_verts:
                if vert.co == _vert.co:
                    split_to_original_vert_lookup[vert.index] = _vert.index
                    
    return split_to_original_vert_lookup


def save_topology_vertex_groups(mesh_object: bpy.types.Object, file_path: Path):
    vertex_groups = {}
    for vertex_group in mesh_object.vertex_groups:
        if vertex_group.name.startswith('TOPO_GROUP_'):
            vertex_groups[vertex_group.name] = [
                vertex.index for vertex in 
                mesh_object.data.vertices if vertex_group.index in [ # type: ignore
                    group.group
                    for group in vertex.groups
                ]
            ]

    with open(file_path, 'w') as file:
        json.dump(vertex_groups, file)


def get_vertex_group_vertices(
        mesh_object: bpy.types.Object, 
        vertex_group_name: str,
        weight_equal_or_above: float = 1.0
    ) -> list[int]:
    vertex_group = mesh_object.vertex_groups.get(vertex_group_name)
    if not vertex_group:
        return []
    
    return [
        vertex.index for vertex in 
        mesh_object.data.vertices if vertex_group.index in [ # type: ignore
            group.group
            for group in vertex.groups
        ] and vertex_group.weight(vertex.index) >= weight_equal_or_above
    ]

@preserve_context
def auto_unwrap_uvs(mesh_objects: list[bpy.types.Object]):
    for mesh_object in mesh_objects:
        bpy.context.view_layer.objects.active = mesh_object # type: ignore
        switch_to_edit_mode(mesh_object)
        bpy.ops.uv.unwrap(
            method='ANGLE_BASED',
            correct_aspect=True,
            fill_holes=True,
            margin_method="SCALED",
            margin=0.001
        )


def get_uv_values(mesh_object: bpy.types.Object) -> tuple[list[float], list[float]]:
    bmesh_object = bmesh.new()
    bmesh_object.from_mesh(mesh_object.data) # type: ignore
    bmesh_object.faces.ensure_lookup_table()
    
    uv_layer = bmesh_object.loops.layers.uv.active
    if not uv_layer:
        bmesh_object.free()
        return [], []
    
    u_values = [loop[uv_layer].uv[0] for face in bmesh_object.faces for loop in face.loops]
    v_values = [loop[uv_layer].uv[1] for face in bmesh_object.faces for loop in face.loops]
    
    bmesh_object.free()

    return u_values, v_values