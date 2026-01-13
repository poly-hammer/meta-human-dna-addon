# standard library imports
import logging
import math
import os

from collections.abc import Iterable
from pathlib import Path

# third party imports
import bpy
import gpu

from gpu_extras.presets import draw_circle_2d
from mathutils import Color, Euler, Matrix, Vector

# local imports
from ..constants import (
    BASE_DNA_FOLDER,
    BODY_HIGH_LEVEL_TOPOLOGY_GROUPS,
    BODY_MAPS,
    HEAD_MAPS,
    HEAD_TO_BODY_LOD_MAPPING,
    NUMBER_OF_HEAD_LODS,
    POSES_FOLDER,
    ToolInfo,
)
from ..typing import *  # noqa: F403


logger = logging.getLogger(__name__)


def get_active_head() -> "MetaHumanComponentHead | None":
    # Avoid circular import
    from ..utilities import get_active_head as _get_active_head

    return _get_active_head()


def get_active_body() -> "MetaHumanComponentBody | None":
    # Avoid circular import
    from ..utilities import get_active_body as _get_active_body

    return _get_active_body()


def get_bake_start_frame(self: "BakeAnimationBase") -> int:
    try:
        return self.get("bake_start_frame", bpy.context.scene.frame_start if bpy.context.scene else 1)
    except AttributeError:
        return self.get("bake_start_frame", 1)


def get_bake_end_frame(self: "BakeAnimationBase") -> int:
    try:
        return self.get("bake_end_frame", bpy.context.scene.frame_end if bpy.context.scene else 250)
    except AttributeError:
        return self.get("bake_end_frame", 250)


def get_active_rig_instance() -> "RigInstance | None":
    """
    Gets the active rig instance.
    """
    scene_properties: "MetahumanSceneProperties" = bpy.context.scene.meta_human_dna  # type: ignore  # noqa: UP037
    if not hasattr(bpy.context.scene, ToolInfo.NAME):
        return None

    if len(scene_properties.rig_instance_list) > 0:
        index = scene_properties.rig_instance_list_active_index
        return scene_properties.rig_instance_list[index]
    return None


def get_head_texture_logic_node(material: bpy.types.Material) -> bpy.types.ShaderNodeGroup | None:
    if not material or not material.node_tree:
        return None
    for node in material.node_tree.nodes:
        # Check if this is the right group node by checking one input name
        # We don't check all to avoid performance issues
        if node.type == "GROUP" and node.inputs.get("wm1.head_wm1_jawOpen_msk"):
            return node  # type: ignore[return-value]
    return None


def get_body_texture_logic_node(material: bpy.types.Material) -> bpy.types.ShaderNodeGroup | None:
    if not material or not material.node_tree:
        return None
    for node in material.node_tree.nodes:
        # Check if this is the right group node by checking one input name
        # We don't check all to avoid performance issues
        if (
            node.type == "GROUP"
            and node.inputs.get("Color_MAIN")
            and node.inputs.get("Normal_MAIN")
            and node.inputs.get("Cavity_MAIN")
        ):
            return node  # type: ignore[return-value]
    return None


def get_active_material_preview(self: "RigInstance") -> int:
    return self.get("active_material_preview", 0)


def get_face_pose_previews_items(self: "RigInstance", context: "Context") -> Iterable[tuple[str, str, str, int, int]]:  # noqa: ARG001
    from ..properties import preview_collections

    enum_items = []

    if context is None:
        return enum_items

    directory = POSES_FOLDER / "face"

    # Get the preview collection.
    preview_collection = preview_collections["face_poses"]

    # If the enum items have already been cached, return them so we don't have to regenerate them.
    if preview_collection.values():
        return preview_collection.face_pose_previews

    if directory.exists():
        image_paths = []

        for folder_path, _, file_names in os.walk(directory):
            for file_name in file_names:
                if file_name == "thumbnail-preview.png":
                    thumbnail_file_path = Path(folder_path, file_name)
                    pose_file_path = Path(folder_path, "pose.json")
                    if pose_file_path.exists() and thumbnail_file_path.exists():
                        image_paths.append(Path(folder_path, file_name))

        for i, file_path in enumerate(image_paths):
            name = file_path.parent.name
            # generates a thumbnail preview for a file.
            icon = preview_collection.get(name)
            if not icon:
                thumb = preview_collection.load(name, str(file_path), "IMAGE")
            else:
                thumb = preview_collection[name]
            enum_items.append((str(file_path), name, "", thumb.icon_id, i))

    # cache the enum item values for later retrieval
    preview_collection.face_pose_previews = enum_items
    return preview_collection.face_pose_previews


