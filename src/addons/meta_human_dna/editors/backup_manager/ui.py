# third party imports
import bpy

# local imports
from ...constants import ToolInfo
from ...typing import *  # noqa: F403
from ...utilities import get_active_rig_instance


class META_HUMAN_DNA_UL_dna_backups(bpy.types.UIList):
    """UIList for displaying DNA backup entries."""

    def draw_item(
        self,
        context: "Context",
        layout: bpy.types.UILayout,
        data: "RigInstance",
        item: "DnaBackupEntry",
        icon: int | None,
        active_data: "RigInstance",
        active_propname: str,
    ):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            # Timestamp
            row.label(text=item.timestamp, icon="TIME")
            # Description
            row.label(text=item.description)
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.timestamp, icon="TIME")


class META_HUMAN_DNA_PT_dna_backups(bpy.types.Panel):
    """Panel for displaying and managing DNA backups."""

    bl_label = "Backup Manager"
    bl_idname = "META_HUMAN_DNA_PT_dna_backups"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MetaHuman DNA"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, _: "Context") -> bool:
        # return get_active_rig_instance() is not None  # noqa: ERA001
        # TODO: Enable panel later in later release
        return False

    def draw(self, context: "Context"):
        layout = self.layout
        if not layout:
            return

        instance = get_active_rig_instance()
        if instance is None:
            layout.label(text="No active MetaHuman instance", icon="INFO")
            return

        # Backup list
        row = layout.row()
        row.template_list(
            "META_HUMAN_DNA_UL_dna_backups",
            "dna_backup_list_id",
            instance,
            "dna_backup_list",
            instance,
            "dna_backup_list_active_index",
            rows=4 if len(instance.dna_backup_list) > 0 else 1,
        )

        # Side buttons
        col = row.column(align=True)
        col.operator(f"{ToolInfo.NAME}.sync_dna_backups", text="", icon="FILE_REFRESH")
        col.operator(f"{ToolInfo.NAME}.open_backup_folder", text="", icon="FILE_FOLDER")
        col.operator(f"{ToolInfo.NAME}.create_manual_backup", text="", icon="ADD")

        # Bottom buttons
        if len(instance.dna_backup_list) > 0:
            row = layout.row(align=True)
            row.operator(f"{ToolInfo.NAME}.restore_dna_backup", text="Restore", icon="LOOP_BACK")
            row.operator(f"{ToolInfo.NAME}.delete_dna_backup", text="Delete", icon="TRASH")

            # Show selected backup details
            active_index = instance.dna_backup_list_active_index
            if 0 <= active_index < len(instance.dna_backup_list):
                backup = instance.dna_backup_list[active_index]
                box = layout.box()
                box.label(text=f"Type: {backup.backup_type}", icon="INFO")
        else:
            layout.label(text="No backups available", icon="INFO")
