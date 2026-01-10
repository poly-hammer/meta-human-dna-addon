# standard library imports
import json
import logging
import math
import os
import re
import subprocess
import sys
import uuid

from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

# third party imports
import bpy

from mathutils import Vector

# local imports
from ..constants import (
    DEFAULT_UV_TOLERANCE,
    EYE_AIM_BONES,
    FACE_BOARD_FILE_PATH,
    FACE_BOARD_NAME,
    FACE_GUI_EMPTIES,
    HEAD_TEXTURE_LOGIC_NODE_LABEL,
    INVALID_NAME_CHARACTERS_REGEX,
    LEGACY_DATA_KEYS,
    MATERIALS_FILE_PATH,
    NUMBER_OF_HEAD_LODS,
    PACKAGES_FOLDER,
    SCRIPTS_FOLDER,
    SENTRY_DSN,
    TEMP_FOLDER,
    ToolInfo,
)
from ..rig_instance import start_listening
from ..typing import *  # noqa: F403
from . import get_active_rig_instance


logger = logging.getLogger(__name__)


def exclude_rig_instance_evaluation(func: Callable) -> Callable:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        window_manager_properties: "MetahumanWindowMangerProperties" = bpy.context.window_manager.meta_human_dna  # type: ignore[attr-defined]  # noqa: UP037
        window_manager_properties.evaluate_dependency_graph = False
        result = func(*args, **kwargs)
        window_manager_properties.evaluate_dependency_graph = True
        return result

    return wrapper


def get_current_context() -> dict[str, Any]:
    object_contexts = {}
    if not bpy.context.scene:
        return {}
    for scene_object in bpy.context.scene.objects:
        active_action_name = ""
        if scene_object.animation_data and scene_object.animation_data.action:
            active_action_name = scene_object.animation_data.action.name

        object_contexts[scene_object.name] = {
            "hide": scene_object.hide_get(),
            "hide_viewport": scene_object.hide_viewport,
            "select": scene_object.select_get(),
            "active_action": active_action_name,
            "show_instancer_for_render": scene_object.show_instancer_for_render,
        }

    active_object = None
    if bpy.context.active_object:
        active_object = bpy.context.active_object.name

    return {
        "mode": getattr(bpy.context, "mode", "OBJECT"),
        "objects": object_contexts,
        "active_object": active_object,
        "current_frame": bpy.context.scene.frame_current,
        "cursor_location": bpy.context.scene.cursor.location,
    }


def set_context(context: dict[str, Any]) -> None:
    mode = context.get("mode", "OBJECT")
    active_object_name = context.get("active_object")
    object_contexts = context.get("objects", {})
    for object_name, attributes in object_contexts.items():
        scene_object = bpy.data.objects.get(object_name)
        if scene_object:
            scene_object.hide_set(attributes.get("hide", False))
            scene_object.hide_viewport = attributes.get("hide_viewport", False)
            scene_object.select_set(attributes.get("select", False))

            active_action = attributes.get("active_action")
            if active_action and scene_object.animation_data:
                scene_object.animation_data.action = bpy.data.actions.get(active_action)

            scene_object.show_instancer_for_render = attributes.get("show_instancer_for_render", False)

    # set the active object
    if active_object_name and bpy.context.view_layer:
        bpy.context.view_layer.objects.active = bpy.data.objects.get(active_object_name)

    # set the mode
    if bpy.context.mode != mode:
        # Note:
        # When the mode context is read in edit mode it can be 'EDIT_ARMATURE' or 'EDIT_MESH', even though you
        # are only able to set the context to 'EDIT' mode. Thus, if 'EDIT' was read from the mode context, the mode
        # is set to edit.
        if "EDIT" in mode:
            mode = "EDIT"
        bpy.ops.object.mode_set(mode=mode)

    if bpy.context.scene:
        # set the current frame
        bpy.context.scene.frame_set(context.get("current_frame", 0))

        # set the cursor location
        bpy.context.scene.cursor.location = context.get("cursor_location", Vector((0, 0, 0)))


def preserve_context(func: Callable) -> Callable:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        window_manager_properties: "MetahumanWindowMangerProperties" = bpy.context.window_manager.meta_human_dna  # type: ignore[attr-defined]  # noqa: UP037
        window_manager_properties.evaluate_dependency_graph = False
        context = get_current_context()
        result = func(*args, **kwargs)
        window_manager_properties.evaluate_dependency_graph = True
        set_context(context)
        return result

    return wrapper


