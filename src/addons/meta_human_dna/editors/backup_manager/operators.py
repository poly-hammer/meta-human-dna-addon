# standard library imports
import subprocess
import sys

# third party imports
import bpy

# local imports
from ...constants import ToolInfo
from ...typing import *  # noqa: F403
from ...utilities import get_active_rig_instance
from . import core


class META_HUMAN_DNA_OT_restore_backup(bpy.types.Operator):
    """Restore DNA files from the selected backup."""

    bl_idname = f"{ToolInfo.NAME}.restore_dna_backup"
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

    bl_idname = f"{ToolInfo.NAME}.delete_dna_backup"
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

    bl_idname = f"{ToolInfo.NAME}.open_backup_folder"
    bl_label = "Open Backup Folder"
    bl_description = "Open the DNA backup folder in the file explorer"

    def execute(self, context: "Context") -> set[str]:
        instance = get_active_rig_instance()
        if not instance:
            self.report({"ERROR"}, "No active instance")
            return {"CANCELLED"}

        backup_folder = core.get_backup_folder(instance=instance)

        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(backup_folder)])  # noqa: S603, S607
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(backup_folder)])  # noqa: S603, S607
        else:
            subprocess.Popen(["xdg-open", str(backup_folder)])  # noqa: S603, S607

        return {"FINISHED"}


class META_HUMAN_DNA_OT_sync_backups(bpy.types.Operator):
    """Synchronize the backup list with files on disk."""

    bl_idname = f"{ToolInfo.NAME}.sync_dna_backups"
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


class META_HUMAN_DNA_OT_create_manual_backup(bpy.types.Operator):
    """Create a manual backup of the DNA files with a custom description."""

    bl_idname = f"{ToolInfo.NAME}.create_manual_backup"
    bl_label = "Create Manual Backup"
    bl_description = "Create a manual backup of the DNA files with a custom description"
    bl_options = {"REGISTER", "UNDO"}

    description: bpy.props.StringProperty(
        name="Description",
        description="A description for this backup",
        default="",
    )  # pyright: ignore[reportInvalidTypeForm]

    @classmethod
    def poll(cls, _: "Context") -> bool:
        instance = get_active_rig_instance()
        if instance is None:
            return False
        # Check if there's at least one DNA file to backup
        return bool(instance.head_dna_file_path or instance.body_dna_file_path)

    def invoke(self, context: "Context", event: bpy.types.Event) -> set[str]:
        # Show a dialog to input the description
        return context.window_manager.invoke_props_dialog(self, width=400)  # pyright: ignore[reportReturnType]

    def draw(self, context: "Context"):
        if not self.layout:
            return
        self.layout.prop(self, "description", text="Description")

    def execute(self, context: "Context") -> set[str]:
        instance = get_active_rig_instance()
        if instance is None:
            self.report({"ERROR"}, "No active MetaHuman instance")
            return {"CANCELLED"}

        # Use a default description if none provided
        description = self.description.strip() if self.description else "Manual Backup"

        # Temporarily enable backup creation even if auto-backup is disabled
        backup_id = core.create_backup(
            instance=instance,
            backup_type=core.BackupType.MANUAL,
            description=description,
        )

        if backup_id:
            self.report({"INFO"}, f"Created manual backup: {description}")
            return {"FINISHED"}

        self.report({"ERROR"}, "Failed to create backup. Check if auto-backup is enabled in preferences.")
        return {"CANCELLED"}
