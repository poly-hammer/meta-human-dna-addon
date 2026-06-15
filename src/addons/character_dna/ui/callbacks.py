# standard library imports
import json
import logging
import math
import os
import re

from collections.abc import Iterable
from pathlib import Path

# third party imports
import bpy
import gpu

from gpu_extras.presets import draw_circle_2d
from mathutils import Color, Euler, Matrix, Vector

# local imports
from ..constants import (
    BODY_MAPS,
    DEFORMER_BONE_COLLECTION,
    HEAD_MAPS,
    HEAD_TO_BODY_LOD_MAPPING,
    NUMBER_OF_HEAD_LODS,
    POSES_FOLDER,
    ToolInfo,
)
from ..typing import *  # noqa: F403


logger = logging.getLogger(__name__)

# Sentinel enum identifier used for the face pose preview when no pose matches the
# active category/tag filters. Keeping a single inert item avoids the empty-enum
# crash and the "current value matches no enum" warnings Blender emits otherwise.
NO_FACE_POSE = "NONE"

# Module-level reference to the dynamic face pose search enum items. Blender requires
# a persistent python reference to dynamic enum items to avoid a GC crash.
_face_pose_search_items: list[tuple[str, str, str, int, int]] = []

# Maps a generated boolean property name (e.g. "tag_speech") to its original tag
# name (e.g. "speech"). Populated when the dynamic tag properties are built at
# addon registration time.
_face_pose_tag_property_map: dict[str, str] = {}


def get_active_head() -> "CharacterComponentHead | None":
    # Avoid circular import
    from ..utilities import get_active_head as _get_active_head

    return _get_active_head()


def get_active_body() -> "CharacterComponentBody | None":
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
    scene_properties: "CharacterSceneProperties" = getattr(bpy.context.scene, ToolInfo.NAME)  # noqa: UP037
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


def get_active_material_preview(self: "CharacterViewOptionsProperties") -> int:
    return self.get("active_material_preview", 0)


def get_face_pose_previews_items(
    self: "CharacterFaceBoardProperties", context: "Context"
) -> Iterable[tuple[str, str, str, int, int]]:
    from ..properties import face_pose_preview_collections

    enum_items = []

    if context is None:
        return enum_items

    # Get the preview collection.
    preview_collection = face_pose_preview_collections["face_poses"]

    metadata = ensure_face_pose_metadata()

    # Build a cache key from the current filters so we only rebuild the filtered
    # enum when the filters actually change.
    enabled_tags = tuple(sorted(get_enabled_face_pose_tags(self)))
    cache_key = (self.category, enabled_tags, self.tag_match_mode)
    if getattr(preview_collection, "face_pose_previews_cache_key", None) == cache_key:
        return preview_collection.face_pose_previews

    enum_items.extend(
        (entry["id"], entry["name"], entry["description"], entry["icon_id"], entry["value"])
        for entry in _filter_face_pose_metadata(metadata, self.category, enabled_tags, self.tag_match_mode)
    )

    # Guard against the empty-enum problem: when no pose matches the active filters,
    # fall back to a single inert sentinel so Blender always has a valid item.
    if not enum_items:
        enum_items.append((NO_FACE_POSE, "No Poses", "No poses match the current filters", 0, 0))

    # Cache the enum item values and the key for later retrieval. We must keep a
    # reference to the returned tuples alive to avoid a Blender enum GC crash.
    preview_collection.face_pose_previews = enum_items
    preview_collection.face_pose_previews_cache_key = cache_key
    return preview_collection.face_pose_previews


