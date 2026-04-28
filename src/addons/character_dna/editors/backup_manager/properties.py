import bpy


class DnaBackupEntry(bpy.types.PropertyGroup):
    """PropertyGroup representing a single DNA backup entry."""

    backup_id: bpy.props.StringProperty(name="Backup ID", description="Unique identifier for this backup", default="")  # pyright: ignore[reportInvalidTypeForm]

    timestamp: bpy.props.StringProperty(name="Timestamp", description="When this backup was created", default="")  # pyright: ignore[reportInvalidTypeForm]

    backup_type: bpy.props.StringProperty(name="Backup Type", description="What triggered this backup", default="")  # pyright: ignore[reportInvalidTypeForm]
    description: bpy.props.StringProperty(name="Description", description="Description of the backup", default="")  # pyright: ignore[reportInvalidTypeForm]

    instance_name: bpy.props.StringProperty(
        name="Instance Name", description="Name of the rig instance that was backed up", default=""
    )  # pyright: ignore[reportInvalidTypeForm]
    folder_path: bpy.props.StringProperty(
        name="Folder Path", description="Path to the backup folder", default="", subtype="DIR_PATH"
    )  # pyright: ignore[reportInvalidTypeForm]