def get_head_mesh_topology_groups(self: "RigInstance", context: "Context") -> list[tuple[str, str, str]]:  # noqa: ARG001
    enum_items: list[tuple[str, str, str]] = []
    instance = get_active_rig_instance()
    if instance and instance.head_mesh:
        enum_items.extend(
            (
                group.name,
                " ".join([i.capitalize() for i in group.name.replace("TOPO_GROUP_", "").split("_")]),
                f"Select vertices assigned to {group.name} on the active head mesh",
            )
            for group in instance.head_mesh.vertex_groups
            if group.name.startswith("TOPO_GROUP_")
        )

    # Sort the enum items alphabetically by their first index (the group name)
    enum_items.sort(key=lambda x: x[0])
    return enum_items


def get_body_mesh_topology_groups(self: "RigInstance", _: "Context") -> list[tuple[str, str, str]]:
    enum_items = []
    instance = get_active_rig_instance()
    if instance and instance.body_mesh:
        for group in instance.body_mesh.vertex_groups:
            if group.name.startswith("TOPO_GROUP_"):
                enum_item = (
                    group.name,
                    " ".join([i.capitalize() for i in group.name.replace("TOPO_GROUP_", "").split("_")]),
                    f"Select vertices assigned to {group.name} on the active body mesh",
                )
                if self.body_show_only_high_level_topology_groups:
                    if any(group.name.endswith(high_level) for high_level in BODY_HIGH_LEVEL_TOPOLOGY_GROUPS):
                        enum_items.append(enum_item)
                elif not any(group.name.endswith(high_level) for high_level in BODY_HIGH_LEVEL_TOPOLOGY_GROUPS):
                    enum_items.append(enum_item)

    # Sort the enum items alphabetically by their first index (the group name)
    enum_items.sort(key=lambda x: x[0])
    return enum_items


def get_head_rig_bone_groups(self: "RigInstance", context: "Context") -> list[tuple[str, str, str]]:
    from ..bindings import meta_human_dna_core  # pyright: ignore[reportAttributeAccessIssue]

    enum_items = [
        (
            group_name,
            " ".join([i.capitalize() for i in group_name.split("_")]),
            f"Select bones in the group {group_name} on the head rig",
        )
        for group_name in meta_human_dna_core.HEAD_BONE_SELECTION_GROUPS
    ]
    instance = get_active_rig_instance()
    if instance and instance.head_mesh and instance.list_surface_bone_groups:
        enum_items.extend(
            (item[0], f"(Surface) {item[1]}", item[2]) for item in get_head_mesh_topology_groups(self, context)
        )
    return enum_items


def get_body_rig_bone_groups(self: "RigInstance", context: "Context") -> list[tuple[str, str, str]]:  # noqa: ARG001
    from ..bindings import meta_human_dna_core  # pyright: ignore[reportAttributeAccessIssue]

    enum_items = [
        (
            group_name,
            " ".join([i.capitalize() for i in group_name.split("_")]),
            f"Select bones in the group {group_name} on the body rig",
        )
        for group_name in meta_human_dna_core.BODY_BONE_SELECTION_GROUPS
    ]

    # TODO: Maybe add surface bone groups here as well
    return enum_items


def get_base_dna_folder(self: "MetahumanWindowMangerProperties", context: "Context") -> list[tuple[str, str, str]]:  # noqa: ARG001
    from ..utilities import get_addon_preferences

    # get all the dna files in the addon's dna folder
    enum_items = [
        (
            str(folder.absolute()),
            " ".join([i.capitalize() for i in folder.stem.split("_")]),
            f"Use the {folder.name} folder and its base DNA component files to convert the selected mesh",
        )
        for folder in BASE_DNA_FOLDER.iterdir()
        if not folder.is_file() and any(f.suffix == ".dna" for f in folder.iterdir())
    ]

    # get all the dna files in the extra dna folders
    addon_preferences = get_addon_preferences()
    extra_dna_folder_list = addon_preferences.extra_dna_folder_list if addon_preferences else []
    enum_items.extend(
        (
            str(file.absolute()),
            " ".join([i.capitalize() for i in file.stem.split("_")]),
            f"Use the {file.name} file as the base DNA to convert the selected mesh",
        )
        for item in extra_dna_folder_list
        for file in Path(item.folder_path).iterdir()
        if file.is_file() and file.suffix == ".dna"
    )
    return enum_items


