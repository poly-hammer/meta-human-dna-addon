# standard library imports
import logging
import shutil
import tempfile

from datetime import datetime
from enum import Enum
from pathlib import Path

# third party imports
import bpy

# local imports
from ...constants import ToolInfo
from ...typing import *  # noqa: F403


logger = logging.getLogger(__name__)


class BackupType(Enum):
    """Enumeration of backup trigger types."""

    POSE_EDITOR = "Pose Editor Commit"
    EXPRESSION_EDITOR = "Expression Editor Commit"
    BLENDER_FILE_SAVE = "Blender File Saved"


def get_backup_folder() -> Path:
    """
    Get the base folder for DNA backups.

    Returns:
        Path to the backup folder in the system's temp directory.
    """
    backup_base = Path(tempfile.gettempdir()) / "meta_human_dna_backups"
    backup_base.mkdir(parents=True, exist_ok=True)
    return backup_base


def _get_addon_preferences() -> "MetahumanAddonProperties | None":
    """Get the addon preferences."""
    if not bpy.context.preferences:
        return None
    addon = bpy.context.preferences.addons.get(ToolInfo.NAME)
    if addon:
        return addon.preferences  # pyright: ignore[reportReturnType]
    return None


def is_auto_backup_enabled() -> bool:
    """
    Check if auto backup is enabled in addon preferences.

    Returns:
        True if auto backup is enabled, False otherwise.
    """
    preferences = _get_addon_preferences()
    if preferences:
        return preferences.enable_auto_dna_backups
    return False


def get_max_backups() -> int:
    """
    Get the maximum number of backups to keep.

    Returns:
        Maximum number of backups from preferences, or 5 as default.
    """
    preferences = _get_addon_preferences()
    if preferences:
        return preferences.max_dna_backups
    return 5


def create_backup(instance: "RigInstance", backup_type: BackupType, description: str | None = None) -> str | None:
    """
    Create a backup of the DNA files for the given rig instance.

    Args:
        instance: The RigInstance to backup DNA files for.
        backup_type: The type of backup (what triggered it).
        description: Optional custom description for the backup.

    Returns:
        The backup ID (folder name) if successful, None otherwise.
    """
    if not is_auto_backup_enabled():
        logger.debug("Auto backup is disabled, skipping backup creation")
        return None

    # Generate unique backup ID using timestamp
    timestamp = datetime.now().astimezone()
    backup_id = timestamp.strftime("%Y%m%d_%H%M%S")

    # Create instance-specific backup folder
    instance_backup_folder = get_backup_folder() / instance.name
    backup_folder = instance_backup_folder / backup_id
    backup_folder.mkdir(parents=True, exist_ok=True)

    files_backed_up = []

    try:
        # Backup head DNA file if it exists
        if instance.head_dna_file_path:
            head_path = Path(bpy.path.abspath(instance.head_dna_file_path))
            if head_path.exists():
                dest = backup_folder / f"head_{head_path.name}"
                shutil.copy2(head_path, dest)
                files_backed_up.append(str(dest))
                logger.debug(f"Backed up head DNA: {head_path} -> {dest}")

        # Backup body DNA file if it exists
        if instance.body_dna_file_path:
            body_path = Path(bpy.path.abspath(instance.body_dna_file_path))
            if body_path.exists():
                dest = backup_folder / f"body_{body_path.name}"
                shutil.copy2(body_path, dest)
                files_backed_up.append(str(dest))
                logger.debug(f"Backed up body DNA: {body_path} -> {dest}")

        if not files_backed_up:
            # No files to backup, remove the empty folder
            backup_folder.rmdir()
            logger.warning("No DNA files found to backup")
            return None

        # Create metadata file
        metadata = {
            "timestamp": timestamp.isoformat(),
            "backup_type": backup_type.value,
            "description": description or backup_type.value,
            "instance_name": instance.name,
            "files": files_backed_up,
            "head_dna_path": instance.head_dna_file_path or "",
            "body_dna_path": instance.body_dna_file_path or "",
        }

        metadata_path = backup_folder / "metadata.json"
        import json

        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        # Add to the instance's backup list in Blender
        _add_backup_to_list(instance, backup_id, timestamp, backup_type, description)

        # Cleanup old backups for this instance
        cleanup_old_backups(instance)

        logger.info(f"Created DNA backup for {instance.name}: {backup_id}")
        return backup_id

    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        # Cleanup on failure
        if backup_folder.exists():
            shutil.rmtree(backup_folder, ignore_errors=True)
        return None


def _add_backup_to_list(
    instance: "RigInstance",
    backup_id: str,
    timestamp: datetime,
    backup_type: BackupType,
    description: str | None,
) -> None:
    """
    Add a backup entry to the RigLogicInstance's backup list.

    Args:
        instance: The RigLogicInstance to add the backup to.
        backup_id: The unique backup identifier.
        timestamp: When the backup was created.
        backup_type: The type of backup.
        description: Optional description override.
    """
    backup_list = instance.dna_backup_list

    # Add new entry
    entry = backup_list.add()
    entry.backup_id = backup_id
    entry.timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    entry.backup_type = backup_type.value
    entry.description = description or backup_type.value
    entry.instance_name = instance.name
    entry.folder_path = str(get_backup_folder() / instance.name / backup_id)

    # Set as active
    instance.dna_backup_list_active_index = len(backup_list) - 1