def ensure_face_pose_metadata(force: bool = False) -> list[dict]:
    """
    Builds (and caches) the face pose metadata by walking the poses folder once,
    reading each ``pose.json`` for its description and tags, and loading a preview
    icon for each pose. Returns a list of dicts with keys: ``id`` (thumbnail path),
    ``name``, ``category``, ``description``, ``tags``, ``icon_id``.
    """
    from ..properties import face_pose_preview_collections

    preview_collection = face_pose_preview_collections["face_poses"]

    cached = getattr(preview_collection, "face_pose_metadata", None)
    if cached and not force:
        return cached

    directory = POSES_FOLDER / "face"
    metadata: list[dict] = []

    if directory.exists():
        for folder_path, _, file_names in os.walk(directory):
            if "thumbnail-preview.png" not in file_names or "pose.json" not in file_names:
                continue

            pose_folder = Path(folder_path)
            thumbnail_file_path = pose_folder / "thumbnail-preview.png"
            pose_file_path = pose_folder / "pose.json"

            description = ""
            tags: list[str] = []
            try:
                with pose_file_path.open() as file:
                    data = json.load(file)
                description = data.get("description", "") or ""
                tags = [str(tag) for tag in data.get("tags", []) or []]
            except (OSError, ValueError) as error:
                logger.debug(f"Failed to read pose metadata from {pose_file_path}: {error}")

            try:
                category = pose_folder.relative_to(directory).parts[0]
            except (ValueError, IndexError):
                category = ""

            pose_id = str(thumbnail_file_path)
            icon = preview_collection.get(pose_id)
            thumb = icon or preview_collection.load(pose_id, pose_id, "IMAGE")

            metadata.append(
                {
                    "id": pose_id,
                    "name": pose_folder.name.replace("_", " "),
                    "category": category,
                    "description": description,
                    "tags": tags,
                    "icon_id": thumb.icon_id,
                }
            )

    metadata.sort(key=lambda entry: (entry["category"], entry["name"]))
    # Assign a stable integer enum value to each pose based on its position in the
    # fully sorted list. The dynamic ``face_pose_previews`` enum must keep a
    # consistent integer per item regardless of the active category/tag filters;
    # using the filtered loop index instead causes Blender to emit
    # "current value 'N' matches no enum" warnings when the filtered list shrinks.
    for value, entry in enumerate(metadata):
        entry["value"] = value
    preview_collection.face_pose_metadata = metadata
    return metadata


def _filter_face_pose_metadata(
    metadata: list[dict], category: str, enabled_tags: tuple[str, ...], match_mode: str = "ANY"
) -> list[dict]:
    """
    Filters the pose metadata by category and enabled tags. When ``match_mode`` is
    ``"ALL"`` a pose must contain every enabled tag (intersection); when ``"ANY"`` a
    pose only needs at least one of the enabled tags (union).
    """
    enabled_tag_set = set(enabled_tags)
    results = []
    for entry in metadata:
        if category != "ALL" and entry["category"] != category:
            continue
        if enabled_tag_set:
            pose_tags = set(entry["tags"])
            if match_mode == "ALL":
                if not enabled_tag_set.issubset(pose_tags):
                    continue
            elif not enabled_tag_set.intersection(pose_tags):
                continue
        results.append(entry)
    return results


def get_tags_for_category(category: str) -> list[str]:
    """Returns the sorted unique tags present on poses within ``category``. When
    ``category`` is ``"ALL"`` every tag across all face poses is returned."""
    tags: set[str] = set()
    for entry in ensure_face_pose_metadata():
        if category != "ALL" and entry["category"] != category:
            continue
        tags.update(entry["tags"])
    return sorted(tags)


def get_all_face_pose_tags() -> list[str]:
    """Returns a sorted list of every unique tag across all face poses."""
    return get_tags_for_category("ALL")


def _tag_to_property_name(tag: str) -> str:
    """Converts a tag string into a valid Blender boolean property identifier."""
    sanitized = re.sub(r"\W+", "_", tag.strip().lower()).strip("_")
    return f"tag_{sanitized or 'unnamed'}"


