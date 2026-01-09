# standard library imports
import subprocess
import sys

# third party imports
import bpy

from ...typing import *  # noqa: F403
from ...utilities import get_active_rig_instance

# local imports
from . import core


class META_HUMAN_DNA_OT_restore_backup(bpy.types.Operator):
    """Restore DNA files from the selected backup."""

    bl_idname = "meta_human_dna.restore_dna_backup"
    bl_label = "Restore Backup"
    bl_description = "Restore DNA files from the selected backup"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, _: "Context") -> bool:
        instance = get_active_rig_instance()
        if instance is None:
            return False
        return len(instance.dna_backup_list) > 0

    def execute(self, context: "Context") -> set[str]:
        instance = get_active_rig_instance()
        if instance is None:
            self.report({"ERROR"}, "No active MetaHuman instance")
            return {"CANCELLED"}

        backup_list = instance.dna_backup_list
        active_index = instance.dna_backup_list_active_index

        if active_index < 0 or active_index >= len(backup_list):
            self.report({"ERROR"}, "No backup selected")
            return {"CANCELLED"}

        backup_entry = backup_list[active_index]

        if core.restore_backup(instance, backup_entry.backup_id):
            self.report({"INFO"}, f"Restored backup from {backup_entry.timestamp}")
            return {"FINISHED"}
        self.report({"ERROR"}, "Failed to restore backup")
        return {"CANCELLED"}


class META_HUMAN_DNA_OT_delete_backup(bpy.types.Operator):
    """Delete the selected backup."""

    bl_idname = "meta_human_dna.delete_dna_backup"
    bl_label = "Delete Backup"
    bl_description = "Delete the selected DNA backup"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, _: "Context") -> bool:
        instance = get_active_rig_instance()
        if instance is None:
            return False
        return len(instance.dna_backup_list) > 0

    def execute(self, context: "Context") -> set[str]:
        instance = get_active_rig_instance()
        if instance is None:
            self.report({"ERROR"}, "No active MetaHuman instance")
            return {"CANCELLED"}

        backup_list = instance.dna_backup_list
        active_index = instance.dna_backup_list_active_index

        if active_index < 0 or active_index >= len(backup_list):
            self.report({"ERROR"}, "No backup selected")
            return {"CANCELLED"}

        backup_entry = backup_list[active_index]
        backup_id = backup_entry.backup_id

        if core.delete_backup(instance, backup_id):
            backup_list.remove(active_index)
            # Adjust active index if needed
            if active_index >= len(backup_list) and len(backup_list) > 0:
                instance.dna_backup_list_active_index = len(backup_list) - 1
            self.report({"INFO"}, "Backup deleted")
            return {"FINISHED"}
        self.report({"ERROR"}, "Failed to delete backup")
        return {"CANCELLED"}


class META_HUMAN_DNA_OT_open_backup_folder(bpy.types.Operator):
    """Open the backup folder in the file explorer."""

    bl_idname = "meta_human_dna.open_backup_folder"
    bl_label = "Open Backup Folder"
    bl_description = "Open the DNA backup folder in the file explorer"

    def execute(self, context: "Context") -> set[str]:
        backup_folder = core.get_backup_folder()

        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(backup_folder)])  # noqa: S603, S607
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(backup_folder)])  # noqa: S603, S607
        else:
            subprocess.Popen(["xdg-open", str(backup_folder)])  # noqa: S603, S607

        return {"FINISHED"}


class META_HUMAN_DNA_OT_sync_backups(bpy.types.Operator):
    """Synchronize the backup list with files on disk."""

    bl_idname = "meta_human_dna.sync_dna_backups"
    bl_label = "Refresh Backups"
    bl_description = "Refresh the backup list from disk"

    @classmethod
    def poll(cls, _: "Context") -> bool:
        return get_active_rig_instance() is not None

    def execute(self, context: "Context") -> set[str]:
        instance = get_active_rig_instance()
        if instance is None:
            self.report({"ERROR"}, "No active MetaHuman instance")
            return {"CANCELLED"}

        core.sync_backup_list_with_disk(instance)
        self.report({"INFO"}, "Backup list refreshed")
        return {"FINISHED"}
