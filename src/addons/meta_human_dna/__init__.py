import os
import sys
import bpy
import bpy.utils.previews
import logging

from . import operators, properties, rig_instance, utilities, manual_map
from .ui import menus, importer, view_3d, viewport_overlay, addon_preferences, callbacks
from .backup_manager import ui as backup_manager_ui
from .backup_manager import operators as backup_manager_operators

logger = logging.getLogger(__name__)

bl_info = {
    "name": "Meta-Human DNA",
    "author": "Poly Hammer",
    "version": (0, 5, 4),
    "blender": (4, 5, 0),
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
    operators.AppendOrLinkMetaHuman,
    operators.ImportFaceBoardAnimation,
    operators.ImportComponentAnimation,
    operators.BakeFaceBoardAnimation,
    operators.BakeComponentAnimation,
    operators.ImportShapeKeys,
    operators.TestSentry,
    operators.OpenBuildToolDocumentation,
    operators.OpenMetricsCollectionAgreement,
    operators.MetricsCollectionConsent,
    operators.MirrorSelectedBones,
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
    operators.AddRBFSolver,
    operators.RemoveRBFSolver,
    operators.EvaluateRBFSolvers,
    operators.EditRBFSolver,
    operators.RevertRBFSolver,
    operators.CommitRBFSolverChanges,
    operators.AddRBFPose,
    operators.DuplicateRBFPose,
    operators.RemoveRBFPose,
    operators.UpdateRBFPose,
    operators.AddRBFDriver,
    operators.RemoveRBFDriver,
    operators.AddRBFDriven,
    operators.RemoveRBFDriven,
    operators.SelectAllRBFDriven,
    operators.DuplicateRigInstance,
    operators.AddRigLogicTextureNode,
    operators.MetaHumanDnaReportError,
    operators.UILIST_RIG_INSTANCE_OT_entry_move,
    operators.UILIST_RIG_INSTANCE_OT_entry_add,
    operators.UILIST_RIG_INSTANCE_OT_entry_remove,
    operators.UILIST_ADDON_PREFERENCES_OT_extra_dna_entry_add,
    operators.UILIST_ADDON_PREFERENCES_OT_extra_dna_entry_remove,
    importer.META_HUMAN_DNA_FILE_DATA_PT_panel,
    importer.META_HUMAN_DNA_LODS_PT_panel,
    importer.META_HUMAN_DNA_EXTRAS_PT_panel,
    importer.META_HUMAN_DNA_FILE_INFO_PT_panel,
    view_3d.META_HUMAN_DNA_PT_face_board,
    view_3d.META_HUMAN_DNA_PT_view_options,
    view_3d.META_HUMAN_DNA_PT_rig_instance,
    view_3d.META_HUMAN_DNA_PT_rig_instance_head_sub_panel,
    view_3d.META_HUMAN_DNA_PT_rig_instance_body_sub_panel,
    view_3d.META_HUMAN_DNA_PT_rig_instance_footer_sub_panel,
    view_3d.META_HUMAN_DNA_PT_shape_keys,
    view_3d.META_HUMAN_DNA_UL_shape_keys,
    view_3d.META_HUMAN_DNA_PT_pose_editor,
    view_3d.META_HUMAN_DNA_PT_pose_editor_solver_settings_sub_panel,
    view_3d.META_HUMAN_DNA_PT_pose_editor_poses_sub_panel,
    view_3d.META_HUMAN_DNA_PT_pose_editor_drivers_sub_panel,
    view_3d.META_HUMAN_DNA_PT_pose_editor_driven_sub_panel,
    view_3d.META_HUMAN_DNA_PT_pose_editor_footer_sub_panel,
    view_3d.META_HUMAN_DNA_UL_rbf_solvers,
    view_3d.META_HUMAN_DNA_UL_rbf_poses,
    view_3d.META_HUMAN_DNA_UL_rbf_drivers,
    view_3d.META_HUMAN_DNA_UL_rbf_driven,
    view_3d.META_HUMAN_DNA_PT_utilities,
    view_3d.META_HUMAN_DNA_PT_mesh_utilities_sub_panel,
    view_3d.META_HUMAN_DNA_PT_armature_utilities_sub_panel,
    view_3d.META_HUMAN_DNA_PT_animation_utilities_sub_panel,
    # view_3d.META_HUMAN_DNA_PT_materials_utilities_sub_panel,
    view_3d.META_HUMAN_DNA_PT_utilities_sub_panel,
    view_3d.META_HUMAN_DNA_UL_output_items,
    view_3d.META_HUMAN_DNA_UL_rig_instances,
    view_3d.META_HUMAN_DNA_UL_material_slot_to_instance_mapping,
    view_3d.META_HUMAN_DNA_PT_output_panel,
    view_3d.META_HUMAN_DNA_PT_output_buttons_sub_panel,
    # DNA Backup Manager
    backup_manager_operators.META_HUMAN_DNA_OT_restore_backup,
    backup_manager_operators.META_HUMAN_DNA_OT_delete_backup,
    backup_manager_operators.META_HUMAN_DNA_OT_open_backup_folder,
    backup_manager_operators.META_HUMAN_DNA_OT_sync_backups,
    backup_manager_ui.META_HUMAN_DNA_UL_dna_backups,
    backup_manager_ui.META_HUMAN_DNA_PT_dna_backups,
]