def build_face_pose_tag_properties() -> dict:
    """
    Collects every unique face pose tag and builds one ``BoolProperty`` per tag.
    Returns a mapping of generated property name to property definition, suitable
    for injecting into a ``PropertyGroup``'s ``__annotations__`` before it is
    registered. This mirrors the dynamic-class technique used for the LOD import
    options. The reverse property-name to tag-name mapping is cached on the module
    so the tag filter can be resolved later.
    """
    global _face_pose_tag_property_map

    _face_pose_tag_property_map = {}
    properties: dict = {}

    for tag_name in get_all_face_pose_tags():
        property_name = _tag_to_property_name(tag_name)
        # Disambiguate any property name collisions from similar tag names.
        unique_name = property_name
        suffix = 1
        while unique_name in _face_pose_tag_property_map:
            suffix += 1
            unique_name = f"{property_name}_{suffix}"

        _face_pose_tag_property_map[unique_name] = tag_name
        properties[unique_name] = bpy.props.BoolProperty(
            name=tag_name,
            description=f"Only show poses tagged with '{tag_name}'",
            default=False,
            update=update_face_pose_filter,  # pyright: ignore[reportArgumentType]
        )

    return properties


def get_face_pose_tag_property_map() -> dict[str, str]:
    """Returns the generated property-name to tag-name mapping for the tag filters."""
    return _face_pose_tag_property_map


def get_enabled_face_pose_tags(face_board: "CharacterFaceBoardProperties") -> set[str]:
    """Returns the set of tags whose dynamic boolean filter is currently enabled."""
    return {
        tag_name
        for property_name, tag_name in _face_pose_tag_property_map.items()
        if getattr(face_board, property_name, False)
    }


def get_face_pose_search_items(
    self: "bpy.types.Operator",  # noqa: ARG001
    context: "Context",
) -> list[tuple[str, str, str, int, int]]:
    """
    Items callback for the face board search popup operator. Returns the same
    category/tag filtered pose set shown in the panel so the user can type to
    quickly jump to a pose by name. The list is cached on the module to keep a
    reference alive and avoid a Blender enum GC crash.
    """
    global _face_pose_search_items

    _face_pose_search_items = []
    if context is None or context.scene is None:
        return _face_pose_search_items

    scene_properties = getattr(context.scene, ToolInfo.NAME, None)
    if scene_properties is None:
        return _face_pose_search_items

    face_board = scene_properties.face_board
    metadata = ensure_face_pose_metadata()
    enabled_tags = tuple(sorted(get_enabled_face_pose_tags(face_board)))

    _face_pose_search_items = [
        (entry["id"], entry["name"], entry["description"], entry["icon_id"], index)
        for index, entry in enumerate(
            _filter_face_pose_metadata(metadata, face_board.category, enabled_tags, face_board.tag_match_mode)
        )
    ]
    return _face_pose_search_items


def update_face_pose_filter(self: "CharacterFaceBoardProperties", context: "Context"):  # noqa: ARG001
    """
    Invalidates the cached filtered enum and, if the currently selected pose is no
    longer part of the filtered set, auto-selects the first remaining pose.
    """
    from ..properties import face_pose_preview_collections

    preview_collection = face_pose_preview_collections["face_poses"]
    # Invalidate the cache so the items callback rebuilds the filtered list.
    preview_collection.face_pose_previews_cache_key = None

    metadata = ensure_face_pose_metadata()
    enabled_tags = tuple(sorted(get_enabled_face_pose_tags(self)))
    filtered = _filter_face_pose_metadata(metadata, self.category, enabled_tags, self.tag_match_mode)
    filtered_ids = [entry["id"] for entry in filtered]
    if not filtered_ids:
        return

    try:
        current = self.face_pose_previews
    except (TypeError, ValueError):
        current = None

    if current not in filtered_ids:
        # Assigning triggers update_face_pose, which applies the pose.
        self.face_pose_previews = filtered_ids[0]


def update_face_pose_category(self: "CharacterFaceBoardProperties", context: "Context"):
    """Category change handler. Disables any enabled tag filters that do not belong
    to the newly selected category so out-of-category tags can never filter the pose
    list down to nothing, then refreshes the filtered pose enum and selection."""
    allowed_tags = set(get_tags_for_category(self.category))
    for property_name, tag_name in _face_pose_tag_property_map.items():
        if tag_name not in allowed_tags and getattr(self, property_name, False):
            setattr(self, property_name, False)
    update_face_pose_filter(self, context)


