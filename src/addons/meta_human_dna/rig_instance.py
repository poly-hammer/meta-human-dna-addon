# standard library imports
import logging  # noqa: I001
import math

from pathlib import Path
from pprint import pformat
from typing import Literal

# third party imports
import bpy

from mathutils import Euler, Matrix, Quaternion, Vector

# local imports
from . import utilities
from .constants import FLOATING_POINT_PRECISION, IS_BLENDER_5, SCALE_FACTOR, SHAPE_KEY_NAME_MAX_LENGTH, ToolInfo
from .ui import callbacks
from .typing import *  # noqa: F403


MEMORY_RESOURCE_SIZE = 1024 * 1024 * 4  # 4MB
MEMORY_RESOURCE_ALIGNMENT = 16
ATTR_COUNT_PER_QUATERNION_JOINT = 10
ATTR_COUNT_PER_EULER_JOINT = 9

logger = logging.getLogger(__name__)


def rig_instance_listener(scene: "Scene", dependency_graph: bpy.types.Depsgraph, is_frame_change: bool = False):  # noqa: PLR0912
    meta_human_dna_window_manager: "MetahumanWindowMangerProperties | None" = getattr(  # noqa: UP037
        bpy.context.window_manager, ToolInfo.NAME, None
    )
    if not meta_human_dna_window_manager:
        return

    # this condition prevents constant evaluation
    if not meta_human_dna_window_manager.evaluate_dependency_graph:
        return

    # this condition prevents evaluation after an undo operation
    if meta_human_dna_window_manager.is_undoing:
        meta_human_dna_window_manager.is_undoing = False
        return

    # track the minimal set of instances that need to be updated and their components
    instance_updates = set()

    # TODO: Investigate if this is needed and if there is a better way to do this
    # if the screen is the temp screen, then is is rendering and we need to evaluate
    # if bpy.context.screen.is_temporary: Blender 5.0+
    if bpy.context.screen and "temp" in bpy.context.screen.name.lower():
        # this rules out other temporary window types
        if len(bpy.context.screen.areas) == 1 and bpy.context.screen.areas[0].type != "IMAGE_EDITOR":
            return

        for instance in scene.meta_human_dna.rig_instance_list:
            if instance.auto_evaluate:
                if instance.auto_evaluate_head:
                    instance_updates.add((instance, "head"))
                if instance.auto_evaluate_body:
                    instance_updates.add((instance, "body"))

    # only evaluate if in pose mode or if animation is
    if is_frame_change or bpy.context.mode == "POSE":
        for update in dependency_graph.updates:
            if not update.id:
                continue

            data_type = update.id.bl_rna.name  # type: ignore[attr-defined]
            if data_type == "Action":
                for instance in scene.meta_human_dna.rig_instance_list:
                    # Check if the action is being used by the face board
                    if (
                        instance.auto_evaluate
                        and instance.auto_evaluate_head
                        and instance.face_board
                        and instance.face_board.animation_data
                        and instance.face_board.animation_data.action
                        and instance.face_board.animation_data.action.name == update.id.name
                    ):
                        instance_updates.add((instance, "head"))
                    # Check if the action is being used by the body rig
                    elif (
                        instance.auto_evaluate
                        and instance.auto_evaluate_body
                        and instance.body_rig
                        and instance.body_rig.animation_data
                        and instance.body_rig.animation_data.action
                        and instance.body_rig.animation_data.action.name == update.id.name
                    ) or (
                        instance.auto_evaluate
                        and instance.auto_evaluate_body
                        and instance.control_rig
                        and instance.control_rig.animation_data
                        and instance.control_rig.animation_data.action
                        and instance.control_rig.animation_data.action.name == update.id.name
                    ):
                        # heads have rbf driven bones that move based on neck quaternions, so if head rig is present,
                        # evaluate all
                        if instance.head_rig and instance.auto_evaluate_head and instance.evaluate_rbfs:
                            instance_updates.add((instance, "all"))
                        else:
                            instance_updates.add((instance, "body"))

            elif data_type == "Armature" and update.is_updated_transform:
                for instance in scene.meta_human_dna.rig_instance_list:
                    armature_name = update.id.name

                    # Check if the armature is the face board
                    if (
                        instance.auto_evaluate
                        and instance.auto_evaluate_head
                        and instance.face_board
                        and instance.face_board.data
                        and instance.face_board.data.name == armature_name
                    ):
                        instance_updates.add((instance, "head"))
                    # Check if the armature is the body rig
                    elif (
                        instance.auto_evaluate
                        and instance.auto_evaluate_body
                        and instance.body_rig
                        and instance.body_rig.data
                        and instance.body_rig.data.name == armature_name
                    ) or (
                        instance.auto_evaluate
                        and instance.auto_evaluate_body
                        and instance.control_rig
                        and instance.control_rig.data
                        and instance.control_rig.data.name == armature_name
                    ):
                        # heads have rbf driven bones that move based on neck quaternions, so if head rig
                        # is present, evaluate all
                        if instance.head_rig and instance.auto_evaluate_head and instance.evaluate_rbfs:
                            instance_updates.add((instance, "all"))
                        else:
                            instance_updates.add((instance, "body"))

    # reduce redundant updates if 'all' components are being updated anyway, no need to
    # update head/body again separately
    final_instance_updates = set()
    for instance, component in instance_updates:
        if (instance, "all") in instance_updates:
            final_instance_updates.add((instance, "all"))
        else:
            final_instance_updates.add((instance, component))

    # apply the updates to the instances
    for instance, component in final_instance_updates:
        instance.evaluate(component=component, dependency_graph=dependency_graph)


def frame_change_handler(scene: "Scene", dependency_graph: bpy.types.Depsgraph):
    rig_instance_listener(scene, dependency_graph, is_frame_change=True)


def stop_listening():
    for handler in bpy.app.handlers.depsgraph_update_post:
        if handler.__name__ == rig_instance_listener.__name__:
            bpy.app.handlers.depsgraph_update_post.remove(handler)

    for handler in bpy.app.handlers.frame_change_post:
        if handler.__name__ == frame_change_handler.__name__:
            bpy.app.handlers.frame_change_post.remove(handler)


def start_listening():
    stop_listening()
    logger.info("Listening for Rig Logic...")
    context: "Context" = bpy.context  # pyright: ignore[reportAssignmentType]  # noqa: UP037
    callbacks.update_head_output_items(None, context)
    bpy.app.handlers.depsgraph_update_post.append(rig_instance_listener)  # type: ignore[call-arg]
    bpy.app.handlers.frame_change_post.append(frame_change_handler)  # type: ignore[call-arg]


class OutputData(bpy.types.PropertyGroup):
    include: bpy.props.BoolProperty(default=True, description="Whether to include this data in the output")  # pyright: ignore[reportInvalidTypeForm]
    name: bpy.props.StringProperty(default="", description="The name of the shape key")  # pyright: ignore[reportInvalidTypeForm]
    scene_object: bpy.props.PointerProperty(
        type=bpy.types.Object,
        description=(
            "A object that is associated with the dna data. This automatically "
            "gets set based on what is linked in the Rig Instance data"
        ),
    )  # pyright: ignore[reportInvalidTypeForm]
    image_object: bpy.props.PointerProperty(
        type=bpy.types.Image,
        description=(
            "A object that is associated with the dna data. This automatically "
            "gets set based on what is linked in the Rig Instance data"
        ),
    )  # pyright: ignore[reportInvalidTypeForm]
    relative_file_path: bpy.props.StringProperty(
        default="", description="The relative file path from the output folder"
    )  # pyright: ignore[reportInvalidTypeForm]
    editable_name: bpy.props.BoolProperty(default=True, description="Whether to include this data in the output")  # pyright: ignore[reportInvalidTypeForm]