def get_active_lod(self: "RigInstance") -> int:
    return self.get("active_lod", 0)


def get_show_head_bones(self: "RigInstance") -> bool:
    if self.head_rig:
        return not self.head_rig.hide_get()
    return False


def get_show_face_board(self: "RigInstance") -> bool:
    if self.face_board:
        return not self.face_board.hide_get()
    return False


def get_show_control_rig(self: "RigInstance") -> bool:
    if self.control_rig:
        return not self.control_rig.hide_get()
    return False


def get_show_body_bones(self: "RigInstance") -> bool:
    if self.body_rig:
        return not self.body_rig.hide_get()
    return False


def get_shape_key_value(self: "RigInstance") -> float:
    instance = get_active_rig_instance()
    if instance:
        channel_index = instance.head_channel_name_to_index_lookup.get(self.name)
        if not channel_index:
            return 0.0

        for shape_key_block in instance.head_shape_key_blocks.get(channel_index, []):
            try:
                if shape_key_block.name == self.name:
                    return shape_key_block.value
            except UnicodeDecodeError:
                # This happens when the block is already removed from memory
                pass
    return 0.0


def get_active_shape_key_mesh_names(self: "RigInstance", context: "Context") -> list[tuple[str, str, str, str, int]]:  # noqa: ARG001
    items = []
    if self.head_mesh_index_lookup:
        enum_index = 0
        for mesh_object in self.head_mesh_index_lookup.values():
            if (
                mesh_object.type == "MESH"
                and isinstance(mesh_object.data, bpy.types.Mesh)
                and mesh_object.data.shape_keys
                and len(mesh_object.data.shape_keys.key_blocks) > 0
            ):
                items.append(
                    (
                        mesh_object.name,
                        mesh_object.name.replace(f"{self.name}_", ""),
                        f'Only display the shape key values for "{mesh_object.name}"',
                        "NONE",
                        enum_index,
                    )
                )
                enum_index += 1
    elif self.head_mesh:
        items.append(
            (
                self.head_mesh.name,
                self.head_mesh.name.replace(f"{self.name}_", ""),
                f'Only display the shape key values for "{self.head_mesh.name}"',
                "NONE",
                0,
            )
        )
    return items


def set_highlight_matching_active_bone(self: "MetahumanSceneProperties", value: bool):
    gpu_draw_handler = self.context.pop("gpu_draw_highlight_matching_active_bone_handler", None)
    if gpu_draw_handler:
        bpy.types.SpaceView3D.draw_handler_remove(gpu_draw_handler, "WINDOW")

    if value:

        def draw():
            if bpy.context.mode == "POSE":
                pose_bone = bpy.context.active_pose_bone
                if pose_bone:
                    scene_properties: "MetahumanSceneProperties" = bpy.context.scene.meta_human_dna  # type: ignore  # noqa: UP037
                    for instance in scene_properties.rig_instance_list:
                        if (
                            instance
                            and instance.head_rig
                            and pose_bone.id_data not in [instance.head_rig, instance.body_rig]
                        ):
                            source_pose_bone = instance.head_rig.pose.bones.get(pose_bone.name)
                            if source_pose_bone:
                                world_location = (
                                    instance.head_rig.matrix_world @ source_pose_bone.matrix.to_translation()
                                )
                                draw_sphere(position=Vector(world_location), color=Color((1, 0, 1, 1)), radius=0.001)
                        if (
                            instance
                            and instance.body_rig
                            and pose_bone.id_data not in [instance.head_rig, instance.body_rig]
                        ):
                            source_pose_bone = instance.body_rig.pose.bones.get(pose_bone.name)
                            if source_pose_bone:
                                world_location = (
                                    instance.body_rig.matrix_world @ source_pose_bone.matrix.to_translation()
                                )
                                draw_sphere(position=Vector(world_location), color=Color((1, 0, 1, 1)), radius=0.001)

        gpu_draw_handler = bpy.types.SpaceView3D.draw_handler_add(draw, (), "WINDOW", "POST_VIEW")
        self.context["gpu_draw_highlight_matching_active_bone_handler"] = gpu_draw_handler

    self["highlight_matching_active_bone"] = value


