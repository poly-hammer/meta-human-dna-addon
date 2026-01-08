# Type checking utilities for the MetaHuman DNA addon.

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    import bpy.types

    from .bindings import riglogic  # noqa: TC004
    from .components.body import MetaHumanComponentBody  # noqa: TC004
    from .components.head import MetaHumanComponentHead  # noqa: TC004
    from .editors.backup_manager.properties import DnaBackupEntry
    from .editors.pose_editor.properties import RBFPoseData, RBFSolverData  # noqa: TC004
    from .operators import BakeAnimationBase, DuplicateRigInstance  # noqa: TC004
    from .properties import (
        ExtraDnaFolder,
        MetahumanDnaAddonProperties,  # noqa: TC004
        MetahumanSceneProperties,  # noqa: TC004
        MetahumanWindowMangerProperties,  # noqa: TC004
    )
    from .rig_instance import RigInstance as _RigInstanceBase

    # =========================================================================
    # Extended RigInstance with dynamically assigned editor properties
    # These are added at runtime in properties.py register() function
    # =========================================================================
    class RigInstance(_RigInstanceBase):
        """Extended RigInstance type with dynamically registered properties."""

        dna_backup_list: bpy.types.bpy_prop_collection[DnaBackupEntry]
        dna_backup_list_active_index: int
        rbf_solver_list: bpy.types.bpy_prop_collection[RBFSolverData]
        rbf_solver_list_active_index: int

    # =========================================================================
    # Addon Preferences Types
    # =========================================================================
    class _MetaHumanAddonPreferences(MetahumanDnaAddonProperties, bpy.types.AddonPreferences):
        """Typed addon preferences for MetaHuman DNA."""

        bl_idname: str
        metrics_collection: bool
        show_pose_editor_viewport_overlay: bool
        enable_auto_dna_backups: bool
        max_dna_backups: int
        next_metrics_consent_timestamp: float
        extra_dna_folder_list: bpy.types.bpy_prop_collection[ExtraDnaFolder]
        extra_dna_folder_list_active_index: int

    class _MetaHumanAddon:
        """Typed addon module reference."""

        preferences: _MetaHumanAddonPreferences

    class _MetaHumanAddons(bpy.types.bpy_prop_collection[bpy.types.Addon]):
        """Typed addons collection with MetaHuman DNA addon."""

        def get(self, name: str, default: _MetaHumanAddon | None = None) -> _MetaHumanAddon | None: ...
        def __getitem__(self, name: str) -> _MetaHumanAddon: ...
        def __contains__(self, name: str) -> bool: ...

    # =========================================================================
    # Patch bpy.types.Preferences
    # =========================================================================
    class Preferences(bpy.types.Preferences):
        """Extended Preferences type with typed addons access."""

        addons: _MetaHumanAddons

    # =========================================================================
    # Patch bpy.types.Scene
    # =========================================================================
    class Scene(bpy.types.Scene):
        """Extended Scene type with MetaHuman DNA properties."""

        meta_human_dna: MetahumanSceneProperties

    # =========================================================================
    # Patch bpy.types.WindowManager
    # =========================================================================
    class WindowManager(bpy.types.WindowManager):
        """Extended WindowManager type with MetaHuman DNA properties."""

        meta_human_dna: MetahumanWindowMangerProperties

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
        "Context",
        "DuplicateRigInstance",
        "MetaHumanComponentBody",
        "MetaHumanComponentHead",
        "MetahumanDnaAddonProperties",
        "MetahumanSceneProperties",
        "MetahumanWindowMangerProperties",
        "Preferences",
        "RBFPoseData",
        "RBFSolverData",
        "RigInstance",
        "Scene",
        "WindowManager",
        "riglogic",
    ]