class ShapeKeyData(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(default="", description="The name of the shape key")  # pyright: ignore[reportInvalidTypeForm]
    value: bpy.props.FloatProperty(
        default=0.0,
        description="The value of the shape key",
        get=callbacks.get_shape_key_value,  # this makes the value read-only
    )  # pyright: ignore[reportInvalidTypeForm]


class RigInstance(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(
        default="my_metahuman",
        description=(
            "The name associated with this Rig Instance. This is also the unique identifier "
            "for all data associated with the MetaHuman"
        ),
        update=callbacks.update_instance_name,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    auto_evaluate: bpy.props.BoolProperty(
        default=True,
        name="Auto Evaluate",
        description="Whether to automatically evaluate this rig instance when the scene is updated",
    )  # pyright: ignore[reportInvalidTypeForm]
    auto_evaluate_head: bpy.props.BoolProperty(
        default=True,
        name="Auto Evaluate Head",
        description=(
            "Whether to automatically evaluate the head components on this rig instance when the scene is updated"
        ),
    )  # pyright: ignore[reportInvalidTypeForm]
    auto_evaluate_body: bpy.props.BoolProperty(
        default=True,
        name="Auto Evaluate Body",
        description=(
            "Whether to automatically evaluate the body components on this rig instance when the scene is updated"
        ),
    )  # pyright: ignore[reportInvalidTypeForm]
    evaluate_bones: bpy.props.BoolProperty(
        default=True,
        name="Evaluate Bones",
        description="Whether to evaluate bone positions based on the face board controls",
    )  # pyright: ignore[reportInvalidTypeForm]
    evaluate_shape_keys: bpy.props.BoolProperty(
        default=True,
        name="Evaluate Shape Keys",
        description="Whether to evaluate shape keys based on the face board controls",
    )  # pyright: ignore[reportInvalidTypeForm]
    evaluate_texture_masks: bpy.props.BoolProperty(
        default=True,
        name="Evaluate Texture Masks",
        description="Whether to evaluate texture masks based on the face board controls",
    )  # pyright: ignore[reportInvalidTypeForm]
    evaluate_rbfs: bpy.props.BoolProperty(
        default=True,
        name="Evaluate RBFs",
        description="Whether to evaluate RBFs based on the driver bones quaternion rotations",
        update=callbacks.update_evaluate_rbfs_value,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    face_board: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Face Board",
        description="The face board that rig logic reads control positions from",
        poll=callbacks.poll_face_boards,
    )  # pyright: ignore[reportInvalidTypeForm]
    control_rig: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Control Rig",
        description="The control rig that drives the body rig",
        poll=callbacks.poll_control_rig,
    )  # pyright: ignore[reportInvalidTypeForm]
    head_dna_file_path: bpy.props.StringProperty(
        name="Head DNA File",
        description="The path to the head DNA file that rig logic reads from when evaluating the face board controls",
        subtype="FILE_PATH",
        options={"PATH_SUPPORTS_BLEND_RELATIVE"},
    )  # pyright: ignore[reportInvalidTypeForm]
    head_mesh: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Head Mesh",
        description="The head mesh with the shape keys that rig logic will evaluate",
        poll=callbacks.poll_head_mesh,
        update=callbacks.update_head_output_items,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    head_rig: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Head Rig",
        description="The armature object that rig logic will evaluate",
        poll=callbacks.poll_head_rig,
        update=callbacks.update_head_output_items,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    head_material: bpy.props.PointerProperty(
        type=bpy.types.Material,
        name="Head Material",
        description="The head material that has a node with wrinkle map sliders that rig logic will evaluate",
        poll=callbacks.poll_head_materials,
        update=callbacks.update_head_output_items,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    body_dna_file_path: bpy.props.StringProperty(
        name="Body DNA File",
        description="The path to the body DNA file",
        subtype="FILE_PATH",
        options={"PATH_SUPPORTS_BLEND_RELATIVE"},
    )  # pyright: ignore[reportInvalidTypeForm]
    body_mesh: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Body Mesh",
        description="The body mesh",
        poll=callbacks.poll_body_mesh,
        update=callbacks.update_body_output_items,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    body_rig: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Body Rig",
        description="The armature object for the body that RBF will evaluate",
        poll=callbacks.poll_body_rig,
        update=callbacks.update_body_output_items,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    body_material: bpy.props.PointerProperty(
        type=bpy.types.Material,
        name="Body Material",
        description="The body material",
        poll=callbacks.poll_body_materials,
        update=callbacks.update_body_output_items,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]

    # ----- View Options Properties -----
    active_lod: bpy.props.EnumProperty(
        name="Active LOD",
        items=callbacks.get_head_mesh_lod_items,  # type: ignore[call-arg]
        description="Choose what Level of Detail should be displayed from the face",
        options={"ANIMATABLE"},
        set=callbacks.set_active_lod,
        get=callbacks.get_active_lod,
    )  # pyright: ignore[reportInvalidTypeForm]
    active_material_preview: bpy.props.EnumProperty(
        name="Material Color",
        items=[
            ("combined", "Combined", "Displays all combined textures maps"),
            ("masks", "Masks", "Displays only the color of the mask texture maps"),
            ("normals", "Normals", "Displays only the color of the normal texture maps"),
            ("topology", "Topology", "Displays only the mesh topology colors"),
        ],
        description="Choose what color should be shown by the material",
        default="combined",
        set=callbacks.set_active_material_preview,
        get=callbacks.get_active_material_preview,
    )  # pyright: ignore[reportInvalidTypeForm]
    show_face_board: bpy.props.BoolProperty(
        name="Show Face Board",
        default=False,
        description="Whether to show or hide the face board that belongs to this MetaHuman instance in the 3D view",
        set=callbacks.set_show_face_board,
        get=callbacks.get_show_face_board,
    )  # pyright: ignore[reportInvalidTypeForm]
    show_control_rig: bpy.props.BoolProperty(
        name="Show Control Rig",
        default=False,
        description="Whether to show or hide the control rig that belongs to this MetaHuman instance in the 3D view",
        set=callbacks.set_show_control_rig,
        get=callbacks.get_show_control_rig,
    )  # pyright: ignore[reportInvalidTypeForm]
    show_head_bones: bpy.props.BoolProperty(
        name="Show Head Bones",
        default=False,
        description="Whether to show or hide the head bones that belong to this MetaHuman instance in the 3D view",
        set=callbacks.set_show_head_bones,
        get=callbacks.get_show_head_bones,
    )  # pyright: ignore[reportInvalidTypeForm]
    show_body_bones: bpy.props.BoolProperty(
        name="Show Body Bones",
        default=False,
        description="Whether to show or hide the body bones that belong to this MetaHuman instance in the 3D view",
        set=callbacks.set_show_body_bones,
        get=callbacks.get_show_body_bones,
    )  # pyright: ignore[reportInvalidTypeForm]

    # --------------------- Mesh Utilities Properties ------------------
    mesh_topology_selection_mode: bpy.props.EnumProperty(
        name="Selection Mode",
        default="isolate",
        items=[
            ("add", "Add", "Adds the chosen topology group to the current selection"),
            ("isolate", "Isolate", "Isolates the chosen topology group by de-selecting everything else"),
        ],
        description="Choose what selection mode to use when selecting the head topology groups",
    )  # pyright: ignore[reportInvalidTypeForm]
    head_mesh_topology_groups: bpy.props.EnumProperty(
        name="Topology Groups",
        items=callbacks.get_head_mesh_topology_groups,  # type: ignore[call-arg]
        description="Select the bone group to display in the 3D view",
        options={"ANIMATABLE"},
        update=callbacks.update_head_topology_selection,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    head_shrink_wrap_target: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Material",
        description=(
            "The head mesh that the shrink wrap modifier will target. This is the mesh that you will wrap "
            "the head topology to"
        ),
        poll=callbacks.poll_shrink_wrap_target,
    )  # pyright: ignore[reportInvalidTypeForm]
    body_mesh_topology_groups: bpy.props.EnumProperty(
        name="Topology Groups",
        items=callbacks.get_body_mesh_topology_groups,  # type: ignore[call-arg]
        description="Select the bone group to display in the 3D view",
        options={"ANIMATABLE"},
        update=callbacks.update_body_topology_selection,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    body_shrink_wrap_target: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Material",
        description=(
            "The body mesh that the shrink wrap modifier will target. This is the mesh that you will wrap "
            "the body topology to"
        ),
        poll=callbacks.poll_shrink_wrap_target,
    )  # pyright: ignore[reportInvalidTypeForm]
    body_show_only_high_level_topology_groups: bpy.props.BoolProperty(
        name="Show Only High Level Topology Groups",
        description=(
            "Use this to only show the high level topology groups in the topology group selection dropdown. "
            "This is useful for when you have a lot of topology groups and want to focus on the high level ones"
        ),
        default=False,
    )  # pyright: ignore[reportInvalidTypeForm]
    body_reset_rbf_pose_on_change: bpy.props.BoolProperty(
        name="Reset RBF Pose on Change",
        description=(
            "If enabled, resets the rig to its rest pose before when changing the active RBF pose from one "
            "pose to another. This isolates the pose changes to only the selected pose"
        ),
        default=True,
    )  # pyright: ignore[reportInvalidTypeForm]

    # --------------------- Armature Utilities Properties ------------------
    rig_bone_group_selection_mode: bpy.props.EnumProperty(
        name="Selection Mode",
        default="isolate",
        items=[
            ("add", "Add", "Adds the chosen bone group to the current selection"),
            ("isolate", "Isolate", "Isolates the chosen bone group by de-selecting everything else"),
        ],
        description="Choose what selection mode to use when selecting the head topology groups",
    )  # pyright: ignore[reportInvalidTypeForm]
    head_rig_bone_groups: bpy.props.EnumProperty(
        name="Bone Groups",
        items=callbacks.get_head_rig_bone_groups,  # type: ignore[call-arg]
        description="Select the bone group to display in the 3D view",
        options={"ANIMATABLE"},
        update=callbacks.update_head_rig_bone_group_selection,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    body_rig_bone_groups: bpy.props.EnumProperty(
        name="Bone Groups",
        items=callbacks.get_body_rig_bone_groups,  # type: ignore[call-arg]
        description="Select the bone group to display in the 3D view",
        options={"ANIMATABLE"},
        update=callbacks.update_body_rig_bone_group_selection,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    list_surface_bone_groups: bpy.props.BoolProperty(
        name="List Surface Bones",
        default=False,
        description="Whether to also show the surface bone groups in the bone group selection dropdown",
    )  # pyright: ignore[reportInvalidTypeForm]
    head_to_body_constraint_influence: bpy.props.FloatProperty(
        name="Constrain Head to Body",
        default=0.0,
        description="The influence of the head to body constraint",
        update=callbacks.update_head_to_body_constraint_influence,  # type: ignore[call-arg]
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )  # pyright: ignore[reportInvalidTypeForm]

    # ----- Shape Keys Properties -----
    active_shape_key_mesh_name: bpy.props.EnumProperty(
        name="Active Shape Key Mesh",
        description="This determines which mesh object's shape keys value are being displayed in the shape key list",
        options={"ANIMATABLE"},
        items=callbacks.get_active_shape_key_mesh_names,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    solo_shape_key: bpy.props.BoolProperty(
        name="Solo Shape Key",
        description=(
            "If this is enabled, every time you sculpt/edit a shape key, it will set all other shape keys to "
            "0 and the selected shape key to 1"
        ),
        default=False,
    )  # pyright: ignore[reportInvalidTypeForm]
    generate_neutral_shapes: bpy.props.BoolProperty(
        name="Generate Neutral Shapes",
        description=(
            "Use this to generate neutral shape keys that match the names in the DNA file. This is useful "
            "when you can't import the deltas because vert ids are not the same, or you just want to use neutral "
            "shapes as a starting point"
        ),
        default=False,
    )  # pyright: ignore[reportInvalidTypeForm]

    # ----- Output Properties -----
    output_run_validations: bpy.props.BoolProperty(
        name="Validate", description="Whether to run validations before exporting", default=True
    )  # pyright: ignore[reportInvalidTypeForm]
    output_folder_path: bpy.props.StringProperty(
        name="Output Folder",
        description="The root folder where the output files will be saved",
        subtype="DIR_PATH",
        options={"PATH_SUPPORTS_BLEND_RELATIVE"},
    )  # pyright: ignore[reportInvalidTypeForm]
    output_method: bpy.props.EnumProperty(
        name="DNA Output Method",
        description="The output method to use when creating the dna file",
        default="calibrate",
        items=[
            (
                "calibrate",
                "Calibrate",
                (
                    "Uses the original dna file and calibrates the included bones and mesh changes into a new dna"
                    " file. Use this method if your vert indices and bone names are the same as the original DNA."
                    " This is the recommended method"
                ),
                "NONE",
                0,
            ),
            (
                "overwrite",
                "Overwrite",
                (
                    "(Experimental, and not fully functional yet) Uses the original dna file and overwrites the"
                    " dna data based on the current mesh and armature data in the scene. Use this method if your "
                    "vert indices and bone names are different from the original DNA. Only use this method when "
                    "calibration method is not possible"
                ),
                "ERROR",
                1,
            ),
        ],
    )  # pyright: ignore[reportInvalidTypeForm]
    output_component: bpy.props.EnumProperty(
        name="DNA Output Component",
        description="Which component to output use when creating the dna file",
        default="head",
        items=[("head", "Head", "The head component of the DNA"), ("body", "Body", "The body component of the DNA")],
        update=callbacks.update_output_component,  # type: ignore[call-arg]
    )  # pyright: ignore[reportInvalidTypeForm]
    output_format: bpy.props.EnumProperty(
        name="File Format",
        description="The file format to use when output the dna file. Either binary or json",
        default="binary",
        items=[
            (
                "json",
                "JSON",
                (
                    "Writes the dna file in a human readable json format. Use this method if you want to manually "
                    "edit the dna file"
                ),
            ),
            (
                "binary",
                "Binary",
                (
                    "Writes the dna file in a binary format. Use this method if you want to use the dna file with the"
                    " rig logic system"
                ),
            ),
        ],
    )  # pyright: ignore[reportInvalidTypeForm]
    output_align_head_and_body: bpy.props.BoolProperty(
        name="Align Head and Body",
        description=(
            "Whether to align the overlapping head and body bones, as well as, aligning the vertices "
            "in the edge loop around the neck during the calibration process"
        ),
        default=True,
    )  # pyright: ignore[reportInvalidTypeForm]

    # ----- Internal Properties -----
    old_name: bpy.props.StringProperty(default="")  # pyright: ignore[reportInvalidTypeForm]
    shape_key_list: bpy.props.CollectionProperty(type=ShapeKeyData)  # pyright: ignore[reportInvalidTypeForm]
    shape_key_list_active_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]

    output_head_item_list: bpy.props.CollectionProperty(type=OutputData)  # pyright: ignore[reportInvalidTypeForm]
    output_head_item_active_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]
    output_body_item_list: bpy.props.CollectionProperty(type=OutputData)  # pyright: ignore[reportInvalidTypeForm]
    output_body_item_active_index: bpy.props.IntProperty()  # pyright: ignore[reportInvalidTypeForm]
    calibrate_bones: bpy.props.BoolProperty(default=True)  # pyright: ignore[reportInvalidTypeForm]
    calibrate_meshes: bpy.props.BoolProperty(default=True)  # pyright: ignore[reportInvalidTypeForm]
    calibrate_shape_keys: bpy.props.BoolProperty(default=True)  # pyright: ignore[reportInvalidTypeForm]

    # rbf editor
    editing_rbf_solver: bpy.props.BoolProperty(default=False)  # pyright: ignore[reportInvalidTypeForm]

    # this holds the rig logic references
    data = {}

    warning_messages = []

    def get_shape_key(self, mesh_index: int) -> bpy.types.Key | None:
        shape_key = self.data.get(f"{self.name}_shape_key", {}).get(mesh_index)
        try:
            if shape_key:
                return shape_key
        except ReferenceError:
            return None

    def get_shape_key_block(self, mesh_index: int, name: str) -> bpy.types.ShapeKey | None:
        cached_shape_key = self.get_shape_key(mesh_index)
        if cached_shape_key and cached_shape_key.key_blocks:
            return cached_shape_key.key_blocks.get(name)

        mesh_object = self.head_mesh_index_lookup.get(mesh_index)
        if mesh_object:
            self.data[f"{self.name}_shape_key"] = self.data.get(f"{self.name}_shape_key", {})
            for shape_key in bpy.data.shape_keys:
                if shape_key.user == mesh_object.data:
                    key_block = shape_key.key_blocks.get(name)
                    if key_block:
                        # store the shape key in the shape key property so we don't have to search for it again
                        self.data[f"{self.name}_shape_key"][mesh_index] = shape_key
                        return key_block
        return None

    def apply_dependency_graph_update(self, dependency_graph: bpy.types.Depsgraph | None = None):
        if not dependency_graph:
            dependency_graph = bpy.context.evaluated_depsgraph_get()

        if self.head_rig:
            self.data[f"{self.name}_evaluated_head_rig"] = self.head_rig.evaluated_get(dependency_graph)
        if self.body_rig:
            self.data[f"{self.name}_evaluated_body_rig"] = self.body_rig.evaluated_get(dependency_graph)

    @property
    def evaluated_head_rig(self) -> bpy.types.Object | None:
        return self.data.get(
            f"{self.name}_evaluated_head_rig",
            self.head_rig.evaluated_get(bpy.context.evaluated_depsgraph_get()) if self.head_rig else None,
        )

    @property
    def evaluated_body_rig(self) -> bpy.types.Object | None:
        return self.data.get(
            f"{self.name}_evaluated_body_rig",
            self.body_rig.evaluated_get(bpy.context.evaluated_depsgraph_get()) if self.body_rig else None,
        )

    @property
    def head_valid(self) -> bool:
        logged_warning = self.data.get(f"{self.name}_logged_head_validation_warning", False)

        if not self.head_dna_file_path:
            if not logged_warning:
                logger.warning(
                    f"The Head DNA file path is not set. The Rig Instance {self.name} will not be initialized."
                )
                self.data[f"{self.name}_logged_head_validation_warning"] = True
            return False
        dna_file_path = Path(bpy.path.abspath(self.head_dna_file_path))
        if not dna_file_path.is_file():
            if not logged_warning:
                logger.warning(
                    f'The Head DNA file path "{dna_file_path}" is not a file. The Rig Instance {self.name} '
                    "will not be initialized."
                )
                self.data[f"{self.name}_logged_head_validation_warning"] = True
            return False

        if not dna_file_path.exists():
            if not logged_warning:
                logger.warning(
                    f'The Head DNA file path "{dna_file_path}" does not exist. The Rig Instance {self.name} '
                    "will not be initialized."
                )
                self.data[f"{self.name}_logged_head_validation_warning"] = True
            return False
        if not self.face_board:
            if not logged_warning:
                logger.warning(f"The Face board is not set. The Rig Instance {self.name} will not be initialized.")
                self.data[f"{self.name}_logged_head_validation_warning"] = True
            return False
        return True

    @property
    def body_valid(self) -> bool:
        logged_warning = self.data.get(f"{self.name}_logged_body_validation_warning", False)
        if not self.body_dna_file_path:
            if not logged_warning:
                logger.warning(
                    f"The Body DNA file path is not set. The Rig Instance {self.name} will not be initialized."
                )
                self.data[f"{self.name}_logged_body_validation_warning"] = True
            return False

        dna_file_path = Path(bpy.path.abspath(self.body_dna_file_path))
        if not dna_file_path.is_file():
            if not logged_warning:
                logger.warning(
                    f'The Body DNA file path "{dna_file_path}" is not a file. The Rig Instance {self.name}'
                    " will not be initialized."
                )
                self.data[f"{self.name}_logged_body_validation_warning"] = True
            return False

        if not dna_file_path.exists():
            if not logged_warning:
                logger.warning(
                    f'The Body DNA file path "{dna_file_path}" does not exist. The Rig Instance {self.name} '
                    "will not be initialized."
                )
                self.data[f"{self.name}_logged_body_validation_warning"] = True
            return False
        return True

    @property
    def head_texture_masks_node(self) -> bpy.types.ShaderNodeGroup | None:
        # first check if the texture masks node is set
        if not self.head_material:
            return None

        return callbacks.get_head_texture_logic_node(self.head_material)

    @property
    def head_initialized(self) -> bool:
        return bool(self.data.get(f"{self.name}_head_initialized"))

    @property
    def body_initialized(self) -> bool:
        return bool(self.data.get(f"{self.name}_body_initialized"))

    @property
    def head_use_eye_aim(self) -> bool:
        look_at_switch = self.face_board.pose.bones.get("CTRL_lookAtSwitch")
        return look_at_switch and look_at_switch.location.y >= 0.99

    @property
    def head_mesh_index_lookup(self) -> dict[int, bpy.types.Object]:
        if not self.head_dna_reader:
            return {}

        mesh_index_lookup = self.data.get(f"{self.name}_head_mesh_index_lookup", {})
        if mesh_index_lookup:
            return mesh_index_lookup

        for mesh_index in range(self.head_dna_reader.getMeshCount()):
            dna_mesh_name = self.head_dna_reader.getMeshName(mesh_index)
            mesh_object = bpy.data.objects.get(f"{self.name}_{dna_mesh_name}")
            if mesh_object:
                mesh_index_lookup[mesh_index] = mesh_object

        self.data[f"{self.name}_head_mesh_index_lookup"] = mesh_index_lookup
        return self.data[f"{self.name}_head_mesh_index_lookup"]

    @property
    def head_channel_name_to_index_lookup(self) -> dict[str, int]:
        if not self.head_dna_reader:
            return {}

        channel_name_to_index_lookup = self.data.get(f"{self.name}_head_channel_name_to_index_lookup", {})
        if channel_name_to_index_lookup:
            return channel_name_to_index_lookup

        for mesh_index in self.head_dna_reader.getMeshIndicesForLOD(0):
            mesh_name = self.head_dna_reader.getMeshName(mesh_index)
            for index in range(self.head_dna_reader.getBlendShapeTargetCount(mesh_index)):
                channel_index = self.head_dna_reader.getBlendShapeChannelIndex(mesh_index, index)
                shape_key_name = self.head_dna_reader.getBlendShapeChannelName(channel_index)
                channel_name_to_index_lookup[f"{mesh_name}__{shape_key_name}"] = channel_index

        self.data[f"{self.name}_head_channel_name_to_index_lookup"] = channel_name_to_index_lookup
        return self.data[f"{self.name}_head_channel_name_to_index_lookup"]

    @property
    def head_channel_index_to_mesh_index_lookup(self) -> dict[int, int]:
        if not self.head_dna_reader:
            return {}

        mesh_shape_key_index_lookup = self.data.get(f"{self.name}_head_mesh_shape_key_index_lookup", {})
        if mesh_shape_key_index_lookup:
            return mesh_shape_key_index_lookup

        # build a lookup dictionary of shape key index to mesh index
        for mesh_index in self.head_dna_reader.getMeshIndicesForLOD(0):
            for index in range(self.head_dna_reader.getBlendShapeTargetCount(mesh_index)):
                channel_index = self.head_dna_reader.getBlendShapeChannelIndex(mesh_index, index)
                mesh_shape_key_index_lookup[channel_index] = mesh_index
        self.data[f"{self.name}_head_mesh_shape_key_index_lookup"] = mesh_shape_key_index_lookup
        return mesh_shape_key_index_lookup

    @property
    def head_manager(self) -> "riglogic.RigLogic":
        return self.data.get(f"{self.name}_head_manager")

    @property
    def head_instance(self) -> "riglogic.RigInstance":
        return self.data.get(f"{self.name}_head_instance")

    @property
    def head_dna_reader(self) -> "riglogic.BinaryStreamReader":
        return self.data.get(f"{self.name}_head_dna_reader")

    @property
    def body_manager(self) -> "riglogic.RigLogic":
        return self.data.get(f"{self.name}_body_manager")

    @property
    def body_instance(self) -> "riglogic.RigInstance":
        return self.data.get(f"{self.name}_body_instance")

    @property
    def body_dna_reader(self) -> "riglogic.BinaryStreamReader":
        return self.data.get(f"{self.name}_body_dna_reader")

    @property
    def head_shape_key_blocks(self) -> dict[int, list[bpy.types.ShapeKey]]:
        if not self.head_dna_reader:
            return {}

        shape_key_blocks = self.data.get(f"{self.name}_head_shape_key_blocks")
        if shape_key_blocks is None:
            self.shape_key_list.clear()
            mesh_index = 0  # this is the head lod 0 mesh index
            shape_key_blocks = {}

            # Note: That lod 0 is the only lod that has shape keys
            failed_to_cache_count = 0
            for mesh_index in self.head_dna_reader.getMeshIndicesForLOD(0):
                mesh_object = self.head_mesh_index_lookup.get(mesh_index)
                if not mesh_object:
                    logger.warning(f'The mesh object for mesh index "{mesh_index}" was not found')
                    continue

                for target_index in range(self.head_dna_reader.getBlendShapeTargetCount(mesh_index)):
                    channel_index = self.head_dna_reader.getBlendShapeChannelIndex(mesh_index, target_index)
                    name = self.head_dna_reader.getBlendShapeChannelName(channel_index)
                    dna_mesh_name = mesh_object.name.replace(f"{self.name}_", "")
                    shape_key_block_name = f"{dna_mesh_name}__{name}"
                    shape_key_block = self.get_shape_key_block(mesh_index=mesh_index, name=shape_key_block_name)
                    if shape_key_block:
                        # store the shape key block names in the shape key list as well
                        shape_key_item = self.shape_key_list.add()
                        shape_key_item.name = shape_key_block_name

                        # store the shape key block in a list on the dictionary
                        key_block_list = shape_key_blocks.get(channel_index, [])
                        key_block_list.append(shape_key_block)
                        shape_key_blocks[channel_index] = key_block_list

                    elif len(shape_key_block_name) <= SHAPE_KEY_NAME_MAX_LENGTH:
                        failed_to_cache_count += 1

            if failed_to_cache_count > 0:
                logger.warning(
                    f"Rig Instance {self.name} did not cache {failed_to_cache_count} shape key blocks, "
                    "because they are not in the scene. However they are in the DNA file. Import all shape "
                    "keys to cache them."
                )

            self.data[f"{self.name}_head_shape_key_blocks"] = shape_key_blocks

        return self.data[f"{self.name}_head_shape_key_blocks"]

    @property
    def head_rest_pose(self) -> dict[str, tuple[Vector, Euler, Vector, Matrix]]:
        rest_pose = self.data.get(f"{self.name}_head_rest_pose", {})
        if rest_pose:
            return rest_pose

        # make sure the rig bone are using the correct rotation mode
        if self.evaluated_head_rig and self.evaluated_head_rig.pose:
            for pose_bone in self.evaluated_head_rig.pose.bones:
                if pose_bone.name in self.head_driver_bone_names:
                    pose_bone.rotation_mode = "QUATERNION"
                else:
                    pose_bone.rotation_mode = "XYZ"
                # save the rest pose and their parent space matrix so we don't have to calculate it again
                try:
                    rest_pose[pose_bone.name] = utilities.get_bone_rest_transformations(pose_bone.bone)
                except ValueError as error:
                    logger.error(f'Error getting rest pose for bone "{pose_bone.name}": {error}')
                    return {}

        # save the rest pose so we don't have to calculate it again
        self.data[f"{self.name}_head_rest_pose"] = rest_pose
        # return a copy so the original rest position is not modified
        return self.data[f"{self.name}_head_rest_pose"]

    @property
    def head_driven_bone_names(self) -> list[str]:
        driven_bone_names = self.data.get(f"{self.name}_head_driven_bone_names", [])
        if driven_bone_names:
            return driven_bone_names

        # get the head rbf driven bone names
        for solver_index in range(self.head_dna_reader.getRBFSolverCount()):
            for pose_index in self.head_dna_reader.getRBFSolverPoseIndices(solver_index):
                for attr_index in self.head_dna_reader.getRBFPoseJointOutputIndices(pose_index):
                    joint_index = attr_index // ATTR_COUNT_PER_EULER_JOINT
                    driven_bone_names.append(self.head_dna_reader.getJointName(joint_index))

        # save the driven bone names so we don't have to query them again
        self.data[f"{self.name}_head_driven_bone_names"] = list(set(driven_bone_names))
        return self.data[f"{self.name}_head_driven_bone_names"]

    @property
    def head_driver_bone_names(self) -> list[str]:
        driver_bone_names = self.data.get(f"{self.name}_head_driver_bone_names", [])
        if driver_bone_names:
            return driver_bone_names

        driver_bone_names = set()
        for index in range(self.head_dna_reader.getRawControlCount()):
            full_name = self.head_dna_reader.getRawControlName(index)
            control_name, axis = full_name.split(".")
            if axis.startswith("q"):
                driver_bone_names.add(control_name)

        # save the raw control bone names so we don't have to query them again
        self.data[f"{self.name}_head_driver_bone_names"] = list(driver_bone_names)
        # return a copy so the original raw control bone names are not modified
        return self.data[f"{self.name}_head_driver_bone_names"]

    @property
    def body_rest_pose(self) -> dict[str, tuple[Vector, Euler, Vector, Matrix]]:
        rest_pose = self.data.get(f"{self.name}_body_rest_pose", {})
        if rest_pose:
            return rest_pose

        # make sure the rig bone are using the correct rotation mode
        if self.evaluated_body_rig and self.evaluated_body_rig.pose:
            for pose_bone in self.evaluated_body_rig.pose.bones:
                # make sure the body bones are using the correct rotation mode
                if pose_bone.name in self.body_driver_bone_names:
                    pose_bone.rotation_mode = "QUATERNION"
                else:
                    pose_bone.rotation_mode = "XYZ"

                # save the rest pose and their parent space matrix so we don't have to calculate it again
                try:
                    rest_pose[pose_bone.name] = utilities.get_bone_rest_transformations(
                        pose_bone.bone, rotation_mode="XYZ"
                    )
                except ValueError as error:
                    logger.error(f'Error getting rest pose for bone "{pose_bone.name}": {error}')
                    return {}

        # save the rest pose so we don't have to calculate it again
        self.data[f"{self.name}_body_rest_pose"] = rest_pose
        # return a copy so the original rest position is not modified
        return self.data[f"{self.name}_body_rest_pose"]

    @property
    def body_twist_bone_names(self) -> list[str]:
        twist_bone_names = self.data.get(f"{self.name}_body_twist_bone_names", [])
        if twist_bone_names:
            return twist_bone_names

        # get the updated twist bone names
        for twist_index in range(self.body_dna_reader.getTwistCount()):
            for output_index in self.body_dna_reader.getTwistOutputJointIndices(twist_index):
                twist_bone_names.append(self.body_dna_reader.getJointName(output_index))

        # save the updated bone names so we don't have to query them again
        self.data[f"{self.name}_body_twist_bone_names"] = list(set(twist_bone_names))
        return self.data[f"{self.name}_body_twist_bone_names"]

    @property
    def body_swing_bone_names(self) -> list[str]:
        swing_bone_names = self.data.get(f"{self.name}_body_swing_bone_names", [])
        if swing_bone_names:
            return swing_bone_names

        # get the body swing bone names
        for swing_index in range(self.body_dna_reader.getSwingCount()):
            for output_index in self.body_dna_reader.getSwingOutputJointIndices(swing_index):
                swing_bone_names.append(self.body_dna_reader.getJointName(output_index))

        # save the updated bone names so we don't have to query them again
        self.data[f"{self.name}_body_swing_bone_names"] = list(set(swing_bone_names))
        return self.data[f"{self.name}_body_swing_bone_names"]

    @property
    def body_driven_bone_names(self) -> list[str]:
        driven_bone_names = self.data.get(f"{self.name}_body_driven_bone_names", [])
        if driven_bone_names:
            return driven_bone_names

        # get the body rbf driven bone names
        for solver_index in range(self.body_dna_reader.getRBFSolverCount()):
            for pose_index in self.body_dna_reader.getRBFSolverPoseIndices(solver_index):
                for attr_index in self.body_dna_reader.getRBFPoseJointOutputIndices(pose_index):
                    joint_index = attr_index // ATTR_COUNT_PER_EULER_JOINT
                    driven_bone_names.append(self.body_dna_reader.getJointName(joint_index))

        # save the driven bone names so we don't have to query them again
        self.data[f"{self.name}_body_driven_bone_names"] = list(set(driven_bone_names))
        return self.data[f"{self.name}_body_driven_bone_names"]

    @property
    def body_driver_bone_names(self) -> list[str]:
        driver_bone_names = self.data.get(f"{self.name}_body_driver_bone_names", [])
        if driver_bone_names:
            return driver_bone_names

        # get the rbf driver bone names
        driver_bone_names = {
            self.body_dna_reader.getRawControlName(i).split(".")[0]
            for i in range(self.body_dna_reader.getRawControlCount())
        }
        # also include the head driver bone names since they are stored in the head DNA, but the
        # body rig uses those same bones (neck_01, neck_02, head)
        if self.head_dna_reader:
            for bone_name in self.head_driver_bone_names:
                # only add the driver bone if it exists in the body rig
                if self.body_rig.pose.bones.get(bone_name):
                    driver_bone_names.add(bone_name)

        # save the driver bone names so we don't have to query them again
        self.data[f"{self.name}_body_driver_bone_names"] = list(driver_bone_names)
        return self.data[f"{self.name}_body_driver_bone_names"]

    def head_initialize(self):
        from .bindings import riglogic
        from .dna_io import get_dna_reader

        if not self.head_valid:
            return

        # ---- Initialize the Head Rig Instance ---
        # set the dna reader
        self.data[f"{self.name}_head_dna_reader"] = get_dna_reader(
            file_path=Path(bpy.path.abspath(self.head_dna_file_path)).absolute(), memory_resource=None
        )

        # make sure the rig bones are using the correct rotation mode
        if self.head_rig and self.head_rig.pose:
            for pose_bone in self.head_rig.pose.bones:
                if pose_bone.name.startswith("FACIAL_"):
                    pose_bone.rotation_mode = "XYZ"
                else:
                    pose_bone.rotation_mode = "QUATERNION"

        # set the rig logic manager and instance
        self.data[f"{self.name}_head_manager"] = riglogic.RigLogic.create(
            reader=self.data[f"{self.name}_head_dna_reader"], config=riglogic.Configuration(), memRes=None
        )
        self.data[f"{self.name}_head_instance"] = riglogic.RigInstance.create(
            rigLogic=self.data[f"{self.name}_head_manager"], memRes=None
        )

        # calling theses properties will cache their values
        self.head_texture_masks_node  # noqa: B018
        self.head_mesh_index_lookup  # noqa: B018
        self.head_channel_name_to_index_lookup  # noqa: B018
        self.head_channel_index_to_mesh_index_lookup  # noqa: B018
        self.head_shape_key_blocks  # noqa: B018
        self.head_driven_bone_names  # noqa: B018
        self.head_driver_bone_names  # noqa: B018
        self.head_rest_pose  # noqa: B018

        self.data[f"{self.name}_head_initialized"] = True

    def body_initialize(self, update_rbf_solver_list: bool = True):
        from .bindings import riglogic
        from .dna_io import get_dna_reader

        if not self.body_valid:
            return

        # ---- Initialize the Body Rig Instance ---
        # set the body dna reader
        self.data[f"{self.name}_body_dna_reader"] = get_dna_reader(
            file_path=Path(bpy.path.abspath(self.body_dna_file_path)).absolute(), memory_resource=None
        )

        # make sure the body bones are using the correct rotation mode
        if self.body_rig and self.body_rig.pose:
            for pose_bone in self.body_rig.pose.bones:
                if pose_bone.name in self.body_driver_bone_names:
                    pose_bone.rotation_mode = "QUATERNION"
                else:
                    pose_bone.rotation_mode = "XYZ"

        # set the rig logic manager and instance
        self.data[f"{self.name}_body_manager"] = riglogic.RigLogic.create(
            reader=self.data[f"{self.name}_body_dna_reader"],
            config=riglogic.Configuration(
                calculationType=riglogic.CalculationType.AnyVector,
                loadJoints=True,
                loadBlendShapes=True,
                loadAnimatedMaps=True,
                loadMachineLearnedBehavior=True,
                loadRBFBehavior=True,
                loadTwistSwingBehavior=True,
                translationType=riglogic.TranslationType.Vector,
                rotationType=riglogic.RotationType.Quaternions,
                rotationOrder=riglogic.RotationOrder.ZYX,
                scaleType=riglogic.ScaleType.Vector,
            ),
            memRes=None,
        )
        self.data[f"{self.name}_body_instance"] = riglogic.RigInstance.create(
            rigLogic=self.data[f"{self.name}_body_manager"], memRes=None
        )

        # populate the body rbf solver list
        if update_rbf_solver_list:
            self.update_body_rbf_solver_list()

        # calling theses properties will cache their values
        self.body_rest_pose  # noqa: B018
        self.body_twist_bone_names  # noqa: B018
        self.body_swing_bone_names  # noqa: B018
        self.body_driven_bone_names  # noqa: B018
        self.body_driver_bone_names  # noqa: B018

        self.data[f"{self.name}_body_initialized"] = True

    def initialize(self):
        self.head_initialize()
        self.body_initialize()

    def destroy(self):
        # clears these data items from the dictionary, this frees them up to be garbage collected
        self.data.clear()
        self.data[f"{self.name}_head_initialized"] = False
        self.data[f"{self.name}_body_initialized"] = False

    def update_head_switch_values(self):  # noqa: PLR0912
        if not self.face_board:
            return

        # update the head follow body switch constraint influence
        face_gui_control = self.face_board.pose.bones.get("CTRL_faceGUI")
        face_follow_head_switch = self.face_board.pose.bones.get("CTRL_faceGUIfollowHead")
        if face_follow_head_switch and face_gui_control:
            constraint = None
            for existing_constraint in face_gui_control.constraints:
                if existing_constraint.type == "CHILD_OF":
                    constraint = existing_constraint
                    break
            if constraint and round(constraint.influence, 3) != round(face_follow_head_switch.location.y, 3):
                constraint.influence = face_follow_head_switch.location.y

        # update the eye aim follow head switch constraint influence
        eye_aim_control = self.face_board.pose.bones.get("CTRL_C_eyesAim")
        eye_aim_follow_head_switch = self.face_board.pose.bones.get("CTRL_eyesAimFollowHead")
        if eye_aim_follow_head_switch and eye_aim_control:
            constraint = None
            for existing_constraint in eye_aim_control.constraints:
                if existing_constraint.type == "CHILD_OF":
                    constraint = existing_constraint
                    break
            if constraint and round(constraint.influence, 3) != round(eye_aim_follow_head_switch.location.y, 3):
                constraint.influence = eye_aim_follow_head_switch.location.y

        # update the eye aim control visibility if needed
        # Note: In Blender 5.0+, the hide property moved from Bone to PoseBone
        if eye_aim_control:
            current_hide = eye_aim_control.hide if IS_BLENDER_5 else eye_aim_control.bone.hide
            if self.head_use_eye_aim == current_hide:
                if IS_BLENDER_5:
                    eye_aim_control.hide = not self.head_use_eye_aim
                else:
                    eye_aim_control.bone.hide = not self.head_use_eye_aim

            for child in eye_aim_control.children_recursive:
                if not child.name.startswith(("GRP_", "LOC_")):
                    child_hide = child.hide if IS_BLENDER_5 else child.bone.hide
                    if self.head_use_eye_aim == child_hide:
                        if IS_BLENDER_5:
                            child.hide = not self.head_use_eye_aim
                        else:
                            child.bone.hide = not self.head_use_eye_aim

    def get_head_gui_control_values_from_eye_aim(self) -> dict[str, dict[str, float]]:
        values = {}
        if not self.face_board:
            return values

        for target_name, eye_bone_name, control_name in [
            ("CTRL_L_eyeAim", "FACIAL_L_Eye", "CTRL_L_eye"),
            ("CTRL_R_eyeAim", "FACIAL_R_Eye", "CTRL_R_eye"),
        ]:
            target = self.face_board.pose.bones.get(target_name)
            eye = self.head_rig.pose.bones.get(eye_bone_name)
            if target and eye:
                eye_rest_matrix = self.face_board.matrix_world @ eye.bone.matrix_local

                # Current eye-to-target direction in world space
                eye_pos = self.face_board.matrix_world @ eye.head
                target_pos = self.face_board.matrix_world @ target.head
                look_direction = target_pos - eye_pos

                if look_direction.length < FLOATING_POINT_PRECISION:
                    continue

                look_direction.normalize()

                # Convert look direction to eye's local space
                eye_matrix_inv = eye_rest_matrix.inverted()
                local_look_direction = (eye_matrix_inv.to_3x3() @ look_direction).normalized()

                # Calculate horizontal distance (projection onto XZ plane)
                horizontal_dist = math.sqrt(local_look_direction.x**2 + local_look_direction.z**2)

                if horizontal_dist > FLOATING_POINT_PRECISION:
                    # Remap yaw to continuous range centered on forward direction (-Z)
                    # Instead of atan2(x, -z), we use the normalized x component directly
                    # This gives us a smooth -1 to 1 range for horizontal movement
                    x_normalized = local_look_direction.x / horizontal_dist

                    # For better control, we can use asin which gives -90° to 90° range
                    yaw = math.asin(max(-1.0, min(1.0, x_normalized)))
                else:
                    # Looking straight up/down, yaw is undefined
                    yaw = 0.0

                # Pitch is the angle from the horizontal plane
                pitch = math.atan2(local_look_direction.y, horizontal_dist)

                # Map angles to -1..1 range based on max rotation
                x_max_rad = math.radians(60.0)
                y_max_rad = math.radians(30.0)

                x_control = max(-1.0, min(1.0, yaw / x_max_rad))
                y_control = max(-1.0, min(1.0, pitch / y_max_rad))

                values[control_name] = {"x": x_control, "y": y_control}

        return values

    def update_head_raw_control_values(self, override_values: dict[str, dict[str, float]] | None = None):
        # skip if the body rig is not set
        if not self.head_rig or not self.evaluated_head_rig or not self.head_dna_reader:
            return

        # skip if the rest pose is not initialized
        if not self.head_rest_pose:
            return

        if not self.evaluated_head_rig.pose:
            return

        missing_raw_controls = []
        converted_quaternions = {}

        # convert the quaternion values to the correct coordinate system
        for pose_bone in self.evaluated_head_rig.pose.bones:
            if pose_bone.name in self.head_driver_bone_names:
                # get the local quaternion, but from the world matrix to account for constraints, since we
                # can't always assume the local quaternion value is what is driving the bone rotation. For
                # example, if the body is driving the head bone transforms via constraints.
                # TODO: This math might have performance implications, so we might want review this later.
                quaternion = utilities.get_pose_bone_local_quaternion(pose_bone)
                converted_quaternions[pose_bone.name] = quaternion

        for index in range(self.head_dna_reader.getRawControlCount()):
            full_name = self.head_dna_reader.getRawControlName(index)
            control_name, axis = full_name.split(".")
            # only process quaternions
            if not axis.startswith("q"):
                continue

            axis = axis.rsplit("q", -1)[-1].lower()
            if self.evaluated_head_rig:
                # override the values can be provided to update values based on them vs current head rig bone locations
                # This can be used for baking the values to an action
                if override_values:
                    value = override_values.get(control_name, {}).get(axis)
                    if value is not None:
                        self.head_instance.setRawControl(index, value)
                else:
                    quaternion = converted_quaternions.get(control_name)
                    if quaternion:
                        value = getattr(quaternion, axis)
                        self.head_instance.setRawControl(index, value)
                    else:
                        missing_raw_controls.append(control_name)

        if missing_raw_controls and not self.data.get(f"{self.name}_head_logged_missing_raw_controls"):
            logger.warning(
                f'The following raw controls are missing on "{self.head_rig.name}":\n{pformat(missing_raw_controls)}.'
            )
            logger.warning(f"You are not listening to {len(missing_raw_controls)} raw controls")
            logger.warning(
                f"This is most likely due to the these bones being missing from the rig {self.head_rig.name}."
            )
            self.data[f"{self.name}_head_logged_missing_raw_controls"] = True

    def update_head_gui_control_values(self, override_values: dict[str, dict[str, float]] | None = None):  # noqa: PLR0912
        # skip if the face board is not set
        if not self.face_board or not self.head_dna_reader:
            return

        missing_gui_controls = []

        center_eye_control = self.face_board.pose.bones.get("CTRL_C_eye")

        eye_aim_override_values = {}
        if self.head_use_eye_aim:
            eye_aim_override_values = self.get_head_gui_control_values_from_eye_aim()

        for index in range(self.head_dna_reader.getGUIControlCount()):
            full_name = self.head_dna_reader.getGUIControlName(index)
            control_name, axis = full_name.split(".")
            axis = axis.rsplit("t", -1)[-1].lower()
            if self.face_board:
                # Override values can be provided to update values based on them vs current face board
                # bone locations. This can be used for baking the values to an action.
                if override_values:
                    value = override_values.get(control_name, {}).get(axis)
                    if value is not None:
                        self.head_instance.setGUIControl(index, value)
                else:
                    pose_bone = self.face_board.pose.bones.get(control_name)
                    if pose_bone:
                        value = getattr(pose_bone.location, axis)
                        # special case for the eye controls, if the center eye control is above 0,
                        # use that value instead
                        if control_name in ["CTRL_L_eye", "CTRL_R_eye"]:
                            center_value = eye_aim_override_values.get(control_name, {}).get(axis)
                            if center_value is not None:
                                if abs(center_value) > FLOATING_POINT_PRECISION:
                                    value = center_value
                            elif center_eye_control:
                                center_value = getattr(center_eye_control.location, axis)
                                if abs(center_value) > FLOATING_POINT_PRECISION:
                                    value = center_value

                        self.head_instance.setGUIControl(index, value)
                    else:
                        missing_gui_controls.append(control_name)

        if missing_gui_controls and not self.data.get(f"{self.name}_logged_missing_gui_controls"):
            logger.warning(
                f'The following GUI controls are missing on "{self.face_board.name}":\n{pformat(missing_gui_controls)}.'
            )
            logger.warning(f"You are not listening to {len(missing_gui_controls)} GUI controls")
            logger.warning(
                "This is most likely due to the DNA file being an older version then what "
                "the face board currently supports."
            )
            logger.warning(
                "Using a new .dna file created from the latest version of MetaHuman Creator will probably resolve this."
            )
            self.data[f"{self.name}_logged_missing_gui_controls"] = True

        # set the active LOD level for the head instance to optimize performance
        self.head_instance.setLOD(level=int(self.active_lod[-1]))
        # map the GUI changes to the raw controls
        self.head_manager.mapGUIToRawControls(self.head_instance)

        if self.evaluate_rbfs:
            self.update_head_raw_control_values()

        # calculate the controls
        self.head_manager.calculate(self.head_instance)

    def solo_head_shape_key_value(self, shape_key: bpy.types.ShapeKey):
        # skip if the head mesh is not set
        if not self.head_mesh or not self.head_dna_reader:
            return

        # skip if there are no shape keys
        if len(bpy.data.shape_keys) == 0:
            return

        # make all other shape keys 0.0
        for index, _ in enumerate(self.head_instance.getBlendShapeOutputs()):
            for _shape_key in self.head_shape_key_blocks.get(index, []):
                if _shape_key and _shape_key != shape_key:
                    _shape_key.value = 0.0

        # set the provided shape key value to 1.0
        shape_key.value = 1.0

    def update_head_shape_keys(self) -> list[tuple[bpy.types.ShapeKey, float]]:
        # skip if the head mesh is not set
        if not self.head_mesh or not self.head_dna_reader:
            return []

        # skip if there are no shape keys
        if len(bpy.data.shape_keys) == 0:
            return []

        missing_shape_keys = []
        shape_key_values = []

        # update blend shapes
        for index, value in enumerate(self.head_instance.getBlendShapeOutputs()):
            for shape_key in self.head_shape_key_blocks.get(index, []):
                if shape_key:
                    shape_key.value = value
                    shape_key_values.append((shape_key, value))
                else:
                    missing_shape_keys.append(index)

        if missing_shape_keys and not self.data.get(f"{self.name}_logged_missing_shape_keys"):
            name_lookup = {v: k for k, v in self.head_channel_name_to_index_lookup.items()}
            missing_data = {}
            # group the missing shape keys by mesh object
            for index in missing_shape_keys:
                missing_name = name_lookup[index]
                mesh_index = self.head_channel_index_to_mesh_index_lookup[index]
                mesh_object = self.head_mesh_index_lookup[mesh_index]
                if len(missing_name) > SHAPE_KEY_NAME_MAX_LENGTH:
                    # skip warning the user about any missing shape keys names being too long.

                    # Currently, Blender has a limit of 63 characters for shape key names.
                    # This is something that the user might be able to overcome by changing blender
                    # source and recompiling. However, this is not something that we can fix in the addon.

                    # Because this limitation there are 42 missing shape keys from the MetaHuman creator DNA files
                    # that can't be imported because their names are too long. However these are extreme
                    # combinations and for most people this will not be an issue.
                    continue

                missing_data[mesh_object.name] = missing_data.get(mesh_object.name, [])
                missing_data[mesh_object.name].append(missing_name)

            for mesh_name, missing_names in missing_data.items():
                logger.warning(
                    f'The following shape key blocks are missing on "{mesh_name}":\n{pformat(missing_names)}.'
                )

            if len(missing_data.keys()) > 0:
                logger.warning(
                    f"A total of {len(missing_data.keys())} shape key blocks are not being updated by Rig Logic."
                )

            self.data[f"{self.name}_logged_missing_shape_keys"] = True

        return shape_key_values

    def update_head_texture_masks(self) -> list[tuple[str, float]]:
        # skip if the material is not set
        if not self.head_material or not self.head_dna_reader:
            return []

        head_texture_masks_node = self.head_texture_masks_node
        # if the texture masks node is not set, we can't update the texture masks
        if not head_texture_masks_node:
            logger.warning(f'The texture masks node was not found on the material "{self.head_material.name}"')
            return []

        texture_mask_values = []

        # update texture masks values
        for index, value in enumerate(self.head_instance.getAnimatedMapOutputs()):
            name = self.head_dna_reader.getAnimatedMapName(index)
            slider_name = f"{name.split('.')[0].split('_')[1].lower().replace('cm', 'wm')}.{name.split('.')[-1]}_msk"

            mask_slider = head_texture_masks_node.inputs.get(slider_name)
            if mask_slider:
                mask_slider.default_value = value  # type: ignore[attr-defined]
                texture_mask_values.append((slider_name, value))
            else:
                logger.warning(
                    f'The texture mask slider "{slider_name}" was not found on the material "{self.head_material.name}"'
                )

        return texture_mask_values

    def update_head_bone_transforms(self):
        # skip if the head rig is not set
        if not self.head_rig or not self.head_dna_reader:
            return

        # skip if the rest pose is not initialized
        # https://github.com/poly-hammer/meta-human-dna-addon/issues/58
        if not self.head_rest_pose:
            return

        raw_joint_output = self.head_instance.getRawJointOutputs()
        # update joint transforms
        for index in range(self.head_dna_reader.getJointCount()):
            # get the bone
            name = self.head_dna_reader.getJointName(index)

            # only update the facial bones or non-driver bones
            if name in self.head_driver_bone_names:
                continue

            pose_bone = self.head_rig.pose.bones.get(name)
            if pose_bone:
                # get the rest pose values that we saved during initialization
                rest_location, rest_rotation, rest_scale, rest_to_parent_matrix = self.head_rest_pose[pose_bone.name]

                # get the values
                matrix_index = (index + 1) * 9
                values = raw_joint_output[(index * 9) : matrix_index]

                # extract the delta values
                location_delta = Vector([values[0] / SCALE_FACTOR, values[1] / SCALE_FACTOR, values[2] / SCALE_FACTOR])
                rotation_delta = Euler([math.radians(values[3]), math.radians(values[4]), math.radians(values[5])])
                scale_delta = Vector(values[6:9])

                # update the transformations using the rest pose and the delta values
                # we need to copy the vectors so we don't modify the original rest pose
                location = Vector(
                    [
                        rest_location.x + location_delta.x,
                        rest_location.y + location_delta.y,
                        rest_location.z + location_delta.z,
                    ]
                )
                rotation = Euler(
                    [
                        rest_rotation.x + rotation_delta.x,
                        rest_rotation.y + rotation_delta.y,
                        rest_rotation.z + rotation_delta.z,
                    ],
                    "XYZ",
                )
                scale = Vector(
                    [rest_scale.x + scale_delta.x, rest_scale.y + scale_delta.y, rest_scale.z + scale_delta.z]
                )

                # update the bone matrix
                modified_matrix = Matrix.LocRotScale(location, rotation, scale)
                try:
                    pose_bone.matrix_basis = rest_to_parent_matrix.inverted() @ modified_matrix
                except ValueError as error:
                    logger.warning(f'Error updating bone "{name}" matrix: {error}')
                    continue

                # if the bone is not a leaf bone, we need to update the rotation again
                if pose_bone.children:
                    pose_bone.rotation_euler = rotation_delta
            else:
                logger.warning(
                    f'The bone "{name}" was not found on "{self.head_rig.name}". Rig Logic will not update the bone.'
                )

    def reset_body_raw_control_values(self):
        # skip if the body rig is not set
        if not self.body_initialized:
            self.body_initialize()

        if not self.body_dna_reader:
            logger.warning("The body DNA reader is not set. The body raw control values will not be reset.")
            return

        if not self.evaluate_rbfs:
            # reset all raw controls to 0.0
            for index in range(self.body_dna_reader.getRawControlCount()):
                full_name = self.body_dna_reader.getRawControlName(index)
                _, axis = full_name.split(".")
                axis = axis.rsplit("q", -1)[-1].lower()
                if axis == "w":
                    self.body_instance.setRawControl(index, 1.0)
                else:
                    self.body_instance.setRawControl(index, 0.0)

            self.body_instance.setLOD(level=int(self.active_lod[-1]))
            self.body_manager.calculate(self.body_instance)
        else:
            self.update_body_raw_control_values()

        self.update_body_bone_transforms()

    def reset_head_raw_control_values(self):
        # skip if the head rig is not set
        if not self.head_initialized:
            self.head_initialize()

        if not self.head_dna_reader:
            logger.warning("The head DNA reader is not set. The head raw control values will not be reset.")
            return

        if not self.evaluate_rbfs:
            # reset all raw controls to 0.0
            for index in range(self.head_dna_reader.getRawControlCount()):
                full_name = self.head_dna_reader.getRawControlName(index)
                control_name, axis = full_name.split(".")
                if control_name in self.head_driver_bone_names:
                    axis = axis.rsplit("q", -1)[-1].lower()
                    if axis == "w":
                        self.head_instance.setRawControl(index, 1.0)
                    else:
                        self.head_instance.setRawControl(index, 0.0)

            self.head_instance.setLOD(level=int(self.active_lod[-1]))
            self.head_manager.calculate(self.head_instance)
        else:
            self.update_head_raw_control_values()
            self.head_instance.setLOD(level=int(self.active_lod[-1]))
            self.head_manager.calculate(self.head_instance)

        self.update_head_bone_transforms()

    def update_body_raw_control_values(self, override_values: dict[str, dict[str, float]] | None = None):
        # skip if the body rig is not set
        if not self.body_rig or not self.evaluated_body_rig or not self.body_dna_reader:
            return

        # skip if the rest pose is not initialized
        if not self.body_rest_pose:
            return

        if not self.evaluated_body_rig.pose:
            return

        missing_raw_controls = []
        converted_quaternions = {}

        # convert the quaternion values to the correct coordinate system
        for pose_bone in self.evaluated_body_rig.pose.bones:
            if pose_bone.name in self.body_driver_bone_names:
                # get the local quaternion, but from the world matrix to account for constraints, since we
                # can't always assume the local quaternion value is what is driving the bone rotation. For
                # example, a control rig might be driving the body bone rotation via constraints.
                # TODO: This math might have performance implications, so we might want review this later.
                quaternion = utilities.get_pose_bone_local_quaternion(pose_bone)
                converted_quaternions[pose_bone.name] = quaternion

        for index in range(self.body_dna_reader.getRawControlCount()):
            full_name = self.body_dna_reader.getRawControlName(index)
            control_name, axis = full_name.split(".")
            axis = axis.rsplit("q", -1)[-1].lower()
            if self.evaluated_body_rig:
                # override the values can be provided to update values based on them vs current body rig bone locations
                # This can be used for baking the values to an action
                if override_values:
                    value = override_values.get(control_name, {}).get(axis)
                    if value is not None:
                        self.body_instance.setRawControl(index, value)
                else:
                    quaternion = converted_quaternions.get(control_name)
                    if quaternion:
                        value = getattr(quaternion, axis)
                        self.body_instance.setRawControl(index, value)
                    else:
                        missing_raw_controls.append(control_name)

        if missing_raw_controls and not self.data.get(f"{self.name}_body_logged_missing_raw_controls"):
            logger.warning(
                f'The following raw controls are missing on "{self.body_rig.name}":\n{pformat(missing_raw_controls)}.'
            )
            logger.warning(f"You are not listening to {len(missing_raw_controls)} raw controls")
            logger.warning(
                f"This is most likely due to the these bones being missing from the rig {self.body_rig.name}."
            )
            self.data[f"{self.name}_body_logged_missing_raw_controls"] = True

        # set the active LOD level for the body instance to optimize performance
        self.body_instance.setLOD(level=int(self.active_lod[-1]))

        # calculate the changes
        self.body_manager.calculate(self.body_instance)

    def update_body_bone_transforms(self):
        # skip if the body rig is not set
        if not self.body_rig or not self.body_dna_reader:
            return

        # skip if the rest pose is not initialized
        if not self.body_rest_pose:
            return

        # get the delta values
        D = self.body_instance.getRawJointOutputs()

        # update joint transforms
        for joint_index in range(self.body_dna_reader.getJointCount()):
            # skip the root joint
            if joint_index == 0:
                continue

            # get the bone
            name = self.body_dna_reader.getJointName(joint_index)
            pose_bone = self.body_rig.pose.bones.get(name)
            if pose_bone:
                # Only update bones that are updated via RBFs, twists, or swings
                if name not in (self.body_driven_bone_names + self.body_swing_bone_names + self.body_twist_bone_names):
                    continue

                # get the values
                attr_index = joint_index * ATTR_COUNT_PER_QUATERNION_JOINT
                # get the rest pose values that we saved during initialization
                rest_location, rest_rotation, rest_scale, rest_to_parent_matrix = self.body_rest_pose[pose_bone.name]
                # extract the delta values
                location_delta = Vector(
                    [D[attr_index] / SCALE_FACTOR, D[attr_index + 1] / SCALE_FACTOR, D[attr_index + 2] / SCALE_FACTOR]
                )
                rotation_delta = Quaternion(
                    [D[attr_index + 6], D[attr_index + 3], D[attr_index + 4], D[attr_index + 5]]
                )
                scale_delta = Vector([D[attr_index + 7], D[attr_index + 8], D[attr_index + 9]])

                # update the transformations using the rest pose and the delta values
                # we need to copy the vectors so we don't modify the original rest pose
                location = Vector(
                    [
                        rest_location.x + location_delta.x,
                        rest_location.y + location_delta.y,
                        rest_location.z + location_delta.z,
                    ]
                )

                rotation = rest_rotation.to_quaternion() @ rotation_delta

                scale = Vector(
                    [rest_scale.x + scale_delta.x, rest_scale.y + scale_delta.y, rest_scale.z + scale_delta.z]
                )

                # update the bone matrix
                modified_matrix = Matrix.LocRotScale(location, rotation, scale)
                try:
                    pose_bone.matrix_basis = rest_to_parent_matrix.inverted() @ modified_matrix
                except ValueError as error:
                    logger.warning(f'Error updating bone "{name}" matrix: {error}')
                    continue

            else:
                logger.warning(
                    f'The bone "{name}" was not found on "{self.body_rig.name}". Rig Logic will not update the bone.'
                )

    def update_body_rbf_solver_list(self):
        try:
            from .editors.pose_editor.core import update_body_rbf_solver_list

            update_body_rbf_solver_list(self)
        except ImportError:
            logger.debug("Could not import the pose editor module to update the body RBF solver list.")

    def evaluate(
        self, component: Literal["head", "body", "all"] = "all", dependency_graph: bpy.types.Depsgraph | None = None
    ):
        window_manager_properties: "MetahumanWindowMangerProperties" = bpy.context.window_manager.meta_human_dna  # type: ignore[attr-defined]  # noqa: UP037
        # this condition prevents constant evaluation
        if window_manager_properties.evaluate_dependency_graph:
            # turn off the dependency graph evaluation so we can update the controls without triggering an update
            window_manager_properties.evaluate_dependency_graph = False

            if not self.head_initialized:
                self.head_initialize()

            if not self.body_initialized:
                self.body_initialize()

            # apply the dependency graph update so we have the latest evaluated bone transforms
            self.apply_dependency_graph_update(dependency_graph)

            if component in ("body", "all") and self.body_initialized:
                if self.evaluate_rbfs:
                    self.update_body_raw_control_values()

                # apply the changes
                if self.evaluate_bones:
                    self.update_body_bone_transforms()

            if component in ("head", "all") and self.head_initialized:
                # update the gui controls
                self.update_head_switch_values()
                self.update_head_gui_control_values()

                # apply the changes
                if self.evaluate_bones:
                    self.update_head_bone_transforms()
                if self.evaluate_shape_keys:
                    self.update_head_shape_keys()
                if self.evaluate_texture_masks:
                    self.update_head_texture_masks()

            # turn on the dependency graph evaluation back on
            window_manager_properties.evaluate_dependency_graph = True
