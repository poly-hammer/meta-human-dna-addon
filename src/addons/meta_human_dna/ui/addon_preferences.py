import bpy
from pathlib import Path
from ..properties import MetahumanDnaAddonProperties, ExtraDnaFolder
from ..constants import ToolInfo
from .. import __package__


class FOLDER_UL_extra_dna_path(bpy.types.UIList):
    def draw_item(
        self, context, layout, data, item, icon, active_data, active_prop_name
    ):
        row = layout.row()
        row.alert = False
        if item.folder_path and not Path(item.folder_path).exists():
            row.alert = True
        row.prop(item, "folder_path", text="", emboss=False)


class MetaHumanDnaPreferences(MetahumanDnaAddonProperties, bpy.types.AddonPreferences):
    bl_idname = str(__package__)

    def draw(self, context):
        preferences = context.preferences.addons[ToolInfo.NAME].preferences
        row = self.layout.row()
        row.prop(self, "metrics_collection", text="Allow Metrics Collection")
        row = self.layout.row()

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
        col.operator(
            "meta_human_dna.addon_preferences_extra_dna_entry_add", text="", icon="ADD"
        )
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
