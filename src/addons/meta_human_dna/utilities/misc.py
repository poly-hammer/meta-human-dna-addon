import json
import os
import re
import bpy
import sys
import math
import uuid
import logging
import subprocess
import addon_utils
from typing import Generator
from pathlib import Path
from mathutils import Vector
from typing import TYPE_CHECKING, Callable
from ..constants import (
    MATERIALS_FILE_PATH, 
    HEAD_TEXTURE_LOGIC_NODE_LABEL,
    SCRIPTS_FOLDER,
    FACE_BOARD_NAME,
    SCALE_FACTOR
)
from ..rig_logic import start_listening
from ..constants import (
    SENTRY_DSN,
    SEND2UE_EXTENSION,
    PACKAGES_FOLDER,
    NUMBER_OF_HEAD_LODS,
    INVALID_NAME_CHARACTERS_REGEX,
    DEFAULT_UV_TOLERANCE,
    FACE_GUI_EMPTIES,
    FACE_BOARD_FILE_PATH,
    EYE_AIM_BONES,
    TEMP_FOLDER,
    ToolInfo
)

if TYPE_CHECKING:
    from ..components.head import MetaHumanComponentHead
    from ..components.body import MetaHumanComponentBody
    from ..rig_logic import RigLogicInstance

logger = logging.getLogger(__name__)

def exclude_rig_logic_evaluation(func):
    def wrapper(*args, **kwargs):
        bpy.context.window_manager.meta_human_dna.evaluate_dependency_graph = False # type: ignore
        result = func(*args, **kwargs)
        bpy.context.window_manager.meta_human_dna.evaluate_dependency_graph = True # type: ignore
        return result
    return wrapper


def get_current_context():
    object_contexts = {}
    for scene_object in bpy.context.scene.objects: # type: ignore
        active_action_name = ''
        if scene_object.animation_data and scene_object.animation_data.action:
            active_action_name = scene_object.animation_data.action.name

        object_contexts[scene_object.name] = {
            'hide': scene_object.hide_get(),
            'hide_viewport': scene_object.hide_viewport,
            'select': scene_object.select_get(),
            'active_action': active_action_name,
            'show_instancer_for_render': scene_object.show_instancer_for_render
        }

    active_object = None
    if bpy.context.active_object: # type: ignore
        active_object = bpy.context.active_object.name # type: ignore

    return {
        'mode': getattr(bpy.context, 'mode', 'OBJECT'),
        'objects': object_contexts,
        'active_object': active_object,
        'current_frame': bpy.context.scene.frame_current, # type: ignore
        'cursor_location': bpy.context.scene.cursor.location # type: ignore
    }


def set_context(context):
    mode = context.get('mode', 'OBJECT')
    active_object_name = context.get('active_object')
    object_contexts = context.get('objects')
    for object_name, attributes in object_contexts.items():
        scene_object = bpy.data.objects.get(object_name)
        if scene_object:
            scene_object.hide_set(attributes.get('hide', False))
            scene_object.hide_viewport = attributes.get('hide_viewport', False)
            scene_object.select_set(attributes.get('select', False))

            active_action = attributes.get('active_action')
            if active_action and scene_object.animation_data:
                scene_object.animation_data.action = bpy.data.actions.get(active_action)

            scene_object.show_instancer_for_render = attributes.get('show_instancer_for_render', False)

    # set the active object
    if active_object_name:
        bpy.context.view_layer.objects.active = bpy.data.objects.get(active_object_name) # type: ignore

    # set the mode
    if bpy.context.mode != mode: # type: ignore
        # Note:
        # When the mode context is read in edit mode it can be 'EDIT_ARMATURE' or 'EDIT_MESH', even though you
        # are only able to set the context to 'EDIT' mode. Thus, if 'EDIT' was read from the mode context, the mode
        # is set to edit.
        if 'EDIT' in mode:
            mode = 'EDIT'
        bpy.ops.object.mode_set(mode=mode)

    # set the current frame
    bpy.context.scene.frame_set(context.get('current_frame', 0)) # type: ignore
    
    # set the cursor location
    bpy.context.scene.cursor.location = context.get('cursor_location', Vector((0,0,0))) # type: ignore


def preserve_context(func):
    def wrapper(*args, **kwargs):
        bpy.context.window_manager.meta_human_dna.evaluate_dependency_graph = False # type: ignore
        context = get_current_context()
        result = func(*args, **kwargs)
        bpy.context.window_manager.meta_human_dna.evaluate_dependency_graph = True # type: ignore
        set_context(context)
        return result
    return wrapper


def deselect_all():
    for scene_object in bpy.data.objects:
        scene_object.select_set(False)


def select_only(*scene_object):
    deselect_all()
    for _scene_object in scene_object:
        _scene_object.select_set(True)
        bpy.context.view_layer.objects.active = _scene_object # type: ignore


def switch_to_object_mode():
    if bpy.context.mode != 'OBJECT': # type: ignore
        bpy.ops.object.mode_set(mode='OBJECT')


def switch_to_edit_mode(*scene_object):
    select_only(*scene_object)
    bpy.ops.object.mode_set(mode='EDIT')

def switch_to_sculpt_mode(*scene_object):
    select_only(*scene_object)
    switch_to_object_mode()
    bpy.ops.object.mode_set(mode='SCULPT')

def switch_to_bone_edit_mode(*armature_object):
    # Switch to edit mode so we can get edit bone data
    if bpy.context.mode != "EDIT_ARMATURE":  # type: ignore
        select_only(*armature_object)
        bpy.context.view_layer.objects.active = armature_object[0]  # type: ignore
        bpy.ops.object.mode_set(mode="EDIT")


def switch_to_pose_mode(*scene_object):
    select_only(*scene_object)
    switch_to_object_mode()
    bpy.ops.object.mode_set(mode='POSE')