def _get_face_board_switch(bone_name: str) -> bool:
    """Reads a face board switch bone's on/off state from the active rig instance.
    Switch bones encode their boolean state in ``location.y`` (1.0 on, 0.0 off)."""
    instance = get_active_rig_instance()
    if instance and instance.face_board:
        pose_bone = instance.face_board.pose.bones.get(bone_name)
        if pose_bone:
            return pose_bone.location.y >= 0.99
    return False


def _set_face_board_switch(bone_name: str, value: bool):
    """Sets a face board switch bone on/off and re-evaluates the active rig instance
    so the dependent constraints and rig logic update to match."""
    instance = get_active_rig_instance()
    if not instance or not instance.face_board:
        return
    pose_bone = instance.face_board.pose.bones.get(bone_name)
    if not pose_bone:
        return
    pose_bone.location.y = 1.0 if value else 0.0
    instance.evaluate()


def get_use_eye_aim(self: "CharacterFaceBoardProperties") -> bool:  # noqa: ARG001
    return _get_face_board_switch("CTRL_lookAtSwitch")


def set_use_eye_aim(self: "CharacterFaceBoardProperties", value: bool):  # noqa: ARG001
    _set_face_board_switch("CTRL_lookAtSwitch", value)


def get_eyes_follow_head(self: "CharacterFaceBoardProperties") -> bool:  # noqa: ARG001
    return _get_face_board_switch("CTRL_eyesAimFollowHead")


def set_eyes_follow_head(self: "CharacterFaceBoardProperties", value: bool):  # noqa: ARG001
    _set_face_board_switch("CTRL_eyesAimFollowHead", value)


def get_face_board_follow_head(self: "CharacterFaceBoardProperties") -> bool:  # noqa: ARG001
    return _get_face_board_switch("CTRL_faceGUIfollowHead")


def set_face_board_follow_head(self: "CharacterFaceBoardProperties", value: bool):  # noqa: ARG001
    _set_face_board_switch("CTRL_faceGUIfollowHead", value)


def _get_view_options_owner(self: "CharacterViewOptionsProperties") -> "RigInstance | None":
    """Resolve the ``RigInstance`` that owns this ``view_options`` property group.

    The view-options get/set callbacks need the owning rig instance to read its
    linked objects (face board, rigs, materials) and its name. We resolve it from
    the RNA data path so the correct instance is targeted even when it is not the
    active one, falling back to the active rig instance if the path can't be resolved.
    """
    try:
        owner_path = self.path_from_id().rsplit(".view_options", 1)[0]
        owner = self.id_data.path_resolve(owner_path)
    except (ValueError, AttributeError):
        owner = None
    if owner is None:
        return get_active_rig_instance()
    return owner  # pyright: ignore[reportReturnType]


def get_active_lod(self: "CharacterViewOptionsProperties") -> int:
    return self.get("active_lod", 0)


def get_show_head_bones(self: "CharacterViewOptionsProperties") -> bool:
    instance = _get_view_options_owner(self)
    if instance and instance.head_rig:
        return not instance.head_rig.hide_get()
    return False


def get_show_face_board(self: "CharacterViewOptionsProperties") -> bool:
    instance = _get_view_options_owner(self)
    if instance and instance.face_board:
        return not instance.face_board.hide_get()
    return False


def get_show_control_rig(self: "CharacterViewOptionsProperties") -> bool:
    instance = _get_view_options_owner(self)
    if instance and instance.control_rig:
        return not instance.control_rig.hide_get()
    return False


def get_show_body_bones(self: "CharacterViewOptionsProperties") -> bool:
    instance = _get_view_options_owner(self)
    if instance and instance.body_rig:
        return not instance.body_rig.hide_get()
    return False


def set_highlight_matching_active_bone(self: "CharacterSceneProperties", value: bool):
    gpu_draw_handler = self.context.pop("gpu_draw_highlight_matching_active_bone_handler", None)
    if gpu_draw_handler:
        bpy.types.SpaceView3D.draw_handler_remove(gpu_draw_handler, "WINDOW")

    if value:

        def draw():
            if bpy.context.mode == "POSE":
                pose_bone = bpy.context.active_pose_bone
                if pose_bone:
                    scene_properties: "CharacterSceneProperties" = getattr(bpy.context.scene, ToolInfo.NAME)  # noqa: UP037
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