def deselect_all():
    for scene_object in bpy.data.objects:
        scene_object.select_set(False)


def select_only(*scene_object: bpy.types.Object):
    deselect_all()
    for _scene_object in scene_object:
        _scene_object.select_set(True)
        if bpy.context.view_layer:
            bpy.context.view_layer.objects.active = _scene_object


def switch_to_object_mode():
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def switch_to_edit_mode(*scene_object: bpy.types.Object):
    select_only(*scene_object)
    bpy.ops.object.mode_set(mode="EDIT")


def switch_to_sculpt_mode(*scene_object: bpy.types.Object):
    select_only(*scene_object)
    switch_to_object_mode()
    bpy.ops.object.mode_set(mode="SCULPT")


def switch_to_bone_edit_mode(*armature_object: bpy.types.Object):
    # Switch to edit mode so we can get edit bone data
    if bpy.context.mode != "EDIT_ARMATURE":
        select_only(*armature_object)
        if bpy.context.view_layer:
            bpy.context.view_layer.objects.active = armature_object[0]
        bpy.ops.object.mode_set(mode="EDIT")


def switch_to_pose_mode(*scene_object: bpy.types.Object):
    select_only(*scene_object)
    switch_to_object_mode()
    bpy.ops.object.mode_set(mode="POSE")


def apply_pose(rig_object: bpy.types.Object, selected: bool = False):
    switch_to_object_mode()
    switch_to_pose_mode(rig_object)
    bpy.ops.pose.armature_apply(selected=selected)


def apply_transforms(
    scene_object: bpy.types.Object,
    location: bool = False,
    rotation: bool = False,
    scale: bool = False,
    recursive: bool = False,
) -> None:
    deselect_all()
    switch_to_object_mode()
    select_only(scene_object)
    bpy.ops.object.transform_apply(location=location, rotation=rotation, scale=scale)

    if recursive:
        for child_object in scene_object.children:
            apply_transforms(child_object, location=location, rotation=rotation, scale=scale, recursive=recursive)


def walk_children(scene_object: bpy.types.Object) -> Generator[bpy.types.Object, None, None]:
    yield scene_object
    for child in scene_object.children:
        yield from walk_children(child)


def hide_empties():
    for scene_object in bpy.data.objects:
        if scene_object.name.startswith("GRP_"):
            scene_object.hide_viewport = True


def set_hide_recursively(scene_object: bpy.types.Object, value: bool) -> None:
    for child in walk_children(scene_object):
        child.hide_set(value)


def set_viewport_shading(mode: str) -> None:
    if not bpy.context.screen:
        return

    for area in bpy.context.screen.areas:
        if area.ui_type == "VIEW_3D":
            for space in area.spaces:
                if hasattr(space, "shading"):
                    space.shading.type = mode  # type: ignore[attr-defined]


def init_sentry():
    # Don't collect metrics when in dev mode
    if os.environ.get("META_HUMAN_DNA_DEV"):
        return

    # Don't collect metrics if the user has disabled online access
    if not bpy.app.online_access:
        return

    # Don't collect metrics if the user has disabled it
    addon_preferences: "MetahumanAddonProperties" = bpy.context.preferences.addons[ToolInfo.NAME].preferences  # pyright: ignore[reportOptionalMemberAccess, reportAssignmentType] # noqa: UP037
    if not addon_preferences.metrics_collection:
        return

    if PACKAGES_FOLDER not in [Path(path) for path in sys.path]:
        sys.path.append(str(PACKAGES_FOLDER))

    try:
        import sentry_sdk

        from sentry_sdk.types import Event, Hint

        def before_send(event: Event, hint: Hint) -> Event | None:  # noqa: ARG001
            # Filter based on module origin. We only want to send errors related
            # to the MetaHuman DNA addon.
            exception = event.get("exception")
            if exception and exception.get("values"):
                exception = exception["values"][0]
                if exception.get("stacktrace") and exception["stacktrace"].get("frames"):
                    # Check if the exception originated from one of the whitelisted modules
                    for frame in exception["stacktrace"]["frames"]:
                        module_name = frame.get("module")
                        if module_name and module_name.startswith(ToolInfo.NAME):
                            break
                    else:
                        return None

            # Add tags to the event
            if "tags" not in event:
                event["tags"] = {}

            from .. import bl_info

            event["tags"]["blender_version"] = bpy.app.version_string
            event["tags"]["blender_mode"] = bpy.context.mode
            event["tags"]["addon_version"] = ".".join([str(i) for i in bl_info.get("version", [])])
            event["tags"]["platform"] = sys.platform

            return event

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            # Set traces_sample_rate to 1.0 to capture 100%
            # of transactions for performance monitoring.
            traces_sample_rate=1.0,
            # Dont send personal identifiable information
            send_default_pii=False,
            # Set profiles_sample_rate to 1.0 to profile 100%
            # of sampled transactions.
            # We recommend adjusting this value in production.
            profiles_sample_rate=1.0,
            # Do some client-side filtering to avoid sending
            # events that are not relevant to us.
            before_send=before_send,
        )
        sentry_sdk.capture_event({"message": "Initialized Sentry"})
    except ImportError:
        logger.warning("The sentry-sdk package is not installed. Un-able to use the Sentry error tracking service.")
    except Exception as error:
        logger.error(error)