def apply_pose(rig_object: bpy.types.Object, selected: bool = False):
    switch_to_object_mode()
    switch_to_pose_mode(rig_object)
    bpy.ops.pose.armature_apply(selected=selected)


def apply_transforms(scene_object, location=False, rotation=False, scale=False, recursive=False):
    deselect_all()
    switch_to_object_mode()
    select_only(scene_object)
    bpy.ops.object.transform_apply(location=location, rotation=rotation, scale=scale)

    if recursive:
        for child_object in scene_object.children:
            apply_transforms(
                child_object,
                location=location,
                rotation=rotation,
                scale=scale,
                recursive=recursive
            )


def walk_children(scene_object):
    yield scene_object
    for child in scene_object.children:
        yield from walk_children(child)


def disable_select_on_non_controls(root='GRP_faceGUI'):
    for scene_object in walk_children(bpy.data.objects.get(root)):
        if scene_object:
            if not scene_object.name.startswith("CTRL_"):
                scene_object.hide_select = True


def hide_empties(root='GRP_faceGUI'):
    for scene_object in bpy.data.objects:
        if scene_object.name.startswith("GRP_"):
            scene_object.hide_viewport = True


def set_hide_recursively(scene_object, value):
    for child in walk_children(scene_object):
        child.hide_set(value)


def set_viewport_shading(mode):
    for area in bpy.context.screen.areas: # type: ignore
        if area.ui_type == 'VIEW_3D':
            for space in area.spaces:
                if hasattr(space, 'shading'):
                    space.shading.type = mode # type: ignore

def init_sentry():
    # Don't collect metrics when in dev mode
    if os.environ.get('META_HUMAN_DNA_DEV'):
        return
    
    # Don't collect metrics if the user has disabled online access
    if not bpy.app.online_access:
        return

    # Don't collect metrics if the user has disabled it
    if not bpy.context.preferences.addons[ToolInfo.NAME].preferences.metrics_collection: # type: ignore
        return

    if PACKAGES_FOLDER not in [Path(path) for path in sys.path]:
        sys.path.append(str(PACKAGES_FOLDER))
    
    try:
        import sentry_sdk # type: ignore
        from sentry_sdk.types import Event, Hint

        def before_send(event: Event, hint: Hint) -> Event | None:
            # Filter based on module origin. We only want to send errors related 
            # to the Meta-Human DNA addon and the send2ue addon.
            if event.get("exception") and event["exception"].get("values"): # type: ignore
                exception = event["exception"]["values"][0] # type: ignore
                if exception.get("stacktrace") and exception["stacktrace"].get("frames"):
                    # Check if the exception originated from one of the whitelisted modules
                    for frame in exception["stacktrace"]["frames"]:
                        module_name = frame.get("module")
                        if module_name and (module_name.startswith(ToolInfo.NAME) or module_name.startswith('send2ue')):
                            break
                    else:
                        return None
                    
            # Add tags to the event
            if "tags" not in event:
                event["tags"] = {}

            from .. import bl_info
            event["tags"]["blender_version"] = bpy.app.version_string
            event["tags"]["blender_mode"] = bpy.context.mode # type: ignore
            event["tags"]["addon_version"] = ".".join([str(i) for i in bl_info.get('version', [])])
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
            before_send=before_send
        )
        sentry_sdk.capture_event({'message': 'Initialized Sentry'})        
    except ImportError:
        logger.warning('The sentry-sdk package is not installed. Un-able to use the Sentry error tracking service.')
    except Exception as error:
        logger.error(error)

def send2ue_addon_is_valid() -> bool:
    for module in addon_utils.modules():
        if module.__name__ == 'send2ue':    
            version = module.bl_info.get('version', (0,0,0))
            if version[0] >= 2 and version[1] >= 6:
                return True
    return False

def link_send2ue_extension():
    addon = bpy.context.preferences.addons.get('send2ue') # type: ignore
    send2ue_properties = getattr(bpy.context.scene, 'send2ue', None) # type: ignore
    if addon and send2ue_properties and send2ue_addon_is_valid():
        # check if the extension is already linked and skip the linking logic if it is
        # this allows the user to manually link their own extension if they want. 
        # It has to have the name 'meta_human_dna'.
        if getattr(send2ue_properties.extensions, ToolInfo.NAME, None): # type: ignore
            bpy.ops.send2ue.reload_extensions() # type: ignore
            return

        for extension_folder in addon.preferences.extension_folder_list: # type: ignore
            if Path(extension_folder.folder_path) == SEND2UE_EXTENSION.parent:
                break
        else:
            extension_folder = addon.preferences.extension_folder_list.add() # type: ignore
            extension_folder.folder_path = str(SEND2UE_EXTENSION.parent)

        bpy.ops.send2ue.reload_extensions() # type: ignore
    else:
        logger.warning(
            'The send2ue addon is not installed. Please install it to use it to '
            ' enable the Send to Unreal button in the Meta-Human DNA addon output panel.'
        )


def setup_scene(*args):
    scene_properties = getattr(bpy.context.scene, ToolInfo.NAME, object) # type: ignore
    
    # initialize the rig logic instances
    for instance in getattr(scene_properties, 'rig_logic_instance_list', []):
        instance.initialize()

    start_listening()
    # link_send2ue_extension()

def teardown_scene(*args):
    scene_properties = getattr(bpy.context.scene, ToolInfo.NAME, object) # type: ignore
    
    for instance in getattr(scene_properties, 'rig_logic_instance_list', []):
        instance.destroy()
    else:
        logging.info('De-allocated Rig Logic instances...')

def pre_undo(*args):
    # Only run the pre-undo logic if the current context is a 3D view area
    if (
        bpy.context.area and 
        bpy.context.area.type == 'VIEW_3D' and
        bpy.context.region and
        bpy.context.region.type == 'WINDOW'
    ):
        bpy.context.window_manager.meta_human_dna.evaluate_dependency_graph = False # type: ignore
        for instance in bpy.context.scene.meta_human_dna.rig_logic_instance_list: # type: ignore
            instance.destroy()

