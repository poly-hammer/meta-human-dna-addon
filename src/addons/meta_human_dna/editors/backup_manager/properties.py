import bpy


class DnaBackupEntry(bpy.types.PropertyGroup):
    """PropertyGroup representing a single DNA backup entry."""

    backup_id: bpy.props.StringProperty(name="Backup ID", description="Unique identifier for this backup", default="")  # type: ignore

    timestamp: bpy.props.StringProperty(name="Timestamp", description="When this backup was created", default="")  # type: ignore

    backup_type: bpy.props.StringProperty(name="Backup Type", description="What triggered this backup", default="")  # type: ignore

    description: bpy.props.StringProperty(name="Description", description="Description of the backup", default="")  # type: ignore

    instance_name: bpy.props.StringProperty(
        name="Instance Name", description="Name of the rig instance that was backed up", default=""
    )  # type: ignore

    folder_path: bpy.props.StringProperty(
        name="Folder Path", description="Path to the backup folder", default="", subtype="DIR_PATH"
    )  # type: ignore