def setup_scene(*_: Any) -> None:
    scene_properties = getattr(bpy.context.scene, ToolInfo.NAME, object)

    # initialize the rig instances
    for instance in getattr(scene_properties, "rig_instance_list", []):
        instance.initialize()

    start_listening()


def teardown_scene(*_: Any) -> None:
    scene_properties = getattr(bpy.context.scene, ToolInfo.NAME, object)

    for instance in getattr(scene_properties, "rig_instance_list", []):
        instance.destroy()
    logger.info("De-allocated Rig Logic instances...")


def pre_undo(*_: Any) -> None:
    context: "Context" = bpy.context  # type: ignore[attr-defined]  # noqa: UP037

    # Only run the pre-undo logic if the current context is a 3D view area
    if context.area and context.area.type == "VIEW_3D" and context.region and context.region.type == "WINDOW":
        context.window_manager.meta_human_dna.evaluate_dependency_graph = False
        context.window_manager.meta_human_dna.is_undoing = True
        for instance in context.scene.meta_human_dna.rig_instance_list:
            instance.destroy()


def post_undo(*_: Any) -> None:
    context: "Context" = bpy.context  # type: ignore[attr-defined]  # noqa: UP037

    # Only run the post-undo logic if the current context is a 3D view area
    if context.area and context.area.type == "VIEW_3D" and context.region and context.region.type == "WINDOW":
        context.window_manager.meta_human_dna.evaluate_dependency_graph = True


def pre_redo(*args: Any) -> None:
    pre_undo(*args)


def post_redo(*args: Any) -> None:
    post_undo(*args)


def pre_render(*args: Any) -> None:
    pre_undo(*args)


def post_render(*args: Any) -> None:
    post_undo(*args)


def post_save(*_: Any) -> None:
    instance = get_active_rig_instance()
    if not instance:
        return

    # Create a DNA backup
    from ..editors.backup_manager.core import BackupType, create_backup

    create_backup(instance, BackupType.BLENDER_FILE_SAVE)


def create_empty(empty_name: str) -> bpy.types.Object:
    empty_object = bpy.data.objects.get(empty_name)
    if not empty_object:
        empty_object = bpy.data.objects.new(empty_name, object_data=None)

    if bpy.context.scene and empty_object not in bpy.context.scene.collection.objects.values():
        bpy.context.scene.collection.objects.link(empty_object)

    return empty_object


def toggle_expand_in_outliner(state: int = 2):
    """
    Collapses or expands the collections in any outliner region on the current screen.


    Args:
        state (int, optional): 1 will expand all collections, 2 will
            collapse them. Defaults to 2.
    """
    if not bpy.context.screen:
        return
    for area in bpy.context.screen.areas:
        if area.type == "OUTLINER":
            for region in area.regions:
                if region.type == "WINDOW":
                    with bpy.context.temp_override(area=area, region=region):  # type: ignore[arg-type]
                        bpy.ops.outliner.show_hierarchy()
                        for _i in range(state):
                            bpy.ops.outliner.expanded_toggle()
                    area.tag_redraw()


def focus_on_selected():
    """
    Focuses any 3D view region on the current screen to the selected object.
    """
    if not bpy.context.screen or not bpy.context.window_manager:
        return
    for window in bpy.context.window_manager.windows:
        if window.screen:
            for area in bpy.context.screen.areas:
                if area.type == "VIEW_3D":
                    for region in area.regions:
                        if region.type == "WINDOW":
                            with bpy.context.temp_override(area=area, region=region):  # type: ignore[arg-type]
                                bpy.ops.view3d.view_selected()


