# Type checking utilities for the Character DNA addon.

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    import bpy

    from bpy.types import bpy_prop_collection, bpy_struct

    from .bindings import riglogic  # pyright: ignore[reportAttributeAccessIssue] # noqa: TC004
    from .components.body import CharacterComponentBody  # noqa: TC004
    from .components.head import CharacterComponentHead  # noqa: TC004
    from .editors.backup_manager.properties import DnaBackupEntry  # noqa: TC004
    from .editors.rbf_editor.properties import (  # noqa: TC004
        RBFDrivenBoneSelectionItem,
        RBFDrivenData,
        RBFDriverData,
        RBFPoseData,
        RBFSolverData,
    )
    from .operators import BakeAnimationBase, DuplicateRigInstance  # noqa: TC004
    from .properties import (
        CharacterAddonProperties,  # noqa: TC004
        CharacterImportProperties,  # noqa: TC004
        CharacterSceneProperties,  # noqa: TC004
        CharacterWindowMangerProperties as _CharacterWindowMangerProperties,
        ExtraDnaFolder,
    )
    from .rig_instance import OutputData, RigInstance as _RigInstanceBase, ShapeKeyData  # noqa: TC004

    # =========================================================================
    # Custom Collections
    # =========================================================================
    class ExtraDnaFolders(bpy_prop_collection[ExtraDnaFolder], bpy_struct):
        def add(self) -> ExtraDnaFolder: ...
        def move(self, src_index: int, dst_index: int) -> None: ...
        def remove(self, index: int) -> None: ...
        def clear(self) -> None: ...

    class DnaBackupEntrys(bpy_prop_collection[DnaBackupEntry], bpy_struct):
        def add(self) -> DnaBackupEntry: ...
        def move(self, src_index: int, dst_index: int) -> None: ...
        def remove(self, index: int) -> None: ...
        def clear(self) -> None: ...

    class RBFSolvers(bpy_prop_collection[RBFSolverData], bpy_struct):
        def add(self) -> RBFSolverData: ...
        def move(self, src_index: int, dst_index: int) -> None: ...
        def remove(self, index: int) -> None: ...
        def clear(self) -> None: ...

    # =========================================================================
    # Extended RigInstance with dynamically assigned editor properties
    # These are added at runtime in properties.py register() function
    # =========================================================================
    class RigInstance(_RigInstanceBase):
        """Extended RigInstance type with dynamically registered properties."""

        dna_backup_list: DnaBackupEntrys
        dna_backup_list_active_index: int
        rbf_solver_list: RBFSolvers
        rbf_solver_list_active_index: int

    # =========================================================================
    # Extended CharacterWindowMangerProperties with dynamically assigned editor properties
    # These are added at runtime in properties.py register() function
    # =========================================================================
    class CharacterWindowMangerProperties(_CharacterWindowMangerProperties):
        """Extended WindowManager properties with RBF Editor properties."""

        add_pose_driven_bones: bpy_prop_collection[RBFDrivenBoneSelectionItem]
        add_pose_driven_bones_active_index: int

    # =========================================================================
    # Addon Preferences Types
    # =========================================================================
    class _CharacterAddonPreferences(CharacterAddonProperties, bpy.types.AddonPreferences):
        """Typed addon preferences for Character DNA."""

        bl_idname: str
        metrics_collection: bool
        rbf_editor_show_viewport_overlay: bool
        rbf_editor_solver_mirror_regex_pattern: str
        rbf_editor_pose_mirror_regex_pattern: str
        rbf_editor_bone_mirror_regex_pattern: str
        dna_backups_enable: bool
        dna_backups_max: int
        next_metrics_consent_timestamp: float
        extra_dna_folder_list: ExtraDnaFolders
        extra_dna_folder_list_active_index: int

    class _CharacterAddon(bpy.types.Addon):
        """Typed addon module reference."""

        preferences: _CharacterAddonPreferences

    class _CharacterAddons(bpy.types.bpy_prop_collection[bpy.types.Addon]):
        """Typed addons collection with Character DNA addon."""

        def get(self, name: str, default: _CharacterAddon | None = None) -> _CharacterAddon | None: ...
        def __getitem__(self, name: str) -> _CharacterAddon: ...
        def __contains__(self, name: str) -> bool: ...

    # =========================================================================
    # Patch bpy.types.Preferences
    # =========================================================================
    class Preferences(bpy.types.Preferences):
        """Extended Preferences type with typed addons access."""

        addons: _CharacterAddons

    # =========================================================================
    # Patch bpy.types.Scene
    # =========================================================================
    class Scene(bpy.types.Scene):
        """Extended Scene type with Character DNA properties."""

        meta_human_dna: CharacterSceneProperties

    # =========================================================================
    # Patch bpy.types.WindowManager
    # =========================================================================
    class WindowManager(bpy.types.WindowManager):
        """Extended WindowManager type with Character DNA properties."""

        meta_human_dna: CharacterWindowMangerProperties

    # =========================================================================
    # Patch bpy.types.Context
    # =========================================================================
    class Context(bpy.types.Context):
        """Extended Context type with typed properties."""

        window_manager: WindowManager
        preferences: Preferences
        scene: Scene

    __all__ = [
        "BakeAnimationBase",
        "CharacterAddonProperties",
        "CharacterComponentBody",
        "CharacterComponentHead",
        "CharacterImportProperties",
        "CharacterSceneProperties",
        "CharacterWindowMangerProperties",
        "Context",
        "DnaBackupEntry",
        "DuplicateRigInstance",
        "OutputData",
        "Preferences",
        "RBFDrivenBoneSelectionItem",
        "RBFDrivenData",
        "RBFDriverData",
        "RBFPoseData",
        "RBFSolverData",
        "RigInstance",
        "Scene",
        "ShapeKeyData",
        "WindowManager",
        "riglogic",
    ]