def post_undo(*args):
    # Only run the post-undo logic if the current context is a 3D view area
    if (
        bpy.context.area and 
        bpy.context.area.type == 'VIEW_3D' and
        bpy.context.region and
        bpy.context.region.type == 'WINDOW'
    ):
        bpy.ops.meta_human_dna.force_evaluate() # type: ignore

def pre_render(*args):
    pre_undo(*args)

def post_render(*args):
    post_undo(*args)

def create_empty(empty_name):
    empty_object = bpy.data.objects.get(empty_name)
    if not empty_object:
        empty_object = bpy.data.objects.new(empty_name, object_data=None)

    if empty_object not in bpy.context.scene.collection.objects.values(): # type: ignore
        bpy.context.scene.collection.objects.link(empty_object) # type: ignore

    return empty_object

def toggle_expand_in_outliner(state: int = 2):
    """
    Collapses or expands the collections in any outliner region on the current screen.
    

    Args:
        state (int, optional): 1 will expand all collections, 2 will 
            collapse them. Defaults to 2.
    """    
    for area in bpy.context.screen.areas: # type: ignore
        if area.type == 'OUTLINER':
            for region in area.regions:
                if region.type == 'WINDOW':
                    with bpy.context.temp_override(area=area, region=region): # type: ignore
                        bpy.ops.outliner.show_hierarchy()
                        for i in range(state):
                            bpy.ops.outliner.expanded_toggle()
                    area.tag_redraw()

def focus_on_selected():
    """
    Focuses any 3D view region on the current screen to the selected object.
    """
    for window in bpy.context.window_manager.windows: # type: ignore
        if window.screen:
            for area in bpy.context.screen.areas: # type: ignore
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            with bpy.context.temp_override(area=area, region=region): # type: ignore
                                bpy.ops.view3d.view_selected()

def get_head(name: str) -> 'MetaHumanComponentHead | None':
    # avoid circular import
    from ..components.head import MetaHumanComponentHead
    
    properties = bpy.context.scene.meta_human_dna # type: ignore
    for instance in properties.rig_logic_instance_list:
        if instance.name == name:
            return MetaHumanComponentHead(
                rig_logic_instance=instance,
                component_type='head'
            )
        
    logger.error(f'No existing head "{name}" was found')

def get_body(name: str) -> 'MetaHumanComponentBody | None':
    # avoid circular import
    from ..components.body import MetaHumanComponentBody
    
    properties = bpy.context.scene.meta_human_dna # type: ignore
    for instance in properties.rig_logic_instance_list:
        if instance.name == name:
            return MetaHumanComponentBody(
                rig_logic_instance=instance,
                component_type='body'
            )

    logger.error(f'No existing body "{name}" was found')

def get_active_head() -> 'MetaHumanComponentHead | None':
    """
    Gets the active head object.
    """
    properties = bpy.context.scene.meta_human_dna # type: ignore
    if len(properties.rig_logic_instance_list) > 0:
        index = properties.rig_logic_instance_list_active_index
        instance = properties.rig_logic_instance_list[index]
        return get_head(instance.name)

def get_active_body() -> 'MetaHumanComponentBody | None':
    """
    Gets the active body object.
    """
    properties = bpy.context.scene.meta_human_dna # type: ignore
    if len(properties.rig_logic_instance_list) > 0:
        index = properties.rig_logic_instance_list_active_index
        instance = properties.rig_logic_instance_list[index]
        return get_body(instance.name)

def move_to_collection(
        scene_objects: list[bpy.types.Object], 
        collection_name: str,
        exclusively: bool = False
    ):
    collection = bpy.data.collections.get(collection_name)
    if not collection:
        collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(collection) # type: ignore
    
    if exclusively:
        # unlink the objects from their current collections
        for scene_object in scene_objects:
            for user_collection in scene_object.users_collection:
                user_collection.objects.unlink(scene_object)
    
    # link the objects to the new collection
    for scene_object in scene_objects:
        if scene_object not in collection.objects.values():
            collection.objects.link(scene_object) # type: ignore

def set_origin_to_world_center(scene_object: bpy.types.Object):   
    switch_to_object_mode()
    # set the active object
    select_only(scene_object)
    # snap the cursor to the world center
    bpy.ops.view3d.snap_cursor_to_center()
    # then move the origin to match the cursor
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='BOUNDS')

def set_objects_origins(scene_objects: list[bpy.types.Object], location: Vector):   
    switch_to_object_mode()
    # set the active object
    for scene_object in scene_objects:
        select_only(scene_object)
        # snap the cursor to the world center
        bpy.context.scene.cursor.location = location # type: ignore
        # then move the origin to match the cursor
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='BOUNDS')
        apply_transforms(scene_object, location=True, rotation=True, scale=True)

def re_create_rig_logic_instance(
        instance: 'RigLogicInstance',
        new_name: str,
        new_dna_file_path: Path | str,
) -> 'RigLogicInstance':
    # copy the instance data
    face_board = instance.face_board
    head_mesh = instance.head_mesh
    head_rig = instance.head_rig
    head_material = instance.head_material

    # clear data dictionary from the old instance so underlying data can be garbage collected
    instance.data.clear()
    # find the index of the old instance and remove it
    index = bpy.context.scene.meta_human_dna.rig_logic_instance_list.find(instance.name) # type: ignore
    bpy.context.scene.meta_human_dna.rig_logic_instance_list.remove(index) # type: ignore

    # create a new instance with the copied data
    new_instance = bpy.context.scene.meta_human_dna.rig_logic_instance_list.add() # type: ignore
    new_instance.name = new_name
    new_instance.head_dna_file_path = str(new_dna_file_path)
    new_instance.face_board = face_board
    new_instance.head_mesh = head_mesh
    new_instance.head_rig = head_rig
    new_instance.head_material = head_material
    
    # set the new instance as the active instance
    index = bpy.context.scene.meta_human_dna.rig_logic_instance_list.find(new_instance.name) # type: ignore
    bpy.context.scene.meta_human_dna.rig_logic_instance_list_active_index = index # type: ignore

    return new_instance


