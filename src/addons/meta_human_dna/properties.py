import bpy
import logging
from .ui import callbacks
from .constants import ToolInfo, NUMBER_OF_HEAD_LODS
from .rig_logic import (
    RigLogicInstance, 
    ShapeKeyData, 
    OutputData,
    MaterialSlotToInstance
)

logger = logging.getLogger(__name__)

preview_collections = {}


def get_dna_import_property_group_base_class():
    """
    Dynamically generates the number of LOD import properties
    """
    _properties = {}

    for i in range(NUMBER_OF_HEAD_LODS):

        # add in import options for lods
        _properties[f'import_lod{i}'] = bpy.props.BoolProperty(
            default=i==0,
            name=f'LOD{i}',
            description=f'Whether to import LOD{i} for the face mesh'
        )

    return type(
        'DnaImportPropertiesBase',
        (object,),
        {
            '__annotations__': _properties,
        }
    )

class ExtraDnaFolder(bpy.types.PropertyGroup):
    folder_path: bpy.props.StringProperty(
        default='',
        description='The folder location of the extension repo.',
        subtype='DIR_PATH'
    ) # type: ignore

class MetahumanDnaAddonProperties:
    """
    This class holds the properties for the addon.
    """
    metrics_collection: bpy.props.BoolProperty(
        name="Collect Metrics",
        default=False,
        description="This will send anonymous usage data to Poly Hammer to help improve the addon and help catch bugs"
    ) # type: ignore

    next_metrics_consent_timestamp: bpy.props.FloatProperty(default=0.0) # type: ignore
    extra_dna_folder_list: bpy.props.CollectionProperty(type=ExtraDnaFolder) # type: ignore
    extra_dna_folder_list_active_index: bpy.props.IntProperty() # type: ignore



class MetahumanDnaImportProperties(get_dna_import_property_group_base_class()):
    import_mesh: bpy.props.BoolProperty(
        default=True,
        name='Mesh',
        description='Whether to import the head meshes'
    )  # type: ignore
    import_normals: bpy.props.BoolProperty(
        default=False,
        name='Normals',
        description='Whether to import custom split normals on the head meshes'
    )  # type: ignore
    import_bones: bpy.props.BoolProperty(
        default=True,
        name='Bones',
        description='Whether to import the bones for the head'
    ) # type: ignore
    import_shape_keys: bpy.props.BoolProperty(
        default=False,
        name='Shape Keys',
        description='Whether to import the shapes key for the head. You can also import these later'
    ) # type: ignore
    import_vertex_groups: bpy.props.BoolProperty(
        default=True,
        name='Vertex Groups',
        description='Whether to import the vertex groups that skin the bones to the head mesh'
    ) # type: ignore
    import_vertex_colors: bpy.props.BoolProperty(
        default=True,
        name='Vertex Colors',
        description='Whether to import the vertex colors for the head mesh. Note this will first look for a vertex_colors.json in the same folder as the .dna file. Otherwise it will use the default vertex_colors.json in the addon resources'
    ) # type: ignore
    import_materials: bpy.props.BoolProperty(
        default=True,
        name='Materials',
        description='Whether to import the materials for the head mesh'
    ) # type: ignore
    import_face_board: bpy.props.BoolProperty(
        default=True,
        name='Face Board',
        description='Whether to import the face board that drives the rig logic'
    ) # type: ignore
    reuse_face_board: bpy.props.BoolProperty(
        default=False,
        name='Reuse Face Board',
        description='Whether to reuse or import a unique face board that drives the rig logic instead of a shared one. This is useful if you want to have multiple rigs in the same scene that drive different face meshes',
    ) # type: ignore
    include_body: bpy.props.BoolProperty(
        default=False,
        name='Include Body',
        description='If true, this will try to find a body.dna file in the same folder as this .dna file. If the body.dna file is found, it will be imported as well',
    ) # type: ignore
    alternate_maps_folder: bpy.props.StringProperty(
        default='',
        name='Maps Folder',
        description='This can be set to an alternate folder location for the face wrinkle maps. If no folder is set, the importer looks for a "Maps" folder next to the .dna file',
    ) # type: ignore