def get_head(name: str) -> "MetaHumanComponentHead | None":
    # avoid circular import
    from ..components.head import MetaHumanComponentHead

    scene_properties: "MetahumanSceneProperties" = bpy.context.scene.meta_human_dna  # type: ignore[attr-defined]  # noqa: UP037
    for instance in scene_properties.rig_instance_list:
        if instance.name == name:
            return MetaHumanComponentHead(rig_instance=instance, component_type="head")

    logger.error(f'No existing head "{name}" was found')
    return None


def get_body(name: str) -> "MetaHumanComponentBody | None":
    # avoid circular import
    from ..components.body import MetaHumanComponentBody

    scene_properties: "MetahumanSceneProperties" = bpy.context.scene.meta_human_dna  # type: ignore[attr-defined]  # noqa: UP037
    for instance in scene_properties.rig_instance_list:
        if instance.name == name:
            return MetaHumanComponentBody(rig_instance=instance, component_type="body")

    logger.error(f'No existing body "{name}" was found')
    return None


def get_active_head() -> "MetaHumanComponentHead | None":
    """
    Gets the active head object.
    """
    instance = get_active_rig_instance()
    if instance:
        return get_head(instance.name)
    return None


def get_active_body() -> "MetaHumanComponentBody | None":
    """
    Gets the active body object.
    """
    instance = get_active_rig_instance()
    if instance:
        return get_body(instance.name)
    return None


def move_to_collection(scene_objects: list[bpy.types.Object], collection_name: str, exclusively: bool = False):
    collection = bpy.data.collections.get(collection_name)
    if not collection and bpy.context.scene:
        collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(collection)

    if exclusively:
        # unlink the objects from their current collections
        for scene_object in scene_objects:
            for user_collection in scene_object.users_collection:
                user_collection.objects.unlink(scene_object)

    # link the objects to the new collection
    for scene_object in scene_objects:
        if collection and scene_object not in collection.objects.values():
            collection.objects.link(scene_object)


def set_origin_to_world_center(scene_object: bpy.types.Object):
    switch_to_object_mode()
    # set the active object
    select_only(scene_object)
    # snap the cursor to the world center
    bpy.ops.view3d.snap_cursor_to_center()
    # then move the origin to match the cursor
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR", center="BOUNDS")


def set_objects_origins(scene_objects: list[bpy.types.Object], location: Vector):
    if not bpy.context.scene:
        return

    switch_to_object_mode()
    # set the active object
    for scene_object in scene_objects:
        select_only(scene_object)
        # snap the cursor to the world center
        bpy.context.scene.cursor.location = location
        # then move the origin to match the cursor
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR", center="BOUNDS")
        apply_transforms(scene_object, location=True, rotation=True, scale=True)


def rename_rig_instance(instance: "RigInstance", old_name: str, new_name: str):
    if instance.face_board:
        instance.face_board.name = instance.face_board.name.replace(old_name, new_name)
        instance.face_board.data.name = instance.face_board.data.name.replace(old_name, new_name)
    if instance.head_mesh:
        instance.head_mesh.name = instance.head_mesh.name.replace(old_name, new_name)
        instance.head_mesh.data.name = instance.head_mesh.data.name.replace(old_name, new_name)
    if instance.head_rig:
        instance.head_rig.name = instance.head_rig.name.replace(old_name, new_name)
        instance.head_rig.data.name = instance.head_rig.data.name.replace(old_name, new_name)
    if instance.head_material:
        instance.head_material.name = instance.head_material.name.replace(old_name, new_name)
    if instance.body_mesh:
        instance.body_mesh.name = instance.body_mesh.name.replace(old_name, new_name)
        instance.body_mesh.data.name = instance.body_mesh.data.name.replace(old_name, new_name)
    if instance.body_rig:
        instance.body_rig.name = instance.body_rig.name.replace(old_name, new_name)
        instance.body_rig.data.name = instance.body_rig.data.name.replace(old_name, new_name)
    if instance.body_material:
        instance.body_material.name = instance.body_material.name.replace(old_name, new_name)

    for item in instance.output_head_item_list.values() + instance.output_body_item_list.values():
        # don't rename these again
        if item.scene_object in [
            instance.face_board,
            instance.head_mesh,
            instance.head_rig,
            instance.body_mesh,
            instance.body_rig,
        ]:
            continue

        if item.scene_object:
            item.scene_object.name = item.scene_object.name.replace(old_name, new_name)
            item.scene_object.data.name = item.scene_object.data.name.replace(old_name, new_name)
        if item.image_object:
            item.image_object.name = item.image_object.name.replace(old_name, new_name)

    # rename the main collection
    main_collection = bpy.data.collections.get(old_name)
    if main_collection:
        main_collection.name = new_name

    # rename the LOD collections
    for index in range(NUMBER_OF_HEAD_LODS):
        collection = bpy.data.collections.get(f"{old_name}_lod{index}")
        if collection:
            collection.name = collection.name.replace(old_name, new_name)

    # this frees up the instance data under the old name, since all data is
    # namespaced under the instance name
    instance.destroy()


