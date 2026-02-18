import logging
import os

import bpy

# This import is necessary to register custom icons
import bpy.utils.previews  # pyright: ignore[reportUnusedImport]

from . import constants, key_maps, manual_map, operators, properties, rig_instance, utilities

# Backup Manager
from .editors.backup_manager import operators as backup_manager_operators, ui as backup_manager_ui

# RBF Editor
from .editors.rbf_editor import operators as rbf_editor_operators, ui as rbf_editor_ui
from .ui import addon_preferences, importer, menus, view_3d


logger = logging.getLogger(constants.ToolInfo.NAME)

bl_info = {
    "name": "MetaHuman DNA",
    "author": "Poly Hammer",
    "version": (0, 5, 23),
    "blender": (4, 5, 0),
    "location": "File > Import > MetaHuman DNA",
    "description": (
        "Imports MetaHuman head and body components from a their DNA files, "
        "lets you customize them, then send them back to MetaHuman Creator."
    ),
    "warning": "",
    "wiki_url": "https://docs.polyhammer.com/meta-human-dna-addon/",
    "category": "Rigging",
}

# RBF Editor
rbf_editor_operator_classes = [
    rbf_editor_operators.AddRBFSolver,
    rbf_editor_operators.RemoveRBFSolver,
    rbf_editor_operators.EvaluateRBFSolvers,
    rbf_editor_operators.EditRBFSolver,
    rbf_editor_operators.RevertRBFSolver,
    rbf_editor_operators.CommitRBFSolverChanges,
    rbf_editor_operators.AddRBFPose,
    rbf_editor_operators.DuplicateRBFPose,
    rbf_editor_operators.RemoveRBFPose,
    rbf_editor_operators.ApplyRBFPoseEdits,
    rbf_editor_operators.AddRBFDriven,
    rbf_editor_operators.RemoveRBFDriven,
    rbf_editor_operators.MirrorRBFSolver,
    rbf_editor_operators.MirrorRBFPose,
]
rbf_editor_ui_classes = [
    rbf_editor_ui.META_HUMAN_DNA_PT_rbf_editor,
    rbf_editor_ui.META_HUMAN_DNA_PT_rbf_editor_solver_settings_sub_panel,
    rbf_editor_ui.META_HUMAN_DNA_PT_rbf_editor_poses_sub_panel,
    rbf_editor_ui.META_HUMAN_DNA_PT_rbf_editor_drivers_sub_panel,
    rbf_editor_ui.META_HUMAN_DNA_PT_rbf_editor_driven_sub_panel,
    rbf_editor_ui.META_HUMAN_DNA_PT_rbf_editor_footer_sub_panel,
    rbf_editor_ui.META_HUMAN_DNA_UL_bone_selection,
    rbf_editor_ui.META_HUMAN_DNA_UL_rbf_solvers,
    rbf_editor_ui.META_HUMAN_DNA_UL_rbf_poses,
    rbf_editor_ui.META_HUMAN_DNA_UL_rbf_drivers,
    rbf_editor_ui.META_HUMAN_DNA_UL_rbf_driven,
]

# Backup Manager
backup_manager_operator_classes = [
    backup_manager_operators.META_HUMAN_DNA_OT_restore_backup,
    backup_manager_operators.META_HUMAN_DNA_OT_delete_backup,
    backup_manager_operators.META_HUMAN_DNA_OT_open_backup_folder,
    backup_manager_operators.META_HUMAN_DNA_OT_sync_backups,
    backup_manager_operators.META_HUMAN_DNA_OT_create_manual_backup,
]
backup_manager_ui_classes = [
    backup_manager_ui.META_HUMAN_DNA_UL_dna_backups,
    backup_manager_ui.META_HUMAN_DNA_PT_dna_backups,
]