class MetahumanWindowMangerProperties(bpy.types.PropertyGroup, MetahumanDnaImportProperties):
    """
    Defines a property group that stores constants in the window manager context.
    """
    assets = {}
    errors = {}
    dna_info = {
        '_previous_file_path': None,
        '_dna_reader': None
    }

    error_message: bpy.props.StringProperty(default='') # type: ignore
    progress: bpy.props.FloatProperty(default=1.0) # type: ignore
    progress_description: bpy.props.StringProperty(default='') # type: ignore
    progress_mesh_name: bpy.props.StringProperty(default='') # type: ignore
    evaluate_dependency_graph: bpy.props.BoolProperty(default=True) # type: ignore

    face_pose_previews: bpy.props.EnumProperty( # type: ignore
        name="Face Poses",
        items=callbacks.get_face_pose_previews_items,
        update=callbacks.update_face_pose
    )
    current_component_type: bpy.props.EnumProperty(
        name="Component Type",
        default='head',
        items=[
            ('head', 'Head', 'Set the head as the current component for utility operations'),
            ('body', 'Body', 'Set the body as the current component for utility operations'),
        ],
        description="Choose what component to use when performing utility operations. This will determine what data is shown in the selection dropdowns as well",
    ) # type: ignore
    base_dna: bpy.props.EnumProperty(
        name="Base DNA",
        items=callbacks.get_base_dna_folder,
        description="Choose the base DNA folder that will be used when converting the selected.",
        options={'ANIMATABLE'}
    ) # type: ignore
    new_folder: bpy.props.StringProperty(
        name="Output Folder",
        default="",
        subtype='DIR_PATH',
        options={'PATH_SUPPORTS_BLEND_RELATIVE'}
    ) # type: ignore
    maps_folder: bpy.props.StringProperty(
        default='',
        name='Maps Folder',
        description='Optionally, this can be set to a folder location for the face wrinkle maps. Textures following the same naming convention as the metahuman source files will be found and set on the materials automatically.',
        subtype='DIR_PATH',
        options={'PATH_SUPPORTS_BLEND_RELATIVE'}
    ) # type: ignore

class MetahumanSceneProperties(bpy.types.PropertyGroup):
    """
    Defines a property group that lives in the scene.
    """
    # --------------------- read/write properties ------------------
    context = {}

    # --------------------- user interface properties ------------------
    highlight_matching_active_bone: bpy.props.BoolProperty(
        name="Highlight Matching Active Bone",
        description="Highlights bones that match the name of the active pose bone across all rig logic instances",
        default=False,
        set=callbacks.set_highlight_matching_active_bone,
        get=callbacks.get_highlight_matching_active_bone
    ) # type: ignore
    push_along_normal_distance: bpy.props.FloatProperty(
        name="Distance Along Normal",
        description="The distance to push the selected bone along the head mesh vertex normals",
        default=0.001,
        min=0.0,
        step=1,
        precision=5
    ) # type: ignore
    # --------------------- riglogic properties ------------------
    rig_logic_instance_list: bpy.props.CollectionProperty(type=RigLogicInstance) # type: ignore
    rig_logic_instance_list_active_index: bpy.props.IntProperty(
        update=callbacks.update_head_output_items
    ) # type: ignore


def register():
    """
    Registers the property group class and adds it to the window manager context when the
    addon is enabled.
    """
    # register the list data classes first, since the scene property groups depends on them
    bpy.utils.register_class(MaterialSlotToInstance)
    bpy.utils.register_class(OutputData)
    bpy.utils.register_class(ShapeKeyData)
    bpy.utils.register_class(RigLogicInstance)

    try:
        bpy.utils.register_class(MetahumanSceneProperties)
        bpy.types.Scene.meta_human_dna = bpy.props.PointerProperty(type=MetahumanSceneProperties) # type: ignore
    except ValueError as error:
        logger.debug(error)

    try:
        bpy.utils.register_class(MetahumanWindowMangerProperties)
        bpy.types.WindowManager.meta_human_dna = bpy.props.PointerProperty(type=MetahumanWindowMangerProperties) # type: ignore
    except ValueError as error:
        logger.debug(error)

    # add the pose previews collection
    face_pose_previews_collection = bpy.utils.previews.new()
    face_pose_previews_collection.face_pose_previews_root_folder = "" # type: ignore
    face_pose_previews_collection.face_pose_previews = () # type: ignore
    preview_collections["face_poses"] = face_pose_previews_collection


def unregister():
    """
    Un-registers the property group class and deletes it from the window manager context when the
    addon is disabled.
    """
    # remove the pose previews collections
    for preview_collection in preview_collections.values():
        bpy.utils.previews.remove(preview_collection)
    preview_collections.clear()

    window_manager_property_class = bpy.types.PropertyGroup.bl_rna_get_subclass_py(MetahumanWindowMangerProperties.__name__)
    if window_manager_property_class:
        bpy.utils.unregister_class(window_manager_property_class)

    scene_property_class = bpy.types.PropertyGroup.bl_rna_get_subclass_py(MetahumanSceneProperties.__name__)
    if scene_property_class:
        bpy.utils.unregister_class(scene_property_class)

    # unregister the list data classes
    bpy.utils.unregister_class(RigLogicInstance)
    bpy.utils.unregister_class(ShapeKeyData)
    bpy.utils.unregister_class(OutputData)
    bpy.utils.unregister_class(MaterialSlotToInstance)

    if hasattr(bpy.types.WindowManager, ToolInfo.NAME):
        del bpy.types.WindowManager.meta_human_dna # type: ignore

    if hasattr(bpy.types.Scene, ToolInfo.NAME):
        del bpy.types.Scene.meta_human_dna # type: ignore