def restore_backup(instance: "RigInstance", backup_id: str) -> bool:
    """
    Restore DNA files from a backup.

    Args:
        instance: The RigLogicInstance whose backup to restore.
        backup_id: The unique backup identifier to restore.

    Returns:
        True if restoration was successful, False otherwise.
    """
    backup_folder = get_backup_folder() / instance.name / backup_id
    metadata_path = backup_folder / "metadata.json"

    if not metadata_path.exists():
        logger.error(f"Backup metadata not found: {backup_id}")
        return False

    try:
        import json

        with metadata_path.open(encoding="utf-8") as f:
            metadata = json.load(f)

        # Restore head DNA
        if metadata.get("head_dna_path"):
            head_backup = backup_folder / f"head_{Path(metadata['head_dna_path']).name}"
            if head_backup.exists():
                dest = Path(bpy.path.abspath(metadata["head_dna_path"]))
                shutil.copy2(head_backup, dest)
                logger.info(f"Restored head DNA: {head_backup} -> {dest}")

        # Restore body DNA
        if metadata.get("body_dna_path"):
            body_backup = backup_folder / f"body_{Path(metadata['body_dna_path']).name}"
            if body_backup.exists():
                dest = Path(bpy.path.abspath(metadata["body_dna_path"]))
                shutil.copy2(body_backup, dest)
                logger.info(f"Restored body DNA: {body_backup} -> {dest}")

        logger.info(f"Successfully restored backup for {instance.name}: {backup_id}")
        bpy.ops.meta_human_dna.force_evaluate()  # type: ignore[attr-defined]
        return True

    except Exception as e:
        logger.error(f"Failed to restore backup {backup_id}: {e}")
        return False


def delete_backup(instance: "RigInstance", backup_id: str) -> bool:
    """
    Delete a backup folder and its contents.

    Args:
        instance: The RigLogicInstance whose backup to delete.
        backup_id: The unique backup identifier to delete.

    Returns:
        True if deletion was successful, False otherwise.
    """
    backup_folder = get_backup_folder() / instance.name / backup_id

    if not backup_folder.exists():
        logger.warning(f"Backup folder not found: {backup_id}")
        return False

    try:
        shutil.rmtree(backup_folder)
        logger.info(f"Deleted backup for {instance.name}: {backup_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete backup {backup_id}: {e}")
        return False


def cleanup_old_backups(instance: "RigInstance") -> None:
    """
    Remove old backups that exceed the maximum count for a specific instance.

    Keeps the most recent backups based on the max_dna_backups preference.

    Args:
        instance: The RigLogicInstance whose old backups to clean up.
    """
    max_backups = get_max_backups()
    instance_backup_folder = get_backup_folder() / instance.name

    if not instance_backup_folder.exists():
        return

    # Get all backup folders sorted by name (which includes timestamp)
    backup_folders = sorted(
        [d for d in instance_backup_folder.iterdir() if d.is_dir()],
        key=lambda x: x.name,
        reverse=True,  # Newest first
    )

    # Delete excess backups
    if len(backup_folders) > max_backups:
        folders_to_delete = backup_folders[max_backups:]
        for folder in folders_to_delete:
            backup_id = folder.name
            delete_backup(instance, backup_id)

            # Also remove from the instance's backup list
            backup_list = instance.dna_backup_list
            for i, entry in enumerate(backup_list):
                if entry.backup_id == backup_id:
                    backup_list.remove(i)
                    break

        logger.info(f"Cleaned up {len(folders_to_delete)} old backups for {instance.name}")


def sync_backup_list_with_disk(instance: "RigInstance") -> None:
    """
    Synchronize the instance's backup list with backups on disk.

    This ensures the list reflects actual backup files and removes
    entries for deleted backups.

    Args:
        instance: The RigLogicInstance whose backup list to sync.
    """
    backup_list = instance.dna_backup_list
    instance_backup_folder = get_backup_folder() / instance.name

    if not instance_backup_folder.exists():
        # No backups folder, clear the list
        backup_list.clear()
        return

    # Get set of existing backup IDs on disk
    existing_backup_ids = {d.name for d in instance_backup_folder.iterdir() if d.is_dir()}

    # Remove list entries that no longer exist on disk
    indices_to_remove = []
    for i, entry in enumerate(backup_list):
        if entry.backup_id not in existing_backup_ids:
            indices_to_remove.append(i)

    # Remove in reverse order to maintain indices
    for i in reversed(indices_to_remove):
        backup_list.remove(i)

    # Add any backups from disk that aren't in the list
    list_backup_ids = {entry.backup_id for entry in backup_list}
    import json

    for backup_folder in instance_backup_folder.iterdir():
        if backup_folder.is_dir() and backup_folder.name not in list_backup_ids:
            metadata_path = backup_folder / "metadata.json"
            if metadata_path.exists():
                try:
                    with metadata_path.open(encoding="utf-8") as f:
                        metadata = json.load(f)

                    entry = backup_list.add()
                    entry.backup_id = backup_folder.name
                    entry.timestamp = metadata.get("timestamp", backup_folder.name)[:19].replace("T", " ")
                    entry.backup_type = metadata.get("backup_type", "Unknown")
                    entry.description = metadata.get("description", "Unknown")
                    entry.instance_name = metadata.get("instance_name", instance.name)
                    entry.folder_path = str(backup_folder)
                except Exception as e:
                    logger.warning(f"Could not load metadata for backup {backup_folder.name}: {e}")
