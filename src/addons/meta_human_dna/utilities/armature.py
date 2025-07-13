import bpy
import json
import math
import bmesh
import logging
from typing import Literal
from mathutils import Vector, Matrix, Euler
from .misc import (
    exclude_rig_logic_evaluation,
    preserve_context,
    switch_to_pose_mode,
    switch_to_bone_edit_mode,
    
)
from .mesh import (
    get_vertex_group_vertices,
    update_vertex_positions
)
from ..constants import ( 
    CUSTOM_BONE_SHAPE_NAME, 
    CUSTOM_BONE_SHAPE_SCALE,
    ComponentType
)


logger = logging.getLogger(__name__)

def get_bone_rest_transformations(
        bone: bpy.types.Bone, 
        force_object_space: bool = False
    ) -> tuple[Vector, Euler, Vector, Matrix]:
    try:
        if force_object_space:
            rest_to_parent_matrix = bone.matrix_local
        elif bone.parent:
            rest_to_parent_matrix = bone.parent.matrix_local.inverted() @ bone.matrix_local
        else:
            rest_to_parent_matrix = bone.matrix_local
    except ValueError as error:
        if bone.parent:
            logger.error(f'Error getting bone rest transformation. Parent bone "{bone.parent.name}" {bone.parent.matrix_local} cannot be inverted.')
        raise error

    bone_matrix_parent_space = rest_to_parent_matrix @ Matrix.Identity(4)
    # get respective transforms in parent space
    rest_location, rest_rotation, rest_scale = bone_matrix_parent_space.decompose()

    return rest_location, rest_rotation.to_euler('XYZ'), rest_scale, rest_to_parent_matrix # type: ignore

def get_bone_shape(name: str = CUSTOM_BONE_SHAPE_NAME):
    rotations = [
        [90, 0, 0],
        [0, 90, 0],
        [0, 0, 90],
    ]
    new_objects = []
    sphere_control = bpy.data.objects.get(name)
    if not sphere_control:
        for rotation in rotations:
            bpy.ops.mesh.primitive_circle_add(
                vertices=16,
                radius=1,
                enter_editmode=False,
                align='WORLD',
                location=[0, 0, 0],
                scale=[1, 1, 1],
                rotation=[
                    math.radians(rotation[0]),
                    math.radians(rotation[1]),
                    math.radians(rotation[2])
                ]
            )
            new_objects.append(bpy.context.active_object) # type: ignore

        for new_object in new_objects:
            new_object.select_set(True)

        bpy.ops.object.join()
        bpy.context.active_object.name = name # type: ignore
        sphere_control = bpy.data.objects.get(name) 
        sphere_control.use_fake_user = True # type: ignore

    if sphere_control in bpy.context.collection.objects.values(): # type: ignore
        bpy.context.collection.objects.unlink(sphere_control) # type: ignore

    sphere_control.hide_viewport = True # type: ignore
    return sphere_control


def set_bone_collection(
        rig_object: bpy.types.Object, 
        bone_names: list[str],
        collection_name: str,
        theme: str | None = None
    ):
    # get or create a new bone collection
    collection = rig_object.data.collections.get(collection_name) # type: ignore
    if not collection:
        collection = rig_object.data.collections.new(name=collection_name) # type: ignore

    for bone_name in bone_names:
        bone = rig_object.data.bones.get(bone_name) # type: ignore
        if bone and theme:
            bone.color.palette = theme # type: ignore

        pose_bone = rig_object.pose.bones.get(bone_name) # type: ignore
        if pose_bone:
            collection.assign(pose_bone)
            if theme:
                pose_bone.color.palette = theme # type: ignore