def get_highlight_matching_active_bone(self: "CharacterSceneProperties") -> bool:
    return self.get("highlight_matching_active_bone", False)


def set_bake_start_frame(self: "BakeAnimationBase", value: int):
    self["bake_start_frame"] = value


def set_bake_end_frame(self: "BakeAnimationBase", value: int):
    self["bake_end_frame"] = value


def set_active_lod(self: "CharacterViewOptionsProperties", value: int):
    self["active_lod"] = value
    if not bpy.context.scene:
        return

    instance = _get_view_options_owner(self)
    if not instance:
        return

    for scene_object in bpy.context.scene.objects:
        if scene_object.name.startswith(instance.name) and scene_object.type == "MESH":
            ignored_names = [
                f"{instance.name}_eyeshell_lod{value}_mesh",
                f"{instance.name}_eyeEdge_lod{value}_mesh",
                f"{instance.name}_cartilage_lod{value}_mesh",
                f"{instance.name}_saliva_lod{value}_mesh",
                f"{instance.name}_body_lod{value}_mesh",
            ]
            scene_object.hide_set(True)
            if scene_object.name.endswith(f"_lod{value}_mesh") and scene_object.name not in ignored_names:
                scene_object.hide_set(False)

    # un-hide the body lod. There are 2 head lods per body lod
    body_lod_index = HEAD_TO_BODY_LOD_MAPPING.get(value)
    body_lod_object = bpy.data.objects.get(f"{instance.name}_body_lod{body_lod_index}_mesh")
    if body_lod_object:
        body_lod_object.hide_set(False)


def set_show_head_bones(self: "CharacterViewOptionsProperties", value: bool):
    instance = _get_view_options_owner(self)
    if instance and instance.head_rig:
        instance.head_rig.hide_set(not value)


def set_show_face_board(self: "CharacterViewOptionsProperties", value: bool):
    instance = _get_view_options_owner(self)
    if instance and instance.face_board:
        instance.face_board.hide_set(not value)


def set_show_control_rig(self: "CharacterViewOptionsProperties", value: bool):
    instance = _get_view_options_owner(self)
    if instance and instance.control_rig:
        instance.control_rig.hide_set(not value)


def set_show_body_bones(self: "CharacterViewOptionsProperties", value: bool):
    instance = _get_view_options_owner(self)
    if instance and instance.body_rig:
        instance.body_rig.hide_set(not value)


def get_solo_deformers(self: "CharacterViewOptionsProperties") -> bool:
    instance = _get_view_options_owner(self)
    if not instance:
        return False
    for rig_object in (instance.head_rig, instance.body_rig):
        if rig_object and isinstance(rig_object.data, bpy.types.Armature):
            collection = rig_object.data.collections.get(DEFORMER_BONE_COLLECTION)
            if collection:
                return bool(collection.is_solo)
    return False


def set_solo_deformers(self: "CharacterViewOptionsProperties", value: bool):
    instance = _get_view_options_owner(self)
    if not instance:
        return
    for rig_object in (instance.head_rig, instance.body_rig):
        if rig_object and isinstance(rig_object.data, bpy.types.Armature):
            collection = rig_object.data.collections.get(DEFORMER_BONE_COLLECTION)
            if collection:
                collection.is_solo = value


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


def set_active_material_preview(self: "CharacterViewOptionsProperties", value: int):
    self["active_material_preview"] = value
    input_name = "Factor"

    instance = _get_view_options_owner(self)
    if not instance:
        return

    head_node_group = get_head_texture_logic_node(instance.head_material)
    body_node_group = get_body_texture_logic_node(instance.body_material)

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


def poll_body_rig_bone_selection(_: bpy.types.Operator, context: "Context") -> bool:
    instance = get_active_rig_instance()
    if not instance or not instance.body_rig:
        return False
    return context.mode == "POSE" and bool(context.selected_pose_bones) and instance.body_rig == context.active_object


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


def update_evaluate_rbfs_value(self: "RigInstance", context: "Context"):
    # Avoid circular import
    try:
        from ..editors.rbf_editor.core import update_evaluate_rbfs_value as _update

        _update(self, context)
    except ImportError:
        logger.debug("Core module missing. This function will not work.")