def get_highlight_matching_active_bone(self: "MetahumanSceneProperties") -> bool:
    return self.get("highlight_matching_active_bone", False)


def set_bake_start_frame(self: "BakeAnimationBase", value: int):
    self["bake_start_frame"] = value


def set_bake_end_frame(self: "BakeAnimationBase", value: int):
    self["bake_end_frame"] = value


def set_active_lod(self: "RigInstance", value: int):
    self["active_lod"] = value
    if not bpy.context.scene:
        return

    for scene_object in bpy.context.scene.objects:
        if scene_object.name.startswith(self.name) and scene_object.type == "MESH":
            ignored_names = [
                f"{self.name}_eyeshell_lod{value}_mesh",
                f"{self.name}_eyeEdge_lod{value}_mesh",
                f"{self.name}_cartilage_lod{value}_mesh",
                f"{self.name}_saliva_lod{value}_mesh",
                f"{self.name}_body_lod{value}_mesh",
            ]
            scene_object.hide_set(True)
            if scene_object.name.endswith(f"_lod{value}_mesh") and scene_object.name not in ignored_names:
                scene_object.hide_set(False)

    # un-hide the body lod. There are 2 head lods per body lod
    body_lod_index = HEAD_TO_BODY_LOD_MAPPING.get(value)
    body_lod_object = bpy.data.objects.get(f"{self.name}_body_lod{body_lod_index}_mesh")
    if body_lod_object:
        body_lod_object.hide_set(False)


def set_show_head_bones(self: "RigInstance", value: bool):
    if self.head_rig:
        self.head_rig.hide_set(not value)


def set_show_face_board(self: "RigInstance", value: bool):
    if self.face_board:
        self.face_board.hide_set(not value)


def set_show_control_rig(self: "RigInstance", value: bool):
    if self.control_rig:
        self.control_rig.hide_set(not value)


def set_show_body_bones(self: "RigInstance", value: bool):
    if self.body_rig:
        self.body_rig.hide_set(not value)


def set_copied_rig_instance_name(self: "DuplicateRigInstance", value: str):
    self["copied_rig_instance_name"] = value


def get_copied_rig_instance_name(self: "DuplicateRigInstance") -> str:
    value = self.get("copied_rig_instance_name")
    if value is None:
        instance = get_active_rig_instance()
        if instance and (instance.head_mesh and instance.body_mesh):
            return f"{instance.name}_copy"
        if instance and (not instance.head_mesh or not instance.body_mesh):
            return instance.name
        return ""
    return value


def set_active_material_preview(self: "RigInstance", value: int):
    self["active_material_preview"] = value
    input_name = "Factor"

    head_node_group = get_head_texture_logic_node(self.head_material)
    body_node_group = get_body_texture_logic_node(self.body_material)

    for node_group in [head_node_group, body_node_group]:
        if not node_group or not node_group.node_tree:
            return

        # combined
        if value == 0:
            node_group.node_tree.nodes["show_color_or_other"].inputs[input_name].default_value = 0  # type: ignore[attr-defined]
            node_group.node_tree.nodes["show_mask_or_normal"].inputs[input_name].default_value = 0  # type: ignore[attr-defined]
            node_group.node_tree.nodes["show_color_or_topology"].inputs[input_name].default_value = 0  # type: ignore[attr-defined]
        # masks
        elif value == 1:
            node_group.node_tree.nodes["show_color_or_other"].inputs[input_name].default_value = 1  # type: ignore[attr-defined]
            node_group.node_tree.nodes["show_mask_or_normal"].inputs[input_name].default_value = 1  # type: ignore[attr-defined]
            node_group.node_tree.nodes["show_color_or_topology"].inputs[input_name].default_value = 0  # type: ignore[attr-defined]
        # normals
        elif value == 2:
            node_group.node_tree.nodes["show_color_or_other"].inputs[input_name].default_value = 1  # type: ignore[attr-defined]
            node_group.node_tree.nodes["show_mask_or_normal"].inputs[input_name].default_value = 0  # type: ignore[attr-defined]
            node_group.node_tree.nodes["show_color_or_topology"].inputs[input_name].default_value = 0  # type: ignore[attr-defined]

        # topology
        elif value == 3:
            node_group.node_tree.nodes["show_color_or_other"].inputs[input_name].default_value = 0  # type: ignore[attr-defined]
            node_group.node_tree.nodes["show_mask_or_normal"].inputs[input_name].default_value = 0  # type: ignore[attr-defined]
            node_group.node_tree.nodes["show_color_or_topology"].inputs[input_name].default_value = 1  # type: ignore[attr-defined]


