# Backup Manager

!!! info "Pro Feature"
    The Backup Manager is part of the **Pro** edition and only appears when Pro is installed.

Automatically snapshots your `.dna` before and after changes are committed, giving you a fast way to roll back to a previous state.

<video autoplay loop muted playsinline class="rounded-image" style="width:100%" poster="../../images/backup-manager/backup_manager.png">
  <source src="../../images/backup-manager/backup_manager.webm" type="video/webm">
</video>

## Backup Events

A backup is taken automatically around every point where your DNA could change, plus whenever you save your `.blend` file:

| Event | Fires |
| ----- | ----- |
| Blender File Saved | Every time you save the `.blend` file |
| Pre Raw Editor Commit | Right before committing an edit from the [Raw Editor](./raw-editor.md) |
| Post Raw Editor Commit | Right after committing an edit from the [Raw Editor](./raw-editor.md) |
| Pre Raw Editor (Rest Pose) Commit | Right before committing a Rest Pose (bind pose) edit from the [Raw Editor](./raw-editor.md) |
| Post Raw Editor (Rest Pose) Commit | Right after committing a Rest Pose (bind pose) edit from the [Raw Editor](./raw-editor.md) |
| Pre RBF Editor Commit | Right before committing an edit from the [RBF Editor](./rbf-editor.md) |
| Post RBF Editor Commit | Right after committing an edit from the [RBF Editor](./rbf-editor.md) |
| Pre Shape Key Editor Commit | Right before committing an edit from the [Shape Key Editor](./shape-key-editor.md) |
| Post Shape Key Editor Commit | Right after committing an edit from the [Shape Key Editor](./shape-key-editor.md) |
| Manual Backup | Whenever you click **Add** in the Backup Manager panel |

Taking both a "pre" and "post" snapshot around each editor commit means you can always roll back to either side of a change — the state right before you committed, or the freshly committed result.

!!! note
    Automatic backups can be turned off entirely from the addon preferences (see [Preferences](#preferences) below). Manual backups are always available regardless of that setting.

## The Backup List

Each entry is a timestamped snapshot with a description and type (for example, taken before or after a commit). Use the side buttons to:

- **Refresh** — rescan the backups folder.
- **Folder** — open the backups folder in your file explorer.
- **Add** — create a manual backup right now.

## Restoring

Select a backup and click **Restore**. Choose what to bring back:

| Option | Restores |
| ------ | -------- |
| Reimport Meshes | Mesh geometry |
| Reimport Bones | Bone/rig data |
| Reimport Shape Keys | Shape keys |

**Delete** removes the selected backup.

!!! tip
    It's good practice to create manual backups with clear descriptions as you make changes to your DNA files.

## Preferences

Backup behavior is configured in the addon's preferences:

| Setting | Purpose |
| ------- | ------- |
| Enable Auto DNA Backups | Master switch for the automatic backups listed above. Turning this off stops new automatic backups from being created — manual backups are unaffected. |
| DNA Backup Folder | Where backups are stored. Defaults to a folder in your system's temp directory. You can point this at any absolute path, or use Blender's `//` relative-path syntax (e.g. `//backups`) to store backups in a folder next to the current saved `.blend` file. |
| Maximum Backups to Keep | The retention policy — the number of **automatic** backups to keep per Rig Instance before the oldest are deleted. Manually created backups are never deleted automatically, regardless of this setting. |