def set_head_bone_collections(
        mesh_object: bpy.types.Object,
        rig_object: bpy.types.Object
    ):

    from ..bindings import meta_human_dna_core
    if mesh_object:
        weighted_leaf_bones = []
        weighted_non_leaf_bones = []
        weighted_bones = get_weighted_bone_names(mesh_object)
        for bone_name in weighted_bones:
            pose_bone = rig_object.pose.bones.get(bone_name) # type: ignore
            if pose_bone:
                if not pose_bone.children: # type: ignore
                    weighted_leaf_bones.append(bone_name)
                else:
                    weighted_non_leaf_bones.append(bone_name)

        set_bone_collection(
            rig_object=rig_object, 
            bone_names=weighted_leaf_bones,
            collection_name=meta_human_dna_core.HeadBoneCollection.WEIGHTED_LEAF_BONES.value,
            theme='THEME01'
        )
        set_bone_collection(
            rig_object=rig_object, 
            bone_names=weighted_non_leaf_bones,
            collection_name=meta_human_dna_core.HeadBoneCollection.WEIGHTED_NON_LEAF_BONES.value,
            theme='THEME03'
        )

        non_weighted_leaf_bones = []
        non_weighted_non_leaf_bones = []
        for pose_bone in rig_object.pose.bones: # type: ignore
            if pose_bone.name not in weighted_bones:
                if not pose_bone.children:
                    non_weighted_leaf_bones.append(pose_bone.name)
                else:
                    non_weighted_non_leaf_bones.append(pose_bone.name)

        set_bone_collection(
            rig_object=rig_object, 
            bone_names=non_weighted_leaf_bones,
            collection_name=meta_human_dna_core.HeadBoneCollection.NON_WEIGHTED_LEAF_BONES.value,
            theme='THEME04'
        )
        set_bone_collection(
            rig_object=rig_object, 
            bone_names=non_weighted_non_leaf_bones,
            collection_name=meta_human_dna_core.HeadBoneCollection.NON_WEIGHTED_NON_LEAF_BONES.value,
            theme='THEME09'
        )

        # additional bone collections
        set_bone_collection(
            rig_object=rig_object,
            bone_names=weighted_bones,
            collection_name=meta_human_dna_core.HeadBoneCollection.WEIGHTED_BONES.value
        )
        set_bone_collection(
            rig_object=rig_object,
            bone_names=weighted_leaf_bones + non_weighted_leaf_bones,
            collection_name=meta_human_dna_core.HeadBoneCollection.LEAF_BONES.value
        )


def set_body_bone_collections(
        mesh_object: bpy.types.Object,
        rig_object: bpy.types.Object
    ):
    from ..bindings import meta_human_dna_core
    if mesh_object:
        driver_bones = []
        driver_leaf_bones = []
        twist_bones = []
        corrective_root_bones = []
        twist_corrective_bones = []
        for pose_bone in rig_object.pose.bones: # type: ignore
            chunks = pose_bone.name.split('_')
            if 'twist' in chunks:
                twist_bones.append(pose_bone.name)
            elif 'twistCor' in chunks:
                twist_corrective_bones.append(pose_bone.name)
            elif 'correctiveRoot' in chunks:
                corrective_root_bones.append(pose_bone.name)
            elif not pose_bone.children:
                driver_leaf_bones.append(pose_bone.name)
            else:
                driver_bones.append(pose_bone.name)

        set_bone_collection(
            rig_object=rig_object, 
            bone_names=driver_bones,
            collection_name=meta_human_dna_core.BodyBoneCollection.DRIVER_BONES.value,
            theme='THEME09'
        )
        set_bone_collection(
            rig_object=rig_object, 
            bone_names=driver_leaf_bones,
            collection_name=meta_human_dna_core.BodyBoneCollection.DRIVER_LEAF_BONES.value,
            theme='THEME01'
        )    
        set_bone_collection(
            rig_object=rig_object, 
            bone_names=twist_bones,
            collection_name=meta_human_dna_core.BodyBoneCollection.TWIST_BONES.value,
            theme='THEME03'
        )    
        set_bone_collection(
            rig_object=rig_object, 
            bone_names=twist_corrective_bones,
            collection_name=meta_human_dna_core.BodyBoneCollection.TWIST_CORRECTIVE_BONES.value,
            theme='THEME03'
        )
        set_bone_collection(
            rig_object=rig_object, 
            bone_names=corrective_root_bones,
            collection_name=meta_human_dna_core.BodyBoneCollection.CORRECTIVE_ROOT_BONES.value,
            theme='THEME04'
        )
        
        


def get_meshes_using_armature(armature_object: bpy.types.Object) -> list[bpy.types.Object]:
    # find the related mesh objects for the head rig
    mesh_objects = []
    for mesh_object in bpy.data.objects:
        if mesh_object.type == 'MESH':
            for modifier in mesh_object.modifiers:
                if modifier.type == 'ARMATURE': 
                    if modifier.object == armature_object: # type: ignore
                        mesh_objects.append(mesh_object)
                        break
    return mesh_objects
            

def get_closet_vertex_to_bone(
        mesh_object: bpy.types.Object, 
        pose_bone: bpy.types.PoseBone,
        max_distance: float = 0.01
    ) -> bpy.types.MeshVertex | None:
    # get the bone applied position not the pose position
    bone = pose_bone.id_data.data.bones[pose_bone.name]
    position = mesh_object.matrix_world.inverted() @ bone.head_local
    vert = min(
        mesh_object.data.vertices,  # type: ignore
        key=lambda vert: (position - vert.co).length_squared
    )
    distance = (position - vert.co).length_squared
    # only return the vertex if it is within the max distance
    if distance < max_distance:
        return vert
    logger.warning(f'Vertex {vert.index} is too far from bone "{pose_bone.name}":\n{distance} > {max_distance}')