def rename_as_lod0_meshes(mesh_objects: list[bpy.types.Object]):
    from ..ui.callbacks import update_head_output_items

    instance = get_active_rig_instance()
    if instance:
        for mesh_object in mesh_objects:
            mesh_object.name = re.sub(INVALID_NAME_CHARACTERS_REGEX, "_", mesh_object.name.strip())
            if not mesh_object.name.startswith(instance.name):
                mesh_object.name = f"{instance.name}_{mesh_object.name}"
            if not mesh_object.name.endswith("_lod0_mesh"):
                mesh_object.name = f"{mesh_object.name}_lod0_mesh"

        # re-populate the output items
        instance.output_head_item_list.clear()
        update_head_output_items(None, bpy.context)  # type: ignore[arg-type]


def report_error(title: str, message: str, fix: Callable | None = None, width: int = 500):
    """
    Raises and error dialog to report error messages to the user with an optional fix.

    Args:
        title (str): The title of the error in the modal header.

        message (str): The body text with the error message.

        fix (Callable | None, optional): An optional function to be run to
            fix the issue if the user confirms. Defaults to None.

        width (int, optional): The width of the modal. Defaults to 500.
    """
    bpy.context.window_manager.meta_human_dna.errors[title] = {"fix": fix}  # type: ignore[attr-defined]
    bpy.ops.meta_human_dna.report_error(  # type: ignore[attr-defined]
        "INVOKE_DEFAULT",
        title=title,
        message=message,
        width=width,
    )


def import_head_texture_logic_node() -> bpy.types.NodeTree | None:
    sep = "\\"
    if sys.platform != "win32":
        sep = "/"

    node_group = bpy.data.node_groups.get(HEAD_TEXTURE_LOGIC_NODE_LABEL)
    if not node_group:
        directory_path = f"{MATERIALS_FILE_PATH}{sep}NodeTree{sep}"
        file_path = f"{MATERIALS_FILE_PATH}{sep}NodeTree{sep}{HEAD_TEXTURE_LOGIC_NODE_LABEL}"
        bpy.ops.wm.append(filepath=file_path, filename=HEAD_TEXTURE_LOGIC_NODE_LABEL, directory=directory_path)
        return bpy.data.node_groups.get(HEAD_TEXTURE_LOGIC_NODE_LABEL)
    return node_group


def dependencies_are_valid() -> bool:
    for module_name in ["riglogic", "meta_human_dna_core"]:
        module = sys.modules.get(module_name)
        if module and getattr(module, "__is_fake__", False):
            return False
    return True


def reduce_close_floats(float_list: list[float], tolerance: float = DEFAULT_UV_TOLERANCE) -> list[float]:
    """
    Reduces a list of floats by removing values that are too close to each other.

    Args:
        float_list: The list of floats to reduce.
        tolerance: The maximum allowed difference for two floats to be considered "close".

    Returns:
        A new list with close values reduced.
    """
    if not float_list:
        return []

    sorted_list = sorted(set(float_list))  # Sort and remove exact duplicates first
    if not sorted_list:
        return []

    reduced_list = [sorted_list[0]]
    for i in range(1, len(sorted_list)):
        # Compare with the last added element in the reduced_list
        if not math.isclose(sorted_list[i], reduced_list[-1], abs_tol=tolerance):
            reduced_list.append(sorted_list[i])
    return reduced_list


def shell(command: str, **kwargs: Any) -> Generator[str, None, None]:
    """
    Runs the command is a fully qualified shell.

    Args:
        command (str): A command.

    Yields:
        str: The output of the command line by line.

    Raises:
        OSError: The error cause by the shell.
    """
    process = subprocess.Popen(  # noqa: S602
        command, shell=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs
    )

    output = []
    if process.stdout:
        for line in iter(process.stdout.readline, ""):
            output += [line.rstrip()]
            yield line.rstrip()

    process.wait()

    if process.returncode != 0:
        raise OSError("\n".join(output))