def rename_rig_logic_instance(
        instance: 'RigLogicInstance',
        old_name: str,
        new_name: str
    ):
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

    for item in (instance.output_head_item_list.values() + instance.output_body_item_list.values()):
        # don't rename these again
        if item.scene_object in [
            instance.face_board, 
            instance.head_mesh, 
            instance.head_rig, 
            instance.body_mesh,
            instance.body_rig
        ]:
            continue

        if item.scene_object:
            item.scene_object.name = item.scene_object.name.replace(old_name, new_name)
            item.scene_object.data.name = item.scene_object.data.name.replace(old_name, new_name)
        if item.image_object:
            item.image_object.name = item.image_object.name.replace(old_name, new_name)

    instance.unreal_content_folder = instance.unreal_content_folder.replace(old_name, new_name)
    instance.unreal_blueprint_asset_path = instance.unreal_blueprint_asset_path.replace(old_name, new_name)

    # rename the main collection
    main_collection = bpy.data.collections.get(old_name)
    if main_collection:
        main_collection.name = new_name

    # rename the LOD collections
    for index in range(NUMBER_OF_HEAD_LODS):
        collection = bpy.data.collections.get(f'{old_name}_lod{index}')
        if collection:
            collection.name = collection.name.replace(old_name, new_name)

    # this frees up the instance data under the old name, since all data is 
    # namespaced under the instance name
    instance.destroy()

def rename_as_lod0_meshes(mesh_objects: list[bpy.types.Object]):
    from ..ui.callbacks import get_active_rig_logic, update_head_output_items
    instance = get_active_rig_logic()
    if instance:
        for mesh_object in mesh_objects:
            mesh_object.name = re.sub(INVALID_NAME_CHARACTERS_REGEX, "_",  mesh_object.name.strip())
            if not mesh_object.name.startswith(instance.name):
                mesh_object.name = f'{instance.name}_{mesh_object.name}'
            if not mesh_object.name.endswith('_lod0_mesh'):
                mesh_object.name = f'{mesh_object.name}_lod0_mesh'

        # re-populate the output items
        instance.output_head_item_list.clear()
        update_head_output_items(None, bpy.context)

def report_error(
        title: str,
        message: str,
        fix: Callable | None = None,
        width: int = 500
    ):
    """
    Raises and error dialog to report error messages to the user with an optional fix.

    Args:
        title (str): The title of the error in the modal header.
        
        message (str): The body text with the error message.

        fix (Callable | None, optional): An optional function to be run to 
            fix the issue if the user confirms. Defaults to None.
        
        width (int, optional): The width of the modal. Defaults to 500.
    """
    bpy.context.window_manager.meta_human_dna.errors[title] = {'fix': fix} # type: ignore
    bpy.ops.meta_human_dna.report_error( # type: ignore
        'INVOKE_DEFAULT',
        title=title,
        message=message,
        width=width,
    ) # type: ignore


def import_head_texture_logic_node() -> bpy.types.NodeTree | None:
    sep = '\\'
    if sys.platform != 'win32':
        sep = '/'

    node_group = bpy.data.node_groups.get(HEAD_TEXTURE_LOGIC_NODE_LABEL)
    if not node_group:
        directory_path = f'{MATERIALS_FILE_PATH}{sep}NodeTree{sep}'
        file_path = f'{MATERIALS_FILE_PATH}{sep}NodeTree{sep}{HEAD_TEXTURE_LOGIC_NODE_LABEL}'
        bpy.ops.wm.append(
            filepath=file_path,
            filename=HEAD_TEXTURE_LOGIC_NODE_LABEL,
            directory=directory_path
        )
        return bpy.data.node_groups.get(HEAD_TEXTURE_LOGIC_NODE_LABEL)
    return node_group


def dependencies_are_valid() -> bool:
    for module_name in ['riglogic', 'meta_human_dna_core']:
        module = sys.modules.get(module_name)
        if module and getattr(module, '__is_fake__', False):
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

    sorted_list = sorted(list(set(float_list))) # Sort and remove exact duplicates first
    if not sorted_list:
        return []

    reduced_list = [sorted_list[0]]
    for i in range(1, len(sorted_list)):
        # Compare with the last added element in the reduced_list
        if not math.isclose(sorted_list[i], reduced_list[-1], abs_tol=tolerance):
            reduced_list.append(sorted_list[i])
    return reduced_list


def shell(command: str, **kwargs) -> Generator[str, None, None]:
    """
    Runs the command is a fully qualified shell.

    Args:
        command (str): A command.

    Yields:
        str: The output of the command line by line.

    Raises:
        OSError: The error cause by the shell.
    """
    process = subprocess.Popen(
        command,
        shell=True,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **kwargs
    )

    output = []
    for line in iter(process.stdout.readline, ""): # type: ignore
        output += [line.rstrip()]
        yield line.rstrip()

    process.wait()

    if process.returncode != 0:
        raise OSError("\n".join(output))


def add_rig_instance(name: None | str = None) -> 'RigLogicInstance':
    my_list = bpy.context.scene.meta_human_dna.rig_logic_instance_list # type: ignore
    active_index = bpy.context.scene.meta_human_dna.rig_logic_instance_list_active_index # type: ignore
    to_index = min(len(my_list), active_index + 1)
    instance = my_list.add()
    
    if not name:
        instance.name = f"Untitled{len(my_list)}"
    else:
        instance.name = name

    my_list.move(len(my_list) - 1, to_index)
    bpy.context.scene.meta_human_dna.rig_logic_instance_list_active_index = to_index # type: ignore
    return instance