def get_ray_cast_normal(
        mesh_object: bpy.types.Object, 
        pose_bone: bpy.types.PoseBone,
        max_distance: float = 0.01
    ) -> Vector | None:
    vertex = get_closet_vertex_to_bone(mesh_object, pose_bone, max_distance)
    if vertex:
        return mesh_object.matrix_world @ vertex.normal


def get_vertex_positions(
        mesh_object: bpy.types.Object, 
        bone_to_vert_index: dict[str, int]
    ) -> dict[str, Vector]:
    positions = {}
    depsgraph = bpy.context.evaluated_depsgraph_get() # type: ignore
    bmesh_object = bmesh.new()
    bmesh_object.from_object(mesh_object, depsgraph)
    bmesh_object.verts.ensure_lookup_table()
    
    for bone_name, index in bone_to_vert_index.items():
        positions[bone_name] = bmesh_object.verts[index].co
    
    bmesh_object.free()
    
    return positions

def get_closet_vertex_indices_to_bones(
        mesh_object: bpy.types.Object, 
        pose_bones: list[bpy.types.PoseBone],
        max_distance: float = 0.01
    ) -> dict[str, int]:
    bone_to_vert_index = {}

    # initialize the bmesh object to evaluate against the current depsgraph so 
    # we get the correct vertex positions with taking into account modifiers
    depsgraph = bpy.context.evaluated_depsgraph_get() # type: ignore
    bmesh_object = bmesh.new()
    bmesh_object.from_object(mesh_object, depsgraph)
    bmesh_object.verts.ensure_lookup_table()

    for pose_bone in pose_bones:
        position = pose_bone.matrix.translation
        vert = min(
            bmesh_object.verts,  # type: ignore
            key=lambda vert: (position - vert.co).length_squared
        )
        # only return the vertex if it is within the max distance
        distance = (position - vert.co).length_squared
        if distance < max_distance:
            bone_to_vert_index[pose_bone.name] = vert.index
        else:
            logger.warning(f'Vertex {vert.index} is too far from bone "{pose_bone.name}":\n{distance} > {max_distance}')

    bmesh_object.free()

    return bone_to_vert_index

def get_matching_vertex_index_location(
        source_mesh_object: bpy.types.Object, 
        target_mesh_object: bpy.types.Object, 
        pose_bone: bpy.types.PoseBone,
        max_distance: float = 0.01
    ) -> Vector | None:
    """
    Gets the location of the vertex on the target mesh that has the same index 
    as the source mesh.
    """
    vertex = get_closet_vertex_to_bone(source_mesh_object, pose_bone, max_distance)
    if not vertex:
        return None

    vertex_positions = get_vertex_positions(
        mesh_object=target_mesh_object,
        vert_pairs=[('', vertex.index)] # type: ignore
    )

    # return target_mesh_object.matrix_world @ target_mesh_object.data.vertices[vertex.index].co   # type: ignore
    return target_mesh_object.matrix_world @ vertex_positions[0][-1]


def get_weighted_bone_names(mesh_object: bpy.types.Object) -> list[str]:
    """
    Gets the names of the bones that are weighted to the given mesh.
    """
    weighted_bones = set()

    # Iterate over all vertices in the mesh
    for vertex in mesh_object.data.vertices: # type: ignore
        for group in vertex.groups:
            # Get the vertex group (bone) name
            bone_name = mesh_object.vertex_groups[group.group].name
            # Add the bone name to the set
            weighted_bones.add(bone_name)

    return list(weighted_bones)


@exclude_rig_logic_evaluation
def copy_armature(armature_object: bpy.types.Object, new_armature_name: str) -> bpy.types.Object:
    # remove the object if it already exists
    armature_object_copy = bpy.data.objects.get(new_armature_name) # type: ignore
    if armature_object_copy:    
        bpy.data.objects.remove(armature_object_copy)

    # remove the existing armature if it exists
    armature = bpy.data.meshes.get(new_armature_name)
    if armature:
        bpy.data.armatures.remove(armature) # type: ignore

    # copy the armature
    armature_data = armature_object.data.copy() # type: ignore
    armature_data.name = new_armature_name
    armature_object_copy = bpy.data.objects.get(new_armature_name)
    armature_object_copy = bpy.data.objects.new(
        name=new_armature_name, 
        object_data=armature_data
    )

    # make sure the mesh is in the scene collection
    if armature_object_copy not in bpy.context.scene.collection.objects.values(): # type: ignore
        bpy.context.scene.collection.objects.link(armature_object_copy) # type: ignore
    
    # set custom bone shape
    bones_shape_object = get_bone_shape()
    switch_to_pose_mode(armature_object_copy)
    for pose_bone in armature_object_copy.pose.bones: # type: ignore
        pose_bone.custom_shape = bones_shape_object
        pose_bone.custom_shape_scale_xyz = CUSTOM_BONE_SHAPE_SCALE

    return armature_object_copy