def add_rig_instance(name: None | str = None) -> "RigInstance":
    scene_properties: "MetahumanSceneProperties" = bpy.context.scene.meta_human_dna  # type: ignore[attr-defined]  # noqa: UP037
    my_list = scene_properties.rig_instance_list
    active_index = scene_properties.rig_instance_list_active_index
    to_index = min(len(my_list), active_index + 1)
    instance: "RigInstance" = my_list.add()  # noqa: UP037

    if not name:
        instance.name = f"Untitled{len(my_list)}"
    else:
        instance.name = name

    my_list.move(len(my_list) - 1, to_index)
    scene_properties.rig_instance_list_active_index = to_index
    return instance


def extract_rig_instance_data_from_blend_file(blend_file_path: Path) -> tuple[list[dict], str]:
    extracted_data = []

    file_id = uuid.uuid4()
    script_file = SCRIPTS_FOLDER / "save_rig_instance_data.py"
    data_file = TEMP_FOLDER / f"{file_id}.json"
    error_file = TEMP_FOLDER / f"{file_id}_error.log"
    addon_folder = Path(__file__).parent.parent.parent

    binary_path = bpy.app.binary_path
    if binary_path:
        if sys.platform == "win32":
            command = (
                f'"{binary_path}" --background --python "{script_file}" -- --data-file "{data_file}" '
                f'--blend-file "{blend_file_path}" --addon-folder "{addon_folder}"'
            )
        else:
            command = (
                f"{binary_path} --background --python {script_file.as_posix()} -- --data-file {data_file.as_posix()} "
                f"--blend-file {blend_file_path.as_posix()} --addon-folder {addon_folder.as_posix()}"
            )
    # binary path can be empty if blender is run headless
    elif sys.platform == "win32":
        command = (
            f'"{sys.executable}" "{script_file}" -- --data-file "{data_file}" --blend-file "{blend_file_path}" '
            f'--addon-folder "{addon_folder}"'
        )
    else:
        command = (
            f"{sys.executable} {script_file.as_posix()} -- --data-file {data_file.as_posix()} --blend-file "
            f"{blend_file_path.as_posix()} --addon-folder {addon_folder.as_posix()}"
        )

    for _line in shell(command=command):
        pass

    if error_file.exists():
        with error_file.open() as f:
            error_message = f.read()

        try:
            error_file.unlink()
        except OSError as error:
            logger.debug(error)

        return [], error_message

    if data_file.exists():
        with data_file.open() as f:
            extracted_data = json.load(f)

        try:
            data_file.unlink()
        except OSError as error:
            logger.debug(error)

        return extracted_data, ""

    return [], "Failed to extract rig instance data."


def duplicate_face_board(name: str) -> bpy.types.Object | None:
    scene_properties: "MetahumanSceneProperties" = bpy.context.scene.meta_human_dna  # type: ignore[attr-defined]  # noqa: UP037
    for instance in scene_properties.rig_instance_list:
        if instance.face_board:
            # Duplicate the face board object
            face_board_duplicate = instance.face_board.copy()
            face_board_duplicate.name = f"{name}_{FACE_BOARD_NAME}"
            face_board_duplicate.data = instance.face_board.data.copy()
            face_board_duplicate.data.name = f"{name}_{FACE_BOARD_NAME}"
            if bpy.context.collection:
                bpy.context.collection.objects.link(face_board_duplicate)
            return face_board_duplicate
    return None


def hide_face_board_widgets():
    # unlink from scene and make fake users so they are not deleted by garbage collection
    for empty_name in FACE_GUI_EMPTIES:
        empty = bpy.data.objects.get(empty_name)
        if empty and bpy.context.scene:
            for collection in [
                bpy.data.collections.get("Collection"),
                bpy.context.scene.collection,
            ]:
                if not collection:
                    continue

                for child in empty.children_recursive:
                    if child in collection.objects.values():
                        collection.objects.unlink(child)
                    child.use_fake_user = True

                if empty in collection.objects.values():
                    collection.objects.unlink(empty)
                empty.use_fake_user = True