def extract_rig_instance_data_from_blend_file(blend_file_path: Path) -> tuple[list[dict], str]:
    extracted_data = []

    file_id = uuid.uuid4()
    script_file = SCRIPTS_FOLDER / 'save_rig_instance_data.py'
    data_file = TEMP_FOLDER / f"{file_id}.json"
    error_file = TEMP_FOLDER / f"{file_id}_error.log"

    if sys.platform == 'win32':
        command = f'"{bpy.app.binary_path}" --background --python "{script_file}" -- --data-file "{data_file}" --blend-file "{blend_file_path}"'
    else:
        command = f"{Path(bpy.app.binary_path).as_posix()} --background --python {script_file} -- --data-file {data_file.as_posix()} --blend-file {blend_file_path.as_posix()}"

    for line in shell(command=command):
        pass

    if error_file.exists():
        with open(error_file, 'r') as f:
            error_message = f.read()

        try:
            os.remove(error_file)
        except OSError as error:
            logger.debug(error)

        return [], error_message

    if data_file.exists():
        with open(data_file, 'r') as f:
            extracted_data = json.load(f)

        try:
            os.remove(data_file)
        except OSError as error:
            logger.debug(error)

        return extracted_data, ''
    
    return [], 'Failed to extract rig instance data.'


def duplicate_face_board(name: str) -> bpy.types.Object | None:    
    for instance in bpy.context.scene.meta_human_dna.rig_logic_instance_list: # type: ignore
        if instance.face_board:
            # Duplicate the face board object
            face_board_duplicate = instance.face_board.copy()
            face_board_duplicate.name = f'{name}_{FACE_BOARD_NAME}'
            face_board_duplicate.data = instance.face_board.data.copy()
            face_board_duplicate.data.name = f'{name}_{FACE_BOARD_NAME}'
            bpy.context.collection.objects.link(face_board_duplicate) # type: ignore
            return face_board_duplicate
        

def hide_face_board_widgets():
    # unlink from scene and make fake users so they are not deleted by garbage collection
    for empty_name in FACE_GUI_EMPTIES:
        empty = bpy.data.objects.get(empty_name)
        if empty:
            for collection in [
                bpy.data.collections.get('Collection'),
                bpy.context.scene.collection # type: ignore
            ]:
                if not collection:
                    continue

                for child in empty.children_recursive:
                    if child in collection.objects.values(): # type: ignore
                        collection.objects.unlink(child) # type: ignore
                    child.use_fake_user = True
                
                if empty in collection.objects.values(): # type: ignore
                    collection.objects.unlink(empty) # type: ignore
                empty.use_fake_user = True


def purge_face_board_components():
    with bpy.data.libraries.load(str(FACE_BOARD_FILE_PATH)) as (data_from, data_to):
        if data_from.objects:
            for name in data_from.objects:
                scene_object = bpy.data.objects.get(name)
                if scene_object:
                    bpy.data.objects.remove(scene_object, do_unlink=True)


def import_face_board(name: str) -> bpy.types.Object | None:
    sep = '\\'
    if sys.platform != 'win32':
        sep = '/'

    # delete all face board objects in the scene that already exist
    purge_face_board_components()

    bpy.ops.wm.append(
        filepath=f'{FACE_BOARD_FILE_PATH}{sep}Object{sep}{FACE_BOARD_NAME}',
        filename=FACE_BOARD_NAME,
        directory=f'{FACE_BOARD_FILE_PATH}{sep}Object{sep}'
    )
    face_board_object = bpy.data.objects[FACE_BOARD_NAME]
    # rename to be prefixed with a unique name
    face_board_object.name = f'{name}_{FACE_BOARD_NAME}' # type: ignore

    # hide all face board elements
    hide_face_board_widgets()

    face_board_object.data.relation_line_position = 'HEAD' # type: ignore
    return face_board_object


def un_constrain_face_board_to_head(
        face_board_object: bpy.types.Object,
        bone_name: str
    ) -> None:
    if face_board_object:
        switch_to_pose_mode(face_board_object)
        pose_bone = face_board_object.pose.bones.get(bone_name) # type: ignore
        if pose_bone:
            constraint = pose_bone.constraints.get('Child Of')
            if constraint:
                pose_bone.constraints.remove(constraint)


def constrain_face_board_to_head(
        head_rig_object: bpy.types.Object,
        body_rig_object: bpy.types.Object,
        face_board_object: bpy.types.Object,
        bone_name: str
    ) -> None:
    if head_rig_object and face_board_object:
        switch_to_pose_mode(face_board_object)
        pose_bone = face_board_object.pose.bones.get(bone_name) # type: ignore
        if pose_bone:
            constraint = pose_bone.constraints.get('Child Of')
            if not constraint:
                constraint = pose_bone.constraints.new(type='CHILD_OF')

            rig_object = body_rig_object or head_rig_object
            constraint.target = rig_object # type: ignore
            constraint.subtarget = 'head' # type: ignore
            # Set the inverse matrix using the operator
            with bpy.context.temp_override(active_object=face_board_object, active_pose_bone=pose_bone): # type: ignore
                bpy.ops.constraint.childof_set_inverse(constraint=constraint.name, owner='BONE')


@preserve_context
def position_eye_aim(
        head_rig_object: bpy.types.Object,
        face_board_object: bpy.types.Object
    ) -> None:

    if head_rig_object and face_board_object:

        un_constrain_face_board_to_head(face_board_object, bone_name='CTRL_C_eyesAim')

        left_eye_bone = head_rig_object.pose.bones.get('FACIAL_L_Eye') # type: ignore
        right_eye_bone = head_rig_object.pose.bones.get('FACIAL_R_Eye') # type: ignore
        if left_eye_bone and right_eye_bone:
            eye_center = head_rig_object.matrix_world.inverted() @ ((left_eye_bone.head + right_eye_bone.head) / 2)
            target_eye_aim_world_location = eye_center + Vector((0, -0.3, 0))

            switch_to_edit_mode(face_board_object)
            eye_aim_center = face_board_object.data.edit_bones.get('CTRL_C_eyesAim') # type: ignore
            if eye_aim_center:
                eye_aim_world_location = face_board_object.matrix_world.inverted() @ eye_aim_center.head

                # calculate the offset between the current eye aim location and the target location
                offset = eye_aim_world_location - target_eye_aim_world_location

                # move all eye aim bones by the offset
                for bone_name in EYE_AIM_BONES:
                    bone = face_board_object.data.edit_bones.get(bone_name) # type: ignore
                    if bone:
                        bone.head -= offset
                        bone.tail -= offset