def get_body_constraint_name(bone_name: str) -> str:
    return f'MH_DNA {bone_name} to body'

def get_topology_group_surface_bones(
        mesh_object: bpy.types.Object,
        armature_object: bpy.types.Object,
        vertex_group_name: str,
        dna_reader
    ) -> list[bpy.types.Bone]:
    from ..bindings import meta_human_dna_core
    bones = []
    vertex_indices = get_vertex_group_vertices(mesh_object, vertex_group_name)
    vertex_to_bone_name = meta_human_dna_core.calculate_vertex_to_bone_name_mapping(
        dna_reader=dna_reader
    )
    for vertex_index in vertex_indices:
        bone_name = vertex_to_bone_name.get(vertex_index, None)
        if bone_name:
            bone = armature_object.data.bones.get(bone_name) # type: ignore
            if bone:
                bones.append(bone)
    return bones

def get_mouth_bone_names(armature_object: bpy.types.Object) -> list[str]:
    bones = []
    from ..bindings import meta_human_dna_core

    for bone_name in [meta_human_dna_core.TEETH_UPPER_BONE, meta_human_dna_core.TEETH_LOWER_BONE]:
        bone = armature_object.data.bones.get(bone_name) # type: ignore
        if not bone:
            continue
        bones.append(bone.name)
        for child in bone.children_recursive:
            bones.append(child.name)

    for bone_name in meta_human_dna_core.INTERNAL_LIP_BONES + meta_human_dna_core.JAW_BONES + [meta_human_dna_core.MOUTH_UPPER_BONE, meta_human_dna_core.MOUTH_LOWER_BONE]:
        bone = armature_object.data.bones.get(bone_name) # type: ignore
        if bone:
           bones.append(bone.name)

    return bones

def get_eye_bones_names(side: Literal['l', 'r']) -> list[str]:
    from ..bindings import meta_human_dna_core
    return meta_human_dna_core.EYE_BALL_L_BONES if side == 'l' else meta_human_dna_core.EYE_BALL_R_BONES

def get_ignored_bones_names(armature_object: bpy.types.Object) -> list[str]:
    from ..bindings import meta_human_dna_core
    mouth_bone_names = get_mouth_bone_names(armature_object)
    return mouth_bone_names + meta_human_dna_core.EYE_BALL_L_BONES + meta_human_dna_core.EYE_BALL_R_BONES

@preserve_context
def auto_fit_bones(
        mesh_object: bpy.types.Object, 
        armature_object: bpy.types.Object,
        dna_reader,
        component_type: ComponentType,
        only_selected: bool = False
    ):
    import meta_human_dna_core
    from ..dna_io import DNAExporter
    bmesh_object = DNAExporter.get_bmesh(mesh_object, rotation=0)
    vertex_indices, vertex_positions = DNAExporter.get_mesh_vertex_positions(bmesh_object)
    bone_data = DNAExporter.get_bone_transforms(armature_object)
    bmesh_object.free()

    bone_names = []
    if only_selected:
        bone_names = [bone.name for bone in bpy.context.selected_pose_bones] # type: ignore

    switch_to_bone_edit_mode(armature_object)
    result = meta_human_dna_core.calculate_fitted_bone_positions(
        data={
            'mesh_name': mesh_object.name,
            'vertex_indices': vertex_indices,
            'vertex_positions': vertex_positions,
            'bone_data': bone_data,
            'rig_name': armature_object.name,
            'dna_reader': dna_reader
        },
        component_type=component_type,
        parent_depth=1,
        factor=1.0,
        only_bone_names=bone_names, # type: ignore
    )
    if result:
        for bone_name, (head, tail) in result['bone_positions'].items():
            edit_bone = armature_object.data.edit_bones.get(bone_name) # type: ignore
            if edit_bone:
                edit_bone.head = Vector(head)
                edit_bone.tail = Vector(tail)
        for bone_name, delta in result['bone_deltas']:
            edit_bone = armature_object.data.edit_bones.get(bone_name) # type: ignore
            if edit_bone:
                edit_bone.head += Vector(delta)
                edit_bone.tail += Vector(delta)
        for data in result['mesh_deltas']:
            update_vertex_positions(
                mesh_object=bpy.data.objects[data['name']],
                vertex_indices=data['vertex_indices'],
                offset=Vector(data['offset'])
            )
    else:
        logger.error('Auto-fitting failed. Please check the input data.')