def purge_face_board_components():
    with bpy.data.libraries.load(str(FACE_BOARD_FILE_PATH)) as (data_from, _data_to):  # type: ignore[arg-type]
        if data_from.objects:
            for name in data_from.objects:
                scene_object = bpy.data.objects.get(name)
                if scene_object:
                    bpy.data.objects.remove(scene_object, do_unlink=True)


def import_face_board(name: str) -> bpy.types.Object | None:
    sep = "\\"
    if sys.platform != "win32":
        sep = "/"

    # delete all face board objects in the scene that already exist
    purge_face_board_components()

    bpy.ops.wm.append(
        filepath=f"{FACE_BOARD_FILE_PATH}{sep}Object{sep}{FACE_BOARD_NAME}",
        filename=FACE_BOARD_NAME,
        directory=f"{FACE_BOARD_FILE_PATH}{sep}Object{sep}",
    )
    face_board_object = bpy.data.objects[FACE_BOARD_NAME]
    # rename to be prefixed with a unique name
    face_board_object.name = f"{name}_{FACE_BOARD_NAME}"

    # hide all face board elements
    hide_face_board_widgets()

    if isinstance(face_board_object.data, bpy.types.Armature):
        face_board_object.data.relation_line_position = "HEAD"
    return face_board_object


def un_constrain_face_board_to_head(face_board_object: bpy.types.Object, bone_name: str) -> None:
    if face_board_object and face_board_object.pose:
        switch_to_pose_mode(face_board_object)
        pose_bone = face_board_object.pose.bones.get(bone_name)
        if pose_bone:
            for constraint in pose_bone.constraints:
                if constraint.type == "CHILD_OF":
                    pose_bone.constraints.remove(constraint)


def constrain_face_board_to_head(
    head_rig_object: bpy.types.Object,
    body_rig_object: bpy.types.Object,
    face_board_object: bpy.types.Object,
    bone_name: str,
) -> None:
    if head_rig_object and face_board_object and face_board_object.pose:
        switch_to_pose_mode(face_board_object)
        pose_bone = face_board_object.pose.bones.get(bone_name)
        if pose_bone:
            constraint = None
            for existing_constraint in pose_bone.constraints:
                if existing_constraint.type == "CHILD_OF":
                    constraint = existing_constraint
                    break
            if not constraint:
                constraint = pose_bone.constraints.new(type="CHILD_OF")

            rig_object = body_rig_object or head_rig_object
            constraint.target = rig_object  # type: ignore[attr-defined]
            constraint.subtarget = "head"  # type: ignore[attr-defined]
            # Set the inverse matrix using the operator
            with bpy.context.temp_override(active_object=face_board_object, active_pose_bone=pose_bone):  # type: ignore[arg-type]
                bpy.ops.constraint.childof_set_inverse(constraint=constraint.name, owner="BONE")


@preserve_context
def position_eye_aim(head_rig_object: bpy.types.Object, face_board_object: bpy.types.Object) -> None:
    if head_rig_object and face_board_object and face_board_object.pose and head_rig_object.pose:
        un_constrain_face_board_to_head(face_board_object, bone_name="CTRL_C_eyesAim")

        left_eye_bone = head_rig_object.pose.bones.get("FACIAL_L_Eye")
        right_eye_bone = head_rig_object.pose.bones.get("FACIAL_R_Eye")
        if left_eye_bone and right_eye_bone:
            eye_center = head_rig_object.matrix_world.inverted() @ ((left_eye_bone.head + right_eye_bone.head) / 2)
            target_eye_aim_world_location = eye_center + Vector((0, -0.3, 0))

            switch_to_edit_mode(face_board_object)
            if isinstance(face_board_object.data, bpy.types.Armature):
                eye_aim_center = face_board_object.data.edit_bones.get("CTRL_C_eyesAim")
                if eye_aim_center:
                    eye_aim_world_location = face_board_object.matrix_world.inverted() @ eye_aim_center.head

                    # calculate the offset between the current eye aim location and the target location
                    offset = eye_aim_world_location - target_eye_aim_world_location

                    # move all eye aim bones by the offset
                    for bone_name in EYE_AIM_BONES:
                        bone = face_board_object.data.edit_bones.get(bone_name)
                        if bone:
                            bone.head -= offset
                            bone.tail -= offset


