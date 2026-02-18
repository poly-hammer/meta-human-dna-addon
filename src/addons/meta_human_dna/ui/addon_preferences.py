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
        layout = self.layout
        # General Settings
        row = layout.row()
        row.prop(self, "metrics_collection", text="Allow Metrics Collection")
        row = layout.row()

        # TODO: Enable RBF Editor settings later in later release
        # # RBF Editor Settings
        # layout.separator()  # noqa: ERA001
        # box = layout.box() # noqa: ERA001
        # box.label(text="RBF Editor Settings:", icon="POSE_HLT") # noqa: ERA001
        # row = box.row() # noqa: ERA001
        # row.prop(self, "rbf_editor_show_viewport_overlay", text="Show RBF Editor Viewport Overlay") # noqa: ERA001
        # row = box.row() # noqa: ERA001
        # row.prop(self, "rbf_editor_solver_mirror_regex_pattern") # noqa: ERA001
        # row = box.row() # noqa: ERA001
        # row.prop(self, "rbf_editor_pose_mirror_regex_pattern") # noqa: ERA001
        # row = box.row() # noqa: ERA001
        # row.prop(self, "rbf_editor_bone_mirror_regex_pattern") # noqa: ERA001

        # # DNA Backup Settings
        # layout.separator() # noqa: ERA001
        # box = layout.box() # noqa: ERA001
        # box.label(text="Backup Manager Settings:", icon="FILE_BACKUP") # noqa: ERA001
        # row = box.row() # noqa: ERA001
        # row.prop(self, "dna_backups_enable", text="Enable Auto DNA Backups") # noqa: ERA001
        # row.enabled = self.dna_backups_enable # noqa: ERA001
        # row.prop(self, "dna_backups_max", text="Maximum Backups to Keep") # noqa: ERA001
        # row = box.row() # noqa: ERA001
        # row.prop(self, "dna_backups_folder_path", text="DNA Backup Folder") # noqa: ERA001

        # Extra DNA Folder Paths
        layout.separator()
        row = layout.row()

        row.label(text="Extra DNA Folder Paths:")
        row = self.layout.row()
        row.template_list(
            "FOLDER_UL_extra_dna_path",
            "extra_dna_folder_list_id",
            self,
            "extra_dna_folder_list",
            self,
            "extra_dna_folder_list_active_index",
            rows=4 if self.extra_dna_folder_list else 1,
        )

        col = row.column()
        col.operator(f"{ToolInfo.NAME}.addon_preferences_extra_dna_entry_add", text="", icon="ADD")
        row = col.row()
        row.enabled = len(self.extra_dna_folder_list) > 0
        row.operator(
            f"{ToolInfo.NAME}.addon_preferences_extra_dna_entry_remove",
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