def position_face_board(
        head_mesh_object: bpy.types.Object,
        head_rig_object: bpy.types.Object,
        face_board_object: bpy.types.Object
    ) -> None:
    from .mesh import (
        get_bounding_box_center,
        get_bounding_box_left_x,
        get_bounding_box_right_x
    )

    if head_mesh_object and head_rig_object:
        un_constrain_face_board_to_head(face_board_object, bone_name='CTRL_faceGUI')

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
        apply_transforms(face_board_object, location=True) # type: ignore

        # position the eye aim controls
        position_eye_aim(head_rig_object, face_board_object)


def collection_to_list(collection: bpy.types.Collection) -> list:
    item_list = []
    for item in collection:
        data = {'__property_group__': item.__class__.__name__}
        for key, data_type in item.__annotations__.items():
            if data_type.function.__name__ == 'CollectionProperty':
                data[key] = collection_to_list(getattr(item, key))
            elif data_type.function.__name__ == 'FloatVectorProperty':
                data[key] = getattr(item, key)[:]
            else:
                data[key] = getattr(item, key)

        item_list.append(data)
    return item_list

def _scale_driven_data(
    driven_data: list[dict],
    weight: float
) -> list[dict]:
    """
    Scale transformation deltas by a weight multiplier.
    """
    scaled_list = []
    for driven in driven_data:
        scaled = dict(
            pose_index=driven['pose_index'],
            joint_index=driven['joint_index'],
            name=driven['name'],
            rotation_mode=driven['rotation_mode'],
            location=[v * weight for v in driven['location']],
            euler_rotation=[v * weight for v in driven['euler_rotation']],
            quaternion_rotation=driven['quaternion_rotation'],
            scale=[1.0 + (v - 1.0) * weight for v in driven['scale']]
        )
        scaled_list.append(scaled)
    return scaled_list

def _get_joint_group_index(
    reader,
    control_index: int
) -> int:
    """
    Find existing joint group containing the control, or create new one.
    """
    # Search for existing group with this control
    group_count = reader.getJointGroupCount()
    
    for gi in range(group_count):
        input_indices = list(reader.getJointGroupInputIndices(gi))
        if control_index in input_indices:
            return gi
    
    # Create new group
    return group_count