def position_face_board(
    head_mesh_object: bpy.types.Object | None,
    head_rig_object: bpy.types.Object | None,
    face_board_object: bpy.types.Object,
) -> None:
    from .mesh import get_bounding_box_center, get_bounding_box_left_x, get_bounding_box_right_x

    if head_mesh_object and head_rig_object:
        un_constrain_face_board_to_head(face_board_object, bone_name="CTRL_faceGUI")

        head_mesh_center = get_bounding_box_center(head_mesh_object)
        face_gui_center = get_bounding_box_center(face_board_object)
        head_mesh_right_x = get_bounding_box_right_x(head_mesh_object)
        face_gui_left_x = get_bounding_box_left_x(face_board_object)

        # align the face gui object to the head mesh vertically
        translation_vector = head_mesh_center - face_gui_center
        face_board_object.location.z += translation_vector.z

        # offset the face gui object to the left of the head mesh
        x_value = head_mesh_right_x - face_gui_left_x
        face_board_object.location.x = x_value

        # apply the translation to the face gui object
        apply_transforms(face_board_object, location=True)

        # position the eye aim controls
        position_eye_aim(head_rig_object, face_board_object)


def collection_to_list(collection: bpy.types.bpy_prop_collection) -> list:
    item_list = []
    for item in collection:
        data = {"__property_group__": item.__class__.__name__}
        for key, data_type in item.__annotations__.items():
            if data_type.function.__name__ == "CollectionProperty":
                data[key] = collection_to_list(getattr(item, key))
            elif data_type.function.__name__ == "FloatVectorProperty":
                data[key] = getattr(item, key)[:]
            else:
                data[key] = getattr(item, key)

        item_list.append(data)
    return item_list


@exclude_rig_instance_evaluation
def migrate_legacy_data(context: "Context") -> None:  # noqa: PLR0912
    rig_instance_names = [instance.name for instance in context.scene.meta_human_dna.rig_instance_list]
    for key in LEGACY_DATA_KEYS:
        # Migrate rig instance data from old format to new format
        old_data = context.scene.meta_human_dna.get(key, [])
        for _instance_data in old_data:
            name = _instance_data.get("name")
            if name is not None and name not in rig_instance_names:
                instance = context.scene.meta_human_dna.rig_instance_list.add()
                instance.name = name

                # File Paths
                body_dna_file_path = _instance_data.get("body_dna_file_path")
                if body_dna_file_path is not None:
                    instance.body_dna_file_path = _instance_data.get("body_dna_file_path")
                head_dna_file_path = _instance_data.get("head_dna_file_path")
                if head_dna_file_path is not None:
                    instance.head_dna_file_path = _instance_data.get("head_dna_file_path")
                output_folder_path = _instance_data.get("output_folder_path")
                if output_folder_path is not None:
                    instance.output_folder_path = _instance_data.get("output_folder_path")
                # Rigs
                _body_rig = _instance_data.get("body_rig")
                if _body_rig:
                    body_rig = bpy.data.objects.get(_body_rig.name)
                    if body_rig is not None:
                        instance.body_rig = body_rig

                _head_rig = _instance_data.get("head_rig")
                if _head_rig:
                    head_rig = bpy.data.objects.get(_head_rig.name)
                    if head_rig is not None:
                        instance.head_rig = head_rig

                _face_board = _instance_data.get("face_board")
                if _face_board:
                    face_board = bpy.data.objects.get(_face_board.name)
                    if face_board is not None:
                        instance.face_board = face_board
                # Meshes
                _body_mesh = _instance_data.get("body_mesh")
                if _body_mesh:
                    body_mesh = bpy.data.objects.get(_body_mesh.name)
                    if body_mesh is not None:
                        instance.body_mesh = body_mesh
                _head_mesh = _instance_data.get("head_mesh")
                if _head_mesh:
                    head_mesh = bpy.data.objects.get(_head_mesh.name)
                    if head_mesh is not None:
                        instance.head_mesh = head_mesh
                # Materials
                _body_material = _instance_data.get("body_material")
                if _body_material:
                    body_material = bpy.data.materials.get(_body_material.name)
                    if body_material is not None:
                        instance.body_material = body_material
                _head_material = _instance_data.get("head_material")
                if _head_material:
                    head_material = bpy.data.materials.get(_head_material.name)
                    if head_material is not None:
                        instance.head_material = head_material
                # Other Properties
                head_to_body_constraint_influence = _instance_data.get("head_to_body_constraint_influence")
                if head_to_body_constraint_influence is not None:
                    instance.head_to_body_constraint_influence = head_to_body_constraint_influence

        # Remove old data after migration
        del context.scene.meta_human_dna[key]