app_handlers = {
    'load_pre': bpy.app.handlers.persistent(utilities.teardown_scene),
    'load_post': bpy.app.handlers.persistent(utilities.setup_scene),
    'undo_pre': bpy.app.handlers.persistent(utilities.pre_undo),
    'undo_post': bpy.app.handlers.persistent(utilities.post_undo),
    'redo_pre': bpy.app.handlers.persistent(utilities.pre_redo),
    'redo_post': bpy.app.handlers.persistent(utilities.post_redo),
    'render_init': bpy.app.handlers.persistent(utilities.pre_render),
    'render_complete': bpy.app.handlers.persistent(utilities.post_render),
    'render_cancel': bpy.app.handlers.persistent(utilities.post_render),
    'save_post': bpy.app.handlers.persistent(utilities.post_save),
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

        # register the overlay
        viewport_overlay.register()

    except Exception as error:
        logger.error(error)

    utilities.init_sentry()

    # add event handlers
    bpy.app.handlers.load_pre.append(app_handlers['load_pre'])
    bpy.app.handlers.load_post.append(app_handlers['load_post'])
    bpy.app.handlers.undo_pre.append(app_handlers['undo_pre'])
    bpy.app.handlers.undo_post.append(app_handlers['undo_post'])
    bpy.app.handlers.redo_pre.append(app_handlers['redo_pre'])
    bpy.app.handlers.redo_post.append(app_handlers['redo_post'])
    bpy.app.handlers.render_init.append(app_handlers['render_init'])
    bpy.app.handlers.render_complete.append(app_handlers['render_complete'])
    bpy.app.handlers.render_cancel.append(app_handlers['render_cancel'])
    bpy.app.handlers.save_post.append(app_handlers['save_post'])


def unregister():
    """
    Un-registers the addon classes when the addon is disabled.
    """
    utilities.teardown_scene()

    # remove event handlers
    if not os.environ.get('META_HUMAN_DNA_DEV'):
        rig_instance.stop_listening()

    if app_handlers['undo_pre'] in bpy.app.handlers.undo_pre:
        bpy.app.handlers.undo_pre.remove(app_handlers['undo_pre'])
    if app_handlers['undo_post'] in bpy.app.handlers.undo_post:
        bpy.app.handlers.undo_post.remove(app_handlers['undo_post'])
    if app_handlers['redo_pre'] in bpy.app.handlers.redo_pre:
        bpy.app.handlers.redo_pre.remove(app_handlers['redo_pre'])
    if app_handlers['redo_post'] in bpy.app.handlers.redo_post:
        bpy.app.handlers.redo_post.remove(app_handlers['redo_post'])
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
    if app_handlers['save_post'] in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(app_handlers['save_post'])

    try:
        # unregister the manual map
        bpy.utils.unregister_manual_map(manual_map.manual_map)

        # remove menu items
        menus.remove_dna_import_menu()
        menus.remove_rig_logic_texture_node_menu()

        # unregister the overlay
        viewport_overlay.unregister()

        # unregister the classes
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)

        # unregister the properties
        properties.unregister()
        addon_preferences.unregister()
    except Exception as error:
        logger.error(error)