def poll_head_rig_bone_selection(_: bpy.types.Operator, context: "Context") -> bool:
    instance = get_active_rig_instance()
    if not instance or not instance.head_rig:
        return False
    return context.mode == "POSE" and bool(context.selected_pose_bones) and instance.head_rig == context.active_object


def poll_head_materials(self: "RigInstance", material: bpy.types.Material) -> bool:  # noqa: ARG001
    node = get_head_texture_logic_node(material)
    return bool(node)


def poll_body_materials(self: "RigInstance", material: bpy.types.Material) -> bool:  # noqa: ARG001
    node = get_body_texture_logic_node(material)
    return bool(node)


def poll_face_boards(self: "RigInstance", scene_object: bpy.types.Object) -> bool:  # noqa: ARG001
    # Check if this is the right armature by checking one bone name
    return (
        scene_object.type == "ARMATURE"
        and scene_object.pose is not None
        and bool(scene_object.pose.bones.get("CTRL_rigLogic"))
    )


def poll_head_rig(self: "RigInstance", scene_object: bpy.types.Object) -> bool:  # noqa: ARG001
    return (
        scene_object.type == "ARMATURE"
        and scene_object.pose is not None
        and not scene_object.pose.bones.get("CTRL_rigLogic")
    )


def poll_body_rig(self: "RigInstance", scene_object: bpy.types.Object) -> bool:  # noqa: ARG001
    return (
        scene_object.type == "ARMATURE"
        and scene_object.pose is not None
        and not scene_object.pose.bones.get("CTRL_rigLogic")
    )


def poll_control_rig(self: "RigInstance", scene_object: bpy.types.Object) -> bool:  # noqa: ARG001
    # This check will filter out the face boards
    return (
        scene_object.type == "ARMATURE"
        and scene_object.pose is not None
        and not scene_object.pose.bones.get("CTRL_rigLogic")
    )


def poll_head_mesh(self: "RigInstance", scene_object: bpy.types.Object) -> bool:  # noqa: ARG001
    return scene_object.type == "MESH" and scene_object.name in bpy.data.objects


def poll_body_mesh(self: "RigInstance", scene_object: bpy.types.Object) -> bool:  # noqa: ARG001
    return scene_object.type == "MESH" and scene_object.name in bpy.data.objects


def poll_shrink_wrap_target(self: "RigInstance", scene_object: bpy.types.Object) -> bool:
    return (
        scene_object.type == "MESH"
        and bpy.context.scene is not None
        and scene_object in bpy.context.scene.objects.values()
        and scene_object not in [self.head_mesh, self.body_mesh]
    )


def update_evaluate_rbfs_value(self: "RigInstance", context: "Context"):
    # Avoid circular import
    from ..editors.pose_editor.core import update_evaluate_rbfs_value as _update_evaluate_rbfs_value

    _update_evaluate_rbfs_value(self, context)


def update_head_topology_selection(self: "RigInstance", context: "Context"):  # noqa: ARG001
    head = get_active_head()
    if head:
        head.select_vertex_group()


def update_body_topology_selection(self: "RigInstance", context: "Context"):  # noqa: ARG001
    body = get_active_body()
    if body:
        body.select_vertex_group()


def update_head_rig_bone_group_selection(self: "RigInstance", context: "Context"):  # noqa: ARG001
    head = get_active_head()
    if head:
        head.select_bone_group()


def update_body_rig_bone_group_selection(self: "RigInstance", context: "Context"):  # noqa: ARG001
    body = get_active_body()
    if body:
        body.select_bone_group()