def _update_joint_group_with_deltas(
    reader,
    writer,
    joint_group_index: int,
    control_index: int,
    driven_data: list[dict],
    lod_count: int | None = None # type: ignore
) -> None:
    """
    Update joint group matrix with transformation deltas.
    """
    
    # Get existing data (or empty if new group)
    try:
        input_indices = list(reader.getJointGroupInputIndices(joint_group_index))
        output_indices = list(reader.getJointGroupOutputIndices(joint_group_index))
        existing_values = list(reader.getJointGroupValues(joint_group_index))
    except:
        input_indices = []
        output_indices = []
        existing_values = []
    
    # Ensure control is in input indices
    if control_index not in input_indices:
        input_indices.append(control_index)
    
    control_column = input_indices.index(control_index)
    
    # Build output indices and values map
    delta_map = {}  # output_index -> value
    
    for driven in driven_data:
        matrix_index = driven['joint_index'] * 9
        
        # Translation (apply scale)
        for i in range(3):
            output_idx = matrix_index + i
            value = driven['location'][i] * SCALE_FACTOR
            if abs(value) > 1e-6:  # Only store non-zero
                delta_map[output_idx] = value
        
        # Rotation (convert to degrees)
        for i in range(3):
            output_idx = matrix_index + 3 + i
            value = math.degrees(driven['euler_rotation'][i])
            if abs(value) > 1e-6:
                delta_map[output_idx] = value
        
        # Scale
        for i in range(3):
            output_idx = matrix_index + 6 + i
            value = driven['scale'][i]
            if abs(value - 1.0) > 1e-6:  # Only store if not 1.0
                delta_map[output_idx] = value
    
    # Merge new output indices
    for out_idx in delta_map.keys():
        if out_idx not in output_indices:
            output_indices.append(out_idx)
    
    output_indices.sort()
    
    # Rebuild values matrix (row-major)
    row_count = len(output_indices)
    col_count = len(input_indices)
    values = [0.0] * (row_count * col_count)
    
    # Copy existing values for other columns
    if existing_values and len(existing_values) > 0:
        old_col_count = len(existing_values) // len(output_indices) if output_indices else 0
        for row in range(min(row_count, len(output_indices))):
            for col in range(min(col_count, old_col_count)):
                if col < len(input_indices):
                    old_idx = row * old_col_count + col
                    new_idx = row * col_count + col
                    if old_idx < len(existing_values):
                        values[new_idx] = existing_values[old_idx]
    
    # Set new values for this control's column
    for row, out_idx in enumerate(output_indices):
        if out_idx in delta_map:
            matrix_idx = row * col_count + control_column
            values[matrix_idx] = delta_map[out_idx]
    
    # Extract unique joint indices
    joint_indices = sorted(set(idx // 9 for idx in output_indices))
    
    # Set LODs (all LODs get all rows by default)
    if lod_count is None:
        lod_count: int = reader.getLODCount()
    lods = [row_count] * lod_count
    
    # Update the joint group
    writer.setJointGroupInputIndices(joint_group_index, input_indices)
    writer.setJointGroupOutputIndices(joint_group_index, output_indices)
    writer.setJointGroupValues(joint_group_index, values)
    writer.setJointGroupJointIndices(joint_group_index, joint_indices)
    writer.setJointGroupLODs(joint_group_index, lods)


def set_rbf_driven_data(
    reader,
    writer,
    pose_index: int,
    driven_data: list[dict],
    lod_count: int | None = None
) -> None:
    """
    Set joint transformations driven by an RBF pose.
    
    Args:
        writer: DNA BinaryStreamWriter instance
        pose_index: Index of the RBF pose
        driven_data_list: List of RBFDrivenData with transformation deltas
        output_control_index: The control index this pose drives
        lod_count: Number of LODs (if None, uses writer.getLODCount())
    """
    
    if not driven_data:
        return
    
    # Get the output controls this pose drives
    if reader is not None:
        # Read from existing DNA
        output_control_indices = list(reader.getRBFPoseOutputControlIndices(pose_index))
        output_control_weights = list(reader.getRBFPoseOutputControlWeights(pose_index))
    else:
        # Need to get from writer or specify manually
        # For new poses, you'll need to call setRBFPoseOutputControlIndices first
        raise ValueError(
            "Either provide a reader to get existing control mappings, "
            "or call setRBFPoseOutputControlIndices before setting driven data"
        )
    
    # Update joint group for each output control
    for control_idx, weight in zip(output_control_indices, output_control_weights):
        # Scale the deltas by the control weight
        scaled_driven_data = _scale_driven_data(driven_data, weight)
        
        # Update the joint group for this control
        joint_group_idx = _get_joint_group_index(reader, control_idx)
        
        _update_joint_group_with_deltas(
            reader,
            writer,
            joint_group_idx,
            control_idx,
            scaled_driven_data,
            lod_count
        )



# def set_rbf_driver_data(reader, writer, solver_index: int, driver_data: list[dict]):
#     rbf_raw_control_indices = []
#     rbf_raw_control_values = []

#     for driver in driver_data:
#         for raw_control_index in driver['raw_control_indices']:
#             bone_name, axis = reader.getRawControlName(raw_control_index).split('.')

#             rbf_raw_control_indices.append(raw_control_index)
#             quaternion_rotation = driver['quaternion_rotation']

#             if axis.lower() == 'qx':
#                 rbf_raw_control_values.append(quaternion_rotation[1])
#             elif axis.lower() == 'qy':
#                 rbf_raw_control_values.append(quaternion_rotation[2])
#             elif axis.lower() == 'qz':
#                 rbf_raw_control_values.append(quaternion_rotation[3])
#             elif axis.lower() == 'qw':
#                 rbf_raw_control_values.append(quaternion_rotation[0])


#     writer.setRBFSolverRawControlIndices(
#         solverIndex=solver_index, 
#         rawControlIndices=rbf_raw_control_indices
#     )
#     writer.setRBFSolverRawControlValues(
#         solverIndex=solver_index, 
#         values=rbf_raw_control_values
#     )


def _build_raw_control_indices_from_driver_data(
    reader,
    driver: dict,
    distance_method
) -> list[int]:
    """
    Build the list of raw control indices from driver data.
    
    For quaternion-based methods, we need 4 controls per driving joint (x, y, z, w).
    For Euclidean, we need 1 control per input.
    """
    raw_control_indices = []
    
    # Find the raw controls for this joint
    # Assuming the joint has associated raw controls
    joint_name = reader.getJointName(driver['joint_index'])
    
    # Search for raw controls matching this joint
    raw_control_count = reader.getRawControlCount()
    
    if distance_method in ['Quaternion', 'SwingAngle', 'TwistAngle']:
        # Need 4 controls: x, y, z, w
        suffixes = ['.qx', '.qy', '.qz', '.qw']
        for suffix in suffixes:
            for rc_idx in range(raw_control_count):
                rc_name = reader.getRawControlName(rc_idx)
                if rc_name == f"{joint_name}{suffix}":
                    raw_control_indices.append(rc_idx)
                    break
    else:
        # Euclidean - single scalar value per input
        for rc_idx in range(raw_control_count):
            rc_name = reader.getRawControlName(rc_idx)
            if rc_name.startswith(joint_name):
                raw_control_indices.append(rc_idx)
                # For Euclidean, might want just one or specific controls
    
    return raw_control_indices


def _extract_values_for_pose(
    reader,
    raw_control_indices: list[int],
    driver: dict,
    distance_method
) -> list[float]:
    """
    Extract the values for raw controls based on the driver data.
    
    Returns values in the same order as raw_control_indices.
    """
    values = []
    
    # Build a map of control name suffix to value
    quat = driver['quaternion_rotation']  # [w, x, y, z]
    
    # Determine quaternion format (check if w is first or last)
    # Standard mathematical notation: [w, x, y, z]
    # Some systems use: [x, y, z, w]
    # Assume [w, x, y, z] format based on your code
    value_map = {
        'qw': quat[0],
        'qx': quat[1],
        'qy': quat[2],
        'qz': quat[3]
    }
    
    # Map each raw control index to its value
    for rc_idx in raw_control_indices:
        rc_name = reader.getRawControlName(rc_idx)
        
        # Extract the suffix (e.g., "head.qx" -> "qx")
        if '.' in rc_name:
            suffix = rc_name.split('.')[-1].lower()
            value = value_map.get(suffix, 0.0)
            values.append(value)
        else:
            # Euclidean or other - might need different logic
            values.append(0.0)
    
    return values


def set_rbf_driver_simple(
    reader,
    writer,
    solver_index: int,
    pose_index: int,
    joint_name: str,
    quaternion: list[float]  # [w, x, y, z]
) -> None:
    """
    Simplified version for setting a single pose's driver values.
    
    This assumes quaternion-based distance method and that the solver
    and poses are already configured.
    """
    
    # Get existing data
    raw_control_indices = list(reader.getRBFSolverRawControlIndices(solver_index))
    pose_indices = list(reader.getRBFSolverPoseIndices(solver_index))
    existing_values = list(reader.getRBFSolverRawControlValues(solver_index))
    
    if pose_index not in pose_indices:
        raise ValueError(f"Pose {pose_index} is not part of solver {solver_index}")
    
    num_raw_controls = len(raw_control_indices)
    pose_position = pose_indices.index(pose_index)
    
    # Calculate where this pose's values start in the array
    start_idx = pose_position * num_raw_controls
    
    # Build the quaternion value map
    quat_map = {
        'qw': quaternion[0],
        'qx': quaternion[1],
        'qy': quaternion[2],
        'qz': quaternion[3]
    }
    
    # Update only this pose's values
    new_values = existing_values.copy() if existing_values else [0.0] * (num_raw_controls * len(pose_indices))
    
    for i, rc_idx in enumerate(raw_control_indices):
        rc_name = reader.getRawControlName(rc_idx)
        
        # Check if this control belongs to our joint
        if rc_name.startswith(joint_name):
            suffix = rc_name.split('.')[-1].lower()
            value = quat_map.get(suffix, 0.0)
            new_values[start_idx + i] = value
    
    # Write back all values
    writer.setRBFSolverRawControlValues(solver_index, new_values)


def set_rbf_driver_data(
    reader,
    writer, 
    solver_index: int,
    driver_data: list[dict],
    distance_method: str
) -> None:
    """
    Set the driver (input) values for all poses in an RBF solver.
    
    Args:
        reader: DNA reader for getting existing metadata
        writer: DNA writer for modifying the data
        solver_index: Index of the RBF solver to modify
        driver_data_list: List of driver data, one per pose
        distance_method: Optional override for distance method
                        (Quaternion, SwingAngle, TwistAngle, Euclidean)
    """
    
    if not driver_data:
        return
    
    # Get the raw control indices (should be same for all poses in solver)
    existing_raw_controls = list(reader.getRBFSolverRawControlIndices(solver_index))
    
    if not existing_raw_controls:
        # Need to determine raw controls from the driver data
        raw_control_indices = _build_raw_control_indices_from_driver_data(
            reader,
            driver_data[0],  # Use first pose to determine structure
            distance_method
        )
        writer.setRBFSolverRawControlIndices(solver_index, raw_control_indices)
    else:
        raw_control_indices = existing_raw_controls
    
    # Get pose indices for this solver
    pose_indices = list(reader.getRBFSolverPoseIndices(solver_index))
    
    # Build the values array: [pose0_values..., pose1_values..., ...]
    num_raw_controls = len(raw_control_indices)
    num_poses = len(pose_indices)
    
    # Create a map from pose_index to driver_data
    driver_map = {d['pose_index']: d for d in driver_data}
    
    # Build values array in the correct order
    values = []
    for pose_idx in pose_indices:
        if pose_idx in driver_map:
            driver = driver_map[pose_idx]
            pose_values = _extract_values_for_pose(
                reader,
                raw_control_indices,
                driver,
                distance_method
            )
            values.extend(pose_values)
        else:
            # Pose not in our driver data, keep existing or use zeros
            existing_values = list(reader.getRBFSolverRawControlValues(solver_index))
            if existing_values:
                # Extract existing values for this pose
                start_idx = pose_indices.index(pose_idx) * num_raw_controls
                end_idx = start_idx + num_raw_controls
                values.extend(existing_values[start_idx:end_idx])
            else:
                # Default to identity quaternions or zeros
                values.extend([0.0] * num_raw_controls)
    
    # Set all values at once
    writer.setRBFSolverRawControlValues(solver_index, values)


def set_rbf_pose_data(
        reader, 
        writer, 
        solver_index: int, 
        poses: list[dict],
        distance_method: str
    ):
    for pose in poses:
        pose_index = pose['pose_index']
        writer.setRBFPoseName(pose_index, pose['name'])
        writer.setRBFPoseScale(pose_index, pose['scale_factor'])
        set_rbf_driven_data(
            reader, 
            writer, 
            pose_index=pose_index, 
            driven_data=pose['driven']
        )
        # set_rbf_driver_data(
        #     reader, 
        #     writer, 
        #     solver_index=solver_index, 
        #     driver_data=pose['drivers'],
        #     distance_method=distance_method
        # )


def commit_rbf_data_to_dna(reader, writer, data: list[dict]):
    import riglogic
    for item in data:
        property_group = item.get('__property_group__', '')
        if property_group == 'RBFSolverData':
            writer.setRBFSolverName(item['solver_index'], item['name'])
            writer.setRBFSolverType(item['solver_index'], getattr(riglogic.RBFSolverType, item['mode']))
            writer.setRBFSolverRadius(item['solver_index'], item['radius'])
            writer.setRBFSolverWeightThreshold(item['solver_index'], item['weight_threshold'])
            writer.setRBFSolverDistanceMethod(item['solver_index'], getattr(riglogic.RBFDistanceMethod, item['distance_method']))
            writer.setRBFSolverNormalizeMethod(item['solver_index'], getattr(riglogic.RBFNormalizeMethod, item['normalize_method']))
            writer.setRBFSolverFunctionType(item['solver_index'], getattr(riglogic.RBFFunctionType, item['function_type']))
            writer.setRBFSolverTwistAxis(item['solver_index'], getattr(riglogic.TwistAxis, item['twist_axis']))
            writer.setRBFSolverAutomaticRadius(item['solver_index'], riglogic.AutomaticRadius.On if item['automatic_radius'] else riglogic.AutomaticRadius.Off)
            set_rbf_pose_data(
                reader,
                writer,
                solver_index=item['solver_index'],
                poses=item['poses'],
                distance_method=item['distance_method']
            )