def update_face_pose(self: "RigInstance", context: "Context"):  # noqa: ARG001
    # The sentinel item shown when no pose matches the active filters is inert.
    if getattr(self, "face_pose_previews", "") == NO_FACE_POSE:
        return

    from ..utilities import (
        get_addon_scene_properties,
        get_addon_window_manager_properties,
        get_body,
        get_head,
        switch_to_pose_mode,
    )

    active_instance = get_active_rig_instance()
    if not active_instance:
        return

    addon_scene_properties = get_addon_scene_properties()
    addon_window_manager_properties = get_addon_window_manager_properties()
    addon_window_manager_properties.evaluate_dependency_graph = False

    # update all instances with the same face board
    for instance in addon_scene_properties.rig_instance_list:
        if instance.face_board == active_instance.face_board:
            body = get_body(instance.name)
            if body:
                body.set_pose()
            head = get_head(instance.name)
            if head:
                head.set_pose()

    if not active_instance.face_board.hide_get():
        switch_to_pose_mode(active_instance.face_board)

    addon_window_manager_properties.evaluate_dependency_graph = True
    active_instance.evaluate()


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
                        image_nodes.append((image_node.image, file_name))  # type: ignore[reportAttributeAccessIssue]
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
    from ..utilities import get_addon_scene_properties

    addon_scene_properties = get_addon_scene_properties(context)
    existing_names = [instance.name for instance in addon_scene_properties.rig_instance_list]
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

    from ..utilities import get_addon_scene_properties

    addon_scene_properties = get_addon_scene_properties(context)

    for instance in addon_scene_properties.rig_instance_list:
        if instance and instance.body_mesh and instance.body_rig:
            # update the output items for the scene objects
            for scene_object in [*get_body_mesh_output_items(instance), instance.body_rig]:
                for i in instance.output.body_item_list:
                    if not i.image_object and i.scene_object == scene_object:
                        break
                else:
                    new_item = instance.output.body_item_list.add()
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
                for i in instance.output.body_item_list:
                    if not i.scene_object and i.image_object == image_object:
                        break
                else:
                    new_item = instance.output.body_item_list.add()
                    new_item.image_object = image_object
                    new_item.name = file_name
                    new_item.editable_name = False

            # remove any output items that do not have a scene object or image object
            for item in instance.output.body_item_list:
                if not item.scene_object and not item.image_object:
                    index = instance.output.body_item_list.find(item.name)
                    instance.output.body_item_list.remove(index)


def update_head_output_items(self: "RigInstance | None", context: "Context"):  # noqa: ARG001, PLR0912
    if not hasattr(context.scene, ToolInfo.NAME):
        return

    from ..utilities import get_addon_scene_properties

    addon_scene_properties = get_addon_scene_properties(context)

    for instance in addon_scene_properties.rig_instance_list:
        if instance and instance.head_mesh and instance.head_rig:
            # update the output items for the scene objects
            for scene_object in [*get_head_mesh_output_items(instance), instance.head_rig]:
                for i in instance.output.head_item_list:
                    if not i.image_object and i.scene_object == scene_object:
                        break
                else:
                    new_item = instance.output.head_item_list.add()
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
                for i in instance.output.head_item_list:
                    if not i.scene_object and i.image_object == image_object:
                        break
                else:
                    new_item = instance.output.head_item_list.add()
                    new_item.image_object = image_object
                    new_item.name = file_name
                    new_item.editable_name = False

            # remove any output items that do not have a scene object or image object
            for item in instance.output.head_item_list:
                if not item.scene_object and not item.image_object:
                    index = instance.output.head_item_list.find(item.name)
                    instance.output.head_item_list.remove(index)


def update_output_component(self: "RigInstance", context: "Context"):
    update_head_output_items(self, context)
    update_body_output_items(self, context)


def get_head_mesh_lod_items(self: "CharacterViewOptionsProperties", context: "Context") -> list[tuple[str, str, str]]:  # noqa: ARG001
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
