# standard library imports
from pathlib import Path

# third party imports
import bpy

# local imports
from .. import __package__ as package_name
from ..constants import ToolInfo
from ..properties import ExtraDnaFolder, MetahumanAddonProperties
from ..typing import *  # noqa: F403


class FOLDER_UL_extra_dna_path(bpy.types.UIList):
    def draw_item(
        self,
        context: "Context",
        layout: bpy.types.UILayout,
        data: "MetaHumanDnaPreferences",
        item: "ExtraDnaFolder",
        icon: int | None,
        active_data: "MetaHumanDnaPreferences",
        active_prop_name: str,
    ):
        row = layout.row()
        row.alert = False
        if item.folder_path and not Path(item.folder_path).exists():
            row.alert = True
        row.prop(item, "folder_path", text="", emboss=False)


class MetaHumanDnaPreferences(MetahumanAddonProperties, bpy.types.AddonPreferences):
    bl_idname = str(package_name)

    def draw(self, context: "Context"):
        preferences = context.preferences.addons[ToolInfo.NAME].preferences
        layout = self.layout

        # General Settings
        row = layout.row()
        row.prop(self, "metrics_collection", text="Allow Metrics Collection")
        row = layout.row()
        row.prop(self, "show_pose_editor_viewport_overlay", text="Show Pose Editor Viewport Overlay")

        # DNA Backup Settings
        layout.separator()
        box = layout.box()
        box.label(text="Backup Manager Settings:", icon="FILE_BACKUP")
        row = box.row()
        row.prop(self, "enable_auto_dna_backups", text="Enable Auto DNA Backups")
        row.enabled = self.enable_auto_dna_backups
        row.prop(self, "max_dna_backups", text="Maximum Backups to Keep")

        # Extra DNA Folder Paths
        layout.separator()
        row = layout.row()

        row.label(text="Extra DNA Folder Paths:")
        row = self.layout.row()
        row.template_list(
            "FOLDER_UL_extra_dna_path",
            "extra_dna_folder_list_id",
            preferences,
            "extra_dna_folder_list",
            preferences,
            "extra_dna_folder_list_active_index",
            rows=4 if preferences.extra_dna_folder_list else 1,
        )

        col = row.column()
        col.operator("meta_human_dna.addon_preferences_extra_dna_entry_add", text="", icon="ADD")
        row = col.row()
        row.enabled = len(preferences.extra_dna_folder_list) > 0
        row.operator(
            "meta_human_dna.addon_preferences_extra_dna_entry_remove",
            text="",
            icon="REMOVE",
        )


def register():
    bpy.utils.register_class(ExtraDnaFolder)
    bpy.utils.register_class(FOLDER_UL_extra_dna_path)
    bpy.utils.register_class(MetaHumanDnaPreferences)


def unregister():
    bpy.utils.unregister_class(MetaHumanDnaPreferences)
    bpy.utils.unregister_class(FOLDER_UL_extra_dna_path)
    bpy.utils.unregister_class(ExtraDnaFolder)