# Main Addon
classes = [
    operators.ImportMetaHumanDna,
    operators.DNA_FH_import_dna,
    operators.ConvertSelectedToDna,
    operators.AppendOrLinkMetaHuman,
    operators.ImportFaceBoardAnimation,
    operators.ImportComponentAnimation,
    operators.BakeFaceBoardAnimation,
    operators.BakeComponentAnimation,
    operators.ImportShapeKeys,
    operators.TestSentry,
    operators.MigrateLegacyData,
    operators.OpenBuildToolDocumentation,
    operators.OpenMetricsCollectionAgreement,
    operators.MetricsCollectionConsent,
    operators.MirrorSelectedBones,
    operators.ShrinkWrapVertexGroup,
    # operators.AutoFitSelectedBones,
    operators.RevertBoneTransformsToDna,
    operators.ForceEvaluate,
    operators.SendToMetaHumanCreator,
    operators.ExportSelectedComponent,
    operators.GenerateMaterial,
    operators.SculptThisShapeKey,
    operators.EditThisShapeKey,
    operators.ReImportThisShapeKey,
    operators.DuplicateRigInstance,
    operators.AddRigLogicTextureNode,
    operators.ReportError,
    operators.ReportErrorWithFix,
    operators.UILIST_RIG_INSTANCE_OT_entry_move,
    operators.UILIST_RIG_INSTANCE_OT_entry_add,
    operators.UILIST_RIG_INSTANCE_OT_entry_remove,
    operators.UILIST_ADDON_PREFERENCES_OT_extra_dna_entry_add,
    operators.UILIST_ADDON_PREFERENCES_OT_extra_dna_entry_remove,
    *backup_manager_operator_classes,
    *rbf_editor_operator_classes,
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
    view_3d.META_HUMAN_DNA_PT_utilities,
    view_3d.META_HUMAN_DNA_PT_mesh_utilities_sub_panel,
    view_3d.META_HUMAN_DNA_PT_armature_utilities_sub_panel,
    view_3d.META_HUMAN_DNA_PT_animation_utilities_sub_panel,
    # view_3d.META_HUMAN_DNA_PT_materials_utilities_sub_panel,
    view_3d.META_HUMAN_DNA_PT_utilities_sub_panel,
    *rbf_editor_ui_classes,
    view_3d.META_HUMAN_DNA_PT_shape_keys,
    view_3d.META_HUMAN_DNA_UL_shape_keys,
    *backup_manager_ui_classes,
    view_3d.META_HUMAN_DNA_UL_output_items,
    view_3d.META_HUMAN_DNA_UL_rig_instances,
    view_3d.META_HUMAN_DNA_PT_output_panel,
    view_3d.META_HUMAN_DNA_PT_output_buttons_sub_panel,
    view_3d.META_HUMAN_DNA_PT_migrate_legacy_data,
]

app_handlers = {
    "load_pre": bpy.app.handlers.persistent(utilities.teardown_scene),
    "load_post": bpy.app.handlers.persistent(utilities.setup_scene),
    "undo_pre": bpy.app.handlers.persistent(utilities.pre_undo),
    "undo_post": bpy.app.handlers.persistent(utilities.post_undo),
    "redo_pre": bpy.app.handlers.persistent(utilities.pre_redo),
    "redo_post": bpy.app.handlers.persistent(utilities.post_redo),
    "render_init": bpy.app.handlers.persistent(utilities.pre_render),
    "render_complete": bpy.app.handlers.persistent(utilities.post_render),
    "render_cancel": bpy.app.handlers.persistent(utilities.post_render),
    "save_post": bpy.app.handlers.persistent(utilities.post_save),
}


def register():
    """
    Registers the addon classes when the addon is enabled.
    """
    if os.environ.get("META_HUMAN_DNA_DEV"):
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

        # register key maps
        key_maps.register()

    except Exception as error:
        logger.error(error)

    utilities.init_sentry()

    # add event handlers
    for handler_name, handler_function in app_handlers.items():
        getattr(bpy.app.handlers, handler_name).append(handler_function)


def unregister():
    """
    Un-registers the addon classes when the addon is disabled.
    """
    utilities.disable_duplicate_addons()

    utilities.teardown_scene()

    if not os.environ.get("META_HUMAN_DNA_DEV"):
        rig_instance.stop_listening()

    # remove event handlers
    for handler_name, handler_function in app_handlers.items():
        handler_list = getattr(bpy.app.handlers, handler_name)
        if handler_function in handler_list:
            handler_list.remove(handler_function)

    try:
        # unregister the manual map
        bpy.utils.unregister_manual_map(manual_map.manual_map)

        # remove menu items
        menus.remove_dna_import_menu()
        menus.remove_rig_logic_texture_node_menu()

        # unregister key maps
        key_maps.unregister()

        # unregister the classes
        for cls in reversed(classes):
            if hasattr(cls, "bl_rna"):
                bpy.utils.unregister_class(cls)

        # unregister the properties
        properties.unregister()
        addon_preferences.unregister()
    except Exception as error:
        logger.error(error)