def update_face_pose(self: "RigInstance", context: "Context"):  # noqa: ARG001
    from ..utilities import get_head

    active_instance = get_active_rig_instance()
    if not active_instance:
        return

    # update all instances with the same face board
    for instance in context.scene.meta_human_dna.rig_instance_list:
        if instance.face_board == active_instance.face_board:
            head = get_head(instance.name)
            if head:
                head.set_face_pose()


def update_head_to_body_constraint_influence(self: "RigInstance", context: "Context"):  # noqa: ARG001
    head = get_active_head()
    if head:
        head.set_head_to_body_constraint_influence(self.head_to_body_constraint_influence)


def get_head_mesh_output_items(instance: "RigInstance") -> list[bpy.types.Object]:
    mesh_objects = []

    # get all mesh objects that are skinned to the head rig
    for scene_object in bpy.data.objects:
        if scene_object.type == "MESH":
            for modifier in scene_object.modifiers:
                if modifier.type == "ARMATURE" and getattr(modifier, "object", None) == instance.head_rig:
                    mesh_objects.append(scene_object)
                    break

    return mesh_objects


def get_body_mesh_output_items(instance: "RigInstance") -> list[bpy.types.Object]:
    mesh_objects = []

    # get all mesh objects that are skinned to the body rig
    for scene_object in bpy.data.objects:
        if scene_object.type == "MESH":
            for modifier in scene_object.modifiers:
                if modifier.type == "ARMATURE" and getattr(modifier, "object", None) == instance.body_rig:
                    mesh_objects.append(scene_object)
                    break

    return mesh_objects


def get_head_image_output_items(instance: "RigInstance") -> list[tuple[bpy.types.Image, str]]:
    image_nodes = []
    if instance.head_material:
        head_texture_logic_node = get_head_texture_logic_node(instance.head_material)
        if head_texture_logic_node:
            for input_name, file_name in HEAD_MAPS.items():
                node_input = head_texture_logic_node.inputs.get(input_name)
                if node_input and node_input.links:
                    image_node = node_input.links[0].from_node
                    if image_node and image_node.type == "TEX_IMAGE":
                        image_nodes.append((image_node.image, file_name))
    return image_nodes


def get_body_image_output_items(instance: "RigInstance") -> list[tuple[bpy.types.Image, str]]:
    image_nodes = []
    if instance.body_material:
        body_texture_logic_node = get_body_texture_logic_node(instance.body_material)
        if body_texture_logic_node:
            for input_name, file_name in BODY_MAPS.items():
                node_input = body_texture_logic_node.inputs.get(input_name)
                if node_input and node_input.links:
                    image_node = node_input.links[0].from_node
                    if image_node and image_node.type == "TEX_IMAGE":
                        image_nodes.append((image_node.image, file_name))  # type: ignore[attr-defined]
    return image_nodes


def update_instance_name(self: "RigInstance", context: "Context"):
    existing_names = [instance.name for instance in context.scene.meta_human_dna.rig_instance_list]
    if existing_names.count(self.name) > 1:
        self.name = self.old_name
        logger.warning(f'Rig Instance with name "{self.name}" already exists. Please choose a different name.')
        return

    if self.old_name != self.name:
        from ..utilities import rename_rig_instance

        rename_rig_instance(instance=self, old_name=self.old_name, new_name=self.name)
        self.old_name = self.name


def update_body_output_items(self: "RigInstance", context: "Context"):  # noqa: ARG001, PLR0912
    if not hasattr(context.scene, ToolInfo.NAME):
        return

    for instance in context.scene.meta_human_dna.rig_instance_list:
        if instance and instance.body_mesh and instance.body_rig:
            # update the output items for the scene objects
            for scene_object in [*get_body_mesh_output_items(instance), instance.body_rig]:
                for i in instance.output_body_item_list:
                    if not i.image_object and i.scene_object == scene_object:
                        break
                else:
                    new_item = instance.output_body_item_list.add()
                    new_item.scene_object = scene_object
                    if scene_object == instance.body_mesh:
                        new_item.name = "body_lod0_mesh"
                        new_item.editable_name = False
                    elif scene_object == instance.body_rig:
                        new_item.name = "rig"
                        new_item.editable_name = False
                    else:
                        new_item.name = scene_object.name.replace(f"{instance.name}_", "")
                        new_item.editable_name = True

            # update the output items for the image textures
            for image_object, file_name in get_body_image_output_items(instance):
                for i in instance.output_body_item_list:
                    if not i.scene_object and i.image_object == image_object:
                        break
                else:
                    new_item = instance.output_body_item_list.add()
                    new_item.image_object = image_object
                    new_item.name = file_name
                    new_item.editable_name = False

            # remove any output items that do not have a scene object or image object
            for item in instance.output_body_item_list:
                if not item.scene_object and not item.image_object:
                    index = instance.output_body_item_list.find(item.name)
                    instance.output_body_item_list.remove(index)


