import os
import sys
import bpy
import bpy.utils.previews
import logging

from . import operators, properties, utilities, manual_map
from .ui import menus, importer, view_3d, addon_preferences, callbacks
from .resources.unreal import meta_human_dna_utilities

# ensure these modules are available to the send2ue extension
sys.modules['meta_human_dna_utilities'] = meta_human_dna_utilities # namespaced for unreal environment
sys.modules['meta_human_dna.ui.callbacks'] = callbacks
sys.modules['meta_human_dna.utilities'] = utilities

logger = logging.getLogger(__name__)

bl_info = {
    "name": "Meta-Human DNA",
    "author": "Poly Hammer",
    "version": (0, 4, 0),
    "blender": (4, 2, 0),
    "location": "File > Import > Metahuman DNA",
    "description": "Imports MetaHuman head and body components from a their DNA files, lets you customize them, then send them back to MetaHuman Creator.",
    "warning": "",
    "wiki_url": "https://docs.polyhammer.com/meta-human-dna-addon/",
    "category": "Rigging",
}

classes = [
    operators.ImportMetahumanDna,
    operators.DNA_FH_import_dna,
    operators.ConvertSelectedToDna,
    operators.ImportAnimation,
    operators.BakeAnimation,
    operators.ImportShapeKeys,
    operators.TestSentry,
    operators.OpenBuildToolDocumentation,
    operators.OpenMetricsCollectionAgreement,
    operators.MetricsCollectionConsent,
    operators.MirrorSelectedBones,
    operators.SyncWithBodyBonesInBlueprint,
    operators.ShrinkWrapVertexGroup,
    # operators.AutoFitSelectedBones,
    operators.RevertBoneTransformsToDna,
    operators.ForceEvaluate,
    operators.SendToMetaHumanCreator,
    operators.SendToUnreal,
    operators.ExportSelectedComponent,
    operators.GenerateMaterial,
    operators.SculptThisShapeKey,
    operators.EditThisShapeKey,
    operators.ReImportThisShapeKey,
    operators.RefreshMaterialSlotNames,
    operators.RevertMaterialSlotValues,
    operators.DuplicateRigLogicInstance,
    operators.AddRigLogicTextureNode,
    operators.MetaHumanDnaReportError,
    operators.UILIST_RIG_LOGIC_OT_entry_move,
    operators.UILIST_RIG_LOGIC_OT_entry_add,
    operators.UILIST_RIG_LOGIC_OT_entry_remove,
    operators.UILIST_ADDON_PREFERENCES_OT_extra_dna_entry_add,
    operators.UILIST_ADDON_PREFERENCES_OT_extra_dna_entry_remove,
    importer.META_HUMAN_DNA_FILE_DATA_PT_panel,
    importer.META_HUMAN_DNA_LODS_PT_panel,
    importer.META_HUMAN_DNA_EXTRAS_PT_panel,
    importer.META_HUMAN_DNA_FILE_INFO_PT_panel,
    view_3d.META_HUMAN_DNA_PT_face_board,
    view_3d.META_HUMAN_DNA_PT_view_options,
    view_3d.META_HUMAN_DNA_PT_rig_logic,
    view_3d.META_HUMAN_DNA_PT_shape_keys,
    view_3d.META_HUMAN_DNA_UL_shape_keys,
    view_3d.META_HUMAN_DNA_PT_utilities,
    view_3d.META_HUMAN_DNA_PT_mesh_utilities_sub_panel,
    view_3d.META_HUMAN_DNA_PT_armature_utilities_sub_panel,
    # view_3d.META_HUMAN_DNA_PT_materials_utilities_sub_panel,
    view_3d.META_HUMAN_DNA_PT_utilities_sub_panel,
    view_3d.META_HUMAN_DNA_UL_output_items,
    view_3d.META_HUMAN_DNA_UL_rig_logic_instances,
    view_3d.META_HUMAN_DNA_UL_material_slot_to_instance_mapping,
    view_3d.META_HUMAN_DNA_PT_output_panel,
    # view_3d.META_HUMAN_DNA_PT_send2ue_settings_sub_panel,
    view_3d.META_HUMAN_DNA_PT_buttons_sub_panel
]

app_handlers = {
    'load_pre': bpy.app.handlers.persistent(utilities.teardown_scene),
    'load_post': bpy.app.handlers.persistent(utilities.setup_scene),
    'undo_pre': bpy.app.handlers.persistent(utilities.pre_undo),
    'undo_post': bpy.app.handlers.persistent(utilities.post_undo),
    'render_init': bpy.app.handlers.persistent(utilities.pre_render),
    'render_complete': bpy.app.handlers.persistent(utilities.post_render),
    'render_cancel': bpy.app.handlers.persistent(utilities.post_render)
}

def register():
    """
    Registers the addon classes when the addon is enabled.
    """
    if os.environ.get('META_HUMAN_DNA_DEV'):
        logging.basicConfig(level=logging.DEBUG)
        
    try:
        # register the manual map
        bpy.utils.register_manual_map(manual_map.manual_map)

        # register the properties
        addon_preferences.register()
        properties.register()

        # register the classes
        for cls in classes:
            bpy.utils.register_class(cls)

        # add menu items
        menus.add_dna_import_menu()
        menus.add_rig_logic_texture_node_menu()

    except Exception as error:
        logger.error(error)

    utilities.init_sentry()

    # add event handlers
    bpy.app.handlers.load_pre.append(app_handlers['load_pre'])
    bpy.app.handlers.load_post.append(app_handlers['load_post'])
    bpy.app.handlers.undo_pre.append(app_handlers['undo_pre'])
    bpy.app.handlers.undo_post.append(app_handlers['undo_post'])
    bpy.app.handlers.render_init.append(app_handlers['render_init'])
    bpy.app.handlers.render_complete.append(app_handlers['render_complete'])
    bpy.app.handlers.render_cancel.append(app_handlers['render_cancel'])


def unregister():
    """
    Un-registers the addon classes when the addon is disabled.
    """
    utilities.teardown_scene()

    # remove event handlers
    if app_handlers['undo_pre'] in bpy.app.handlers.undo_pre:
        bpy.app.handlers.undo_pre.remove(app_handlers['undo_pre'])
    if app_handlers['undo_post'] in bpy.app.handlers.undo_post:
        bpy.app.handlers.undo_post.remove(app_handlers['undo_post'])
    if app_handlers['load_pre'] in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(app_handlers['load_pre'])
    if app_handlers['load_post'] in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(app_handlers['load_post'])
    if app_handlers['render_init'] in bpy.app.handlers.render_init:
        bpy.app.handlers.render_init.remove(app_handlers['render_init'])
    if app_handlers['render_complete'] in bpy.app.handlers.render_complete:
        bpy.app.handlers.render_complete.remove(app_handlers['render_complete'])
    if app_handlers['render_cancel'] in bpy.app.handlers.render_cancel:
        bpy.app.handlers.render_cancel.remove(app_handlers['render_cancel'])

    try:
        # unregister the manual map
        bpy.utils.unregister_manual_map(manual_map.manual_map)

        # remove menu items
        menus.remove_dna_import_menu()
        menus.remove_rig_logic_texture_node_menu()

        # unregister the classes
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)

        # unregister the properties
        properties.unregister()
        addon_preferences.unregister()
    except Exception as error:
        logger.error(error)
