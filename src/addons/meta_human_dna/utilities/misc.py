import os
import re
import bpy
import sys
import math
import logging
import addon_utils
from pathlib import Path
from mathutils import Vector
from typing import TYPE_CHECKING, Callable
from ..constants import MATERIALS_FILE_PATH, TEXTURE_LOGIC_NODE_LABEL
from ..rig_logic import start_listening
from ..constants import (
    SENTRY_DSN,
    SEND2UE_EXTENSION,
    PACKAGES_FOLDER,
    NUMBER_OF_FACE_LODS,
    INVALID_NAME_CHARACTERS_REGEX,
    DEFAULT_UV_TOLERANCE,
    ToolInfo
)
if TYPE_CHECKING:
    from ..face import MetahumanFace
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
    link_send2ue_extension()

def teardown_scene(*args):
    scene_properties = getattr(bpy.context.scene, ToolInfo.NAME, object) # type: ignore
    
    for instance in getattr(scene_properties, 'rig_logic_instance_list', []):
        instance.destroy()
    else:
        logging.info('De-allocated Rig Logic instances...')

def pre_undo(*args):
    bpy.context.window_manager.meta_human_dna.evaluate_dependency_graph = False # type: ignore
    for instance in bpy.context.scene.meta_human_dna.rig_logic_instance_list: # type: ignore
        instance.destroy()

def post_undo(*args):
    bpy.context.window_manager.meta_human_dna.evaluate_dependency_graph = True # type: ignore
    for instance in bpy.context.scene.meta_human_dna.rig_logic_instance_list: # type: ignore
        instance.evaluate()

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

def get_face(name: str) -> 'MetahumanFace | None':
    # avoid circular import
    from ..face import MetahumanFace
    
    properties = bpy.context.scene.meta_human_dna # type: ignore
    for instance in properties.rig_logic_instance_list:
        if instance.name == name:
            return MetahumanFace(rig_logic_instance=instance)
        
    logger.error(f'No existing face "{name}" was found')

def get_active_face() -> 'MetahumanFace | None':
    """
    Gets the active face object.
    """
    properties = bpy.context.scene.meta_human_dna # type: ignore
    if len(properties.rig_logic_instance_list) > 0:
        index = properties.rig_logic_instance_list_active_index
        instance = properties.rig_logic_instance_list[index]
        return get_face(instance.name)
    
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
    material = instance.material

    # clear data dictionary from the old instance so underlying data can be garbage collected
    instance.data.clear()
    # find the index of the old instance and remove it
    index = bpy.context.scene.meta_human_dna.rig_logic_instance_list.find(instance.name) # type: ignore
    bpy.context.scene.meta_human_dna.rig_logic_instance_list.remove(index) # type: ignore

    # create a new instance with the copied data
    new_instance = bpy.context.scene.meta_human_dna.rig_logic_instance_list.add() # type: ignore
    new_instance.name = new_name
    new_instance.dna_file_path = str(new_dna_file_path)
    new_instance.face_board = face_board
    new_instance.head_mesh = head_mesh
    new_instance.head_rig = head_rig
    new_instance.material = material
    
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
    if instance.head_mesh:
        instance.head_mesh.name = instance.head_mesh.name.replace(old_name, new_name)
    if instance.head_rig:
        instance.head_rig.name = instance.head_rig.name.replace(old_name, new_name)
    if instance.material:
        instance.material.name = instance.material.name.replace(old_name, new_name)

    for item in instance.output_item_list:
        if item.scene_object:
            item.scene_object.name = item.scene_object.name.replace(old_name, new_name)
        if item.image_object:
            item.image_object.name = item.image_object.name.replace(old_name, new_name)

    instance.unreal_content_folder = instance.unreal_content_folder.replace(old_name, new_name)
    instance.unreal_blueprint_asset_path = instance.unreal_blueprint_asset_path.replace(old_name, new_name)

    # rename the face LOD collections
    for index in range(NUMBER_OF_FACE_LODS):
        collection = bpy.data.collections.get(f'{old_name}_lod{index}')
        if collection:
            collection.name = collection.name.replace(old_name, new_name)

def rename_as_lod0_meshes(mesh_objects: list[bpy.types.Object]):
    from ..ui.callbacks import get_active_rig_logic, update_output_items
    instance = get_active_rig_logic()
    if instance:
        for mesh_object in mesh_objects:
            mesh_object.name = re.sub(INVALID_NAME_CHARACTERS_REGEX, "_",  mesh_object.name.strip())
            if not mesh_object.name.startswith(instance.name):
                mesh_object.name = f'{instance.name}_{mesh_object.name}'
            if not mesh_object.name.endswith('_lod0_mesh'):
                mesh_object.name = f'{mesh_object.name}_lod0_mesh'

        # re-populate the output items
        instance.output_item_list.clear()
        update_output_items(None, bpy.context)

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


def import_texture_logic_node() -> bpy.types.NodeTree | None:
    sep = '\\'
    if sys.platform != 'win32':
        sep = '/'

    node_group = bpy.data.node_groups.get(TEXTURE_LOGIC_NODE_LABEL)
    if not node_group:
        directory_path = f'{MATERIALS_FILE_PATH}{sep}NodeTree{sep}'
        file_path = f'{MATERIALS_FILE_PATH}{sep}NodeTree{sep}{TEXTURE_LOGIC_NODE_LABEL}'
        bpy.ops.wm.append(
            filepath=file_path,
            filename=TEXTURE_LOGIC_NODE_LABEL,
            directory=directory_path
        )
        return bpy.data.node_groups.get(TEXTURE_LOGIC_NODE_LABEL)
    return node_group


def dependencies_are_valid() -> bool:
    for module_name in ['dna', 'dnacalib', 'riglogic', 'meta_human_dna_core']:
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