def update_head_output_items(self: "RigInstance | None", context: "Context"):  # noqa: ARG001, PLR0912
    if not hasattr(context.scene, ToolInfo.NAME):
        return

    for instance in context.scene.meta_human_dna.rig_instance_list:
        if instance and instance.head_mesh and instance.head_rig:
            # update the output items for the scene objects
            for scene_object in [*get_head_mesh_output_items(instance), instance.head_rig]:
                for i in instance.output_head_item_list:
                    if not i.image_object and i.scene_object == scene_object:
                        break
                else:
                    new_item = instance.output_head_item_list.add()
                    new_item.scene_object = scene_object
                    if scene_object == instance.head_mesh:
                        new_item.name = "head_lod0_mesh"
                        new_item.editable_name = False
                    elif scene_object == instance.head_rig:
                        new_item.name = "rig"
                        new_item.editable_name = False
                    else:
                        new_item.name = scene_object.name.replace(f"{instance.name}_", "")
                        new_item.editable_name = True

            # update the output items for the image textures
            for image_object, file_name in get_head_image_output_items(instance):
                for i in instance.output_head_item_list:
                    if not i.scene_object and i.image_object == image_object:
                        break
                else:
                    new_item = instance.output_head_item_list.add()
                    new_item.image_object = image_object
                    new_item.name = file_name
                    new_item.editable_name = False

            # remove any output items that do not have a scene object or image object
            for item in instance.output_head_item_list:
                if not item.scene_object and not item.image_object:
                    index = instance.output_head_item_list.find(item.name)
                    instance.output_head_item_list.remove(index)


def update_output_component(self: "RigInstance", context: "Context"):
    update_head_output_items(self, context)
    update_body_output_items(self, context)


def get_head_mesh_lod_items(self: "RigInstance", context: "Context") -> list[tuple[str, str, str]]:  # noqa: ARG001
    items = []

    try:
        # get the lods for the active face
        instance = get_active_rig_instance()
        if instance:
            for i in range(NUMBER_OF_HEAD_LODS):
                head_mesh = bpy.data.objects.get(f"{instance.name}_head_lod{i}_mesh")
                if head_mesh:
                    items.append((f"lod{i}", f"LOD {i}", f"Displays only LOD {i}"))
    except AttributeError:
        pass

    # if no lods are found, add a default item
    if not items:
        items = [("lod0", "LOD 0", "Displays only LOD 0")]

    return items


def draw_sphere(position: Vector, color: Color, radius: float = 0.001):
    segments = 16
    draw_circle_2d(position=position[:], color=color[:], radius=radius, segments=segments)
    rotation_matrix = Matrix.Rotation(math.radians(90), 4, "X")  # type: ignore[call-arg]
    rotation_matrix.translation = position
    x_rotation_matrix = rotation_matrix.to_4x4()
    gpu.matrix.multiply_matrix(x_rotation_matrix)
    draw_circle_2d(
        position=(0, 0, 0),
        color=color[:],
        radius=radius,
        segments=segments,
    )
    rotation_matrix = rotation_matrix.to_3x3()
    rotation_matrix.rotate(Euler((0, 0, math.radians(90))))
    z_rotation_matrix = rotation_matrix.to_4x4()
    gpu.matrix.multiply_matrix(z_rotation_matrix)
    draw_circle_2d(
        position=(0, 0, 0),
        color=color[:],
        radius=radius,
        segments=segments,
    )

    # undo the rotations
    gpu.matrix.multiply_matrix(z_rotation_matrix.inverted())
    gpu.matrix.multiply_matrix(x_rotation_matrix.inverted())
